#!/usr/bin/env python3
"""Reproduce social-distance experiment tables from repository data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
TABLES_DIR = REPO_ROOT / "results" / "tables"


def read_csv_clean(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(column).strip() for column in df.columns]
    for column in df.columns:
        if df[column].dtype == object:
            df[column] = df[column].map(lambda value: value.strip() if isinstance(value, str) else value)
    return df


def reproduce_hnd_summary() -> None:
    path = DATA_DIR / "summary_counts" / "distance_hnd_video_level.csv"
    if not path.exists():
        print(f"[skip] Missing {path}")
        return

    df = read_csv_clean(path)
    for column in ("HND_white", "HND_black"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if {"HND_white", "HND_black"}.issubset(df.columns):
        df["HND_black_minus_white"] = df["HND_black"] - df["HND_white"]

    group_cols = [column for column in ("indicator", "model") if column in df.columns]
    if not group_cols:
        print("[skip] distance_hnd_video_level.csv has no indicator/model columns")
        return

    numeric_cols = [column for column in ("HND_white", "HND_black", "HND_black_minus_white") if column in df.columns]
    summary = df.groupby(group_cols, dropna=False)[numeric_cols].agg(["count", "mean", "std"]).reset_index()
    summary.columns = [
        "_".join(str(part) for part in column if part).strip("_")
        if isinstance(column, tuple)
        else str(column)
        for column in summary.columns
    ]
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES_DIR / "distance_hnd_video_level_clean.csv", index=False)
    summary.to_csv(TABLES_DIR / "distance_hnd_summary.csv", index=False)
    print(f"[ok] Wrote {TABLES_DIR / 'distance_hnd_summary.csv'}")


def reproduce_avoidance_counts() -> None:
    source = DATA_DIR / "summary_counts" / "distance_racial_avoidance.csv"
    if source.exists():
        df = read_csv_clean(source)
        TABLES_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(TABLES_DIR / "distance_racial_avoidance_counts.csv", index=False)
        print(f"[ok] Wrote {TABLES_DIR / 'distance_racial_avoidance_counts.csv'}")

    annotations = DATA_DIR / "annotations" / "video_level_annotations.csv"
    if not annotations.exists():
        return
    labels = read_csv_clean(annotations)
    required = {"indicator", "model", "avoidance_label"}
    if not required.issubset(labels.columns):
        return
    counts = (
        labels.groupby(["indicator", "model", "avoidance_label"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["indicator", "model", "avoidance_label"])
    )
    counts.to_csv(TABLES_DIR / "distance_video_label_counts.csv", index=False)
    print(f"[ok] Wrote {TABLES_DIR / 'distance_video_label_counts.csv'}")


def main() -> None:
    reproduce_hnd_summary()
    reproduce_avoidance_counts()


if __name__ == "__main__":
    main()
