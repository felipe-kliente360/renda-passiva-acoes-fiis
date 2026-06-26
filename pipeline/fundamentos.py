"""Extração de fundamentos das demonstrações da CVM (ITR/DFP) — puro e testável.

As demonstrações vêm em formato long-format: uma linha por conta, com CD_CONTA,
DS_CONTA e VL_CONTA. O layout CIA_ABERTA é estável (ISO-8859-1, `;`, decimal PONTO,
valores em ESCALA_MOEDA — MIL/UNIDADE), e separa o exercício de referência (ORDEM_EXERC
= ÚLTIMO) do comparativo (PENÚLTIMO).

Conceitos lógicos (proventos pagos, lucro líquido, ...) são localizados por config
(`config/contas.yml`): casamos por SEÇÃO (prefixo do CD_CONTA) + PALAVRAS na DS_CONTA e
SOMAMOS as linhas que batem — resiliente aos planos financeiro e não-financeiro, onde os
códigos diferem. Nada de CD_CONTA fixo no código.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Colunas estáveis do layout CIA_ABERTA (DFP/ITR). Validar presença antes de confiar.
COLS = {
    "cnpj": "CNPJ_CIA",
    "cd_cvm": "CD_CVM",
    "denom": "DENOM_CIA",
    "dt_refer": "DT_REFER",
    "dt_fim_exerc": "DT_FIM_EXERC",
    "ordem": "ORDEM_EXERC",
    "escala": "ESCALA_MOEDA",
    "cd_conta": "CD_CONTA",
    "ds_conta": "DS_CONTA",
    "vl_conta": "VL_CONTA",
}

SCALE_FACTOR = {"UNIDADE": 1.0, "MIL": 1_000.0, "MILHAO": 1_000_000.0, "MILHÃO": 1_000_000.0}


@dataclass(frozen=True)
class ContaSpec:
    """Como localizar um conceito nas demonstrações (ver config/contas.yml)."""

    name: str
    statement: str
    section_prefix: str
    ds_includes: list[str]
    ds_excludes: list[str]
    absolute: bool


def load_contas_config(path: str | Path | None = None) -> dict[str, ContaSpec]:
    """Carrega `config/contas.yml` em specs tipadas por conceito."""
    path = Path(path) if path is not None else CONFIG_DIR / "contas.yml"
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    specs: dict[str, ContaSpec] = {}
    for name, c in raw.items():
        specs[name] = ContaSpec(
            name=name,
            statement=str(c["statement"]),
            section_prefix=str(c.get("section_prefix", "")),
            ds_includes=[_norm(s) for s in c.get("ds_includes", [])],
            ds_excludes=[_norm(s) for s in c.get("ds_excludes", [])],
            absolute=bool(c.get("absolute", False)),
        )
    return specs


def _norm(text: object) -> str:
    """Minúsculas sem acento — para casar DS_CONTA de forma robusta."""
    s = str(text).strip().lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _scale_factor(escala: object) -> float:
    return SCALE_FACTOR.get(_norm(escala).upper(), 1.0)


def _matches(ds_norm: str, includes: list[str], excludes: list[str]) -> bool:
    if not any(inc in ds_norm for inc in includes):
        return False
    return not any(exc in ds_norm for exc in excludes)


def extract_concept(
    df: pd.DataFrame, spec: ContaSpec, *, ordem: str = "ÚLTIMO"
) -> pd.DataFrame:
    """Extrai um conceito por empresa/exercício, somando as linhas que batem.

    Saída: cnpj, cd_cvm, denom, dt_fim_exerc (datetime), valor (float, já escalado por
    ESCALA_MOEDA e com |valor| se spec.absolute). Uma linha por (empresa, exercício).
    """
    missing = [c for c in COLS.values() if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas CIA_ABERTA ausentes: {missing}. Reais: {list(df.columns)}")

    w = df[df[COLS["ordem"]].map(_norm) == _norm(ordem)].copy()
    cd = w[COLS["cd_conta"]].astype("string").fillna("")
    ds_norm = w[COLS["ds_conta"]].map(_norm)
    sec = cd.str.startswith(spec.section_prefix) if spec.section_prefix else True
    hit = ds_norm.map(lambda s: _matches(s, spec.ds_includes, spec.ds_excludes))
    w = w[sec & hit]
    if w.empty:
        return _empty_concept()

    w["_valor"] = (
        pd.to_numeric(w[COLS["vl_conta"]], errors="coerce")
        * w[COLS["escala"]].map(_scale_factor)
    )
    grp = (
        w.groupby([COLS["cnpj"], COLS["cd_cvm"], COLS["denom"], COLS["dt_fim_exerc"]])["_valor"]
        .sum()
        .reset_index()
    )
    grp = grp.rename(
        columns={
            COLS["cnpj"]: "cnpj",
            COLS["cd_cvm"]: "cd_cvm",
            COLS["denom"]: "denom",
            COLS["dt_fim_exerc"]: "dt_fim_exerc",
            "_valor": "valor",
        }
    )
    grp["dt_fim_exerc"] = pd.to_datetime(grp["dt_fim_exerc"], errors="coerce")
    if spec.absolute:
        grp["valor"] = grp["valor"].abs()
    return grp.dropna(subset=["dt_fim_exerc"]).reset_index(drop=True)


def _empty_concept() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj": pd.Series(dtype="string"),
            "cd_cvm": pd.Series(dtype="string"),
            "denom": pd.Series(dtype="string"),
            "dt_fim_exerc": pd.Series(dtype="datetime64[ns]"),
            "valor": pd.Series(dtype="float64"),
        }
    )


def lucro_liquido(
    df_dre: pd.DataFrame, specs: dict[str, ContaSpec] | None = None, *, ordem: str = "ÚLTIMO"
) -> pd.DataFrame:
    """Lucro líquido por empresa/exercício, preferindo o ATRIBUÍDO À CONTROLADORA.

    Cai no consolidado do período só onde não há abertura por controladora (empresas sem
    minoritários). Coluna `fonte_lucro` registra qual saiu. Mesma saída tidy do
    extract_concept (cnpj, cd_cvm, denom, dt_fim_exerc, valor).
    """
    specs = specs or load_contas_config()
    contr = extract_concept(df_dre, specs["lucro_controladora"], ordem=ordem)
    conso = extract_concept(df_dre, specs["lucro_consolidado"], ordem=ordem)
    contr = contr.assign(fonte_lucro="controladora")
    keys = ["cnpj", "cd_cvm", "denom", "dt_fim_exerc"]
    # consolidado só para chaves ausentes na controladora
    falta = conso.merge(contr[keys], on=keys, how="left", indicator=True)
    falta = falta[falta["_merge"] == "left_only"].drop(columns="_merge")
    falta = falta.assign(fonte_lucro="consolidado")
    out = pd.concat([contr, falta], ignore_index=True)
    return out.reset_index(drop=True)


def resolve_share_scale(cvm_raw: float, anchor_shares: float | None) -> float:
    """Fator de escala (1 ou 1000) para a contagem de ações crua da CVM.

    O `composicao_capital` mistura unidades e milhares por empresa, sem coluna que sinalize
    (validado: Petrobras em unidades, Vale/Itaú/Ambev em milhares). A CVM dá a CONTAGEM
    autoritativa; uma âncora de mercado (ex.: sharesOutstanding do yfinance) só desambigua a
    UNIDADE. Compara a ordem de grandeza: razão ~1 ⇒ unidades; ~1000 ⇒ milhares. As bandas
    são folgadas porque a âncora pode ser de uma só classe (ON) vs total ON+PN da CVM.
    Sem âncora confiável, assume 1 (não inventa) — o chamador deve sinalizar baixa confiança.
    """
    if not anchor_shares or not cvm_raw or cvm_raw <= 0:
        return 1.0
    ratio = anchor_shares / cvm_raw
    if 200 < ratio < 5000:
        return 1000.0
    return 1.0


def total_acoes(df_comp: pd.DataFrame) -> pd.DataFrame:
    """Ações em circulação por empresa = (ON + PN) integralizadas − tesouraria.

    Lê o membro `composicao_capital`. ATENÇÃO: a escala da quantidade varia por empresa no
    arquivo cru (algumas reportam em unidades, outras em milhares) — quem consome deve
    validar a magnitude (ex.: cruzar com valor de mercado conhecido), não confiar cego.
    """
    need = ["CNPJ_CIA", "DENOM_CIA", "DT_REFER"]
    missing = [c for c in need if c not in df_comp.columns]
    if missing:
        raise ValueError(f"composicao_capital sem colunas {missing}")

    def col(name: str) -> pd.Series:
        return (
            pd.to_numeric(df_comp[name], errors="coerce").fillna(0)
            if name in df_comp.columns
            else pd.Series(0, index=df_comp.index)
        )

    emitidas = col("QT_ACAO_ORDIN_CAP_INTEGR") + col("QT_ACAO_PREF_CAP_INTEGR")
    tesouro = col("QT_ACAO_ORDIN_TESOURO") + col("QT_ACAO_PREF_TESOURO")
    out = pd.DataFrame(
        {
            "cnpj": df_comp["CNPJ_CIA"].astype("string"),
            "denom": df_comp["DENOM_CIA"].astype("string"),
            "dt_refer": pd.to_datetime(df_comp["DT_REFER"], errors="coerce"),
            "acoes_circulacao": (emitidas - tesouro).astype("float64"),
        }
    )
    return out.dropna(subset=["dt_refer"]).reset_index(drop=True)
