import pandas as pd
from conftest import DATA_DIR

from pipeline.ipe import fatos_relevantes, parse_ipe
from pipeline.normalize import read_cvm_csv

SAMPLE = DATA_DIR / "ipe_sample.csv"


def test_parse_ipe_normaliza_e_remove_zeros():
    out = parse_ipe(read_cvm_csv(SAMPLE))
    assert set(out["cd_cvm"]) == {"9512", "19348", "99999"}
    assert out["data"].notna().all()


def test_fatos_relevantes_filtra_categoria_e_watchlist():
    df = parse_ipe(read_cvm_csv(SAMPLE))
    recs = fatos_relevantes(df, {"9512", "19348"})  # watchlist sem a "99999"
    assuntos = {r["assunto"] for r in recs}
    cats = {r["categoria"] for r in recs}
    # mantém fato relevante, relatório proventos e aviso aos acionistas
    assert "Fato Relevante" in cats and "Aviso aos Acionistas" in cats
    # exclui "Política de Divulgação..." (governança) e "Reunião da Administração"
    assert not any("Politica" in c or "Reuniao" in c for c in cats)
    # exclui empresa fora da watchlist
    assert "Fora da watchlist" not in assuntos
    # ordenado por data desc
    datas = [r["data"] for r in recs]
    assert datas == sorted(datas, reverse=True)


def test_fatos_relevantes_limit_por_empresa():
    df = parse_ipe(read_cvm_csv(SAMPLE))
    recs = fatos_relevantes(df, {"9512"}, limit_por_empresa=1)
    assert len([r for r in recs if r["cd_cvm"] == "9512"]) == 1


def test_fatos_relevantes_vazio():
    assert fatos_relevantes(pd.DataFrame(columns=["cd_cvm", "data", "categoria"]), {"9512"}) == []
