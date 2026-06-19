"""Funções puras de Dividend Yield e sustentabilidade — metodologia TRAVADA.

Regras (não relitigar sem sinalização do Felipe):
- Proventos atribuídos pela DATA-COM (não data de pagamento).
- Denominador = preço negociado ajustado SÓ por split, NUNCA por dividendo.
- DY corrente = proventos dos últimos 12 meses ÷ preço atual.
- DY histórico = soma anual ÷ preço médio do ano; reportar média E mediana.
- Flag de yield trap: DY corrente > 1,5× a mediana histórica.

Tudo aqui é puro e offline. As entradas de preço já devem vir ajustadas só por split
(ver pipeline/prices.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

YIELD_TRAP_MULTIPLE = 1.5
PAYOUT_MIN = 0.30
PAYOUT_MAX = 0.80
RECURRENCE_WINDOW = 10
RECURRENCE_MIN_YEARS = 8


def _as_proventos(proventos: pd.DataFrame) -> pd.DataFrame:
    """Valida/normaliza um DataFrame de proventos (colunas: data_com, valor)."""
    if not {"data_com", "valor"} <= set(proventos.columns):
        raise ValueError("proventos precisa das colunas 'data_com' e 'valor'")
    out = proventos[["data_com", "valor"]].copy()
    out["data_com"] = pd.to_datetime(out["data_com"], errors="coerce")
    out["valor"] = pd.to_numeric(out["valor"], errors="coerce")
    return out.dropna(subset=["data_com", "valor"])


def ttm_dividends(proventos: pd.DataFrame, asof: pd.Timestamp | str) -> float:
    """Soma dos proventos com DATA-COM nos 12 meses até `asof` (inclusive)."""
    asof = pd.Timestamp(asof)
    p = _as_proventos(proventos)
    window_start = asof - pd.DateOffset(years=1)
    mask = (p["data_com"] > window_start) & (p["data_com"] <= asof)
    return float(p.loc[mask, "valor"].sum())


def current_dy(ttm_div: float, current_price: float) -> float:
    """DY corrente = proventos TTM ÷ preço atual. NaN se preço inválido."""
    if current_price is None or current_price <= 0:
        return float("nan")
    return ttm_div / current_price


def annual_dividends(proventos: pd.DataFrame) -> pd.Series:
    """Soma de proventos por ano-calendário da DATA-COM. Índice = ano (int)."""
    p = _as_proventos(proventos)
    if p.empty:
        return pd.Series(dtype="float64")
    return p.groupby(p["data_com"].dt.year)["valor"].sum().rename("dividendos")


@dataclass(frozen=True)
class HistoricalDY:
    """DY histórico por ano + estatísticas. Divergência média×mediana ⇒ extraordinário."""

    by_year: pd.Series  # índice = ano, valor = DY anual
    mean: float
    median: float


def historical_dy(annual_div: pd.Series, annual_avg_price: pd.Series) -> HistoricalDY:
    """DY histórico = soma anual de proventos ÷ preço médio do ano.

    Só considera anos presentes em ambas as séries com preço médio > 0. Reporta média
    e mediana dos DYs anuais (divergência grande sinaliza provento extraordinário).
    """
    years = annual_div.index.intersection(annual_avg_price.index)
    by_year_vals: dict[int, float] = {}
    for y in sorted(years):
        price = annual_avg_price.loc[y]
        if pd.notna(price) and price > 0:
            by_year_vals[int(y)] = float(annual_div.loc[y]) / float(price)
    by_year = pd.Series(by_year_vals, dtype="float64").rename("dy")
    if by_year.empty:
        return HistoricalDY(by_year=by_year, mean=float("nan"), median=float("nan"))
    return HistoricalDY(
        by_year=by_year, mean=float(by_year.mean()), median=float(by_year.median())
    )


def yield_trap_flag(current_dy_value: float, historical_median: float) -> bool:
    """True se DY corrente > 1,5× a mediana histórica (possível armadilha de yield)."""
    if (
        current_dy_value is None
        or historical_median is None
        or pd.isna(current_dy_value)
        or pd.isna(historical_median)
        or historical_median <= 0
    ):
        return False
    return current_dy_value > YIELD_TRAP_MULTIPLE * historical_median


def payout_ratio(dividends: float, earnings: float) -> float:
    """Payout = proventos ÷ lucro. NaN se lucro <= 0 (payout indefinido/negativo)."""
    if earnings is None or earnings <= 0:
        return float("nan")
    return dividends / earnings


def payout_in_range(payout: float, low: float = PAYOUT_MIN, high: float = PAYOUT_MAX) -> bool:
    """True se o payout está na faixa saudável travada (30–80% por padrão)."""
    if payout is None or pd.isna(payout):
        return False
    return low <= payout <= high


def recurrence(
    annual_div: pd.Series,
    asof_year: int,
    window: int = RECURRENCE_WINDOW,
    min_years: int = RECURRENCE_MIN_YEARS,
) -> dict[str, object]:
    """Recorrência: pagou em ≥ `min_years` dos últimos `window` anos até `asof_year`.

    Conta um ano como "pago" se a soma de proventos daquele ano > 0. Retorna o número
    de anos pagos, a janela considerada e o booleano de aprovação.
    """
    years = range(asof_year - window + 1, asof_year + 1)
    paid = sum(1 for y in years if float(annual_div.get(y, 0.0)) > 0)
    return {
        "years_paid": paid,
        "window": window,
        "min_years": min_years,
        "passes": paid >= min_years,
    }


def dividend_growth(annual_div: pd.Series) -> float:
    """CAGR dos proventos anuais entre o primeiro e o último ano com pagamento > 0.

    NaN se houver menos de 2 anos pagos ou se o primeiro pagamento for <= 0.
    """
    paid = annual_div[annual_div > 0].sort_index()
    if len(paid) < 2:
        return float("nan")
    first, last = float(paid.iloc[0]), float(paid.iloc[-1])
    n_years = int(paid.index[-1]) - int(paid.index[0])
    if first <= 0 or n_years <= 0:
        return float("nan")
    return (last / first) ** (1 / n_years) - 1
