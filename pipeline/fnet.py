"""Vacância e inadimplência de FII de tijolo via FNET (Fundos.NET da B3).

A CVM aberta (INF_MENSAL) NÃO traz vacância — ela vive no **Informe Trimestral Estruturado**
(ANEXO 39-II) protocolado no FNET. Cada imóvel de renda reporta `% de Vacância`,
`% de Inadimplência` e `% em relação às receitas do FII`. Daqui derivamos a vacância e a
inadimplência do FUNDO, ponderadas pela receita.

Honestidade: o FNET é **lento/instável** (retry/backoff) e o layout do informe **varia por
administrador** — funds que não parseiam ficam N/A (não inventa). `parse_imoveis` é puro e
testável; o acesso a rede (`fetch_*`) é isolado e degrada para None.
"""

from __future__ import annotations

import base64
import html as ihtml
import re
import time

BASE = "https://fnet.bmfbovespa.com.br/fnet/publico"
LISTA = f"{BASE}/pesquisarGerenciadorDocumentosDados"
DOC = f"{BASE}/exibirDocumento"
_VAC_IMPLAUSIVEL = 0.40  # vacância de fundo acima disto = coluna mal-preenchida → N/A


def _pct(s: str) -> float | None:
    """'12,3456%' → 0.123456. None se não numérico."""
    t = s.replace("%", "").strip().replace(".", "").replace(",", ".")
    try:
        return float(t) / 100.0
    except ValueError:
        return None


def _flat_cells(html: str) -> list[str]:
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", html, re.S | re.I):
        out.append(ihtml.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip())
    return [c for c in out if c]


def parse_imoveis(html: str) -> list[dict]:
    """Extrai os imóveis de renda do Informe Trimestral: nome, %vacância, %inadimplência,
    %receita. Puro e testável.

    Varre por PADRÃO (não pelo cabeçalho, que aparece uma vez só): cada imóvel é uma célula
    com 'Área (m...)' seguida de TRÊS percentuais — vacância, inadimplência e % das receitas
    do FII (validado no ANEXO 39-II real; ex.: HGLG lista 37 galpões assim, só o 1º sob o
    cabeçalho). Linhas cujos 2 primeiros vizinhos não são percentuais não são imóvel.
    """
    flat = _flat_cells(html)
    out: list[dict] = []
    for i, c in enumerate(flat):
        if "rea (m" not in c.lower() or i + 3 >= len(flat):
            continue
        vac, inad, rec = _pct(flat[i + 1]), _pct(flat[i + 2]), _pct(flat[i + 3])
        if vac is None or inad is None:
            continue  # não é a linha-imóvel (vac e inadimplência são sempre percentuais)
        out.append({"imovel": c[:60], "vacancia": vac, "inadimplencia": inad,
                    "pct_receita": rec})
    return out


def aggregate_vacancia(imoveis: list[dict]) -> dict:
    """Vacância e inadimplência do FUNDO, ponderadas pela receita (fallback média simples)."""
    if not imoveis:
        return {"vacancia": None, "inadimplencia": None, "n_imoveis": 0}
    pesos = [(im.get("pct_receita") or 0.0) for im in imoveis]
    wsum = sum(pesos)
    if wsum > 0:
        vac = sum(im["vacancia"] * (im.get("pct_receita") or 0.0) for im in imoveis) / wsum
        inj = [
            (im, im.get("pct_receita") or 0.0)
            for im in imoveis if im.get("inadimplencia") is not None
        ]
        inad = (
            sum(im["inadimplencia"] * w for im, w in inj) / sum(w for _, w in inj)
            if inj and sum(w for _, w in inj) > 0 else None
        )
    else:
        vac = sum(im["vacancia"] for im in imoveis) / len(imoveis)
        inads = [im["inadimplencia"] for im in imoveis if im.get("inadimplencia") is not None]
        inad = sum(inads) / len(inads) if inads else None
    return {"vacancia": round(vac, 4), "inadimplencia": None if inad is None else round(inad, 4),
            "n_imoveis": len(imoveis)}


# --------------------------------------------------------------------------- #
# Rede (isolada, resiliente — FNET é lento/instável)
# --------------------------------------------------------------------------- #


def _get(url: str, params: dict, *, timeout: int, retries: int = 3):
    try:
        import requests
    except ImportError:
        return None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(2 * (attempt + 1))  # backoff
    return None


def _dataref_key(d: dict) -> tuple:
    p = (d.get("dataReferencia") or "01/01/1900").split("/")
    return (p[2], p[1], p[0]) if len(p) == 3 else ("1900", "01", "01")


def latest_informe_trimestral(cnpj: str, *, timeout: int = 90) -> dict | None:
    """Doc do Informe Trimestral Estruturado mais recente (por data de referência) do fundo."""
    cnpj = re.sub(r"\D", "", cnpj)
    resp = _get(LISTA, {"d": 1, "s": 0, "l": 60, "cnpjFundo": cnpj,
                        "o[0][dataEntrega]": "desc"}, timeout=timeout)
    if resp is None:
        return None
    try:
        docs = resp.json().get("data") or []
    except ValueError:
        return None
    its = [d for d in docs if "Trimestral Estruturado" in (d.get("tipoDocumento") or "")]
    if not its:
        return None
    its.sort(key=_dataref_key, reverse=True)
    return its[0]


def fetch_documento_html(doc_id: int, *, timeout: int = 120) -> str | None:
    """Conteúdo HTML (base64-decodificado) de um documento do FNET. None em falha."""
    resp = _get(DOC, {"id": doc_id}, timeout=timeout)
    if resp is None:
        return None
    txt = resp.text.strip().strip('"')
    try:
        return base64.b64decode(txt).decode("utf-8", "replace")
    except Exception:
        return txt or None


def fetch_vacancia(cnpj: str) -> dict | None:
    """Vacância/inadimplência do fundo a partir do último Informe Trimestral. None se a rede
    falhar ou o informe não parsear (sem imóveis) — o chamador marca N/A, não inventa."""
    doc = latest_informe_trimestral(cnpj)
    if doc is None:
        return None
    html = fetch_documento_html(doc.get("id"))
    if not html:
        return None
    agg = aggregate_vacancia(parse_imoveis(html))
    if not agg["n_imoveis"]:
        return None
    # Trava de sanidade: alguns administradores preenchem a coluna "% de Vacância" com
    # ocupação/participação (ex.: XPML reporta 100% por imóvel). Uma vacância de fundo > 40%
    # não é vacância real de um fundo em operação → dado inutilizável, marca N/A (não inventa).
    if agg["vacancia"] is not None and agg["vacancia"] > _VAC_IMPLAUSIVEL:
        return None
    agg["data_ref"] = doc.get("dataReferencia")
    return agg
