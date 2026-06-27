import pandas as pd
import pytest
from conftest import DATA_DIR

from pipeline.fiagro import (
    aggregate_fund,
    clean_fiagro_dy,
    credit_profile,
    parse_fiagro_inf_mensal,
    ticker_from_isin,
)
from pipeline.normalize import read_cvm_csv

SAMPLE = DATA_DIR / "fiagro_inf_mensal_sample.csv"


# --------------------------------------------------------------------------- #
# ticker_from_isin
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "isin,expected",
    [
        ("BRSNAGCTF000", "SNAG11"),
        ("BRRURAR01M16", "RURA11"),   # formato de ISIN diferente, mnemônico ainda em [2:6]
        ("BRXPCACTF004", "XPCA11"),
        ("", None),
        (None, None),
        ("US12345", None),           # não-BR
        ("BR", None),                # curto demais
    ],
)
def test_ticker_from_isin(isin, expected):
    assert ticker_from_isin(isin) == expected


# --------------------------------------------------------------------------- #
# clean_fiagro_dy — desambiguação de escala (gotcha do dado real)
# --------------------------------------------------------------------------- #


def test_clean_fiagro_dy_escala_e_lixo():
    raw = pd.Series([1.07, 1.46, 0.01, 0.13, 16810448.45, 0.00])
    out = clean_fiagro_dy(raw)
    assert out.iloc[0] == pytest.approx(0.0107)   # 1,07% -> fração (percentual ÷100)
    assert out.iloc[1] == pytest.approx(0.0146)   # 1,46%
    assert out.iloc[2] == pytest.approx(0.01)     # ≤0,05 já é fração (1%/mês)
    assert out.iloc[3] == pytest.approx(0.0013)   # 0,13% -> fração
    assert pd.isna(out.iloc[4])                   # R$ mal-arquivado -> NaN
    assert out.iloc[5] == pytest.approx(0.0)      # não pagou


# --------------------------------------------------------------------------- #
# parse_fiagro_inf_mensal
# --------------------------------------------------------------------------- #


def test_parse_resolve_ticker_e_vp_direto():
    parsed = parse_fiagro_inf_mensal(read_cvm_csv(SAMPLE))
    snag = parsed[parsed["cnpj_fundo"] == "11.111.111/0001-11"]
    assert set(snag["ticker"]) == {"SNAG11"}
    assert sorted(snag["valor_patrimonial_cota"].tolist()) == [100.0, 101.0]
    assert sorted(snag["dividend_yield_mes"].tolist()) == [0.011, 0.0115]


def test_parse_deriva_vp_de_pl_e_cotas():
    parsed = parse_fiagro_inf_mensal(read_cvm_csv(SAMPLE))
    rzag = parsed[parsed["cnpj_fundo"] == "33.333.333/0001-33"]
    # 50.000.000 / 100.000 = 500,00
    assert rzag["valor_patrimonial_cota"].iloc[0] == pytest.approx(500.0)
    assert rzag["ticker"].iloc[0] == "RZAG11"


def test_parse_sem_isin_fica_sem_ticker():
    parsed = parse_fiagro_inf_mensal(read_cvm_csv(SAMPLE))
    fechado = parsed[parsed["cnpj_fundo"] == "22.222.222/0001-22"]
    assert fechado["ticker"].isna().all()


def test_parse_extrai_passivo_e_taxa():
    parsed = parse_fiagro_inf_mensal(read_cvm_csv(SAMPLE))
    snag = parsed[parsed["cnpj_fundo"] == "11.111.111/0001-11"].iloc[0]
    assert snag["total_passivo"] == pytest.approx(5_000_000.0)
    assert snag["taxa_administracao"] == pytest.approx(0.0008)


def test_parse_missing_required_raises():
    df = pd.DataFrame({"foo": ["x"], "Nome_Classe": ["y"]})
    with pytest.raises(ValueError, match="obrigatórias"):
        parse_fiagro_inf_mensal(df)


# --------------------------------------------------------------------------- #
# aggregate_fund (genérica — FIAgro e FII)
# --------------------------------------------------------------------------- #


def _monthly(meses, **extra):
    df = pd.DataFrame({
        "competencia": pd.to_datetime([d for d, _ in meses]),
        "dy_mes": [v for _, v in meses],
    })
    for k, v in extra.items():
        df[k] = v
    return df


def test_aggregate_fund_ttm_e_baseline_historico_curto():
    # 8 meses a ~1%/mês (caso FIAgro: < 1 ano). Sem ano completo -> mediana None,
    # baseline = média mensal anualizada.
    meses = [(f"2025-{m:02d}-01", 0.01) for m in range(5, 13)]
    agg = aggregate_fund(_monthly(meses))
    assert agg["meses_disponiveis"] == 8
    # < 12 meses -> TTM anualizado pela média (0,01 × 12 = 12%), marcado como estimado.
    assert agg["dy_ttm"] == pytest.approx(0.12)
    assert agg["dy_ttm_estimado"] is True
    assert agg["dy_mediana"] is None
    assert agg["dy_baseline"] == pytest.approx(0.12)   # 0.01 * 12
    assert agg["yield_trap"] is False


def test_aggregate_fund_cagr_quando_dois_anos_completos():
    # 2024 a 1%/mês (12%), 2025 a 1,2%/mês (14,4%): CAGR = 14,4/12 - 1 = 20%.
    meses = [(f"2024-{m:02d}-01", 0.01) for m in range(1, 13)]
    meses += [(f"2025-{m:02d}-01", 0.012) for m in range(1, 13)]
    agg = aggregate_fund(_monthly(meses))
    assert agg["crescimento_base"] == "cagr_anual"
    assert agg["crescimento"] == pytest.approx(0.20, abs=1e-6)
    assert agg["dy_mediana"] == pytest.approx(0.132)   # mediana de {0.12, 0.144}


def test_aggregate_fund_tendencia_quando_historico_curto():
    # 12 meses, segunda metade mais alta -> tendência 6m positiva, base 'tendencia_6m'.
    meses = [(f"2025-{m:02d}-01", 0.01) for m in range(1, 7)]
    meses += [(f"2025-{m:02d}-01", 0.012) for m in range(7, 13)]
    agg = aggregate_fund(_monthly(meses))
    assert agg["crescimento_base"] == "tendencia_6m"
    assert agg["crescimento"] == pytest.approx(0.2, abs=1e-6)


def test_aggregate_fund_saude_financeira():
    meses = [(f"2025-{m:02d}-01", 0.01) for m in range(5, 13)]
    df = _monthly(meses)
    # PL crescente, VP preservado, passivo = 10% do PL no último mês.
    df["patrimonio_liquido"] = [100.0 + i for i in range(len(df))]
    df["valor_patrimonial_cota"] = [10.0 + 0.1 * i for i in range(len(df))]
    df["total_passivo"] = [0.1 * (100.0 + i) for i in range(len(df))]
    agg = aggregate_fund(df)
    assert agg["alavancagem"] == pytest.approx(0.1, abs=1e-3)
    assert agg["vp_cota_var"] > 0
    assert agg["pl_crescimento_aa"] > 0


def test_credit_profile_credito_vs_terras_e_inadimplencia():
    # Fundo de crédito: CRA+CPR dominam, um pouco vencido.
    cred = pd.DataFrame({
        "competencia": pd.to_datetime(["2026-01-01", "2026-02-01"]),
        "total_investido": [1000.0, 1000.0],
        "imoveis_rurais": [0.0, 0.0],
        "cra": [600.0, 600.0], "cri": [0.0, 0.0], "cpr": [400.0, 400.0],
        "debentures": [0.0, 0.0],
        "vencidos": [0.0, 50.0], "a_vencer": [1000.0, 950.0],
        "patrimonio_liquido": [1000.0, 1000.0], "necessidades_liquidez": [100.0, 100.0],
    })
    p = credit_profile(cred)
    assert p["tipo"] == "credito"
    assert p["inadimplencia"] == pytest.approx(50 / 1000)        # 50/(950+50)
    assert p["diversificacao_hhi"] == pytest.approx(0.6**2 + 0.4**2)  # CRA 60%, CPR 40%
    assert p["liquidez_pl"] == pytest.approx(0.1)
    assert p["composicao"]["cra"] == pytest.approx(0.6)

    # Fundo de terras: imóveis rurais dominam.
    terras = pd.DataFrame({
        "competencia": pd.to_datetime(["2026-02-01"]),
        "total_investido": [1000.0], "imoveis_rurais": [800.0],
        "cra": [200.0], "cri": [0.0], "cpr": [0.0], "debentures": [0.0],
    })
    assert credit_profile(terras)["tipo"] == "terras"


def test_aggregate_fund_vazio():
    agg = aggregate_fund(pd.DataFrame(columns=["competencia", "dy_mes"]))
    assert agg["dy_ttm"] is None and agg["yield_trap"] is False
