import pandas as pd
import pytest
from conftest import DATA_DIR

from pipeline.fii import (
    aggregate_fii_dy,
    classify_fii_tipo,
    latest_vp_por_fundo,
    parse_fii_enriched,
    parse_fii_inf_mensal,
)
from pipeline.normalize import read_cvm_csv

SAMPLE = DATA_DIR / "fii_inf_mensal_sample.csv"


def test_parse_uses_direct_vp_when_present():
    df = read_cvm_csv(SAMPLE)
    parsed = parse_fii_inf_mensal(df)
    fundo_a = parsed[parsed["cnpj_fundo"] == "11.111.111/0001-11"]
    assert sorted(fundo_a["valor_patrimonial_cota"].tolist()) == [100.0, 102.0]


def test_parse_derives_vp_from_pl_and_cotas():
    df = read_cvm_csv(SAMPLE)
    parsed = parse_fii_inf_mensal(df)
    fundo_b = parsed[parsed["cnpj_fundo"] == "22.222.222/0001-22"]
    # 5.000.000 / 100.000 = 50,00 ; 5.100.000 / 100.000 = 51,00
    assert sorted(fundo_b["valor_patrimonial_cota"].tolist()) == [50.0, 51.0]


def test_parse_handles_zero_cotas_without_dividing_by_zero():
    df = read_cvm_csv(SAMPLE)
    parsed = parse_fii_inf_mensal(df)
    fundo_c = parsed[parsed["cnpj_fundo"] == "33.333.333/0001-33"]
    assert fundo_c["valor_patrimonial_cota"].isna().all()


def test_latest_vp_picks_most_recent_competencia():
    df = read_cvm_csv(SAMPLE)
    parsed = parse_fii_inf_mensal(df)
    latest = latest_vp_por_fundo(parsed)
    a = latest[latest["cnpj_fundo"] == "11.111.111/0001-11"]
    assert len(a) == 1
    assert a["valor_patrimonial_cota"].iloc[0] == 102.0
    assert a["competencia"].iloc[0] == pd.Timestamp("2026-02-01")
    # fundo C (sempre NaN) não entra
    assert "33.333.333/0001-33" not in set(latest["cnpj_fundo"])


def test_missing_required_column_raises():
    df = pd.DataFrame({"foo": ["x"], "Data_Referencia": ["2024-01-31"]})
    with pytest.raises(ValueError, match="obrigatórias"):
        parse_fii_inf_mensal(df)


def test_parse_fii_enriched_extrai_dy_passivo_taxa():
    df = read_cvm_csv(DATA_DIR / "fii_inf_mensal_enriched_sample.csv")
    out = parse_fii_enriched(df).sort_values("competencia").reset_index(drop=True)
    assert out["dy_mes"].tolist() == [0.009, 0.0095]
    # passivo derivado = Valor_Ativo − PL = 1.100.000 − 1.000.000 = 100.000
    assert out["total_passivo"].iloc[0] == pytest.approx(100000.0)
    assert out["taxa_administracao"].iloc[0] == pytest.approx(0.0008)
    assert out["valor_patrimonial_cota"].iloc[0] == pytest.approx(100.0)


def test_classify_fii_tipo_tijolo_papel_hibrido():
    ap = pd.DataFrame({
        "CNPJ_Fundo_Classe": ["1", "2", "3"],
        "Data_Referencia": ["2026-02-01", "2026-02-01", "2026-02-01"],
        "Imoveis_Renda_Acabados": ["900.00", "0.00", "500.00"],
        "CRI": ["0.00", "950.00", "450.00"],
        "FII": ["100.00", "50.00", "50.00"],
    })
    assert classify_fii_tipo(ap, "1") == "tijolo"   # imóveis dominam
    assert classify_fii_tipo(ap, "2") == "papel"    # CRI domina
    assert classify_fii_tipo(ap, "3") == "híbrido"  # imóveis ~ papel, nenhum ≥60%
    assert classify_fii_tipo(ap, "999") is None     # fora do arquivo


def _monthly(dy_por_mes):
    return pd.DataFrame({
        "competencia": pd.to_datetime([d for d, _ in dy_por_mes]),
        "dy_mes": [v for _, v in dy_por_mes],
    })


def test_aggregate_fii_dy_ttm_e_mediana():
    # 2 anos completos a 1%/mês = 12% ao ano; TTM (últimos 12) = 12%.
    meses = [(f"2024-{m:02d}-01", 0.01) for m in range(1, 13)]
    meses += [(f"2025-{m:02d}-01", 0.01) for m in range(1, 13)]
    agg = aggregate_fii_dy(_monthly(meses))
    assert agg["dy_ttm"] == pytest.approx(0.12)
    assert agg["dy_mediana"] == pytest.approx(0.12)
    assert agg["meses_com_pagamento_12m"] == 12
    assert agg["yield_trap"] is False


def test_aggregate_fii_dy_detecta_trap():
    # baseline 1%/mês (12%/ano) em 2023 e 2024; últimos 12 (2025) a 2%/mês (24%).
    # mediana dos anos completos = 12%; TTM 24% > 1,5 × 12% -> trap.
    meses = [(f"{y}-{m:02d}-01", 0.01) for y in (2023, 2024) for m in range(1, 13)]
    meses += [(f"2025-{m:02d}-01", 0.02) for m in range(1, 13)]
    agg = aggregate_fii_dy(_monthly(meses))
    assert agg["dy_ttm"] == pytest.approx(0.24)
    assert agg["dy_mediana"] == pytest.approx(0.12)
    assert agg["yield_trap"] is True


def test_aggregate_fii_dy_vazio():
    agg = aggregate_fii_dy(pd.DataFrame(columns=["competencia", "dy_mes"]))
    assert agg["dy_ttm"] is None and agg["yield_trap"] is False
