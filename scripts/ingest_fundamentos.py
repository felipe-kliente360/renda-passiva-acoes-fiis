#!/usr/bin/env python3
"""Ingestão de fundamentos de AÇÕES via CVM ITR/DFP (Fase 2 — espinha da tese).

Para cada ano do intervalo baixa a DFP, extrai (config-driven) proventos pagos (DFC),
lucro atribuível à controladora (DRE) e ações em circulação (composicao_capital) das
empresas da watchlist, e monta as séries por competência. Cruza com a série de preços
(Fase 1, data/prices.json) e roda as métricas puras (DY histórico média/mediana, payout,
recorrência, crescimento, flag de yield trap). Exporta data/fundamentos.json.

Metodologia (TRAVADA, revisada 2026-06-26): proventos por COMPETÊNCIA da CVM, DY no nível
da empresa (proventos ÷ valor de mercado = preço × ações). A escala de ações da CVM é
desambiguada por âncora de mercado (yfinance sharesOutstanding); sem âncora, baixa
confiança e não inventa.

Uso:
    python scripts/ingest_fundamentos.py --start 2015 --end 2025 [--out data/fundamentos]
    python scripts/ingest_fundamentos.py --start 2015 --end 2025 --no-download  # usa cache
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import metrics  # noqa: E402
from pipeline.cvm import download_dfp, download_itr  # noqa: E402
from pipeline.export import export_json, export_parquet  # noqa: E402
from pipeline.fundamentos import (  # noqa: E402
    extract_concept,
    load_contas_config,
    lucro_liquido,
    patrimonio_liquido,
    resolve_share_scale,
    total_acoes,
    ttm_proventos,
)
from pipeline.normalize import list_zip_members, read_cvm_csv_from_zip  # noqa: E402
from pipeline.prices import fetch_shares_outstanding  # noqa: E402

DEFAULT_RAW = Path("data/raw")


def _member(zip_path: Path, contains: str) -> str | None:
    """Membro do ZIP cujo nome contém `contains` (prefere consolidado _con)."""
    members = [m for m in list_zip_members(zip_path) if contains in m and m.endswith(".csv")]
    con = [m for m in members if "_con_" in m]
    return (con or members or [None])[0]


def _by_key(df: pd.DataFrame, key_col: str, key_val: str, val_col: str = "valor") -> float | None:
    sub = df[df[key_col].astype("string").str.zfill(6) == str(key_val).zfill(6)]
    return float(sub[val_col].iloc[0]) if not sub.empty else None


def _latest_ytd(df: pd.DataFrame, cd_cvm: str) -> tuple[float, int] | None:
    """(valor, ano) do trimestre YTD mais recente de uma empresa num extract de ITR."""
    sub = df[df["cd_cvm"].astype("string").str.zfill(6) == str(cd_cvm).zfill(6)]
    if sub.empty:
        return None
    row = sub.loc[sub["dt_fim_exerc"].idxmax()]
    return float(row["valor"]), int(row["dt_fim_exerc"].year)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, required=True, help="primeiro ano fiscal (DFP)")
    ap.add_argument("--end", type=int, required=True, help="último ano fiscal (DFP)")
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.yml"))
    ap.add_argument("--prices", type=Path, default=Path("data/prices.json"))
    ap.add_argument("--out", type=Path, default=Path("data/fundamentos"))
    ap.add_argument("--no-download", action="store_true", help="usar ZIPs já em data/raw")
    args = ap.parse_args()

    wl = yaml.safe_load(args.watchlist.read_text(encoding="utf-8"))
    acoes = [a for a in (wl.get("acoes") or []) if a.get("cd_cvm")]
    specs = load_contas_config()

    prices = {}
    if args.prices.exists():
        for r in json.loads(args.prices.read_text(encoding="utf-8")).get("data", []):
            prices[r["ticker"]] = r

    # Acumula por (cd_cvm/cnpj, ano): proventos pagos, lucro, ações cruas.
    prov: dict[str, dict[int, float]] = {}
    lucro: dict[str, dict[int, float]] = {}
    pl: dict[str, dict[int, float]] = {}
    shares_raw: dict[str, dict[int, float]] = {}

    for year in range(args.start, args.end + 1):
        zip_path = DEFAULT_RAW / f"dfp_cia_aberta_{year}.zip"
        if not args.no_download and not zip_path.exists():
            try:
                zip_path = download_dfp(year)
            except Exception as e:  # ano ainda não publicado (DFP sai no ano seguinte) etc.
                print(f"[{year}] download falhou ({e}); pulando.", file=sys.stderr)
                continue
        if not zip_path.exists():
            print(f"[{year}] ZIP ausente, pulando.", file=sys.stderr)
            continue

        m_dfc, m_dre, m_bpp, m_comp = (
            _member(zip_path, "DFC_MI"),
            _member(zip_path, "DRE"),
            _member(zip_path, "BPP"),
            _member(zip_path, "composicao_capital"),
        )
        prov_y = (
            extract_concept(read_cvm_csv_from_zip(zip_path, m_dfc), specs["proventos_pagos"])
            if m_dfc else None
        )
        lucro_y = lucro_liquido(read_cvm_csv_from_zip(zip_path, m_dre), specs) if m_dre else None
        pl_y = patrimonio_liquido(read_cvm_csv_from_zip(zip_path, m_bpp), specs) if m_bpp else None
        # composicao_capital só existe em DFPs recentes; ações por ano ficam limitadas a eles.
        acoes_y = total_acoes(read_cvm_csv_from_zip(zip_path, m_comp)) if m_comp else None

        for a in acoes:
            cd, cnpj = a["cd_cvm"], a.get("cnpj")
            p = _by_key(prov_y, "cd_cvm", cd) if prov_y is not None else None
            ll = _by_key(lucro_y, "cd_cvm", cd) if lucro_y is not None else None
            plv = _by_key(pl_y, "cd_cvm", cd) if pl_y is not None else None
            sh = (
                _by_key(acoes_y, "cnpj", cnpj, "acoes_circulacao")
                if (acoes_y is not None and cnpj) else None
            )
            if p is not None:
                prov.setdefault(cd, {})[year] = p
            if ll is not None:
                lucro.setdefault(cd, {})[year] = ll
            if plv is not None:
                pl.setdefault(cd, {})[year] = plv
            if sh is not None:
                shares_raw.setdefault(cd, {})[year] = sh
        print(f"[{year}] ok")

    # TTM via ITR do ano corrente: YTD atual (ÚLTIMO) e do mesmo período do ano anterior
    # (PENÚLTIMO). Latest dt_fim por empresa = trimestre mais recente publicado.
    ytd_cur: dict[str, tuple[float, int]] = {}
    ytd_pri: dict[str, float] = {}
    itr_zip = DEFAULT_RAW / f"itr_cia_aberta_{args.end}.zip"
    if not args.no_download and not itr_zip.exists():
        try:
            itr_zip = download_itr(args.end)
        except Exception as e:
            print(f"[ITR {args.end}] download falhou ({e}); TTM indisponível.", file=sys.stderr)
    if itr_zip.exists():
        m_dfc = _member(itr_zip, "DFC_MI")
        if m_dfc:
            itr_dfc = read_cvm_csv_from_zip(itr_zip, m_dfc)
            cur = extract_concept(itr_dfc, specs["proventos_pagos"], ordem="ÚLTIMO")
            pri = extract_concept(itr_dfc, specs["proventos_pagos"], ordem="PENÚLTIMO")
            for a in acoes:
                cd = a["cd_cvm"]
                v = _latest_ytd(cur, cd)
                if v is not None:
                    ytd_cur[cd] = v
                p = _latest_ytd(pri, cd)
                if p is not None:
                    ytd_pri[cd] = p[0]
            print(f"[ITR {args.end}] TTM calculado para {len(ytd_cur)} ações.")

    records = []
    for a in acoes:
        cd, tk = a["cd_cvm"], a["ticker"]
        rec = _build_record(a, prov.get(cd, {}), lucro.get(cd, {}), pl.get(cd, {}),
                            shares_raw.get(cd, {}), prices.get(tk, {}),
                            ytd_cur.get(cd), ytd_pri.get(cd))
        records.append(rec)

    meta = {
        "metodologia": "proventos por competência CVM (DFP); DY nível empresa; "
        "denominador split-adj (Fase 1); escala de ações ancorada no yfinance",
        "anos": [args.start, args.end],
    }
    json_path = export_json(records, args.out.with_suffix(".json"), meta=meta)
    export_parquet(records, args.out.with_suffix(".parquet"))
    print(f"Ações processadas: {len(records)}")
    print(f"Escrito: {json_path}")
    return 0


def _build_record(
    a: dict, prov: dict, lucro: dict, pl: dict, shares_raw: dict, price: dict,
    ytd_cur: tuple[float, int] | None = None, ytd_pri: float | None = None,
) -> dict:
    tk = a["ticker"]
    notes: list[str] = []

    # escala das ações: âncora yfinance desambigua unidade x milhar, POR ANO (a CVM chega a
    # trocar de unidade no meio do histórico — ex.: Bradesco em milhares até 2023, unidades
    # depois). A âncora é a contagem atual; cada ano é classificado contra ela.
    latest_share_year = max(shares_raw) if shares_raw else None
    anchor = fetch_shares_outstanding(tk) if latest_share_year is not None else None
    if latest_share_year is not None and anchor is None:
        notes.append("sem âncora de ações (yfinance): escala assumida 1, baixa confiança")
    shares = {y: v * resolve_share_scale(v, anchor) for y, v in shares_raw.items()}
    scales = {resolve_share_scale(v, anchor) for v in shares_raw.values()}
    if len(scales) > 1:
        notes.append("escala de ações variou entre anos no arquivo da CVM (corrigida por ano)")

    # séries por ano
    prov_total = pd.Series(prov, dtype="float64").sort_index()  # R$ por ano
    dps = pd.Series(
        {y: prov[y] / shares[y] for y in prov if shares.get(y, 0) > 0}, dtype="float64"
    ).sort_index()  # provento por ação
    avg_price = pd.Series(
        {int(y): float(v) for y, v in (price.get("annual_avg_price") or {}).items()},
        dtype="float64",
    ).sort_index()

    hist = metrics.historical_dy(dps, avg_price)
    current_price = price.get("current_price")
    latest_y = max(prov) if prov else None
    shares_now = shares.get(latest_share_year) if latest_share_year else None

    # proventos correntes: TTM via ITR (ponte ano-cheio + YTD) quando disponível; senão o
    # último ano fiscal cheio (DFP). Ambos no nível da empresa, mesmas ações atuais.
    prov_corrente = prov.get(latest_y) if latest_y is not None else None
    base_corrente = "ano_fiscal"
    ttm = None
    if ytd_cur is not None and ytd_pri is not None:
        full_prior = prov.get(ytd_cur[1] - 1)
        if full_prior is not None:
            ttm = ttm_proventos(full_prior, ytd_cur[0], ytd_pri)
            prov_corrente, base_corrente = ttm, "ttm_itr"

    current_dy = float("nan")
    if prov_corrente is not None and shares_now and current_price:
        current_dy = metrics.current_dy(prov_corrente / shares_now, current_price)

    payout = {
        int(y): metrics.payout_ratio(prov[y], lucro[y])
        for y in sorted(set(prov) & set(lucro))
    }
    rec_y = latest_y or (max(avg_price.index) if len(avg_price) else 0)
    recur = metrics.recurrence(prov_total, asof_year=int(rec_y)) if rec_y else {}

    # VPA (book value por ação) e P/VP corrente. PL e ações da mesma competência.
    vpa = {
        int(y): pl[y] / shares[y] for y in sorted(set(pl) & set(shares)) if shares.get(y, 0) > 0
    }
    pl_latest = max(vpa) if vpa else None
    pvp = (current_price / vpa[pl_latest]) if (pl_latest and current_price) else None

    return {
        "ticker": tk,
        "nome": a.get("nome"),
        "cd_cvm": a["cd_cvm"],
        "proventos_pagos_por_ano": {int(y): float(v) for y, v in prov_total.items()},
        "lucro_liquido_por_ano": {int(y): float(v) for y, v in sorted(lucro.items())},
        "dps_por_ano": {int(y): float(v) for y, v in dps.items()},
        "dy_historico_por_ano": {int(y): float(v) for y, v in hist.by_year.items()},
        "dy_historico_media": None if pd.isna(hist.mean) else hist.mean,
        "dy_historico_mediana": None if pd.isna(hist.median) else hist.median,
        "dy_corrente": None if pd.isna(current_dy) else current_dy,
        "dy_corrente_base": base_corrente,
        "ttm_proventos": ttm,
        "payout_por_ano": {y: (None if pd.isna(v) else v) for y, v in payout.items()},
        "patrimonio_liquido_por_ano": {int(y): float(v) for y, v in sorted(pl.items())},
        "vpa_por_ano": vpa,
        "pvp": pvp,
        "recorrencia": recur,
        "crescimento_dps_cagr": (
            None if pd.isna(g := metrics.dividend_growth(dps)) else g
        ),
        "yield_trap": metrics.yield_trap_flag(current_dy, hist.median),
        "acoes_circulacao": shares.get(latest_share_year) if latest_share_year else None,
        "escala_acoes_recente": (
            resolve_share_scale(shares_raw[latest_share_year], anchor)
            if latest_share_year else None
        ),
        "notes": notes,
    }


if __name__ == "__main__":
    raise SystemExit(main())
