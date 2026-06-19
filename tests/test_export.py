import json
from dataclasses import dataclass

import pandas as pd

from pipeline.export import export_json, export_parquet


@dataclass
class Rec:
    ticker: str
    pvp: float
    annual_avg_price: dict


def test_export_json_writes_meta_and_data(tmp_path):
    items = [Rec("HGLG11", 1.1, {2023: 99.0})]
    path = export_json(items, tmp_path / "out.json", meta={"source": "test"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["count"] == 1
    assert payload["meta"]["source"] == "test"
    assert "generated_at" in payload["meta"]
    assert payload["data"][0]["ticker"] == "HGLG11"
    assert payload["data"][0]["annual_avg_price"] == {"2023": 99.0}


def test_export_parquet_serializes_nested(tmp_path):
    items = [Rec("HGLG11", 1.1, {2023: 99.0})]
    path = export_parquet(items, tmp_path / "out.parquet")
    df = pd.read_parquet(path)
    assert df.loc[0, "ticker"] == "HGLG11"
    # coluna aninhada vira JSON string
    assert json.loads(df.loc[0, "annual_avg_price"]) == {"2023": 99.0}


def test_export_json_accepts_dicts(tmp_path):
    items = [{"ticker": "PETR4", "current_price": 38.0}]
    path = export_json(items, tmp_path / "d.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["data"][0]["current_price"] == 38.0
