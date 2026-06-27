"""Parser e agregação do informe mensal de FIAgro (INF_MENSAL FIAgro da CVM).

DATASET PRÓPRIO da CVM (não os "agro" do INF_MENSAL de FII). Layout pós-Resolução 175:
identidade por CLASSE. Traz, num CSV único, o DY mensal oficial + saúde patrimonial
(PL, VP da cota, passivo, taxa de administração) que sustentam a análise estilo-ações.

Duas peças aqui:
- `parse_fiagro_inf_mensal`: normaliza o CSV cru para colunas lógicas estáveis (config-driven).
- `aggregate_fund`: agrega a série mensal de UM fundo em DY (TTM/baseline), recorrência,
  projeção (CAGR quando há ≥2 anos cheios; senão tendência 6m×6m) e saúde financeira no
  tempo (alavancagem, preservação do VP, taxa de adm). É GENÉRICA — serve FIAgro e FII.

Cobertura do FIAgro começa em 2025-05 (~1 ano): a agregação é honesta sobre histórico
curto — marca a base do crescimento e não inventa mediana de anos incompletos.
`ticker_from_isin` reconstrói o ticker B3 pelo mnemônico do ISIN; quem valida contra a
lista real de fi-agro (brapi) é o script de ingestão.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .columns import DatasetSpec, load_columns_config, resolve_columns
from .normalize import to_numeric_ptbr

DATASET = "fiagro_inf_mensal"

# GOTCHA validado no dado real (inf_mensal_fiagro_2025-05..2026-05): o campo
# `Dividend_Yield_Mes` do FIAgro NÃO é a fração limpa do FII, apesar do nome parecido.
# Convive com TRÊS convenções no mesmo arquivo, por administrador/mês:
#   - valores ~0,9–1,5 (que VARIAM mês a mês) estão em PERCENTUAL: 1,07 = 1,07%/mês → ÷100.
#   - valores ≤ 0,05 são lidos como FRAÇÃO já decimal (0,01 = 1%/mês) — mas costumam vir
#     "chapados" (placeholder); marcados como BAIXA CONFIANÇA pelo agregador/ingestão.
#   - valores absurdos (> ~5/mês, ex.: 16.810.448) são o R$ distribuído mal-arquivado no
#     campo de DY → descartados (NaN), não viram yield.
# A fronteira 0,05 funciona porque um yield MENSAL realista (~0,3%–2%) não se sobrepõe
# entre as duas escalas: 1,07 só faz sentido como 1,07%, e 0,01 só como 1%.
_DY_FRACTION_MAX = 0.05   # ≤ isto: já é fração decimal (ex.: 0,01 = 1%/mês)
_DY_PLAUSIBLE_MAX = 5.0   # em %: acima de 5%/mês é implausível -> valor mal-arquivado


def clean_fiagro_dy(raw: pd.Series) -> pd.Series:
    """Normaliza `Dividend_Yield_Mes` do FIAgro para FRAÇÃO mensal limpa.

    Aplica a desambiguação de escala validada no dado real: ≤0,05 já é fração; (0,05, 5]
    é percentual (÷100); >5 é R$ mal-arquivado → NaN. Ver constantes acima.
    """
    v = pd.to_numeric(raw, errors="coerce")
    out = v.copy()
    pct = (v > _DY_FRACTION_MAX) & (v <= _DY_PLAUSIBLE_MAX)
    out = out.where(~pct, v / 100.0)            # percentual -> fração
    out = out.where(v <= _DY_PLAUSIBLE_MAX)     # implausível (R$ mal-arquivado) -> NaN
    out = out.where(v >= 0)                     # DY de distribuição não é negativo -> NaN
    return out

# Campos numéricos do informe (todos opcionais; o que faltar vira NaN sem quebrar).
_NUMERIC_FIELDS = (
    "patrimonio_liquido",
    "cotas_emitidas",
    "valor_patrimonial_cota",
    "dividend_yield_mes",
    "numero_cotistas",
    "total_passivo",
    "valor_ativo",
    "taxa_administracao",
    # camada de crédito / composição
    "total_investido",
    "imoveis_rurais",
    "cra",
    "cri",
    "cpr",
    "debentures",
    "vencidos",
    "a_vencer",
    "necessidades_liquidez",
)

# Instrumentos de crédito do agro (para diversificação e classificação de tipo).
_CREDIT_INSTRUMENTS = ("cra", "cri", "cpr", "debentures")


def ticker_from_isin(isin: str | None) -> str | None:
    """Reconstrói o ticker B3 (cota XXXX11) pelo mnemônico do ISIN (posições 3-6).

    ISIN de cota brasileiro = "BR" + mnemônico(4) + sufixo. O ticker negociado é
    mnemônico + "11". Validado contra a lista fi-agro da brapi (ex.: BRSNAGCTF000 → SNAG11,
    BRRURAR01M16 → RURA11). Retorna None se o ISIN for vazio/curto — não inventa.
    """
    if not isinstance(isin, str):  # None / pd.NA / NaN não viram ticker
        return None
    s = isin.strip().upper()
    if not s:
        return None
    if len(s) < 6 or not s.startswith("BR"):
        return None
    mnem = s[2:6]
    if not mnem.isalnum():
        return None
    return f"{mnem}11"


def parse_fiagro_inf_mensal(
    df: pd.DataFrame, spec: DatasetSpec | None = None
) -> pd.DataFrame:
    """Normaliza o informe mensal de FIAgro para colunas lógicas estáveis.

    Saída (uma linha por fundo/competência): cnpj_fundo, competencia, nome, isin, ticker,
    patrimonio_liquido, valor_patrimonial_cota, dividend_yield_mes, numero_cotistas,
    total_passivo, valor_ativo, taxa_administracao. O VP da cota é derivado de PL/cotas
    quando não vier direto. Linhas sem competência válida são descartadas.
    """
    spec = spec or load_columns_config()[DATASET]
    resolved, missing = resolve_columns(spec, list(df.columns))
    if missing:
        raise ValueError(
            f"Colunas obrigatórias ausentes no informe FIAgro: {missing}. "
            f"Colunas reais: {list(df.columns)}. "
            f"Atualize config/columns.yml (valide com scripts/inspect_zip.py)."
        )

    out = pd.DataFrame()
    out["cnpj_fundo"] = df[resolved["cnpj_fundo"]].astype("string").str.strip()
    out["competencia"] = pd.to_datetime(
        df[resolved["competencia"]], errors="coerce", format="mixed"
    )
    out["nome"] = (
        df[resolved["nome"]].astype("string").str.strip()
        if "nome" in resolved
        else pd.Series([pd.NA] * len(df), dtype="string")
    )
    isin = (
        df[resolved["isin"]].astype("string").str.strip()
        if "isin" in resolved
        else pd.Series([pd.NA] * len(df), dtype="string")
    )
    out["isin"] = isin
    out["ticker"] = isin.map(ticker_from_isin).astype("string")

    for fld in _NUMERIC_FIELDS:
        out[fld] = (
            to_numeric_ptbr(df[resolved[fld]], decimal=spec.decimal)
            if fld in resolved
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )

    # DY mensal: limpa a escala (percentual×fração) e descarta R$ mal-arquivado.
    if "dividend_yield_mes" in out:
        out["dividend_yield_mes"] = clean_fiagro_dy(out["dividend_yield_mes"])

    # Deriva VP da cota onde não veio direto: PL / cotas emitidas.
    derived = out["patrimonio_liquido"].where(out["cotas_emitidas"].gt(0)) / out[
        "cotas_emitidas"
    ].where(out["cotas_emitidas"].gt(0))
    out["valor_patrimonial_cota"] = out["valor_patrimonial_cota"].where(
        out["valor_patrimonial_cota"].notna(), derived
    )
    return out.dropna(subset=["competencia"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Agregação de fundos (pura, testável) — DY + projeção + saúde financeira
# --------------------------------------------------------------------------- #


def _annual_sums(monthly: pd.DataFrame) -> tuple[dict[int, float], dict[int, int]]:
    """Soma e contagem de meses do DY por ano-calendário."""
    by_year = monthly.groupby(monthly["competencia"].dt.year)["dy_mes"]
    sums = {int(y): float(v) for y, v in by_year.sum().items()}
    counts = {int(y): int(v) for y, v in by_year.count().items()}
    return sums, counts


def _dy_cagr(annual_sums: dict[int, float], annual_counts: dict[int, int]) -> float | None:
    """CAGR do DY anual entre o primeiro e o último ano COMPLETO (≥12 meses).

    Precisa de ≥2 anos completos. Sem isso (caso do FIAgro, ~1 ano), retorna None — o
    chamador então usa a tendência de curto prazo e marca a base.
    """
    full = sorted(y for y, c in annual_counts.items() if c >= 12 and annual_sums.get(y, 0) > 0)
    if len(full) < 2:
        return None
    y0, y1 = full[0], full[-1]
    v0, v1 = annual_sums[y0], annual_sums[y1]
    n = y1 - y0
    if v0 <= 0 or n <= 0:
        return None
    return (v1 / v0) ** (1 / n) - 1.0


def _dy_trend_6m(series: pd.Series) -> float | None:
    """Tendência de curto prazo: média dos 6 meses recentes vs 6 anteriores − 1.

    Projeção honesta para histórico curto (FIAgro). Precisa de ≥6 meses; usa metades
    iguais quando há entre 6 e 11 meses. Retorna None se a base anterior for ~zero.
    """
    s = series.dropna()
    if len(s) < 6:
        return None
    half = min(6, len(s) // 2)
    recent = float(s.iloc[-half:].mean())
    earlier = float(s.iloc[-2 * half : -half].mean())
    if earlier <= 0:
        return None
    return recent / earlier - 1.0


def _slope_per_year(series: pd.Series) -> float | None:
    """Inclinação linear do PL/VP por ano (insumo de 'PL crescente', 'VP preservado').

    Normaliza pela média para virar variação relativa anual. None se série insuficiente.
    """
    s = series.dropna()
    if len(s) < 3:
        return None
    base = float(s.mean())
    if base <= 0:
        return None
    x = np.arange(len(s), dtype="float64")
    slope_month = float(np.polyfit(x, s.to_numpy(dtype="float64"), 1)[0])
    return slope_month * 12.0 / base


def aggregate_fund(monthly: pd.DataFrame, *, trap_multiple: float = 1.5) -> dict:
    """Agrega a série mensal de UM fundo (FIAgro ou FII) em métricas estilo-ações.

    Espera colunas: competencia, dy_mes, e (opcionais) patrimonio_liquido,
    valor_patrimonial_cota, total_passivo, taxa_administracao, numero_cotistas.

    Devolve DY (TTM, por ano, baseline, mediana de anos completos), recorrência,
    projeção (CAGR de anos completos OU tendência 6m, com a base usada), saúde financeira
    no tempo (alavancagem, crescimento do PL, preservação do VP, taxa de adm, cotistas) e
    o flag de yield trap. Honesto com histórico curto: campos sem base ficam None.
    """
    monthly = monthly.copy()
    # Aceita tanto `dy_mes` (convenção do FII) quanto `dividend_yield_mes` (parser FIAgro).
    if "dy_mes" not in monthly and "dividend_yield_mes" in monthly:
        monthly = monthly.rename(columns={"dividend_yield_mes": "dy_mes"})
    m = monthly.dropna(subset=["competencia"]).sort_values("competencia")
    if "dy_mes" in m:
        # DY de distribuição não é negativo: um mês negativo (ex.: XPML11 2026-01 = −5,9%)
        # é correção/clawback mal-reportado, não rendimento. Trata como anomalia (descarta),
        # senão um único mês afunda o TTM. Vale p/ FII e FIAgro.
        m = m[m["dy_mes"].isna() | (m["dy_mes"] >= 0)]
        m = m.dropna(subset=["dy_mes"])
    empty = {
        "dy_ttm": None, "dy_ttm_estimado": False, "dy_por_ano": {}, "dy_baseline": None,
        "dy_mediana": None,
        "dy_media": None, "meses_disponiveis": 0, "meses_com_pagamento_12m": 0,
        "meses_pagando": 0, "dy_cv": None, "dy_constante": False,
        "crescimento": None, "crescimento_base": None,
        "alavancagem": None, "pl_crescimento_aa": None, "vp_cota_var": None,
        "taxa_admin_aa": None, "num_cotistas": None,
        "pl_atual": None, "vp_cota_atual": None, "yield_trap": False,
    }
    if m.empty:
        return empty

    last12 = m.tail(12)
    n = len(last12)
    # TTM = soma dos 12 meses quando o ano está completo (igual ao FII); com <12 meses
    # limpos (FIAgro, ~1 ano), anualiza pela média mensal — honesto e robusto a buracos.
    if n >= 12:
        dy_ttm = float(last12["dy_mes"].sum())
        dy_estimado = False
    else:
        dy_ttm = float(last12["dy_mes"].mean()) * 12 if n else 0.0
        dy_estimado = True
    meses_disp = int(len(m))
    meses_pg = int((last12["dy_mes"] > 0).sum())

    # Confiança do DY: distribuição real VARIA mês a mês; DY positivo perfeitamente
    # constante (cv≈0) sobre muitos meses cheira a placeholder do administrador (ex.: 0,01
    # chapado). Não inventamos — sinalizamos para tirar esses do topo da shortlist.
    paying = m[m["dy_mes"] > 0]["dy_mes"]
    meses_pagando = int(len(paying))
    dy_cv = (
        float(paying.std(ddof=0) / paying.mean())
        if meses_pagando > 1 and paying.mean() > 0
        else None
    )
    dy_constante = bool(meses_pagando >= 6 and dy_cv is not None and dy_cv < 0.02)

    sums, counts = _annual_sums(m)
    full_years = {y: v for y, v in sums.items() if counts.get(y, 0) >= 12}
    mediana = float(np.median(list(full_years.values()))) if full_years else None
    media = float(np.mean(list(full_years.values()))) if full_years else None

    # baseline para o "yield vs baseline": mediana dos anos completos quando existir;
    # senão, a média mensal anualizada (×12) — honesto para histórico curto.
    monthly_mean = float(m["dy_mes"].mean())
    baseline = mediana if mediana else (monthly_mean * 12 if monthly_mean > 0 else None)

    # Projeção: CAGR de anos completos; fallback tendência 6m×6m.
    cagr = _dy_cagr(sums, counts)
    if cagr is not None:
        crescimento, base = cagr, "cagr_anual"
    else:
        trend = _dy_trend_6m(m["dy_mes"])
        crescimento, base = trend, ("tendencia_6m" if trend is not None else None)

    trap = bool(baseline and baseline > 0 and dy_ttm > trap_multiple * baseline)

    # Saúde financeira no tempo (usa o que existir na série).
    def _last(col: str) -> float | None:
        if col not in m:
            return None
        s = m[col].dropna()
        return float(s.iloc[-1]) if not s.empty else None

    pl_atual = _last("patrimonio_liquido")
    passivo_atual = _last("total_passivo")
    vp_atual = _last("valor_patrimonial_cota")
    alav = (
        passivo_atual / pl_atual
        if (pl_atual and pl_atual > 0 and passivo_atual is not None)
        else None
    )
    pl_cresc = _slope_per_year(m["patrimonio_liquido"]) if "patrimonio_liquido" in m else None
    vp_var = None
    if "valor_patrimonial_cota" in m:
        vp = m["valor_patrimonial_cota"].dropna()
        if len(vp) >= 2 and float(vp.iloc[0]) > 0:
            vp_var = float(vp.iloc[-1]) / float(vp.iloc[0]) - 1.0
    taxa_aa = None
    if "taxa_administracao" in m:
        t = m["taxa_administracao"].dropna()
        if not t.empty:
            taxa_aa = float(t.tail(12).sum())  # soma das taxas mensais ≈ taxa anual

    return {
        "dy_ttm": dy_ttm,
        "dy_ttm_estimado": dy_estimado,
        "dy_por_ano": {int(y): float(v) for y, v in sums.items()},
        "dy_baseline": baseline,
        "dy_mediana": mediana,
        "dy_media": media,
        "meses_disponiveis": meses_disp,
        "meses_com_pagamento_12m": meses_pg,
        "meses_pagando": meses_pagando,
        "dy_cv": dy_cv,
        "dy_constante": dy_constante,
        "crescimento": crescimento,
        "crescimento_base": base,
        "alavancagem": alav,
        "pl_crescimento_aa": pl_cresc,
        "vp_cota_var": vp_var,
        "taxa_admin_aa": taxa_aa,
        "num_cotistas": int(_last("numero_cotistas")) if _last("numero_cotistas") else None,
        "pl_atual": pl_atual,
        "vp_cota_atual": vp_atual,
        "yield_trap": trap,
    }


def credit_profile(monthly: pd.DataFrame) -> dict:
    """Perfil de crédito/composição do FIAgro na competência mais recente.

    - tipo: 'terras' se imóveis rurais dominam (>50% do investido), senão 'credito'.
    - inadimplencia: Vencidos / (A_Vencer + Vencidos) — núcleo da qualidade de crédito.
    - diversificacao_hhi: HHI dos instrumentos de crédito (1 = um só papel; →0 diversificado).
    - liquidez_pl: colchão de liquidez / PL.
    - composicao: participação de cada bucket no investido.
    Campos sem dado ficam None — não inventa.
    """
    empty = {"tipo": None, "inadimplencia": None, "diversificacao_hhi": None,
             "liquidez_pl": None, "composicao": {}}
    m = monthly.dropna(subset=["competencia"]).sort_values("competencia")
    if m.empty:
        return empty
    last = m.iloc[-1]

    def g(c: str) -> float:
        v = last.get(c)
        return float(v) if v is not None and not pd.isna(v) else 0.0

    instrs = {k: g(k) for k in _CREDIT_INSTRUMENTS}
    imoveis = g("imoveis_rurais")
    credito_total = sum(instrs.values())
    base = g("total_investido") or (credito_total + imoveis)
    if base <= 0:
        return empty

    tipo = "terras" if imoveis / base > 0.5 else "credito"
    venc, aver = g("vencidos"), g("a_vencer")
    inad = venc / (venc + aver) if (venc + aver) > 0 else None
    hhi = (
        sum((v / credito_total) ** 2 for v in instrs.values())
        if credito_total > 0 else None
    )
    pl = g("patrimonio_liquido")
    liq = g("necessidades_liquidez") / pl if pl > 0 else None
    composicao = {
        k: round(v / base, 3)
        for k, v in {**instrs, "imoveis_rurais": imoveis}.items()
        if v > 0
    }
    return {
        "tipo": tipo,
        "inadimplencia": None if inad is None else round(inad, 4),
        "diversificacao_hhi": None if hhi is None else round(hhi, 3),
        "liquidez_pl": None if liq is None else round(liq, 3),
        "composicao": composicao,
    }
