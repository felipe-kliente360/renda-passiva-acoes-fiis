from pipeline.columns import load_columns_config, resolve_columns


def test_load_config_has_fii_dataset():
    specs = load_columns_config()
    assert "fii_inf_mensal" in specs
    spec = specs["fii_inf_mensal"]
    assert spec.encoding == "ISO-8859-1"
    assert spec.sep == ";"
    assert spec.decimal == ","
    names = {f.name for f in spec.fields}
    assert {"cnpj_fundo", "competencia", "valor_patrimonial_cota"} <= names


def test_resolve_picks_first_present_candidate():
    specs = load_columns_config()
    spec = specs["fii_inf_mensal"]
    available = ["CNPJ_Fundo", "Data_Referencia", "Patrimonio_Liquido", "Cotas_Emitidas"]
    resolved, missing = resolve_columns(spec, available)
    assert resolved["cnpj_fundo"] == "CNPJ_Fundo"
    assert resolved["competencia"] == "Data_Referencia"
    assert "valor_patrimonial_cota" not in resolved  # ausente, opcional
    assert missing == []


def test_resolve_reports_missing_required():
    specs = load_columns_config()
    spec = specs["fii_inf_mensal"]
    resolved, missing = resolve_columns(spec, ["foo", "bar"])
    assert "cnpj_fundo" in missing
    assert "competencia" in missing
