import pandas as pd
import pytest
from conftest import DATA_DIR

from pipeline.fundamentos import (
    extract_concept,
    load_contas_config,
    lucro_liquido,
    resolve_share_scale,
    total_acoes,
)
from pipeline.normalize import read_cvm_csv

DFC = DATA_DIR / "dfp_dfc_sample.csv"
DRE = DATA_DIR / "dfp_dre_sample.csv"
COMP = DATA_DIR / "dfp_composicao_capital_sample.csv"


def _proventos():
    df = read_cvm_csv(DFC)
    spec = load_contas_config()["proventos_pagos"]
    return extract_concept(df, spec)


def test_proventos_soma_controladora_aplica_escala_e_absoluto():
    out = _proventos()
    alfa = out[out["denom"] == "CIA ALFA SA"]
    # 100.000 (MIL) -> 100.000.000 ; exclui não-controladores (5.000) e recebidos (2.000),
    # exclui o PENÚLTIMO; toma valor absoluto.
    assert len(alfa) == 1
    assert alfa["valor"].iloc[0] == pytest.approx(100_000_000.0)


def test_proventos_plano_financeiro_exclui_nao_controladores():
    out = _proventos()
    beta = out[out["denom"] == "BANCO BETA SA"]
    # 50.000,50 (MIL) -> 50.000.500 ; exclui a linha de não controladores (300).
    assert beta["valor"].iloc[0] == pytest.approx(50_000_500.0)


def test_proventos_so_considera_ultimo_exercicio():
    out = _proventos()
    assert set(out["dt_fim_exerc"].dt.year.unique()) == {2025}


def test_extract_concept_sem_match_retorna_vazio():
    df = read_cvm_csv(DFC)
    spec = load_contas_config()["proventos_pagos"]
    # força um conceito que não casa nada
    from dataclasses import replace

    out = extract_concept(df, replace(spec, ds_includes=["xpto inexistente"]))
    assert out.empty


def test_extract_concept_valida_colunas_obrigatorias():
    spec = load_contas_config()["proventos_pagos"]
    with pytest.raises(ValueError, match="ausentes"):
        extract_concept(pd.DataFrame({"foo": [1]}), spec)


def test_lucro_prefere_controladora_sobre_consolidado():
    out = lucro_liquido(read_cvm_csv(DRE))
    alfa = out[out["denom"] == "CIA ALFA SA"]
    # 180.000 (controladora, MIL) -> 180.000.000 ; NÃO 200.000 (consolidado) nem soma.
    assert len(alfa) == 1
    assert alfa["valor"].iloc[0] == pytest.approx(180_000_000.0)
    assert alfa["fonte_lucro"].iloc[0] == "controladora"


def test_lucro_cai_no_consolidado_sem_abertura():
    out = lucro_liquido(read_cvm_csv(DRE))
    beta = out[out["denom"] == "BANCO BETA SA"]
    # banco sem linha de controladora -> usa o consolidado do período (90.000 MIL).
    assert beta["valor"].iloc[0] == pytest.approx(90_000_000.0)
    assert beta["fonte_lucro"].iloc[0] == "consolidado"


def test_lucro_uma_linha_por_empresa_exercicio():
    out = lucro_liquido(read_cvm_csv(DRE))
    assert out.groupby(["cnpj", "dt_fim_exerc"]).size().max() == 1
    assert set(out["dt_fim_exerc"].dt.year.unique()) == {2025}


def test_resolve_share_scale_detecta_milhares_e_unidades():
    # Vale: CVM cru 4,5M, âncora yfinance 4,26bi -> milhares (x1000).
    assert resolve_share_scale(4_539_007, 4_257_407_053) == 1000.0
    # Petrobras: CVM cru 12,9bi, âncora 5,4bi (só PN) -> unidades (x1).
    assert resolve_share_scale(12_888_732_761, 5_446_501_379) == 1.0
    # sem âncora confiável -> assume 1 (não inventa).
    assert resolve_share_scale(4_539_007, None) == 1.0
    assert resolve_share_scale(0, 1_000_000) == 1.0


def test_total_acoes_emitidas_menos_tesouraria():
    comp = read_cvm_csv(COMP)
    out = total_acoes(comp)
    alfa = out[out["denom"] == "CIA ALFA SA"]
    # (1000 + 500) - 100 = 1400
    assert alfa["acoes_circulacao"].iloc[0] == pytest.approx(1400.0)
    beta = out[out["denom"] == "BANCO BETA SA"]
    assert beta["acoes_circulacao"].iloc[0] == pytest.approx(2000.0)
