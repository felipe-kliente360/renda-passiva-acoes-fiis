"""Export de artefatos estáticos (JSON + Parquet) versionados no repo.

Sem banco: os dados mudam mensal/trimestralmente; estático é auditável e grátis.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _to_records(items: list[Any]) -> list[dict[str, Any]]:
    """Normaliza dataclasses/dicts em lista de dicts serializáveis."""
    records: list[dict[str, Any]] = []
    for item in items:
        is_instance = is_dataclass(item) and not isinstance(item, type)
        records.append(asdict(item) if is_instance else dict(item))
    return records


def export_json(
    items: list[Any],
    path: str | Path,
    *,
    meta: dict[str, Any] | None = None,
) -> Path:
    """Exporta uma lista de registros para JSON com bloco de metadados/proveniência."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "count": len(items),
            **(meta or {}),
        },
        "data": _to_records(items),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return path


def export_parquet(items: list[Any], path: str | Path) -> Path:
    """Exporta os mesmos registros para Parquet (colunas aninhadas viram JSON string)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(_to_records(items))
    for col in df.columns:
        if df[col].apply(lambda v: isinstance(v, (dict, list))).any():
            df[col] = df[col].apply(lambda v: json.dumps(v, ensure_ascii=False, default=str))
    df.to_parquet(path, index=False)
    return path
