import numpy as np
import pandas as pd

from pipeline import prices


def _dates(n: int, start: str = "2023-01-02") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="D")


# --------------------------------------------------------------------------- #
# Ajuste por split / grupamento
# --------------------------------------------------------------------------- #


def test_split_adjust_desdobramento_2x():
    idx = _dates(5)
    # raw: preço cai pela metade no desdobramento (ratio 2) em idx[2]
    raw = pd.Series([100.0, 100.0, 50.0, 50.0, 50.0], index=idx)
    adj = prices.split_adjust(raw, [(idx[2], 2.0)])
    # série fica contínua em 50: pré-split dividido por 2
    assert adj.tolist() == [50.0, 50.0, 50.0, 50.0, 50.0]


def test_split_adjust_grupamento():
    idx = _dates(4)
    # grupamento 1:10 (ratio 0.1): preço sobe 10x em idx[2]
    raw = pd.Series([10.0, 10.0, 100.0, 100.0], index=idx)
    adj = prices.split_adjust(raw, [(idx[2], 0.1)])
    assert adj.tolist() == [100.0, 100.0, 100.0, 100.0]


def test_split_adjust_no_events_is_identity():
    idx = _dates(3)
    raw = pd.Series([10.0, 11.0, 12.0], index=idx)
    pd.testing.assert_series_equal(prices.split_adjust(raw, []), raw)


# --------------------------------------------------------------------------- #
# Reconstrução da série negociada a partir do adjusted close (caminho B)
# --------------------------------------------------------------------------- #


def _make_adjusted(traded: pd.Series, dividends: list[tuple[pd.Timestamp, float]]) -> pd.Series:
    """Gera o adjusted close (Yahoo) a partir da série negociada conhecida.

    Definição forward e INDEPENDENTE da reconstrução: f_e = 1 - D_e/C[e-1];
    adj[t] = C[t] · Π_{data-com > t} f_e. Serve de oráculo para o round-trip.
    """
    c = traded.sort_index()
    factors: dict[pd.Timestamp, float] = {}
    for ex, d in sorted(dividends):
        prior = c.index[c.index < ex]
        c_prev = float(c.loc[prior[-1]])
        factors[ex] = 1.0 - d / c_prev
    cf = pd.Series(1.0, index=c.index)
    for ex, f_e in factors.items():
        cf.loc[c.index < ex] *= f_e
    return c * cf


def test_reconstruct_roundtrip_recovers_traded_series():
    idx = _dates(10)
    traded = pd.Series(np.linspace(100.0, 109.0, 10), index=idx)  # split-adj, div-unadj
    dividends = [(idx[3], 2.0), (idx[7], 3.0)]

    adj = _make_adjusted(traded, dividends)
    # sanity: adjusted close fica ABAIXO do negociado no passado (back-adjust por div)
    assert (adj.iloc[:3] < traded.iloc[:3]).all()

    recovered = prices.reconstruct_traded_from_adjusted(adj, dividends)
    pd.testing.assert_series_equal(recovered, traded, check_names=False, rtol=1e-12)


def test_reconstruct_with_split_and_dividend_combined():
    # A série negociada já é contínua (ajustada por split); reconstrução deve recuperá-la
    # mesmo com dividendos, cobrindo o caso split + provento.
    idx = _dates(8)
    traded = pd.Series([50.0, 50.0, 51.0, 52.0, 52.0, 53.0, 54.0, 55.0], index=idx)
    dividends = [(idx[2], 1.0), (idx[5], 1.5)]
    adj = _make_adjusted(traded, dividends)
    recovered = prices.reconstruct_traded_from_adjusted(adj, dividends)
    pd.testing.assert_series_equal(recovered, traded, check_names=False, rtol=1e-12)


def test_reconstruct_no_dividends_is_identity():
    idx = _dates(4)
    adj = pd.Series([10.0, 11.0, 12.0, 13.0], index=idx)
    pd.testing.assert_series_equal(
        prices.reconstruct_traded_from_adjusted(adj, []), adj
    )


# --------------------------------------------------------------------------- #
# Derivados
# --------------------------------------------------------------------------- #


def test_annual_avg_price():
    idx = pd.to_datetime(["2022-01-01", "2022-07-01", "2023-01-01", "2023-12-31"])
    close = pd.Series([10.0, 20.0, 30.0, 40.0], index=idx)
    avg = prices.annual_avg_price(close)
    assert avg.loc[2022] == 15.0
    assert avg.loc[2023] == 35.0


def test_price_to_book():
    assert prices.price_to_book(110.0, 100.0) == 1.1
    assert np.isnan(prices.price_to_book(110.0, 0.0))
    assert np.isnan(prices.price_to_book(110.0, float("nan")))


def test_build_price_record():
    idx = _dates(3)
    close = pd.Series([98.0, 99.0, 100.0], index=idx)
    rec = prices.build_price_record("HGLG11", close, vp_cota=80.0, source="test")
    assert rec.current_price == 100.0
    assert rec.pvp == 1.25
    assert rec.as_of == idx[-1].date().isoformat()
    assert rec.annual_avg_price == {2023: 99.0}


def test_build_price_record_without_vp_has_no_pvp():
    idx = _dates(2)
    close = pd.Series([10.0, 11.0], index=idx)
    rec = prices.build_price_record("PETR4", close, source="test")
    assert rec.pvp is None


def test_market_symbol():
    assert prices.market_symbol("PETR4") == "PETR4.SA"
    assert prices.market_symbol("PETR4.SA") == "PETR4.SA"
