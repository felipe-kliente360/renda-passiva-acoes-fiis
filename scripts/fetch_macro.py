#!/usr/bin/env python3
"""Snapshot macro (BCB/SGS) → data/macro.json.

Camada de CONTEXTO (juros/inflação) para o spread sobre CDI dos fundos de recebíveis e
para qualificar o crescimento do DY. Aditiva — não altera a metodologia de DY. Sem rede
no runtime do front.

Uso:
    python scripts/fetch_macro.py [--out data/macro.json]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.export import export_json  # noqa: E402
from pipeline.macro import fetch_macro_snapshot  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("data/macro.json"))
    args = ap.parse_args()

    snap = fetch_macro_snapshot()
    if snap is None:
        print("Macro indisponível (rede?); mantendo artefato anterior se existir.",
              file=sys.stderr)
        return 0 if args.out.exists() else 1

    # export_json espera uma lista de registros; macro é um snapshot único.
    export_json([snap], args.out, meta={"fonte": "BCB/SGS (CDI 12m, Selic meta, IPCA 12m)"})
    pct = lambda v: f"{v * 100:.2f}%" if v is not None else "—"  # noqa: E731
    print(f"Macro: CDI 12m={pct(snap['cdi_12m'])}  Selic={pct(snap['selic_meta'])}  "
          f"IPCA 12m={pct(snap['ipca_12m'])}  (as_of {snap.get('as_of')})")
    print(f"Escrito: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
