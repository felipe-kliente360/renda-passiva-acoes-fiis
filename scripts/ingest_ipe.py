#!/usr/bin/env python3
"""Fatos relevantes da watchlist via IPE-RAD da CVM (Fase 7).

Baixa o índice IPE (documentos protocolados) dos anos do intervalo, filtra os papéis da
watchlist (ações, por CD_CVM) e as categorias relevantes para a tese de renda passiva
(fatos relevantes, avisos aos acionistas, relatórios de proventos), e exporta os mais
recentes com link para o RAD. Só o ÍNDICE — não lê o corpo dos PDFs. Sem rede no front.

Uso:
    python scripts/ingest_ipe.py [--start 2025] [--end 2026] [--out data/fatos_relevantes]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.columns import load_columns_config  # noqa: E402
from pipeline.cvm import download_ipe  # noqa: E402
from pipeline.export import export_json, export_parquet  # noqa: E402
from pipeline.ipe import DATASET, fatos_relevantes, parse_ipe  # noqa: E402
from pipeline.normalize import list_zip_members, read_cvm_csv_from_zip  # noqa: E402

DEFAULT_RAW = Path("data/raw")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=2025)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.yml"))
    ap.add_argument("--limit", type=int, default=8, help="máx. de itens por empresa")
    ap.add_argument("--out", type=Path, default=Path("data/fatos_relevantes"))
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args()
    from datetime import date

    end = args.end or date.today().year

    wl = yaml.safe_load(args.watchlist.read_text(encoding="utf-8"))
    acoes = [a for a in (wl.get("acoes") or []) if a.get("cd_cvm")]
    # CD_CVM da watchlist sem zeros à esquerda (chave de JOIN com o IPE).
    cd_to_ticker = {a["cd_cvm"].lstrip("0"): a["ticker"] for a in acoes}
    cds = set(cd_to_ticker)
    spec = load_columns_config()[DATASET]

    frames: list[pd.DataFrame] = []
    for year in range(args.start, end + 1):
        zip_path = DEFAULT_RAW / f"ipe_cia_aberta_{year}.zip"
        if not args.no_download and not zip_path.exists():
            try:
                zip_path = download_ipe(year)
            except Exception as e:
                print(f"[{year}] download falhou ({e}); pulando.", file=sys.stderr)
                continue
        if not zip_path.exists():
            continue
        member = next(
            (m for m in list_zip_members(zip_path) if m.endswith(".csv")), None
        )
        if not member:
            continue
        parsed = parse_ipe(read_cvm_csv_from_zip(zip_path, member), spec)
        frames.append(parsed[parsed["cd_cvm"].isin(cds)])
        print(f"[{year}] ok ({len(frames[-1])} docs da watchlist)")

    allm = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["cd_cvm", "data", "categoria"]
    )
    records = fatos_relevantes(allm, cds, limit_por_empresa=args.limit)
    # anexa o ticker (mais legível que o CD_CVM no front)
    for r in records:
        r["ticker"] = cd_to_ticker.get(r["cd_cvm"])

    meta = {
        "fonte": "CVM IPE (ipe_cia_aberta) — índice de documentos protocolados (RAD)",
        "categorias": "fato relevante, aviso aos acionistas, relatório de proventos",
        "escopo": f"watchlist de ações ({len(cds)} empresas), {args.start}–{end}",
    }
    json_path = export_json(records, args.out.with_suffix(".json"), meta=meta)
    export_parquet(records, args.out.with_suffix(".parquet"))

    print(f"\nFatos relevantes da watchlist: {len(records)} docs")
    for r in records[:12]:
        print(f"  {r['data']}  {r.get('ticker') or r['cd_cvm']:6}  {r['categoria'][:22]:22}  "
              f"{(r['assunto'] or '')[:45]}")
    print(f"Escrito: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
