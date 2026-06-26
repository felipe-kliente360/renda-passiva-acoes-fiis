#!/usr/bin/env python3
"""Entry point da ingestão do informe mensal de FII (INF_MENSAL da CVM).

Uso:
    python scripts/ingest_fii.py [<zip_inf_mensal_fii>] [--member <csv>] [--out data/fii_vp]
    python scripts/ingest_fii.py --download [--year 2026]

Lê o ZIP, parseia via config, deriva o último VP da cota por fundo e exporta
JSON+Parquet. Com --download (ou sem path), baixa o pacote do ano via pipeline.cvm;
caso contrário o parsing é totalmente offline sobre um ZIP/CSV local.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.columns import (  # noqa: E402
    DatasetSpec,
    load_columns_config,
    pick_member_by_resolution,
)
from pipeline.export import export_json, export_parquet  # noqa: E402
from pipeline.fii import DATASET, latest_vp_por_fundo, parse_fii_inf_mensal  # noqa: E402
from pipeline.normalize import (  # noqa: E402
    list_zip_members,
    read_cvm_csv,
    read_cvm_csv_from_zip,
)

# Campos que carregam o VP da cota (direto ou derivável). O membro escolhido do ZIP
# deve resolver pelo menos um deles, senão o parse sai vazio (ex.: o membro
# `ativo_passivo` resolve cnpj/competencia mas NÃO tem VP/PL/cotas; vivem no `complemento`).
VP_FIELDS = ("valor_patrimonial_cota", "patrimonio_liquido", "cotas_emitidas")


def _select_member(zip_path: Path, spec: DatasetSpec, members: list[str]) -> str | None:
    """Lê o header de cada CSV do ZIP e delega a escolha à lógica pura (config-driven)."""
    members_columns = {
        m: list(read_cvm_csv_from_zip(zip_path, m, nrows=0).columns)
        for m in members
        if m.lower().endswith(".csv")
    }
    return pick_member_by_resolution(spec, members_columns, prefer_fields=VP_FIELDS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path, nargs="?", help="ZIP do INF_MENSAL de FII ou CSV")
    ap.add_argument("--download", action="store_true", help="baixar o pacote via CVM")
    ap.add_argument("--year", type=int, help="ano do pacote a baixar (default: corrente)")
    ap.add_argument("--member", help="CSV específico dentro do ZIP")
    ap.add_argument("--out", type=Path, default=Path("data/fii_vp"))
    args = ap.parse_args()

    if args.path is None or args.download:
        from pipeline.cvm import download_fii_inf_mensal  # rede isolada

        args.path = download_fii_inf_mensal(args.year)
        print(f"Baixado: {args.path}")

    spec = load_columns_config()[DATASET]
    if args.path.suffix.lower() == ".zip":
        member = args.member or _select_member(args.path, spec, list_zip_members(args.path))
        if member is None:
            print(
                "Nenhum CSV do ZIP resolveu os campos do dataset. "
                "Rode scripts/inspect_zip.py e ajuste config/columns.yml.",
                file=sys.stderr,
            )
            return 2
        print(f"Membro: {member}")
        df = read_cvm_csv_from_zip(args.path, member)
    else:
        df = read_cvm_csv(args.path)

    parsed = parse_fii_inf_mensal(df, spec)
    latest = latest_vp_por_fundo(parsed)

    records = [
        {
            "cnpj_fundo": row.cnpj_fundo,
            "competencia": row.competencia.date().isoformat(),
            "valor_patrimonial_cota": float(row.valor_patrimonial_cota),
        }
        for row in latest.itertuples()
    ]
    json_path = export_json(records, args.out.with_suffix(".json"), meta={"dataset": DATASET})
    pq_path = export_parquet(records, args.out.with_suffix(".parquet"))
    print(f"Fundos com VP: {len(records)}")
    print(f"Escrito: {json_path}")
    print(f"Escrito: {pq_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
