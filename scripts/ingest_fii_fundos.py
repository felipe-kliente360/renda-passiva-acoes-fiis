#!/usr/bin/env python3
"""FII estilo-ações: DY + projeção + saúde financeira + score (shortlist).

Eleva o FII ao mesmo patamar das ações: além do DY oficial (Percentual_Dividend_Yield_Mes),
agrega projeção (CAGR do DY sobre os anos completos) e saúde financeira no tempo
(alavancagem = passivo/PL, preservação da cota, taxa de administração) via aggregate_fund,
e aplica o score de fundos. Diferente do FIAgro, o FII tem ~5 anos de história: o baseline
do yield é o PRÓPRIO histórico do fundo (mediana dos anos completos) e o trap é per-fundo.

Exporta data/fii_fundos.json (métricas completas) + data/fii_score.json (shortlist
ranqueada). Sem rede em runtime do front.

Uso:
    python scripts/ingest_fii_fundos.py --start 2020 --end 2026 [--no-download]
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
from pipeline.fiagro import aggregate_fund  # noqa: E402
from pipeline.fii import DATASET, classify_fii_tipo, parse_fii_enriched  # noqa: E402
from pipeline.normalize import list_zip_members, read_cvm_csv_from_zip  # noqa: E402
from pipeline.score import fund_composite_score  # noqa: E402

DEFAULT_RAW = Path("data/raw")


def _complemento_member(zip_path: Path) -> str | None:
    return next(
        (m for m in list_zip_members(zip_path) if "complemento" in m and m.endswith(".csv")),
        None,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=2020)
    ap.add_argument("--end", type=int, default=2026)
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.yml"))
    ap.add_argument("--out", type=Path, default=Path("data/fii_fundos"))
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args()

    wl = yaml.safe_load(args.watchlist.read_text(encoding="utf-8"))
    fiis = [f for f in (wl.get("fiis") or []) if f.get("cnpj")]
    cnpjs = {f["cnpj"] for f in fiis}
    spec = load_columns_config()[DATASET]

    frames: list[pd.DataFrame] = []
    last_zip: Path | None = None
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
        parsed = parse_fii_enriched(read_cvm_csv_from_zip(zip_path, member), spec)
        frames.append(parsed[parsed["cnpj_fundo"].isin(cnpjs)])
        last_zip = zip_path
        print(f"[{year}] ok")

    allm = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["cnpj_fundo", "competencia", "dy_mes"])
    )

    # Classificação tijolo/papel/FoF pela composição do ativo (membro ativo_passivo do
    # informe mais recente). Lido uma vez; o tipo é estrutural, não muda mês a mês.
    ap_df = None
    if last_zip is not None:
        ap_member = next(
            (m for m in list_zip_members(last_zip)
             if "ativo_passivo" in m and m.endswith(".csv")), None
        )
        if ap_member:
            ap_df = read_cvm_csv_from_zip(last_zip, ap_member)

    def _latest(sub: pd.DataFrame, col: str):
        if col not in sub.columns:
            return None
        s = sub[col].dropna()
        return float(s.iloc[-1]) if not s.empty else None

    records = []
    for f in fiis:
        sub = allm[allm["cnpj_fundo"] == f["cnpj"]].sort_values("competencia")
        agg = aggregate_fund(sub)
        tipo = classify_fii_tipo(ap_df, f["cnpj"]) if ap_df is not None else None
        cotistas = _latest(sub, "numero_cotistas")
        records.append({"ticker": f["ticker"], "nome": f.get("nome"), "cnpj": f["cnpj"],
                        "tipo": tipo, "num_cotistas": int(cotistas) if cotistas else None,
                        "amortizacao_recente": _latest(sub, "amortizacao_mes"), **agg})

    meta = {
        "fonte": "CVM INF_MENSAL FII (Percentual_Dividend_Yield_Mes + saúde patrimonial)",
        "baseline_yield": "histórico do próprio fundo (mediana dos anos completos)",
    }
    json_path = export_json(records, args.out.with_suffix(".json"), meta=meta)
    export_parquet(records, args.out.with_suffix(".parquet"))

    # P/VP do pipeline de preços (Fase 1), por ticker — sinal de valuation na shortlist.
    pvp_by_ticker: dict[str, float] = {}
    prices_path = args.out.parent / "prices.json"
    if prices_path.exists():
        import json

        for p in json.loads(prices_path.read_text(encoding="utf-8")).get("data", []):
            if p.get("pvp") is not None:
                pvp_by_ticker[p["ticker"]] = p["pvp"]

    # Score de fundos: baseline = mediana histórica do PRÓPRIO fundo (FII tem ~5 anos).
    rows: list[dict] = []
    for r in records:
        bd = fund_composite_score(
            r["ticker"],
            months_paid_12m=int(r.get("meses_com_pagamento_12m") or 0),
            dy_ttm=r.get("dy_ttm"),
            dy_baseline=r.get("dy_mediana"),
            crescimento=r.get("crescimento"),
            leverage=r.get("alavancagem"),
            vp_cota_var=r.get("vp_cota_var"),
            taxa_admin_aa=r.get("taxa_admin_aa"),
            yield_trap=bool(r.get("yield_trap")),
            months_window=min(12, int(r.get("meses_disponiveis") or 12)),
        )
        rows.append({
            "ticker": r["ticker"], "nome": r.get("nome"), "score": bd.score,
            "tipo": r.get("tipo"),
            "recurrence": bd.recurrence, "yield": bd.yield_, "growth": bd.growth,
            "sustainability": bd.sustainability, "yield_trap": bd.yield_trap,
            "dy_ttm": r.get("dy_ttm"), "dy_mediana": r.get("dy_mediana"),
            "pvp": pvp_by_ticker.get(r["ticker"]), "alavancagem": r.get("alavancagem"),
            "vp_cota_var": r.get("vp_cota_var"), "meses_disponiveis": r.get("meses_disponiveis"),
            "num_cotistas": r.get("num_cotistas"),
            "amortizacao_recente": r.get("amortizacao_recente"),
            "crescimento": r.get("crescimento"), "crescimento_base": r.get("crescimento_base"),
        })
    rows.sort(key=lambda x: x["score"], reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    score_path = export_json(
        rows, args.out.parent / "fii_score.json",
        meta={"metodologia": "score de fundos 40/30/30 × sustentabilidade (alavancagem/cota/taxa)",
              **meta},
    )
    export_parquet(rows, args.out.parent / "fii_score.parquet")

    print("\nShortlist FII (rank — ticker — score — DY TTM — mediana — cresc):")
    for row in rows:
        ttm = f"{row['dy_ttm'] * 100:.1f}%" if row.get("dy_ttm") is not None else "—"
        med = f"{row['dy_mediana'] * 100:.1f}%" if row.get("dy_mediana") is not None else "—"
        cr = f"{row['crescimento'] * 100:+.1f}%" if row.get("crescimento") is not None else "—"
        print(f"  {row['rank']:>2}. {row['ticker']:7} {row['score']:>5}  DY_TTM={ttm:>7}  "
              f"mediana={med:>7}  cresc={cr:>7}{'  TRAP' if row['yield_trap'] else ''}")
    print(f"Escrito: {json_path} e {score_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
