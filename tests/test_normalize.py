import io
import zipfile

import pandas as pd
from conftest import DATA_DIR

from pipeline.normalize import (
    list_zip_members,
    read_cvm_csv,
    read_cvm_csv_from_zip,
    to_numeric_ptbr,
)

SAMPLE = DATA_DIR / "fii_inf_mensal_sample.csv"


def test_read_cvm_csv_handles_latin1_sep_decimal():
    df = read_cvm_csv(SAMPLE)
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
    df = read_cvm_csv(SAMPLE)
    pl = to_numeric_ptbr(df["Patrimonio_Liquido"])
    assert pl.iloc[0] == 1_000_000.00
    assert pl.iloc[1] == 1_020_000.00


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
