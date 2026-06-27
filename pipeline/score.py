"""Score composto da short-list — metodologia TRAVADA (pesos equilibrados).

Pergunta-guia: "isto paga, e vai continuar pagando?". O score NÃO premia o maior yield
do trimestre — premia o fluxo que se sustenta. Componentes (cada um 0..1):

- Recorrência/segurança do pagamento — peso 40%
- Yield atual vs. baseline histórico — peso 30% (penaliza tanto o yield baixo quanto o
  yield trap: corrente muito acima da mediana ⇒ provável armadilha)
- Crescimento do dividendo (CAGR do DPS) — peso 30%

Sobre isso aplica-se um MULTIPLICADOR de sustentabilidade (0.5..1.0): payout saudável
(30–80%), recorrência (≥8/10 anos) e ROE positivo. O flag de yield trap corta o score.
Dívida líquida/EBITDA fica para quando a ingestão trouxer dívida/EBITDA (BPP/DRE).

Tudo puro e offline. Constantes espelham CLAUDE.md.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

W_RECURRENCE = 0.40
W_YIELD = 0.30
W_GROWTH = 0.30

PAYOUT_MIN = 0.30
PAYOUT_MAX = 0.80
LEVERAGE_MAX = 3.0         # dívida líquida/EBITDA acima disso pesa na sustentabilidade
YIELD_TRAP_PENALTY = 0.70  # multiplica o score quando o yield trap dispara


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _isnum(x: object) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def recurrence_score(years_paid: int, window: int = 10) -> float:
    """Fração dos anos da janela em que pagou (proxy de segurança/recorrência)."""
    if not window:
        return 0.0
    return _clamp(years_paid / window)


def yield_score(current_dy: float | None, hist_median: float | None) -> float:
    """Yield atual vs. baseline histórico.

    Cresce até o yield corrente alcançar ~1,5× a mediana (bom ponto de entrada), e DECAI
    acima disso (zona de yield trap). Abaixo da mediana, premia parcialmente. Sem baseline
    utilizável, fica neutro (0,5).
    """
    if not _isnum(current_dy) or not _isnum(hist_median) or hist_median <= 0:
        return 0.5
    r = current_dy / hist_median
    if r <= 1.0:
        return _clamp(0.4 + 0.6 * r)          # 0→0.4 .. 1.0→1.0
    if r <= 1.5:
        return 1.0                            # faixa boa: acima da baseline, ainda saudável
    return _clamp(1.0 - (r - 1.5) / 1.5)      # 1.5→1.0 .. 3.0→0.0 (trap)


def growth_score(cagr: float | None) -> float:
    """CAGR do DPS mapeado a 0..1: ≤−10%→0, 0%→0.5, ≥+15%→1 (linear por trecho)."""
    if not _isnum(cagr):
        return 0.5
    if cagr <= -0.10:
        return 0.0
    if cagr <= 0.0:
        return _clamp(0.5 + cagr / 0.10 * 0.5)   # -0.10→0 .. 0→0.5
    return _clamp(0.5 + cagr / 0.15 * 0.5)       # 0→0.5 .. 0.15→1.0


def sustainability_multiplier(
    payout_recent: float | None,
    years_paid: int,
    window: int = 10,
    min_years: int = 8,
    roe_recent: float | None = None,
    net_debt_ebitda: float | None = None,
) -> float:
    """Multiplicador 0.5..1.0 de sustentabilidade do pagamento.

    Parte de 1.0 e desconta: payout fora de 30–80%, recorrência abaixo de ≥min_years/window,
    ROE não-positivo e alavancagem alta (dívida líq./EBITDA > LEVERAGE_MAX). Cada falha custa
    ~0.15. Alavancagem N/A (banco) não penaliza. Piso 0.5 (não zera por um único critério).
    """
    m = 1.0
    if _isnum(payout_recent) and not (PAYOUT_MIN <= payout_recent <= PAYOUT_MAX):
        m -= 0.15
    if years_paid < min_years:
        m -= 0.15
    if _isnum(roe_recent) and roe_recent <= 0:
        m -= 0.15
    if _isnum(net_debt_ebitda) and net_debt_ebitda > LEVERAGE_MAX:
        m -= 0.15
    return _clamp(m, 0.5, 1.0)


# Sustentabilidade de FUNDOS (FII/FIAgro): payout/ROE/dívida-EBITDA das ações não se
# aplicam. A "solidez de saúde financeira no tempo" da tese vira: alavancagem baixa,
# cota que não derrete, taxa de administração razoável e recorrência do pagamento.
FUND_LEVERAGE_MAX = 0.50      # passivo / PL acima disso pesa (fundo muito alavancado)
FUND_VP_DROP_MAX = -0.05      # queda do VP da cota no período pior que -5% = capital derretendo
FUND_FEE_MAX = 0.020          # taxa de administração anualizada acima de 2% a.a. = drag alto
FUND_MIN_MONTHS_PAID = 10     # pagar em <10 dos últimos 12 meses fere a recorrência


def fund_sustainability_multiplier(
    *,
    leverage: float | None = None,
    vp_cota_var: float | None = None,
    taxa_admin_aa: float | None = None,
    months_paid_12m: int | None = None,
) -> float:
    """Multiplicador 0.5..1.0 de sustentabilidade para FUNDOS (FII/FIAgro).

    Parte de 1.0 e desconta ~0.12 por falha: alavancagem (passivo/PL) alta, VP da cota
    derretendo, taxa de administração elevada e recorrência baixa de pagamento. Métricas
    ausentes (None) não penalizam — honesto com histórico curto. Piso 0.5.
    """
    m = 1.0
    if _isnum(leverage) and leverage > FUND_LEVERAGE_MAX:
        m -= 0.12
    if _isnum(vp_cota_var) and vp_cota_var < FUND_VP_DROP_MAX:
        m -= 0.12
    if _isnum(taxa_admin_aa) and taxa_admin_aa > FUND_FEE_MAX:
        m -= 0.12
    if months_paid_12m is not None and months_paid_12m < FUND_MIN_MONTHS_PAID:
        m -= 0.12
    return _clamp(m, 0.5, 1.0)


def fund_composite_score(
    ticker: str,
    *,
    months_paid_12m: int,
    dy_ttm: float | None,
    dy_baseline: float | None,
    crescimento: float | None,
    leverage: float | None = None,
    vp_cota_var: float | None = None,
    taxa_admin_aa: float | None = None,
    yield_trap: bool = False,
) -> ScoreBreakdown:
    """Score composto de FUNDO (mesma metodologia 40/30/30 × sustentabilidade das ações).

    Recorrência = meses pagando nos últimos 12 (janela de 12). Yield = DY TTM vs baseline
    (mediana de anos completos ou média mensal anualizada). Crescimento = CAGR/tendência do
    DY. Multiplicador de sustentabilidade adaptado a fundos. Corte por yield trap.
    """
    rec = recurrence_score(months_paid_12m, window=12)
    yld = yield_score(dy_ttm, dy_baseline)
    grw = growth_score(crescimento)
    sustain = fund_sustainability_multiplier(
        leverage=leverage,
        vp_cota_var=vp_cota_var,
        taxa_admin_aa=taxa_admin_aa,
        months_paid_12m=months_paid_12m,
    )
    base = W_RECURRENCE * rec + W_YIELD * yld + W_GROWTH * grw
    score = base * sustain
    if yield_trap:
        score *= YIELD_TRAP_PENALTY
    return ScoreBreakdown(
        ticker=ticker,
        score=round(100 * _clamp(score), 1),
        recurrence=round(rec, 3),
        yield_=round(yld, 3),
        growth=round(grw, 3),
        sustainability=round(sustain, 3),
        yield_trap=yield_trap,
    )


@dataclass(frozen=True)
class ScoreBreakdown:
    ticker: str
    score: float                  # 0..100
    recurrence: float
    yield_: float
    growth: float
    sustainability: float
    yield_trap: bool


def composite_score(
    ticker: str,
    *,
    years_paid: int,
    window: int,
    current_dy: float | None,
    hist_median: float | None,
    cagr: float | None,
    payout_recent: float | None,
    roe_recent: float | None,
    yield_trap: bool,
    min_years: int = 8,
    net_debt_ebitda: float | None = None,
) -> ScoreBreakdown:
    """Combina os componentes (40/30/30) × sustentabilidade, com corte por yield trap."""
    rec = recurrence_score(years_paid, window)
    yld = yield_score(current_dy, hist_median)
    grw = growth_score(cagr)
    sustain = sustainability_multiplier(
        payout_recent, years_paid, window, min_years, roe_recent, net_debt_ebitda
    )
    base = W_RECURRENCE * rec + W_YIELD * yld + W_GROWTH * grw
    score = base * sustain
    if yield_trap:
        score *= YIELD_TRAP_PENALTY
    return ScoreBreakdown(
        ticker=ticker,
        score=round(100 * _clamp(score), 1),
        recurrence=round(rec, 3),
        yield_=round(yld, 3),
        growth=round(grw, 3),
        sustainability=round(sustain, 3),
        yield_trap=yield_trap,
    )


def rank(breakdowns: list[ScoreBreakdown]) -> list[dict]:
    """Ordena por score desc e devolve dicts prontos para export (com posição)."""
    ordered = sorted(breakdowns, key=lambda b: b.score, reverse=True)
    out = []
    for i, b in enumerate(ordered, start=1):
        d = asdict(b)
        d["yield"] = d.pop("yield_")  # nome amigável no JSON
        d["rank"] = i
        out.append(d)
    return out
