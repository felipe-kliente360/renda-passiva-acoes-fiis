#!/usr/bin/env python3
"""FIAgro: DY de rendimentos + saúde financeira + shortlist (estilo-ações).

Universo AUTO-DETECTADO (decisão do Felipe): os FIAgros negociados na B3 vêm da lista
fi-agro da brapi (com volume = liquidez e close = spot p/ P/VP); o JOIN com o informe
mensal da CVM é por ticker reconstruído do ISIN da cota. Não inventa tickers nem fundos.

Para cada FIAgro negociado, agrega a série mensal da CVM (DY TTM/baseline, recorrência,
projeção, alavancagem, preservação da cota, taxa de adm) e aplica o score de fundos.
Exporta data/fiagro.json (métricas completas) e data/fiagro_score.json (shortlist).

Histórico do FIAgro começa em 2025-05 (~1 ano): os artefatos são honestos sobre isso
(meses_disponiveis, base do crescimento). Sem rede em runtime do front.

Uso:
    python scripts/ingest_fiagro.py [--start 202505] [--end 202606] [--no-download]
                                    [--min-cotistas 1000] [--out data/fiagro]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import median

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.columns import load_columns_config  # noqa: E402
from pipeline.cvm import (  # noqa: E402
    download_fiagro_inf_mensal,
    iter_fiagro_periods,
)
from pipeline.export import export_json, export_parquet  # noqa: E402
from pipeline.fiagro import (  # noqa: E402
    DATASET,
    aggregate_fund,
    credit_profile,
    parse_fiagro_inf_mensal,
)
from pipeline.normalize import read_cvm_csv_from_zip  # noqa: E402
from pipeline.prices import fetch_brapi_fund_list, price_to_book  # noqa: E402
from pipeline.score import fund_composite_score  # noqa: E402

DEFAULT_RAW = Path("data/raw")
MIN_MESES_RANK = 6     # história mínima p/ entrar na shortlist ranqueada
CONF_DAMPER = 0.60     # amortecedor de score p/ DY de baixa confiança (placeholder constante)


def _period_arg(s: str) -> tuple[int, int]:
    """'202505' -> (2025, 5)."""
    return int(s[:4]), int(s[4:6])


def _main_member(zip_path: Path) -> str | None:
    """O CSV principal do ZIP (ignora o `_subclasse_`)."""
    from pipeline.normalize import list_zip_members

    return next(
        (
            m
            for m in list_zip_members(zip_path)
            if m.endswith(".csv") and "subclasse" not in m
        ),
        None,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=_period_arg, default=(2025, 5))
    ap.add_argument("--end", type=_period_arg, default=None)
    ap.add_argument("--min-cotistas", type=int, default=500,
                    help="piso de cotistas p/ considerar negociado de fato (default 500)")
    ap.add_argument("--out", type=Path, default=Path("data/fiagro"))
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args()

    spec = load_columns_config()[DATASET]

    # 1) Universo negociado + spot, da brapi (autoritativo).
    fund_list = fetch_brapi_fund_list("fi-agro") or []
    by_ticker = {f["ticker"]: f for f in fund_list}
    traded = set(by_ticker)
    print(f"brapi fi-agro negociados: {len(traded)}")

    # 2) Série mensal da CVM (todos os meses do intervalo), só FIAgros negociados.
    frames: list[pd.DataFrame] = []
    for year, month in iter_fiagro_periods(args.start, args.end):
        zip_path = DEFAULT_RAW / f"inf_mensal_fiagro_{year}{month:02d}.zip"
        if not args.no_download and not zip_path.exists():
            try:
                zip_path = download_fiagro_inf_mensal(year, month)
            except Exception as e:
                print(f"[{year}{month:02d}] download falhou ({e}); pulando.", file=sys.stderr)
                continue
        if not zip_path.exists():
            continue
        member = _main_member(zip_path)
        if not member:
            continue
        parsed = parse_fiagro_inf_mensal(read_cvm_csv_from_zip(zip_path, member), spec)
        frames.append(parsed[parsed["ticker"].isin(traded)])
        print(f"[{year}{month:02d}] ok ({len(frames[-1])} negociados)")

    allm = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["ticker", "cnpj_fundo", "competencia"])
    )

    # 3) Resolve multi-classe: por ticker, fica a classe (CNPJ) com mais cotistas.
    records = []
    for ticker, grp in allm.groupby("ticker"):
        cnpjs = grp.groupby("cnpj_fundo")["numero_cotistas"].max()
        cnpj = cnpjs.idxmax() if not cnpjs.empty else None
        sub = grp[grp["cnpj_fundo"] == cnpj].sort_values("competencia")
        agg = aggregate_fund(sub)
        prof = credit_profile(sub)  # tipo (crédito/terras) + inadimplência + diversificação
        cotistas = agg.get("num_cotistas") or 0
        if cotistas < args.min_cotistas:
            continue  # fundo registrado mas sem dispersão real -> fora da shortlist
        spot = by_ticker.get(ticker, {})
        pvp = price_to_book(spot.get("close"), agg.get("vp_cota_atual")) \
            if spot.get("close") and agg.get("vp_cota_atual") else None
        records.append({
            "ticker": ticker,
            "nome": (sub["nome"].dropna().iloc[-1] if sub["nome"].notna().any() else None),
            "cnpj": cnpj,
            "volume_brapi": spot.get("volume"),
            "preco": spot.get("close"),
            "pvp": None if (pvp is not None and pd.isna(pvp)) else pvp,
            **agg,
            **prof,
        })

    records.sort(key=lambda r: r.get("volume_brapi") or 0, reverse=True)
    meta = {
        "fonte": "CVM INF_MENSAL FIAgro (Dividend_Yield_Mes) + brapi (universo/spot)",
        "universo": "auto-detectado: fi-agro da brapi ∩ ISIN→ticker da CVM",
        "cobertura": "FIAgro inicia 2025-05 (~1 ano) — histórico curto, ver meses_disponiveis",
        "min_cotistas": args.min_cotistas,
    }
    json_path = export_json(records, args.out.with_suffix(".json"), meta=meta)
    export_parquet(records, args.out.with_suffix(".parquet"))

    # 4) Score de fundos -> shortlist ranqueada.
    # Baseline do yield é CROSS-SECTIONAL (mediana dos pares confiáveis): com ~1 ano de
    # história, um baseline per-fundo seria circular. Honesto e documentado — o trap aqui
    # é "muito acima dos pares", não "muito acima do próprio histórico" (que exige anos).
    # Baseline POR TIPO (crédito × terras): comparar um FIAgro de terras com fundos de
    # crédito distorce — eles têm perfil de yield diferente. Mediana dos pares do MESMO tipo;
    # cai para a mediana global se o tipo tiver poucos pares confiáveis.
    confiaveis = [
        r for r in records
        if (r.get("meses_disponiveis") or 0) >= MIN_MESES_RANK
        and not r.get("dy_constante")
        and (r.get("dy_ttm") or 0) > 0
    ]
    global_median = median([r["dy_ttm"] for r in confiaveis]) if confiaveis else None
    by_tipo: dict[str, list[float]] = {}
    for r in confiaveis:
        by_tipo.setdefault(r.get("tipo") or "credito", []).append(r["dy_ttm"])
    tipo_median = {t: median(v) for t, v in by_tipo.items() if len(v) >= 3}

    def baseline_for(r: dict) -> float | None:
        return tipo_median.get(r.get("tipo") or "credito", global_median)

    rows: list[dict] = []
    excluidos = 0
    for r in records:
        if (r.get("meses_disponiveis") or 0) < MIN_MESES_RANK:
            excluidos += 1  # história insuficiente p/ ranquear (fica só em fiagro.json)
            continue
        # Confiança: DY-placeholder constante ou quase sem pagamentos = baixa.
        conf_baixa = bool(r.get("dy_constante") or (r.get("meses_pagando") or 0) < 4)
        base = baseline_for(r)
        bd = fund_composite_score(
            r["ticker"],
            months_paid_12m=int(r.get("meses_com_pagamento_12m") or 0),
            dy_ttm=r.get("dy_ttm"),
            dy_baseline=base,
            crescimento=r.get("crescimento"),
            leverage=r.get("alavancagem"),
            vp_cota_var=r.get("vp_cota_var"),
            taxa_admin_aa=r.get("taxa_admin_aa"),
            yield_trap=bool(r.get("yield_trap")),
            months_window=min(12, int(r.get("meses_disponiveis") or 12)),
        )
        # Amortecedor de qualidade do dado (específico do FIAgro): DY-placeholder não pode
        # liderar a shortlist só por "parecer recorrente". Não é mérito do fundo.
        score = round(bd.score * (CONF_DAMPER if conf_baixa else 1.0), 1)
        rows.append({
            "ticker": r["ticker"], "nome": r.get("nome"), "score": score,
            "tipo": r.get("tipo"),
            "recurrence": bd.recurrence, "yield": bd.yield_, "growth": bd.growth,
            "sustainability": bd.sustainability, "yield_trap": bd.yield_trap,
            "confianca": "baixa" if conf_baixa else "alta",
            "dy_ttm": r.get("dy_ttm"), "dy_ttm_estimado": r.get("dy_ttm_estimado"),
            "dy_baseline_pares": base, "pvp": r.get("pvp"),
            "alavancagem": r.get("alavancagem"), "vp_cota_var": r.get("vp_cota_var"),
            "inadimplencia": r.get("inadimplencia"),
            "diversificacao_hhi": r.get("diversificacao_hhi"),
            "liquidez_pl": r.get("liquidez_pl"),
            "meses_disponiveis": r.get("meses_disponiveis"),
            "crescimento": r.get("crescimento"), "crescimento_base": r.get("crescimento_base"),
            "volume_brapi": r.get("volume_brapi"),
        })
    rows.sort(key=lambda x: x["score"], reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    score_meta = {
        "metodologia": "score de fundos 40/30/30 × sustentabilidade (alavancagem/cota/taxa)",
        "baseline_yield": "cross-sectional POR TIPO (crédito × terras); fallback mediana global",
        "median_dy_ttm_por_tipo": {t: round(v, 4) for t, v in tipo_median.items()},
        "median_dy_ttm_global": global_median,
        "min_meses_rank": MIN_MESES_RANK,
        "excluidos_por_historico_curto": excluidos,
        "damper_baixa_confianca": CONF_DAMPER,
        **meta,
    }
    score_path = export_json(rows, args.out.parent / "fiagro_score.json", meta=score_meta)
    export_parquet(rows, args.out.parent / "fiagro_score.parquet")

    print(f"\nFIAgro negociados com dados: {len(records)} "
          f"(ranqueados: {len(rows)}; excluídos <{MIN_MESES_RANK} meses: {excluidos})")
    print("baseline por tipo (DY TTM): "
          + ", ".join(f"{t}={v * 100:.1f}%" for t, v in tipo_median.items()))
    print("Shortlist (rank — ticker — tipo — score — DY TTM — inadimpl. — conf):")
    for row in rows:
        ttm = f"{row['dy_ttm'] * 100:.1f}%" if row.get("dy_ttm") is not None else "—"
        inad = f"{row['inadimplencia'] * 100:.1f}%" if row.get("inadimplencia") is not None else "—"
        print(f"  {row['rank']:>2}. {row['ticker']:8} {(row.get('tipo') or '—'):8} "
              f"{row['score']:>5}  DY_TTM={ttm:>7}  inad={inad:>6}  conf={row['confianca']:5}"
              f"{'  TRAP' if row['yield_trap'] else ''}")
    print(f"Escrito: {json_path} e {score_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
