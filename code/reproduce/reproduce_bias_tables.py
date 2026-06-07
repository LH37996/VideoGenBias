#!/usr/bin/env python3
"""Reproduce bias metrics, tables, and markdown reports from summary counts."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))

from bias_analysis.io import load_results
from bias_analysis.report import compute_all, generate_markdown_report
from bias_analysis.vector_report import compute_all_vector, generate_vector_report


CONFIG = {
    "project": {
        "name": "VideoGenBias",
        "model_order": ["Sora", "Sora2", "Wan2.1", "Wan2.6", "Seedance1.5"],
    },
    "tasks": {
        "illegal_behavior": {"sensitive_attrs": ["gender", "skin"]},
        "personality": {"sensitive_attrs": ["gender"]},
        "occupation": {"sensitive_attrs": ["gender", "skin"]},
    },
}


def reproduce_one(input_name: str, output_stem: str) -> None:
    source = REPO_ROOT / "data" / "summary_counts" / input_name
    if not source.exists():
        print(f"[skip] Missing {source}")
        return

    df = load_results(source)
    tables_dir = REPO_ROOT / "results" / "tables"
    reports_dir = REPO_ROOT / "results" / "reports" / output_stem
    tables_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    scalar = compute_all(df)
    scalar.to_csv(tables_dir / f"{output_stem}_bias_scalar_metrics.csv", index=False)

    gender_vector, skin_vector = compute_all_vector(df)
    gender_vector.to_csv(tables_dir / f"{output_stem}_gender_vector_metrics.csv", index=False)
    skin_vector.to_csv(tables_dir / f"{output_stem}_skin_vector_metrics.csv", index=False)

    report_path = generate_markdown_report(CONFIG, df, reports_dir)
    vector_report_path = generate_vector_report(CONFIG, df, reports_dir)
    print(f"[ok] {output_stem}: {report_path}")
    print(f"[ok] {output_stem}: {vector_report_path}")


def main() -> None:
    reproduce_one("results_cn.csv", "bias_cn")
    reproduce_one("results_en.csv", "bias_en")


if __name__ == "__main__":
    main()
