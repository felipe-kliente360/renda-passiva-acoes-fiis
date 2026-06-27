"""Feed de fatos relevantes / comunicados da watchlist (IPE-RAD da CVM) — Fase 7.

O dataset IPE é o ÍNDICE estruturado dos documentos protocolados pelas companhias
(data, categoria, assunto, link para o RAD). Não lemos o corpo do PDF — só o índice.
Foco da tese de renda passiva: avisos de proventos, fatos relevantes e comunicados.

Puro e testável: `parse_ipe` normaliza o CSV; `fatos_relevantes` filtra por empresa e
categoria e devolve os mais recentes. Acesso a rede fica no downloader (pipeline/cvm).
"""

from __future__ import annotations

import pandas as pd

from .columns import DatasetSpec, load_columns_config, resolve_columns

DATASET = "ipe_cia_aberta"

# Categorias mais relevantes para a tese (proventos + materialidade). Casadas por substring
# normalizada — a CVM usa "Fato Relevante", "Aviso aos Acionistas", "Relatório Proventos".
CATEGORIAS_RELEVANTES = (
    "fato relevante",
    "aviso aos acionistas",
    "proventos",
)
# Exclui categorias de GOVERNANÇA que contêm "fato relevante" no nome mas não são eventos
# (ex.: "Política de Divulgação de Ato ou Fato Relevante").
CATEGORIAS_EXCLUDES = ("politica",)


def parse_ipe(df: pd.DataFrame, spec: DatasetSpec | None = None) -> pd.DataFrame:
    """Normaliza o índice IPE para colunas lógicas estáveis.

    Saída: cd_cvm (str, sem zeros à esquerda), nome, data (datetime), categoria, tipo,
    especie, assunto, link. Linhas sem data/categoria válidas são descartadas.
    """
    spec = spec or load_columns_config()[DATASET]
    resolved, missing = resolve_columns(spec, list(df.columns))
    if missing:
        raise ValueError(
            f"Colunas obrigatórias ausentes no IPE: {missing}. Reais: {list(df.columns)}."
        )

    out = pd.DataFrame()
    out["cd_cvm"] = df[resolved["cd_cvm"]].astype("string").str.strip().str.lstrip("0")
    out["nome"] = (
        df[resolved["nome"]].astype("string").str.strip()
        if "nome" in resolved else pd.Series([pd.NA] * len(df), dtype="string")
    )
    out["data"] = pd.to_datetime(df[resolved["data_entrega"]], errors="coerce", format="mixed")
    out["categoria"] = df[resolved["categoria"]].astype("string").str.strip()
    for fld in ("tipo", "especie", "assunto", "link"):
        out[fld] = (
            df[resolved[fld]].astype("string").str.strip()
            if fld in resolved else pd.Series([pd.NA] * len(df), dtype="string")
        )
    return out.dropna(subset=["data", "categoria"]).reset_index(drop=True)


def _norm(s: object) -> str:
    import unicodedata

    t = str(s).strip().lower()
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def fatos_relevantes(
    df: pd.DataFrame,
    cds: set[str],
    *,
    categorias: tuple[str, ...] = CATEGORIAS_RELEVANTES,
    limit_por_empresa: int = 8,
) -> list[dict]:
    """Seleciona os documentos relevantes por empresa, mais recentes primeiro.

    `df` é a saída de `parse_ipe`; `cds` os CD_CVM (sem zeros à esquerda) da watchlist.
    Filtra por categoria (substring normalizada) e devolve até `limit_por_empresa` itens por
    empresa, ordenados por data desc. Retorna registros prontos para export.
    """
    if df.empty:
        return []
    sub = df[df["cd_cvm"].isin(cds)].copy()
    cat_norm = sub["categoria"].map(_norm)
    hit = cat_norm.map(
        lambda c: any(k in c for k in categorias)
        and not any(x in c for x in CATEGORIAS_EXCLUDES)
    )
    sub = sub[hit].sort_values("data", ascending=False)

    out: list[dict] = []
    for cd, grp in sub.groupby("cd_cvm"):
        for _, r in grp.head(limit_por_empresa).iterrows():
            out.append({
                "cd_cvm": cd,
                "nome": None if pd.isna(r["nome"]) else r["nome"],
                "data": r["data"].date().isoformat(),
                "categoria": r["categoria"],
                "tipo": None if pd.isna(r["tipo"]) else r["tipo"],
                "assunto": None if pd.isna(r["assunto"]) else r["assunto"],
                "link": None if pd.isna(r["link"]) else r["link"],
            })
    out.sort(key=lambda x: x["data"], reverse=True)
    return out
