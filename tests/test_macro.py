import pytest

from pipeline.macro import accumulate_daily


def test_accumulate_daily_compoe():
    # 252 pregões a ~0,0525%/dia ≈ 13,8% no ano (ordem de grandeza do CDI atual).
    r = accumulate_daily([0.052531] * 252)
    assert 0.13 < r < 0.145


def test_accumulate_daily_vazio_e_zero():
    assert accumulate_daily([]) == 0.0
    assert accumulate_daily([0.0, 0.0]) == pytest.approx(0.0)


def test_accumulate_daily_um_por_cento():
    # dois dias a 1%/dia: 1,01 * 1,01 - 1 = 2,01%.
    assert accumulate_daily([1.0, 1.0]) == pytest.approx(0.0201)
