#!/usr/bin/env python3
"""Valida as colunas REAIS de um ZIP/CSV da CVM contra config/columns.yml.

Uso:
    python scripts/inspect_zip.py <arquivo.zip|arquivo.csv> [--dataset fii_inf_mensal]

Lista os membros do ZIP, mostra as colunas reais e reporta, por dataset, quais campos
lógicos resolveram para qual coluna e quais obrigatórios estão faltando. Use isto antes
de confiar no parser — os nomes pós-Resolução 175 podem ter mudado.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.columns import load_columns_config, resolve_columns  # noqa: E402
from pipeline.normalize import (  # noqa: E402
    list_zip_members,
    read_cvm_csv,
    read_cvm_csv_from_zip,
)


def _columns_of(path: Path, member: str | None) -> tuple[list[str], str]:
    if path.suffix.lower() == ".zip":
        members = list_zip_members(path)
        chosen = member or members[0]
        df = read_cvm_csv_from_zip(path, chosen, nrows=5)
        return list(df.columns), chosen
    df = read_cvm_csv(path, nrows=5)
    return list(df.columns), path.name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--member", help="CSV específico dentro do ZIP")
    ap.add_argument("--dataset", default="fii_inf_mensal")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"Arquivo não encontrado: {args.path}", file=sys.stderr)
        return 2

    if args.path.suffix.lower() == ".zip":
        print("Membros do ZIP:")
        for m in list_zip_members(args.path):
            print(f"  - {m}")

    columns, member = _columns_of(args.path, args.member)
    print(f"\nColunas reais em '{member}':")
    for c in columns:
        print(f"  - {c}")

    specs = load_columns_config()
    if args.dataset not in specs:
        print(f"\nDataset '{args.dataset}' não está em columns.yml.", file=sys.stderr)
        return 2
    resolved, missing = resolve_columns(specs[args.dataset], columns)
    print(f"\nResolução para dataset '{args.dataset}':")
    for field_name, real in resolved.items():
        print(f"  ✓ {field_name:24s} -> {real}")
    for field_name in (f.name for f in specs[args.dataset].fields if f.name not in resolved):
        flag = "OBRIGATÓRIO FALTANDO" if field_name in missing else "opcional ausente"
        print(f"  ✗ {field_name:24s} -> ({flag})")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
