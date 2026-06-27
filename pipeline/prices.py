"""Pipeline de preços (Fase 1).

Decisão TRAVADA: a série usada como denominador do DY é o preço NEGOCIADO ajustado
SÓ por split/grupamento, NUNCA por dividendo. Ver docs/prices-methodology.md.

Organização:
- Funções PURAS e testáveis offline: split_adjust, reconstruct_traded_from_adjusted,
  annual_avg_price, price_to_book, build_price_record.
- Acesso a REDE isolado em fetch_* (brapi primário p/ spot; yfinance p/ série histórica
  e eventos). Degradam graciosamente quando offline / sem dependência.

Fontes (refinamento sobre o briefing, sinalizado ao Felipe):
- yfinance `Close` (auto_adjust=False) já vem ajustado por split e NÃO por dividendo —
  é exatamente a série canônica; por isso é a fonte da SÉRIE histórica.
- brapi é o primário para o PREÇO SPOT (cotação corrente); yfinance é fallback do spot.
- Se uma fonte só der o adjusted close (split+div), usar reconstruct_traded_from_adjusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# --------------------------------------------------------------------------- #
# Funções puras (offline, testáveis)
# --------------------------------------------------------------------------- #


def split_adjust(
    raw_close: pd.Series, splits: list[tuple[pd.Timestamp | str, float]]
) -> pd.Series:
    """Ajusta uma série de close CRU apenas por split/grupamento.

    `splits`: lista de (data_ex_split, razao). Razão > 1 = desdobramento (preço cai),
    < 1 = grupamento (preço sobe). Cada evento divide os preços ANTERIORES à sua data
    pela razão (back-adjust), tornando a série contínua com o preço atual.
    """
    s = raw_close.sort_index()
    factor = pd.Series(1.0, index=s.index)
    for raw_date, ratio in splits:
        ex = pd.Timestamp(raw_date)
        factor.loc[s.index < ex] *= float(ratio)
    return s / factor


def reconstruct_traded_from_adjusted(
    adj_close: pd.Series, dividends: list[tuple[pd.Timestamp | str, float]]
) -> pd.Series:
    """Reconstrói a série negociada (ajustada só por split) a partir do adjusted close.

    Caminho B de docs/prices-methodology.md: desfaz o ajuste de dividendo. `dividends`:
    lista de (data_com, valor). Usa o fator padrão Yahoo/CRSP f_e = 1 - D_e/C_{e-1},
    resolvido pela recursão f_e = 1/(1 + D_e·CF[e]/adj[e-1]), varrendo as data-com da
    mais recente para a mais antiga.
    """
    s = adj_close.sort_index()
    evs = sorted((pd.Timestamp(d), float(v)) for d, v in dividends)

    cf_after = 1.0  # CF[e] = produto dos fatores das data-com POSTERIORES a e
    factor_by_exdate: dict[pd.Timestamp, float] = {}
    for ex_date, dividend in reversed(evs):
        prior = s.index[s.index < ex_date]
        if len(prior) == 0:
            factor_by_exdate[ex_date] = 1.0  # sem pregão anterior: não há o que desfazer
            continue
        adj_prev = float(s.loc[prior[-1]])
        if adj_prev <= 0:
            factor_by_exdate[ex_date] = 1.0
            continue
        f_e = 1.0 / (1.0 + dividend * cf_after / adj_prev)
        factor_by_exdate[ex_date] = f_e
        cf_after *= f_e

    cf = pd.Series(1.0, index=s.index)  # CF[t] = produto de f_e p/ data-com > t
    for ex_date, f_e in sorted(factor_by_exdate.items()):
        cf.loc[s.index < ex_date] *= f_e
    return s / cf


def annual_avg_price(close: pd.Series) -> pd.Series:
    """Preço médio por ano-calendário (insumo do DY histórico). Índice = ano (int)."""
    s = close.dropna()
    if s.empty:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime(s.index)
    return s.groupby(idx.year).mean().rename("preco_medio")


def price_to_book(current_price: float, vp_cota: float) -> float:
    """P/VP = preço atual ÷ valor patrimonial da cota. NaN se VP inválido."""
    if vp_cota is None or pd.isna(vp_cota) or vp_cota <= 0:
        return float("nan")
    return current_price / vp_cota


@dataclass
class PriceRecord:
    """Registro exportável por ticker."""

    ticker: str
    current_price: float | None
    as_of: str | None
    pvp: float | None
    annual_avg_price: dict[int, float] = field(default_factory=dict)
    source: str | None = None
    notes: list[str] = field(default_factory=list)


def build_price_record(
    ticker: str,
    close: pd.Series,
    *,
    vp_cota: float | None = None,
    current_price: float | None = None,
    source: str | None = None,
    notes: list[str] | None = None,
) -> PriceRecord:
    """Monta o registro de um ticker a partir da série canônica (split-adj, div-unadj).

    `close` deve estar ajustada SÓ por split. `current_price` default = último close.
    """
    notes = list(notes or [])
    s = close.dropna().sort_index()
    if current_price is None and not s.empty:
        current_price = float(s.iloc[-1])

    as_of = None
    if not s.empty:
        as_of = pd.Timestamp(s.index[-1]).date().isoformat()

    pvp = (
        price_to_book(current_price, vp_cota)
        if (current_price is not None and vp_cota is not None)
        else None
    )
    avg = {int(y): float(v) for y, v in annual_avg_price(s).items()}
    return PriceRecord(
        ticker=ticker,
        current_price=current_price,
        as_of=as_of,
        pvp=None if (pvp is not None and pd.isna(pvp)) else pvp,
        annual_avg_price=avg,
        source=source,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Acesso a rede (isolado, degradação graciosa)
# --------------------------------------------------------------------------- #


@dataclass
class FetchResult:
    """Resultado cru de um fetch. `close` já é split-adj/div-unadj quando possível."""

    ticker: str
    close: pd.Series
    current_price: float | None
    source: str
    splits: list[tuple[pd.Timestamp, float]] = field(default_factory=list)
    dividends: list[tuple[pd.Timestamp, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def market_symbol(ticker: str) -> str:
    """Sufixo de mercado B3 para o yfinance (ex.: PETR4 -> PETR4.SA)."""
    return ticker if ticker.endswith(".SA") else f"{ticker}.SA"


def fetch_yfinance(ticker: str, period: str = "5y") -> FetchResult | None:
    """Série histórica via yfinance. `Close` (auto_adjust=False) = split-adj/div-unadj.

    Retorna None se o yfinance não estiver instalado ou a rede falhar.
    """
    try:
        import yfinance as yf  # import tardio: dependência opcional em runtime
    except ImportError:
        return None
    try:
        sym = market_symbol(ticker)
        tk = yf.Ticker(sym)
        hist = tk.history(period=period, auto_adjust=False)
        if hist is None or hist.empty:
            return None
        close = hist["Close"].copy()
        close.index = pd.to_datetime(close.index).tz_localize(None)
        dividends = [
            (pd.Timestamp(d).tz_localize(None), float(v))
            for d, v in tk.dividends.items()
            if v > 0
        ]
        splits = [
            (pd.Timestamp(d).tz_localize(None), float(v))
            for d, v in tk.splits.items()
            if v > 0
        ]
        return FetchResult(
            ticker=ticker,
            close=close,
            current_price=float(close.iloc[-1]),
            source="yfinance",
            splits=splits,
            dividends=dividends,
            notes=["Close yfinance auto_adjust=False: ajustado por split, não por dividendo"],
        )
    except Exception:  # rede/parsing — degradar para fallback
        return None


def fetch_shares_outstanding(ticker: str) -> float | None:
    """Ações em circulação via yfinance — ÂNCORA para desambiguar a escala da CVM.

    Não é a fonte da contagem (essa é o composicao_capital da CVM); serve só para decidir
    se o número cru da CVM está em unidades ou milhares (ver fundamentos.resolve_share_scale).
    Retorna None se indisponível — o chamador sinaliza baixa confiança, não inventa.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(market_symbol(ticker)).info
        n = info.get("sharesOutstanding")
        return float(n) if n else None
    except Exception:
        return None


def fetch_brapi(
    ticker: str, *, token: str | None = None, range_: str = "3mo"
) -> FetchResult | None:
    """Preço spot (e série recente crua) via brapi. Primário para a cotação corrente.

    brapi entrega `close` cru (não ajustado). Sem eventos de split confiáveis na
    resposta básica, a série crua só é segura como spot/curto prazo — registramos isso
    em notes. A série histórica canônica vem do yfinance.
    """
    try:
        import requests
    except ImportError:
        return None
    try:
        url = f"https://brapi.dev/api/quote/{ticker}"
        params: dict[str, str] = {"range": range_, "interval": "1d"}
        if token:
            params["token"] = token
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return None
        r = results[0]
        current = r.get("regularMarketPrice")
        hist = r.get("historicalDataPrice") or []
        if hist:
            df = pd.DataFrame(hist)
            df["date"] = pd.to_datetime(df["date"], unit="s")
            close = df.set_index("date")["close"].astype("float64")
        else:
            close = pd.Series(dtype="float64")
        return FetchResult(
            ticker=ticker,
            close=close,
            current_price=float(current) if current is not None else None,
            source="brapi",
            notes=["brapi close é cru (não ajustado por split); usar como spot/curto prazo"],
        )
    except Exception:
        return None


def fetch_brapi_fund_list(
    subtype: str = "fi-agro", *, token: str | None = None
) -> list[dict] | None:
    """Lista os fundos negociados de um subtipo na B3 via brapi (ex.: 'fi-agro', 'fii').

    Devolve [{ticker, close, volume}, ...] ordenado por volume desc. É a fonte
    AUTORITATIVA do universo negociado (e do preço spot p/ P/VP) — o JOIN com a CVM é por
    ticker reconstruído do ISIN. Retorna None se a rede/dependência falhar (não inventa).
    """
    try:
        import requests
    except ImportError:
        return None
    try:
        params: dict[str, str] = {"type": "fund"}
        if token:
            params["token"] = token
        resp = requests.get("https://brapi.dev/api/quote/list", params=params, timeout=30)
        resp.raise_for_status()
        stocks = resp.json().get("stocks") or []
        out = [
            {
                "ticker": s.get("stock"),
                "close": s.get("close"),
                "volume": s.get("volume") or 0,
            }
            for s in stocks
            if s.get("subType") == subtype and s.get("stock")
        ]
        out.sort(key=lambda r: r["volume"], reverse=True)
        return out
    except Exception:
        return None


def fetch_canonical(ticker: str, *, brapi_token: str | None = None) -> FetchResult | None:
    """Orquestra: série canônica via yfinance; spot via brapi (primário) com fallback.

    Estratégia honesta com a metodologia:
    - série histórica (split-adj/div-unadj): yfinance.
    - preço spot: brapi primário; se falhar, usa o último close do yfinance.
    Se nada estiver disponível (offline), retorna None — não inventa cotação.
    """
    yf_res = fetch_yfinance(ticker)
    brapi_res = fetch_brapi(ticker, token=brapi_token)

    if yf_res is None and brapi_res is None:
        return None

    if yf_res is not None:
        # spot do brapi tem prioridade quando disponível
        if brapi_res is not None and brapi_res.current_price is not None:
            yf_res.current_price = brapi_res.current_price
            yf_res.source = "yfinance(série)+brapi(spot)"
        return yf_res

    # só brapi: série crua, sem ajuste de split garantido
    return brapi_res
