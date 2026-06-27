#!/usr/bin/env python3
"""Vacância e inadimplência de FII de tijolo via FNET (Informe Trimestral Estruturado).

A CVM aberta não traz vacância — ela vive no FNET (B3). Para cada FII da watchlist, busca o
último Informe Trimestral, extrai a vacância/inadimplência por imóvel e agrega no nível do
fundo (ponderado pela receita). Exporta data/fii_vacancia.json.

Cobertura PARCIAL e honesta: o FNET é lento/instável e o layout varia por administrador —
FIIs de papel (sem imóveis) e os que não parseiam ficam de fora (N/A), não inventa.

Uso:
    python scripts/ingest_fii_vacancia.py [--out data/fii_vacancia.json]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.export import export_json  # noqa: E402
from pipeline.fnet import fetch_vacancia  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.yml"))
    ap.add_argument("--out", type=Path, default=Path("data/fii_vacancia.json"))
    args = ap.parse_args()

    wl = yaml.safe_load(args.watchlist.read_text(encoding="utf-8"))
    fiis = [f for f in (wl.get("fiis") or []) if f.get("cnpj")]

    records = []
    for f in fiis:
        v = fetch_vacancia(f["cnpj"])
        if v is None:
            print(f"  {f['ticker']:8} — sem vacância (papel, ou não parseou/rede)")
            continue
        rec = {"ticker": f["ticker"], "cnpj": f["cnpj"], **v}
        records.append(rec)
        vac = f"{rec['vacancia'] * 100:.2f}%" if rec.get("vacancia") is not None else "—"
        inad = (
            f"{rec['inadimplencia'] * 100:.2f}%" if rec.get("inadimplencia") is not None else "—"
        )
        print(f"  {f['ticker']:8} vacância={vac:>7} inadimpl={inad:>7} "
              f"imóveis={rec.get('n_imoveis')} ({rec.get('data_ref')})")

    meta = {
        "fonte": "FNET (B3) — Informe Trimestral Estruturado (ANEXO 39-II)",
        "metrica": "vacância e inadimplência do fundo, ponderadas pela receita dos imóveis",
        "cobertura": "parcial: só FII de tijolo cujo informe parseia; papel/falha = ausente",
    }
    json_path = export_json(records, args.out, meta=meta)
    print(f"\nFIIs com vacância: {len(records)}/{len(fiis)}. Escrito: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
