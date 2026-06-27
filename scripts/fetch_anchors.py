#!/usr/bin/env python3
"""Coleta a âncora de escala (yfinance sharesOutstanding) das ações da watchlist.

Por quê um script SÓ pra isso: o ambiente que alcança a CVM (gera fundamentos) NÃO
alcança o Yahoo, e o runner do GitHub é o inverso — alcança o Yahoo mas NÃO a CVM
(dados.cvm.gov.br → Network is unreachable). Então a âncora é coletada onde o yfinance
funciona (GH) e cacheada em config/shares_anchor.yml; os fundamentos são gerados onde a
CVM funciona, lendo esse cache. Ver fundamentos.resolve_share_scale e o guard em
scripts/ingest_fundamentos.py.

Uso:
    python scripts/fetch_anchors.py [--watchlist config/watchlist.yml]
                                    [--out config/shares_anchor.yml]

MERGE, não sobrescreve: preserva âncoras existentes; só atualiza/insere as que o
yfinance devolveu agora. Ticker sem resposta é deixado como está (nunca zera).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.prices import fetch_shares_outstanding  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.yml"))
    ap.add_argument("--out", type=Path, default=Path("config/shares_anchor.yml"))
    args = ap.parse_args()

    raw = yaml.safe_load(args.watchlist.read_text(encoding="utf-8"))
    tickers = [e["ticker"] for e in (raw.get("acoes") or [])]

    existing: dict = {}
    if args.out.exists():
        existing = yaml.safe_load(args.out.read_text(encoding="utf-8")) or {}
    anchors: dict = dict(existing.get("acoes") or {})

    updated, missing = [], []
    for tk in tickers:
        n = fetch_shares_outstanding(tk)
        if n:
            anchors[tk] = int(n)
            updated.append(f"{tk}={int(n)}")
        else:
            missing.append(tk)
            if tk not in anchors:
                print(f"  {tk}: sem âncora (yfinance vazio) — fica N/A nos fundamentos")

    header = (
        "# Âncora de ações em circulação (sharesOutstanding) — CACHE para desambiguar a\n"
        "# escala caótica da CVM (`composicao_capital` mistura unidades × milhares). A CVM\n"
        "# continua sendo a CONTAGEM; esta âncora só decide a UNIDADE (×1 vs ×1000), via\n"
        "# fundamentos.resolve_share_scale. Sem âncora E sem yfinance, o pipeline marca\n"
        "# DY/P-VP como N/A (não inventa escala — ver guard em scripts/ingest_fundamentos).\n"
        "#\n"
        "# GERADO por scripts/fetch_anchors.py (workflow anchors.yml, roda no GH onde o\n"
        "# yfinance funciona). MERGE: tickers sem resposta preservam o valor anterior.\n"
    )
    body = yaml.safe_dump(
        {"acoes": dict(sorted(anchors.items()))}, allow_unicode=True, sort_keys=False
    )
    args.out.write_text(header + body, encoding="utf-8")

    print(f"Âncoras atualizadas ({len(updated)}): {', '.join(updated) or '—'}")
    if missing:
        print(f"Sem resposta do yfinance ({len(missing)}): {', '.join(missing)}")
    print(f"Escrito: {args.out} ({len(anchors)} tickers no total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
