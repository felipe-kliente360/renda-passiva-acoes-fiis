import io
import zipfile

import pandas as pd
import pytest
from conftest import DATA_DIR

from pipeline.normalize import (
    list_zip_members,
    read_cvm_csv,
    read_cvm_csv_from_zip,
    to_numeric_ptbr,
)

COMMA_SAMPLE = DATA_DIR / "cvm_comma_sample.csv"
SAMPLE = DATA_DIR / "fii_inf_mensal_sample.csv"


def test_read_cvm_csv_handles_latin1_sep_decimal():
    df = read_cvm_csv(COMMA_SAMPLE)
    assert list(df.columns) == [
        "CNPJ_Fundo",
        "Data_Referencia",
        "Patrimonio_Liquido",
        "Cotas_Emitidas",
        "Valor_Patrimonial_Cotas",
    ]
    # dtype=str por padrão: nada convertido ainda
    assert df["Patrimonio_Liquido"].iloc[0] == "1.000.000,00"


def test_to_numeric_ptbr_thousand_and_decimal():
    df = read_cvm_csv(COMMA_SAMPLE)
    pl = to_numeric_ptbr(df["Patrimonio_Liquido"])  # default vírgula
    assert pl.iloc[0] == 1_000_000.00
    assert pl.iloc[1] == 1_020_000.00


def test_to_numeric_ptbr_dot_decimal_keeps_point():
    # Caminho do FII INF_MENSAL: ponto é o decimal, NÃO separador de milhar.
    # Regressão do bug que lia "92.21" como 9221 ao remover o ponto.
    s = pd.Series(["92.2101419138767", "100.00", "606485090.82"])
    out = to_numeric_ptbr(s, decimal=".")
    assert out.iloc[0] == pytest.approx(92.2101419138767)
    assert out.iloc[1] == 100.0
    assert out.iloc[2] == pytest.approx(606485090.82)


def test_to_numeric_ptbr_idempotent_on_numeric():
    s = pd.Series([1.0, 2.5, 3.0])
    out = to_numeric_ptbr(s)
    pd.testing.assert_series_equal(out, s)


def test_read_from_zip_roundtrip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("inf_mensal_fii.csv", SAMPLE.read_bytes())
    data = buf.getvalue()
    assert list_zip_members(data) == ["inf_mensal_fii.csv"]
    df = read_cvm_csv_from_zip(data, "inf_mensal_fii.csv")
    assert len(df) == 5
