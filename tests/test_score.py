import pytest

from pipeline.score import (
    composite_score,
    fund_composite_score,
    fund_sustainability_multiplier,
    growth_score,
    rank,
    recurrence_score,
    sustainability_multiplier,
    yield_score,
)


def test_recurrence_score_fracao_da_janela():
    assert recurrence_score(10, 10) == 1.0
    assert recurrence_score(8, 10) == pytest.approx(0.8)
    assert recurrence_score(0, 10) == 0.0


def test_yield_score_premia_faixa_saudavel_e_pune_trap():
    # corrente = mediana -> faixa boa
    assert yield_score(0.06, 0.06) == 1.0
    # corrente bem acima da mediana -> trap, decai
    assert yield_score(0.18, 0.06) < 0.3
    # corrente abaixo da mediana -> parcial
    assert 0.4 <= yield_score(0.03, 0.06) < 1.0
    # sem baseline -> neutro
    assert yield_score(0.06, None) == 0.5


def test_growth_score_monotonica():
    assert growth_score(-0.2) == 0.0
    assert growth_score(0.0) == pytest.approx(0.5)
    assert growth_score(0.15) == pytest.approx(1.0)
    assert growth_score(None) == 0.5


def test_sustainability_multiplier_desconta_falhas():
    # tudo saudável
    assert sustainability_multiplier(0.5, 10, roe_recent=0.15) == 1.0
    # payout fora da faixa + ROE negativo -> dois descontos
    assert sustainability_multiplier(0.95, 10, roe_recent=-0.01) == pytest.approx(0.7)
    # três falhas (payout, recorrência, ROE) -> 1.0 - 0.45 = 0.55 (ainda acima do piso)
    assert sustainability_multiplier(1.5, 2, roe_recent=-0.1) == pytest.approx(0.55)
    # alavancagem alta penaliza; N/A (banco) e caixa líquido não
    sm = sustainability_multiplier
    assert sm(0.5, 10, roe_recent=0.15, net_debt_ebitda=4.0) == pytest.approx(0.85)
    assert sm(0.5, 10, roe_recent=0.15, net_debt_ebitda=None) == 1.0
    assert sm(0.5, 10, roe_recent=0.15, net_debt_ebitda=-0.5) == 1.0


def test_composite_aplica_pesos_e_corte_de_trap():
    base = dict(
        years_paid=10, window=10, current_dy=0.06, hist_median=0.06, cagr=0.15,
        payout_recent=0.5, roe_recent=0.2,
    )
    bom = composite_score("AAAA", yield_trap=False, **base)
    com_trap = composite_score("AAAA", yield_trap=True, **base)
    # componentes todos ~1 e sustentabilidade 1 -> score perto de 100
    assert bom.score > 95
    # trap corta o score (penalidade de 0.7)
    assert com_trap.score == pytest.approx(bom.score * 0.7, rel=1e-3)


def test_fund_sustainability_desconta_falhas_de_fundo():
    fsm = fund_sustainability_multiplier
    # tudo saudável (baixa alavancagem, VP preservado, taxa baixa, paga 12/12)
    assert fsm(leverage=0.1, vp_cota_var=0.02, taxa_admin_aa=0.01, months_paid_12m=12) == 1.0
    # alavancado + cota derretendo -> dois descontos
    assert fsm(leverage=0.8, vp_cota_var=-0.10, taxa_admin_aa=0.01,
               months_paid_12m=12) == pytest.approx(0.76)
    # métricas ausentes não penalizam (histórico curto)
    assert fsm() == 1.0
    # recorrência baixa penaliza
    assert fsm(months_paid_12m=6) == pytest.approx(0.88)


def test_fund_composite_recorrencia_escala_pela_janela_disponivel():
    # Fundo novo (9 meses) que pagou TODOS os 9: recorrência deve ser 1,0, não 9/12.
    novo = fund_composite_score("NOVO11", months_paid_12m=9, dy_ttm=0.10, dy_baseline=0.10,
                                crescimento=0.0, months_window=9)
    assert novo.recurrence == pytest.approx(1.0)
    # E a sustentabilidade não pune por "não ter existido" 12 meses (pagou 9/9).
    assert novo.sustainability == pytest.approx(1.0)
    # Já com janela cheia, pagar só 9/12 penaliza a recorrência.
    velho = fund_composite_score("VELHO11", months_paid_12m=9, dy_ttm=0.10, dy_baseline=0.10,
                                 crescimento=0.0, months_window=12)
    assert velho.recurrence == pytest.approx(0.75)


def test_fund_composite_usa_baseline_e_corte_de_trap():
    base = dict(months_paid_12m=12, dy_ttm=0.10, dy_baseline=0.10, crescimento=0.15,
                leverage=0.1, vp_cota_var=0.02, taxa_admin_aa=0.01)
    bom = fund_composite_score("SNAG11", yield_trap=False, **base)
    trap = fund_composite_score("SNAG11", yield_trap=True, **base)
    assert bom.score > 95
    assert trap.score == pytest.approx(bom.score * 0.7, rel=1e-3)
    # crescimento None (FIAgro sem base) -> neutro, não zera o score
    neutro = fund_composite_score("XPCA11", months_paid_12m=12, dy_ttm=0.10,
                                  dy_baseline=0.10, crescimento=None)
    assert 0.5 < neutro.score / 100 < 1.0


def test_rank_ordena_desc_e_numera():
    a = composite_score("AAAA", years_paid=10, window=10, current_dy=0.06, hist_median=0.06,
                         cagr=0.15, payout_recent=0.5, roe_recent=0.2, yield_trap=False)
    b = composite_score("BBBB", years_paid=3, window=10, current_dy=0.2, hist_median=0.05,
                         cagr=-0.2, payout_recent=1.2, roe_recent=-0.1, yield_trap=True)
    out = rank([b, a])
    assert [r["ticker"] for r in out] == ["AAAA", "BBBB"]
    assert out[0]["rank"] == 1 and "yield" in out[0]
