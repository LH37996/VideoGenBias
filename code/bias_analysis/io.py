from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json
import pandas as pd
import yaml

def load_config(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_results(path: Path) -> pd.DataFrame:
    """Load results from CSV/JSON."""
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return pd.DataFrame(data)
    raise ValueError(f"Unsupported results format: {path.suffix}. Use .csv or .json.")

def parse_counts(counts_json: Any) -> Dict[str, float]:
    """Parse counts_json into a dict. Supports both integer and float (proportion) values."""
    if isinstance(counts_json, dict):
        return {str(k): float(v) for k, v in counts_json.items()}
    if isinstance(counts_json, str):
        obj = json.loads(counts_json)
        return {str(k): float(v) for k, v in obj.items()}
    raise ValueError(f"Unsupported counts_json type: {type(counts_json)}")
