"""Camada macro (BCB / SGS) — contexto de juros e inflação.

Aditiva, NÃO mexe na metodologia travada de DY. Serve para contextualizar o yield dos
fundos de recebíveis (spread sobre CDI) e lembrar que o "crescimento" de DY de FII de
papel acompanha o ciclo de juros, não é crescimento fundamental.

A API do BCB (SGS) é pública, JSON, sem auth. Acesso a REDE isolado em `fetch_*`;
`accumulate_daily` é puro e testável offline. Séries:
  12 = CDI diário (% a.d.) · 432 = Selic meta (% a.a.) · 13522 = IPCA acumulado 12m (%).
"""

from __future__ import annotations

SGS_ULTIMOS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{n}"
SGS_RANGE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
CDI_DIARIO, SELIC_META, IPCA_12M = 12, 432, 13522


def accumulate_daily(daily_pct: list[float]) -> float:
    """Acumula taxas diárias (% ao dia) em retorno composto do período (fração).

    Ex.: 252 pregões de ~0,0525%/dia → ~13,8% no ano. Puro — base do CDI 12m.
    """
    acc = 1.0
    for v in daily_pct:
        acc *= 1.0 + v / 100.0
    return acc - 1.0


def _get_json(url: str, params: dict, timeout: int) -> list[dict]:
    try:
        import requests
    except ImportError:
        return []
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def fetch_sgs(code: int, *, last_n: int = 1, timeout: int = 30) -> list[dict]:
    """Últimos `last_n` pontos de uma série do SGS (cap ~20 no endpoint). [] em falha."""
    return _get_json(SGS_ULTIMOS.format(code=code, n=last_n), {"formato": "json"}, timeout)


def fetch_sgs_range(code: int, inicio: str, fim: str, *, timeout: int = 30) -> list[dict]:
    """Pontos da série no intervalo [inicio, fim] (datas DD/MM/AAAA). Para o CDI 12m, onde
    `ultimos/N` não serve (limite de 20 pontos)."""
    return _get_json(
        SGS_RANGE.format(code=code),
        {"formato": "json", "dataInicial": inicio, "dataFinal": fim},
        timeout,
    )


def _latest_value(points: list[dict]) -> float | None:
    if not points:
        return None
    try:
        return float(points[-1]["valor"])
    except (KeyError, ValueError, TypeError):
        return None


def fetch_macro_snapshot(today: object = None) -> dict | None:
    """Snapshot macro corrente: CDI 12m (composto), Selic meta e IPCA 12m (frações).

    O CDI 12m vem do intervalo dos últimos ~365 dias (compõe os pregões). Retorna None se
    nada for obtido (offline) — o pipeline degrada sem inventar.
    """
    from datetime import date, timedelta

    today = today or date.today()
    inicio = (today - timedelta(days=400)).strftime("%d/%m/%Y")
    fim = today.strftime("%d/%m/%Y")
    cdi_pts = fetch_sgs_range(CDI_DIARIO, inicio, fim)
    cdi_12m = None
    if cdi_pts:
        diarios = []
        for p in cdi_pts:
            try:
                diarios.append(float(p["valor"]))
            except (KeyError, ValueError, TypeError):
                continue
        # últimos ~252 pregões = janela de 12 meses
        cdi_12m = accumulate_daily(diarios[-252:]) if diarios else None

    selic = _latest_value(fetch_sgs(SELIC_META))
    ipca = _latest_value(fetch_sgs(IPCA_12M))
    if cdi_12m is None and selic is None and ipca is None:
        return None
    return {
        "cdi_12m": cdi_12m,                                  # fração (ex.: 0.138)
        "selic_meta": selic / 100 if selic is not None else None,
        "ipca_12m": ipca / 100 if ipca is not None else None,
        "as_of": (cdi_pts[-1].get("data") if cdi_pts else fim),
    }
