#!/usr/bin/env python3
"""Entry point do pipeline de preços (Fase 1).

Uso:
    python scripts/fetch_prices.py [--watchlist config/watchlist.yml]
                                   [--fii-vp data/fii_vp.json]
                                   [--out data/prices]

Para cada ticker da watchlist: baixa a série canônica (split-adj/div-unadj), calcula
preço atual, P/VP (para FIIs com VP do informe CVM) e preço médio anual; exporta
JSON+Parquet. Rede isolada em pipeline.prices; se offline, registra o ticker como
indisponível em vez de inventar cotação.

BRAPI_TOKEN pode ser passado via env para ranges maiores na brapi.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.export import export_json, export_parquet  # noqa: E402
from pipeline.prices import build_price_record, fetch_canonical  # noqa: E402


def load_watchlist(path: Path) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items: list[dict] = []
    for tipo, entries in raw.items():
        for e in entries or []:
            items.append({**e, "tipo": tipo.rstrip("s")})  # acoes->acao, fiis->fii
    return items


def load_fii_vp(path: Path | None) -> dict[str, float]:
    """Mapa cnpj_fundo -> VP da cota, a partir do export da ingestão de FII."""
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {r["cnpj_fundo"]: r["valor_patrimonial_cota"] for r in payload.get("data", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.yml"))
    ap.add_argument("--fii-vp", type=Path, default=Path("data/fii_vp.json"))
    ap.add_argument("--out", type=Path, default=Path("data/prices"))
    args = ap.parse_args()

    watchlist = load_watchlist(args.watchlist)
    vp_by_cnpj = load_fii_vp(args.fii_vp)
    token = os.environ.get("BRAPI_TOKEN")

    records = []
    unavailable: list[str] = []
    for item in watchlist:
        ticker = item["ticker"]
        res = fetch_canonical(ticker, brapi_token=token)
        if res is None:
            unavailable.append(ticker)
            continue
        cnpj = item.get("cnpj")
        vp = vp_by_cnpj.get(cnpj) if cnpj else None
        rec = build_price_record(
            ticker,
            res.close,
            vp_cota=vp,
            current_price=res.current_price,
            source=res.source,
            notes=res.notes,
        )
        record = {
            "ticker": rec.ticker,
            "tipo": item.get("tipo"),
            "nome": item.get("nome"),
            "current_price": rec.current_price,
            "as_of": rec.as_of,
            "pvp": rec.pvp,
            "annual_avg_price": rec.annual_avg_price,
            "source": rec.source,
            "notes": rec.notes,
        }
        records.append(record)

    meta = {"unavailable": unavailable, "watchlist_size": len(watchlist)}
    json_path = export_json(records, args.out.with_suffix(".json"), meta=meta)
    export_parquet(records, args.out.with_suffix(".parquet"))
    print(f"Tickers exportados: {len(records)}; indisponíveis: {unavailable}")
    print(f"Escrito: {json_path}")
    if not records:
        print(
            "Nenhum preço obtido (provável ausência de rede). Rode localmente:\n"
            "  pip install -e .[prices]\n"
            "  python scripts/fetch_prices.py",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
