"""Resolução config-driven de nomes de coluna da CVM.

Os nomes crus podem mudar (ex.: Resolução 175). Em vez de fixá-los no código,
declaramos candidatos em `config/columns.yml` e resolvemos contra as colunas reais
do arquivo. Compartilhado entre os parsers e `scripts/inspect_zip.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    candidates: list[str]
    required: bool = False


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    encoding: str
    sep: str
    decimal: str
    fields: list[FieldSpec] = field(default_factory=list)


def load_columns_config(path: str | Path | None = None) -> dict[str, DatasetSpec]:
    """Carrega `config/columns.yml` em specs tipadas por dataset."""
    path = Path(path) if path is not None else CONFIG_DIR / "columns.yml"
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    specs: dict[str, DatasetSpec] = {}
    for ds_name, ds in raw.items():
        fields = [
            FieldSpec(
                name=fname,
                candidates=list(fspec.get("candidates", [])),
                required=bool(fspec.get("required", False)),
            )
            for fname, fspec in ds.get("fields", {}).items()
        ]
        specs[ds_name] = DatasetSpec(
            name=ds_name,
            encoding=ds.get("encoding", "ISO-8859-1"),
            sep=ds.get("sep", ";"),
            decimal=ds.get("decimal", ","),
            fields=fields,
        )
    return specs


def pick_member_by_resolution(
    spec: DatasetSpec,
    members_columns: dict[str, list[str]],
    *,
    prefer_fields: tuple[str, ...] = (),
) -> str | None:
    """Escolhe, entre vários membros (CSV de um ZIP), o que melhor resolve o dataset.

    Pura e testável: recebe um mapa `membro -> colunas reais`. Descarta membros que
    deixam campos obrigatórios faltando; entre os válidos, vence o que resolve mais
    campos de `prefer_fields` (ex.: as colunas de VP do FII). Empate fica com a ordem
    de inserção do dict. Retorna None se nenhum membro resolver os obrigatórios.
    """
    best: tuple[int, str] | None = None
    for member, cols in members_columns.items():
        resolved, missing = resolve_columns(spec, cols)
        if missing:
            continue
        score = sum(1 for f in prefer_fields if f in resolved)
        if best is None or score > best[0]:
            best = (score, member)
    return best[1] if best else None


def resolve_columns(
    spec: DatasetSpec, available: list[str]
) -> tuple[dict[str, str], list[str]]:
    """Mapeia campo lógico -> nome real escolhido entre os candidatos presentes.

    Retorna (mapeamento_resolvido, campos_required_faltando). O primeiro candidato
    presente em `available` vence. Campos opcionais ausentes simplesmente não entram
    no mapeamento.
    """
    available_set = set(available)
    resolved: dict[str, str] = {}
    missing_required: list[str] = []
    for f in spec.fields:
        chosen = next((c for c in f.candidates if c in available_set), None)
        if chosen is not None:
            resolved[f.name] = chosen
        elif f.required:
            missing_required.append(f.name)
    return resolved, missing_required
