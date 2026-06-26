from pipeline.columns import (
    load_columns_config,
    pick_member_by_resolution,
    resolve_columns,
)


def test_load_config_has_fii_dataset():
    specs = load_columns_config()
    assert "fii_inf_mensal" in specs
    spec = specs["fii_inf_mensal"]
    assert spec.encoding == "ISO-8859-1"
    assert spec.sep == ";"
    assert spec.decimal == "."  # INF_MENSAL de FII é ponto-decimal (validado no real)
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


def test_pick_member_prefers_one_with_vp_fields():
    # Reproduz o ZIP real do INF_MENSAL: 3 membros, só `complemento` tem VP/PL/cotas.
    spec = load_columns_config()["fii_inf_mensal"]
    members = {
        "inf_mensal_fii_ativo_passivo_2026.csv": [
            "CNPJ_Fundo_Classe", "Data_Referencia", "Total_Passivo"
        ],
        "inf_mensal_fii_complemento_2026.csv": [
            "CNPJ_Fundo_Classe", "Data_Referencia",
            "Patrimonio_Liquido", "Cotas_Emitidas", "Valor_Patrimonial_Cotas",
        ],
        "inf_mensal_fii_geral_2026.csv": [
            "CNPJ_Fundo_Classe", "Data_Referencia", "Nome_Fundo_Classe"
        ],
    }
    chosen = pick_member_by_resolution(
        spec, members,
        prefer_fields=("valor_patrimonial_cota", "patrimonio_liquido", "cotas_emitidas"),
    )
    assert chosen == "inf_mensal_fii_complemento_2026.csv"


def test_pick_member_returns_none_when_required_missing():
    spec = load_columns_config()["fii_inf_mensal"]
    members = {"lixo.csv": ["foo", "bar"]}
    assert pick_member_by_resolution(spec, members) is None
