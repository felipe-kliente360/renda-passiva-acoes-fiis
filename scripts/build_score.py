#!/usr/bin/env python3
"""Score composto da short-list (Fase 4) a partir de data/fundamentos.json.

Lê os fundamentos já calculados (DY histórico/corrente, payout, recorrência, CAGR, flag
yield trap) e o ROE recente (lucro ÷ PL do último ano disponível), aplica a metodologia
TRAVADA de score (pipeline.score) e exporta data/score.json ranqueado. Puro sobre o
artefato — sem rede.

Uso:
    python scripts/build_score.py [--fundamentos data/fundamentos.json] [--out data/score]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.export import export_json, export_parquet  # noqa: E402
from pipeline.score import composite_score, rank  # noqa: E402


def _roe_recente(rec: dict) -> float | None:
    """ROE do último ano com lucro e PL disponíveis (lucro ÷ patrimônio líquido)."""
    lucro = rec.get("lucro_liquido_por_ano") or {}
    pl = rec.get("patrimonio_liquido_por_ano") or {}
    anos = sorted(set(map(int, lucro)) & set(map(int, pl)), reverse=True)
    for y in anos:
        plv = pl[str(y)] if str(y) in pl else pl.get(y)
        lv = lucro[str(y)] if str(y) in lucro else lucro.get(y)
        if plv and plv > 0:
            return lv / plv
    return None


def _payout_recente(rec: dict) -> float | None:
    pay = rec.get("payout_por_ano") or {}
    anos = sorted((int(y) for y, v in pay.items() if v is not None), reverse=True)
    if not anos:
        return None
    y = anos[0]
    return pay.get(str(y), pay.get(y))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fundamentos", type=Path, default=Path("data/fundamentos.json"))
    ap.add_argument("--out", type=Path, default=Path("data/score"))
    args = ap.parse_args()

    payload = json.loads(args.fundamentos.read_text(encoding="utf-8"))
    breakdowns = []
    for rec in payload.get("data", []):
        recur = rec.get("recorrencia") or {}
        bd = composite_score(
            rec["ticker"],
            years_paid=int(recur.get("years_paid", 0)),
            window=int(recur.get("window", 10)),
            current_dy=rec.get("dy_corrente"),
            hist_median=rec.get("dy_historico_mediana"),
            cagr=rec.get("crescimento_dps_cagr"),
            payout_recent=_payout_recente(rec),
            roe_recent=_roe_recente(rec),
            yield_trap=bool(rec.get("yield_trap")),
            min_years=int(recur.get("min_years", 8)),
            net_debt_ebitda=rec.get("divida_liquida_ebitda"),
        )
        breakdowns.append(bd)

    ranked = rank(breakdowns)
    # enriquece com alguns números do fundamento para a short-list ser legível
    by_tk = {r["ticker"]: r for r in payload.get("data", [])}
    for row in ranked:
        f = by_tk.get(row["ticker"], {})
        row["nome"] = f.get("nome")
        row["dy_corrente"] = f.get("dy_corrente")
        row["dy_mediana_hist"] = f.get("dy_historico_mediana")
        row["pvp"] = f.get("pvp")
        row["roe_recente"] = _roe_recente(f)
        row["divida_liquida_ebitda"] = f.get("divida_liquida_ebitda")

    meta = {"metodologia": "score 40/30/30 (recorrência/yield/crescimento) × sustentabilidade"}
    json_path = export_json(ranked, args.out.with_suffix(".json"), meta=meta)
    export_parquet(ranked, args.out.with_suffix(".parquet"))
    print("Short-list (rank — ticker — score):")
    for r in ranked:
        print(f"  {r['rank']:>2}. {r['ticker']:6} {r['score']:>5} "
              f"(rec={r['recurrence']} yld={r['yield']} grw={r['growth']} sus={r['sustainability']}"
              f"{' TRAP' if r['yield_trap'] else ''})")
    print(f"Escrito: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
