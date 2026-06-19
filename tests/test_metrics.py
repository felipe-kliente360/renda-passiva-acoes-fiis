import math

import pandas as pd

from pipeline import metrics


def _proventos():
    # Proventos por DATA-COM (não pagamento).
    return pd.DataFrame(
        {
            "data_com": [
                "2023-07-15",
                "2023-12-15",
                "2024-03-15",
                "2024-06-15",  # exatamente asof
            ],
            "valor": [1.0, 1.0, 1.5, 1.5],
        }
    )


def test_ttm_dividends_uses_data_com_window():
    # asof 2024-06-15: janela (2023-06-15, 2024-06-15]. Pega os 4? 2023-07-15 entra.
    total = metrics.ttm_dividends(_proventos(), "2024-06-15")
    assert total == 1.0 + 1.0 + 1.5 + 1.5


def test_ttm_excludes_outside_window():
    total = metrics.ttm_dividends(_proventos(), "2024-03-14")
    # janela (2023-03-14, 2024-03-14]: só 2023-07-15 e 2023-12-15
    assert total == 2.0


def test_current_dy():
    assert metrics.current_dy(5.0, 100.0) == 0.05
    assert math.isnan(metrics.current_dy(5.0, 0.0))


def test_annual_dividends_groups_by_year():
    annual = metrics.annual_dividends(_proventos())
    assert annual.loc[2023] == 2.0
    assert annual.loc[2024] == 3.0


def test_historical_dy_mean_and_median():
    annual_div = pd.Series({2021: 8.0, 2022: 10.0, 2023: 12.0})
    annual_price = pd.Series({2021: 100.0, 2022: 100.0, 2023: 100.0})
    hist = metrics.historical_dy(annual_div, annual_price)
    assert hist.by_year.loc[2022] == 0.10
    assert hist.mean == (0.08 + 0.10 + 0.12) / 3
    assert hist.median == 0.10


def test_historical_dy_ignores_year_without_price():
    annual_div = pd.Series({2021: 8.0, 2022: 10.0})
    annual_price = pd.Series({2021: 100.0})  # 2022 sem preço
    hist = metrics.historical_dy(annual_div, annual_price)
    assert list(hist.by_year.index) == [2021]


def test_yield_trap_flag():
    # mediana histórica 0.08; corrente 0.13 > 1.5*0.08=0.12 -> trap
    assert metrics.yield_trap_flag(0.13, 0.08) is True
    assert metrics.yield_trap_flag(0.11, 0.08) is False
    assert metrics.yield_trap_flag(0.13, 0.0) is False
    assert metrics.yield_trap_flag(float("nan"), 0.08) is False


def test_payout_ratio_and_range():
    assert metrics.payout_ratio(50.0, 100.0) == 0.5
    assert math.isnan(metrics.payout_ratio(50.0, 0.0))
    assert metrics.payout_in_range(0.5) is True
    assert metrics.payout_in_range(0.2) is False
    assert metrics.payout_in_range(0.9) is False


def test_recurrence():
    # pagou em 9 dos 10 anos até 2024 (faltou 2016)
    paid_years = {y: 1.0 for y in range(2015, 2025) if y != 2016}
    annual = pd.Series(paid_years)
    out = metrics.recurrence(annual, asof_year=2024)
    assert out["years_paid"] == 9
    assert out["passes"] is True

    sparse = pd.Series({2023: 1.0, 2024: 1.0})
    out2 = metrics.recurrence(sparse, asof_year=2024)
    assert out2["years_paid"] == 2
    assert out2["passes"] is False


def test_dividend_growth_cagr():
    # de 10 (2020) a 14,641 (2024): 4 anos, CAGR esperado 10%
    annual = pd.Series({2020: 10.0, 2021: 11.0, 2022: 12.1, 2023: 13.31, 2024: 14.641})
    g = metrics.dividend_growth(annual)
    assert abs(g - 0.10) < 1e-6

    assert math.isnan(metrics.dividend_growth(pd.Series({2024: 1.0})))
