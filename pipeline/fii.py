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
        vp = to_numeric_ptbr(df[resolved["valor_patrimonial_cota"]])

    # Deriva VP da cota onde não veio direto: PL / cotas emitidas.
    if {"patrimonio_liquido", "cotas_emitidas"} <= resolved.keys():
        pl = to_numeric_ptbr(df[resolved["patrimonio_liquido"]])
        cotas = to_numeric_ptbr(df[resolved["cotas_emitidas"]])
        derived = pl.where(cotas.gt(0)) / cotas.where(cotas.gt(0))
        vp = vp.where(vp.notna(), derived)

    out["valor_patrimonial_cota"] = vp
    return out


def latest_vp_por_fundo(parsed: pd.DataFrame) -> pd.DataFrame:
    """Último VP da cota disponível por fundo (maior competência com VP não-nulo)."""
    valid = parsed.dropna(subset=["valor_patrimonial_cota", "competencia"])
    if valid.empty:
        return valid.copy()
    idx = valid.sort_values("competencia").groupby("cnpj_fundo").tail(1).index
    return valid.loc[idx].reset_index(drop=True)
