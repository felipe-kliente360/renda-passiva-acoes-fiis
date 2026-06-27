#!/usr/bin/env python3
"""DY de FII (rendimentos) via CVM INF_MENSAL — oficial, por competência.

Usa o DY MENSAL publicado no informe (Percentual_Dividend_Yield_Mes, complemento): baixa
os informes do intervalo, acumula o DY mensal por fundo da watchlist e agrega em TTM
(soma dos 12 meses), histórico anual, mediana/média e flag de yield trap. Exporta
data/fii_dy.json por ticker. Sem rede em runtime do front.

Uso:
    python scripts/ingest_fii_dy.py --start 2020 --end 2026 [--out data/fii_dy]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.columns import load_columns_config  # noqa: E402
from pipeline.cvm import download_fii_inf_mensal  # noqa: E402
from pipeline.export import export_json, export_parquet  # noqa: E402
from pipeline.fii import DATASET, aggregate_fii_dy, dy_mensal_por_fundo  # noqa: E402
from pipeline.normalize import list_zip_members, read_cvm_csv_from_zip  # noqa: E402

DEFAULT_RAW = Path("data/raw")


def _complemento_member(zip_path: Path) -> str | None:
    return next(
        (m for m in list_zip_members(zip_path) if "complemento" in m and m.endswith(".csv")),
        None,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.yml"))
    ap.add_argument("--out", type=Path, default=Path("data/fii_dy"))
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args()

    wl = yaml.safe_load(args.watchlist.read_text(encoding="utf-8"))
    fiis = [f for f in (wl.get("fiis") or []) if f.get("cnpj")]
    cnpjs = {f["cnpj"] for f in fiis}
    spec = load_columns_config()[DATASET]

    frames: list[pd.DataFrame] = []
    for year in range(args.start, args.end + 1):
        zip_path = DEFAULT_RAW / f"inf_mensal_fii_{year}.zip"
        if not args.no_download and not zip_path.exists():
            try:
                zip_path = download_fii_inf_mensal(year)
            except Exception as e:
                print(f"[{year}] download falhou ({e}); pulando.", file=sys.stderr)
                continue
        if not zip_path.exists():
            continue
        member = _complemento_member(zip_path)
        if not member:
            continue
        monthly = dy_mensal_por_fundo(read_cvm_csv_from_zip(zip_path, member), spec)
        frames.append(monthly[monthly["cnpj_fundo"].isin(cnpjs)])
        print(f"[{year}] ok")

    allm = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["cnpj_fundo", "competencia", "dy_mes"]
    )

    records = []
    for f in fiis:
        sub = allm[allm["cnpj_fundo"] == f["cnpj"]]
        agg = aggregate_fii_dy(sub)
        records.append({"ticker": f["ticker"], "nome": f.get("nome"),
                        "cnpj": f["cnpj"], **agg})

    json_path = export_json(records, args.out.with_suffix(".json"),
                            meta={"fonte": "CVM INF_MENSAL (Percentual_Dividend_Yield_Mes)"})
    export_parquet(records, args.out.with_suffix(".parquet"))
    print("DY de FII (ticker — TTM — mediana — trap):")
    for r in records:
        ttm = f"{r['dy_ttm'] * 100:.1f}%" if r["dy_ttm"] is not None else "—"
        med = f"{r['dy_mediana'] * 100:.1f}%" if r["dy_mediana"] is not None else "—"
        print(f"  {r['ticker']:7} TTM={ttm:>7}  mediana={med:>7}"
              f"  {'TRAP' if r['yield_trap'] else ''}")
    print(f"Escrito: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
