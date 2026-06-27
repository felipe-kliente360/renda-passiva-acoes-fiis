"""Parser do informe mensal de FII (INF_MENSAL da CVM).

Objetivo na Fase 0/1: extrair o **valor patrimonial da cota** por fundo/competência,
insumo do P/VP. Dirigido por `config/columns.yml` — nada de nome de coluna fixo aqui.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .columns import DatasetSpec, load_columns_config, resolve_columns
from .normalize import to_numeric_ptbr

DATASET = "fii_inf_mensal"


def parse_fii_inf_mensal(
    df: pd.DataFrame, spec: DatasetSpec | None = None
) -> pd.DataFrame:
    """Normaliza o informe mensal de FII para colunas lógicas estáveis.

    Saída: cnpj_fundo, competencia (datetime), valor_patrimonial_cota (float).
    O VP da cota vem direto da coluna correspondente quando existe; senão é derivado
    de patrimonio_liquido / cotas_emitidas. Linhas sem VP derivável ficam com NaN.
    """
    spec = spec or load_columns_config()[DATASET]
    resolved, missing = resolve_columns(spec, list(df.columns))
    if missing:
        raise ValueError(
            f"Colunas obrigatórias ausentes no informe FII: {missing}. "
            f"Colunas reais: {list(df.columns)}. "
            f"Atualize config/columns.yml (valide com scripts/inspect_zip.py)."
        )

    out = pd.DataFrame()
    out["cnpj_fundo"] = df[resolved["cnpj_fundo"]].astype("string").str.strip()
    out["competencia"] = pd.to_datetime(
        df[resolved["competencia"]], errors="coerce", format="mixed"
    )

    vp = pd.Series(np.nan, index=df.index, dtype="float64")
    if "valor_patrimonial_cota" in resolved:
        vp = to_numeric_ptbr(df[resolved["valor_patrimonial_cota"]], decimal=spec.decimal)

    # Deriva VP da cota onde não veio direto: PL / cotas emitidas.
    if {"patrimonio_liquido", "cotas_emitidas"} <= resolved.keys():
        pl = to_numeric_ptbr(df[resolved["patrimonio_liquido"]], decimal=spec.decimal)
        cotas = to_numeric_ptbr(df[resolved["cotas_emitidas"]], decimal=spec.decimal)
        derived = pl.where(cotas.gt(0)) / cotas.where(cotas.gt(0))
        vp = vp.where(vp.notna(), derived)

    out["valor_patrimonial_cota"] = vp
    return out


def dy_mensal_por_fundo(df: pd.DataFrame, spec: DatasetSpec | None = None) -> pd.DataFrame:
    """Extrai o DY MENSAL oficial por fundo/competência do INF_MENSAL (complemento).

    Saída: cnpj_fundo, competencia (datetime), dy_mes (fração decimal). Linhas sem o DY
    mensal são descartadas. É o insumo do DY de FII (TTM e histórico anual).
    """
    spec = spec or load_columns_config()[DATASET]
    resolved, _ = resolve_columns(spec, list(df.columns))
    if "dividend_yield_mes" not in resolved:
        return pd.DataFrame(
            {"cnpj_fundo": pd.Series(dtype="string"),
             "competencia": pd.Series(dtype="datetime64[ns]"),
             "dy_mes": pd.Series(dtype="float64")}
        )
    out = pd.DataFrame()
    out["cnpj_fundo"] = df[resolved["cnpj_fundo"]].astype("string").str.strip()
    out["competencia"] = pd.to_datetime(
        df[resolved["competencia"]], errors="coerce", format="mixed"
    )
    out["dy_mes"] = to_numeric_ptbr(df[resolved["dividend_yield_mes"]], decimal=spec.decimal)
    return out.dropna(subset=["competencia", "dy_mes"])


def parse_fii_enriched(df: pd.DataFrame, spec: DatasetSpec | None = None) -> pd.DataFrame:
    """Série mensal ENRIQUECIDA do FII para a análise estilo-ações (alimenta aggregate_fund).

    Saída por fundo/competência: cnpj_fundo, competencia, dy_mes (fração, já oficial),
    patrimonio_liquido, valor_patrimonial_cota, total_passivo (= Valor_Ativo − PL),
    taxa_administracao. Reúsa a resolução config-driven; campos ausentes ficam NaN.
    """
    spec = spec or load_columns_config()[DATASET]
    resolved, _ = resolve_columns(spec, list(df.columns))

    out = pd.DataFrame()
    out["cnpj_fundo"] = df[resolved["cnpj_fundo"]].astype("string").str.strip()
    out["competencia"] = pd.to_datetime(
        df[resolved["competencia"]], errors="coerce", format="mixed"
    )

    def _num(field: str) -> pd.Series:
        return (
            to_numeric_ptbr(df[resolved[field]], decimal=spec.decimal)
            if field in resolved
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )

    out["dy_mes"] = _num("dividend_yield_mes")
    out["patrimonio_liquido"] = _num("patrimonio_liquido")
    out["taxa_administracao"] = _num("taxa_administracao")

    vp = _num("valor_patrimonial_cota")
    cotas = _num("cotas_emitidas")
    pl = out["patrimonio_liquido"]
    derived = pl.where(cotas.gt(0)) / cotas.where(cotas.gt(0))
    out["valor_patrimonial_cota"] = vp.where(vp.notna(), derived)

    # Passivo do FII não vem direto no complemento: deriva de Valor_Ativo − PL.
    ativo = _num("valor_ativo")
    out["total_passivo"] = (ativo - pl).where(ativo.notna() & pl.notna())
    return out.dropna(subset=["competencia"]).reset_index(drop=True)


def aggregate_fii_dy(monthly: pd.DataFrame, *, trap_multiple: float = 1.5) -> dict:
    """Agrega o DY mensal de UM fundo em TTM, histórico anual, mediana e flag de trap.

    - dy_ttm = soma dos 12 meses mais recentes (yield 12m corrente).
    - dy_por_ano = soma dos meses de cada ano-calendário (anos completos = 12 meses).
    - mediana/média sobre os anos completos; recorrência = meses com DY>0 nos últimos 12.
    - yield trap: dy_ttm > trap_multiple × mediana dos anos completos.
    """
    m = monthly.dropna(subset=["competencia", "dy_mes"]).sort_values("competencia")
    if m.empty:
        return {"dy_ttm": None, "dy_por_ano": {}, "dy_mediana": None, "dy_media": None,
                "meses_com_pagamento_12m": 0, "yield_trap": False}
    last12 = m.tail(12)
    dy_ttm = float(last12["dy_mes"].sum())
    meses_pg = int((last12["dy_mes"] > 0).sum())
    by_year_all = m.groupby(m["competencia"].dt.year)
    counts = by_year_all["dy_mes"].count()
    sums = by_year_all["dy_mes"].sum()
    full = sums[counts >= 12]  # só anos completos entram na mediana histórica
    dy_por_ano = {int(y): float(v) for y, v in sums.items()}
    mediana = float(full.median()) if not full.empty else None
    media = float(full.mean()) if not full.empty else None
    trap = bool(mediana and mediana > 0 and dy_ttm > trap_multiple * mediana)
    return {"dy_ttm": dy_ttm, "dy_por_ano": dy_por_ano, "dy_mediana": mediana,
            "dy_media": media, "meses_com_pagamento_12m": meses_pg, "yield_trap": trap}


def latest_vp_por_fundo(parsed: pd.DataFrame) -> pd.DataFrame:
    """Último VP da cota disponível por fundo (maior competência com VP não-nulo)."""
    valid = parsed.dropna(subset=["valor_patrimonial_cota", "competencia"])
    if valid.empty:
        return valid.copy()
    idx = valid.sort_values("competencia").groupby("cnpj_fundo").tail(1).index
    return valid.loc[idx].reset_index(drop=True)
