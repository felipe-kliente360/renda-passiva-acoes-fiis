import pandas as pd
import pytest
from conftest import DATA_DIR

from pipeline.fii import latest_vp_por_fundo, parse_fii_inf_mensal
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
