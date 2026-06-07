#!/usr/bin/env python3
"""Reproduce compact paper-supporting figures from repository results/data."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = REPO_ROOT / "results" / "figures"
TABLES_DIR = REPO_ROOT / "results" / "tables"
DATA_DIR = REPO_ROOT / "data"


def set_plot_font() -> None:
    try:
        from matplotlib import font_manager

        available = {font.name for font in font_manager.fontManager.ttflist}
        candidates = [
            "PingFang SC",
            "Songti SC",
            "Heiti SC",
            "Arial Unicode MS",
            "Noto Sans CJK SC",
            "SimHei",
            "DejaVu Sans",
        ]
        chosen = [name for name in candidates if name in available]
        if chosen:
            plt.rcParams["font.family"] = chosen
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        return


def save_coverage_figure() -> None:
    coverage_path = DATA_DIR / "metadata" / "coverage_report.csv"
    if not coverage_path.exists():
        print(f"[skip] Missing {coverage_path}")
        return
    df = pd.read_csv(coverage_path)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    shortages = df[df["missing_videos"] > 0].copy()
    shortages.to_csv(TABLES_DIR / "coverage_shortages.csv", index=False)

    missing = (
        df.groupby(["model", "category"], as_index=False)["missing_videos"]
        .sum()
        .sort_values(["model", "category"])
    )
    if missing.empty:
        return

    labels = [f"{row.model}\n{row.category}" for row in missing.itertuples()]
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.45), 4.5))
    ax.bar(range(len(labels)), missing["missing_videos"], color="#4c78a8")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Missing videos")
    ax.set_title("Current Video Coverage Gaps")
    fig.tight_layout()
    out = FIGURES_DIR / "coverage_missing_videos.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"[ok] Wrote {out}")


def save_bias_summary_figure() -> None:
    metric_paths = sorted(TABLES_DIR.glob("bias_*_bias_scalar_metrics.csv"))
    if not metric_paths:
        print("[skip] Bias metric tables not found; run reproduce_bias_tables.py first")
        return
    df = pd.concat([pd.read_csv(path).assign(source=path.stem) for path in metric_paths], ignore_index=True)
    if "score" not in df.columns:
        return
    summary = df.groupby(["source", "task", "model"], as_index=False)["score"].mean()
    summary["label"] = summary["source"].str.replace("_bias_scalar_metrics", "", regex=False) + "\n" + summary["task"] + "\n" + summary["model"]

    fig, ax = plt.subplots(figsize=(max(10, len(summary) * 0.28), 5))
    ax.bar(range(len(summary)), summary["score"], color="#59a14f")
    ax.set_xticks(range(len(summary)))
    ax.set_xticklabels(summary["label"], rotation=90, fontsize=7)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Mean bias score")
    ax.set_title("Bias Score Summary")
    fig.tight_layout()
    out = FIGURES_DIR / "bias_score_summary.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"[ok] Wrote {out}")


def save_distance_gap_figure() -> None:
    summary_path = TABLES_DIR / "distance_hnd_summary.csv"
    if not summary_path.exists():
        print("[skip] Distance summary not found; run reproduce_distance_tables.py first")
        return
    df = pd.read_csv(summary_path)
    mean_col = "HND_black_minus_white_mean"
    if mean_col not in df.columns:
        return
    labels = [f"{row.indicator}\n{row.model}" for row in df.itertuples()]
    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.5), 4.5))
    colors = ["#e15759" if value > 0 else "#4c78a8" for value in df[mean_col]]
    ax.bar(range(len(labels)), df[mean_col], color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Mean HND(Black) - HND(White)")
    ax.set_title("Race-Conditioned Distance Gap")
    fig.tight_layout()
    out = FIGURES_DIR / "distance_hnd_gap.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"[ok] Wrote {out}")


def main() -> None:
    set_plot_font()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    save_coverage_figure()
    save_bias_summary_figure()
    save_distance_gap_figure()


if __name__ == "__main__":
    main()
