"""Vector bias metrics report generation.

Produces an independent ``vector_report.md`` with:
- Gender SPD (Statistical Parity Difference) tables
- Skin Helmert Orthogonal Contrast Projection tables
- Accompanying charts (butterfly, ternary, heatmap, Helmert scatter)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
from collections import OrderedDict

import math
import textwrap
import pandas as pd

from .metrics import (
    compute_gender_vector,
    compute_skin_vector,
    GenderVectorResult,
    SkinVectorResult,
)
from .io import parse_counts
from .report import _get_model_order, _attach_model_rank, _task_title

SQRT2 = math.sqrt(2)
SQRT6 = math.sqrt(6)


def _pool_skin_by_indicator(skin_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate skin counts across models per (task, indicator).

    Returns a DataFrame with one row per indicator, with pooled counts,
    recomputed proportions and Helmert coordinates.  The ``model`` column
    is set to ``"全部模型"`` so existing viz functions can be reused.
    """
    if skin_df.empty:
        return pd.DataFrame()
    rows = []
    for (task, indicator), g in skin_df.groupby(["task", "indicator"], sort=False):
        cw = g["count_white"].sum()
        cy = g["count_yellow"].sum()
        cb = g["count_black"].sum()
        total = cw + cy + cb
        if total == 0:
            continue
        pw, py_, pb = cw / total, cy / total, cb / total
        third = 1.0 / 3.0
        c1 = (pw - pb) / SQRT2
        c2 = (2 * py_ - pw - pb) / SQRT6
        rows.append({
            "task": task, "indicator": indicator, "model": "全部模型",
            "count_white": cw, "count_yellow": cy, "count_black": cb,
            "p_white": pw, "p_yellow": py_, "p_black": pb,
            "delta_w": pw - third, "delta_y": py_ - third, "delta_b": pb - third,
            "c1": c1, "c2": c2, "helmert_r": math.sqrt(c1 * c1 + c2 * c2),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def compute_all_vector(results_df: pd.DataFrame) -> tuple:
    """Compute vector metrics for every row.

    Returns
    -------
    gender_df : pd.DataFrame
        One row per (task, indicator, model) for gender rows.
    skin_df : pd.DataFrame
        One row per (task, indicator, model) for skin rows.
    """
    required = {"task", "indicator", "model", "sensitive_attr", "counts_json"}
    missing = required - set(results_df.columns)
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    gender_rows: list[dict] = []
    skin_rows: list[dict] = []

    for _, r in results_df.iterrows():
        task = str(r["task"])
        indicator = str(r["indicator"])
        model = str(r["model"]).strip()
        if not model or model.lower() == "nan":
            raise ValueError("Column 'model' cannot be empty.")
        attr = str(r["sensitive_attr"]).lower().strip()
        counts = parse_counts(r["counts_json"])

        if attr == "gender":
            vr = compute_gender_vector(task, indicator, counts)
            gender_rows.append({
                "task": task,
                "indicator": indicator,
                "model": model,
                "count_female": vr.counts.get("female", 0.0),
                "count_male": vr.counts.get("male", 0.0),
                "p_female": vr.proportions.get("female", 0.0),
                "p_male": vr.proportions.get("male", 0.0),
                "SPD": vr.spd,
            })
        elif attr == "skin":
            vr = compute_skin_vector(task, indicator, counts)
            skin_rows.append({
                "task": task,
                "indicator": indicator,
                "model": model,
                "count_white": vr.counts.get("white", 0.0),
                "count_yellow": vr.counts.get("yellow", 0.0),
                "count_black": vr.counts.get("black", 0.0),
                "p_white": vr.proportions.get("white", 0.0),
                "p_yellow": vr.proportions.get("yellow", 0.0),
                "p_black": vr.proportions.get("black", 0.0),
                "delta_w": vr.delta_w,
                "delta_y": vr.delta_y,
                "delta_b": vr.delta_b,
                "c1": vr.c1,
                "c2": vr.c2,
                "helmert_r": vr.helmert_r,
            })

    return pd.DataFrame(gender_rows), pd.DataFrame(skin_rows)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def _gender_task_summary(gender_df: pd.DataFrame, model_order: List[str]) -> pd.DataFrame:
    """Mean SPD per (task, model)."""
    if gender_df.empty:
        return pd.DataFrame()
    rows = []
    for (task, model), g in gender_df.groupby(["task", "model"], sort=False):
        valid = g["SPD"].dropna()
        rows.append({
            "task": task,
            "model": model,
            "n_prompts": len(g),
            "mean_SPD": float(valid.mean()) if len(valid) > 0 else float("nan"),
            "std_SPD": float(valid.std()) if len(valid) > 1 else float("nan"),
            "min_SPD": float(valid.min()) if len(valid) > 0 else float("nan"),
            "max_SPD": float(valid.max()) if len(valid) > 0 else float("nan"),
        })
    df = pd.DataFrame(rows)
    df = _attach_model_rank(df, model_order)
    return df.sort_values(["task", "_model_rank"]).drop(columns=["_model_rank"]).reset_index(drop=True)


def _skin_task_summary(skin_df: pd.DataFrame, model_order: List[str]) -> pd.DataFrame:
    """Mean Helmert components per (task, model)."""
    if skin_df.empty:
        return pd.DataFrame()
    rows = []
    for (task, model), g in skin_df.groupby(["task", "model"], sort=False):
        valid_c1 = g["c1"].dropna()
        valid_c2 = g["c2"].dropna()
        valid_r = g["helmert_r"].dropna()
        rows.append({
            "task": task,
            "model": model,
            "n_prompts": len(g),
            "mean_c1": float(valid_c1.mean()) if len(valid_c1) > 0 else float("nan"),
            "mean_c2": float(valid_c2.mean()) if len(valid_c2) > 0 else float("nan"),
            "mean_helmert_r": float(valid_r.mean()) if len(valid_r) > 0 else float("nan"),
            "mean_delta_w": float(g["delta_w"].dropna().mean()) if g["delta_w"].notna().any() else float("nan"),
            "mean_delta_y": float(g["delta_y"].dropna().mean()) if g["delta_y"].notna().any() else float("nan"),
            "mean_delta_b": float(g["delta_b"].dropna().mean()) if g["delta_b"].notna().any() else float("nan"),
        })
    df = pd.DataFrame(rows)
    df = _attach_model_rank(df, model_order)
    return df.sort_values(["task", "_model_rank"]).drop(columns=["_model_rank"]).reset_index(drop=True)


def _gender_overall_summary(gender_df: pd.DataFrame, model_order: List[str]) -> pd.DataFrame:
    """Overall mean SPD per model (across all tasks)."""
    if gender_df.empty:
        return pd.DataFrame()
    rows = []
    for model, g in gender_df.groupby("model", sort=False):
        valid = g["SPD"].dropna()
        rows.append({
            "model": model,
            "n_prompts": len(g),
            "mean_SPD": float(valid.mean()) if len(valid) > 0 else float("nan"),
            "std_SPD": float(valid.std()) if len(valid) > 1 else float("nan"),
        })
    df = pd.DataFrame(rows)
    df = _attach_model_rank(df, model_order)
    return df.sort_values("_model_rank").drop(columns=["_model_rank"]).reset_index(drop=True)


def _skin_overall_summary(skin_df: pd.DataFrame, model_order: List[str]) -> pd.DataFrame:
    """Overall mean Helmert per model (across all tasks)."""
    if skin_df.empty:
        return pd.DataFrame()
    rows = []
    for model, g in skin_df.groupby("model", sort=False):
        valid_r = g["helmert_r"].dropna()
        rows.append({
            "model": model,
            "n_prompts": len(g),
            "mean_c1": float(g["c1"].dropna().mean()) if g["c1"].notna().any() else float("nan"),
            "mean_c2": float(g["c2"].dropna().mean()) if g["c2"].notna().any() else float("nan"),
            "mean_helmert_r": float(valid_r.mean()) if len(valid_r) > 0 else float("nan"),
        })
    df = pd.DataFrame(rows)
    df = _attach_model_rank(df, model_order)
    return df.sort_values("_model_rank").drop(columns=["_model_rank"]).reset_index(drop=True)


def _gender_indicator_wide(gender_df: pd.DataFrame, model_order: List[str]) -> pd.DataFrame:
    """Wide-format: rows = (task, indicator), columns = each model's SPD + avg."""
    if gender_df.empty:
        return pd.DataFrame()
    rows = []
    for (task, indicator), g in gender_df.groupby(["task", "indicator"], sort=False):
        row: dict = {"task": task, "indicator": indicator}
        for _, mr in g.iterrows():
            row[mr["model"]] = round(float(mr["SPD"]), 2) if pd.notna(mr["SPD"]) else float("nan")
        valid = g["SPD"].dropna()
        row["avg_SPD"] = round(float(valid.mean()), 2) if len(valid) > 0 else float("nan")
        rows.append(row)
    df = pd.DataFrame(rows)
    # reorder columns
    fixed = ["task", "indicator"]
    model_cols = [m for m in model_order if m in df.columns]
    extra = [c for c in df.columns if c not in fixed + model_cols + ["avg_SPD"]]
    return df[fixed + model_cols + extra + ["avg_SPD"]].sort_values(["task", "indicator"]).reset_index(drop=True)


def _skin_indicator_wide(skin_df: pd.DataFrame, model_order: List[str], col: str = "helmert_r") -> pd.DataFrame:
    """Wide-format for a chosen skin metric column (default: helmert_r)."""
    if skin_df.empty:
        return pd.DataFrame()
    rows = []
    for (task, indicator), g in skin_df.groupby(["task", "indicator"], sort=False):
        row: dict = {"task": task, "indicator": indicator}
        for _, mr in g.iterrows():
            row[mr["model"]] = round(float(mr[col]), 2) if pd.notna(mr[col]) else float("nan")
        valid = g[col].dropna()
        row[f"avg_{col}"] = round(float(valid.mean()), 2) if len(valid) > 0 else float("nan")
        rows.append(row)
    df = pd.DataFrame(rows)
    fixed = ["task", "indicator"]
    model_cols = [m for m in model_order if m in df.columns]
    avg_col = f"avg_{col}"
    extra = [c for c in df.columns if c not in fixed + model_cols + [avg_col]]
    return df[fixed + model_cols + extra + [avg_col]].sort_values(["task", "indicator"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def _vector_metric_definition_md() -> str:
    return textwrap.dedent(r"""
    ## 向量偏见指标定义

    在标量偏见指标（Score ∈ [0, 1]）的基础上，引入 **向量偏见指标**，
    以保留偏见的 *方向* 信息（哪个群体被过度/不足代表）。

    ### 1) 性别偏见 — Statistical Parity Difference (SPD)

    $$\mathrm{SPD} = p_{\text{female}} - p_{\text{male}} \in [-1, +1]$$

    | 值域 | 含义 |
    |------|------|
    | SPD > 0 | 女性过度代表 |
    | SPD = 0 | 完美人口统计等价 |
    | SPD < 0 | 男性过度代表 |

    SPD 源自 Calders & Verwer (2010) 的统计性等价差异，广泛用于公平性审计。

    ### 2) 肤色偏见 — Helmert 正交对比投影

    对三类分类变量（white / yellow / black），比例向量 $\mathbf{p}=(p_w, p_y, p_b)$ 位于 2-单纯形上，
    利用 Helmert 正交对比矩阵将偏差投影到正交二维坐标：

    $$c_1 = \frac{p_w - p_b}{\sqrt{2}} \quad\text{（White-Black 轴）}$$
    $$c_2 = \frac{2p_y - p_w - p_b}{\sqrt{6}} \quad\text{（Yellow vs Others 轴）}$$
    $$r = \sqrt{c_1^2 + c_2^2} \quad\text{（偏离程度标量）}$$

    同时输出直观偏差向量 $\Delta = (p_w - 1/3,\; p_y - 1/3,\; p_b - 1/3)$。

    原点 $(c_1, c_2) = (0, 0)$ 对应均匀分布，$r$ 越大偏见越严重。
    """).strip()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_vector_report(
    cfg: Dict[str, Any],
    raw_results_df: pd.DataFrame,
    outdir: Path,
) -> Path:
    """Generate ``vector_report.md`` and supporting CSVs / figures.

    Parameters
    ----------
    cfg : dict
        Experiment configuration (from YAML).
    raw_results_df : pd.DataFrame
        Raw results with columns task, indicator, model, sensitive_attr, counts_json.
    outdir : Path
        Output directory (tables/ and figures/ subdirectories will be created).

    Returns
    -------
    Path to the generated vector_report.md.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    tab_dir = outdir / "tables"
    tab_dir.mkdir(exist_ok=True)
    fig_dir = outdir / "figures"
    fig_dir.mkdir(exist_ok=True)

    model_order = _get_model_order(cfg, raw_results_df)
    gender_df, skin_df = compute_all_vector(raw_results_df)

    # Attach model rank for ordering
    if not gender_df.empty:
        gender_df = _attach_model_rank(gender_df, model_order)
        gender_df = gender_df.sort_values(["task", "indicator", "_model_rank"]).drop(columns=["_model_rank"]).reset_index(drop=True)
    if not skin_df.empty:
        skin_df = _attach_model_rank(skin_df, model_order)
        skin_df = skin_df.sort_values(["task", "indicator", "_model_rank"]).drop(columns=["_model_rank"]).reset_index(drop=True)

    # Summaries
    gender_task_sum = _gender_task_summary(gender_df, model_order)
    skin_task_sum = _skin_task_summary(skin_df, model_order)
    gender_overall = _gender_overall_summary(gender_df, model_order)
    skin_overall = _skin_overall_summary(skin_df, model_order)
    gender_wide = _gender_indicator_wide(gender_df, model_order)
    skin_wide_r = _skin_indicator_wide(skin_df, model_order, col="helmert_r")
    skin_wide_c1 = _skin_indicator_wide(skin_df, model_order, col="c1")
    skin_wide_c2 = _skin_indicator_wide(skin_df, model_order, col="c2")

    # Save CSVs
    if not gender_df.empty:
        gender_df.round(2).to_csv(tab_dir / "vector_gender_per_indicator.csv", index=False)
    if not skin_df.empty:
        skin_df.round(2).to_csv(tab_dir / "vector_skin_per_indicator.csv", index=False)
    if not gender_task_sum.empty:
        gender_task_sum.round(2).to_csv(tab_dir / "vector_gender_task_summary.csv", index=False)
    if not skin_task_sum.empty:
        skin_task_sum.round(2).to_csv(tab_dir / "vector_skin_task_summary.csv", index=False)
    if not gender_overall.empty:
        gender_overall.round(2).to_csv(tab_dir / "vector_gender_overall.csv", index=False)
    if not skin_overall.empty:
        skin_overall.round(2).to_csv(tab_dir / "vector_skin_overall.csv", index=False)
    if not gender_wide.empty:
        gender_wide.round(2).to_csv(tab_dir / "vector_gender_indicator_wide.csv", index=False)
    if not skin_wide_r.empty:
        skin_wide_r.round(2).to_csv(tab_dir / "vector_skin_helmert_r_wide.csv", index=False)

    # Generate visualizations
    from .viz import (
        butterfly_chart,
        ternary_scatter,
        helmert_scatter,
        spd_heatmap,
        joint_3d_scatter,
    )

    fig_paths: dict[str, Path] = {}
    if not gender_df.empty:
        p = fig_dir / "vector_gender_butterfly.png"
        butterfly_chart(gender_df, model_order, p)
        fig_paths["gender_butterfly"] = p

        p = fig_dir / "vector_gender_spd_heatmap.png"
        spd_heatmap(gender_df, model_order, p)
        fig_paths["gender_heatmap"] = p

    if not skin_df.empty:
        # Models-merged per-task plots (pool all models per indicator)
        pooled = _pool_skin_by_indicator(skin_df)
        pooled_order = ["全部模型"]
        skin_tasks = skin_df["task"].unique().tolist()
        for task in skin_tasks:
            task_pool = pooled[pooled["task"] == task]
            safe = task.replace(" ", "_").replace("/", "_")
            title_label = _task_title(task)

            p = fig_dir / f"vector_skin_ternary_merged_{safe}.png"
            ternary_scatter(task_pool, pooled_order, p,
                            title=f"Skin Colour Ternary (合并模型) — {title_label}")
            fig_paths[f"skin_ternary_merged_{task}"] = p

            p = fig_dir / f"vector_skin_helmert_merged_{safe}.png"
            helmert_scatter(task_pool, pooled_order, p,
                            title=f"Helmert Projection (合并模型) — {title_label}")
            fig_paths[f"skin_helmert_merged_{task}"] = p

        # Sora / Sora2 specific ternary plots for illegal_behavior task
        ILLEGAL_TASK = "illegal_behavior"
        SORA_MODELS = ["Sora", "Sora2"]
        sora_illegal = skin_df[
            (skin_df["task"] == ILLEGAL_TASK) & (skin_df["model"].isin(SORA_MODELS))
        ]
        if not sora_illegal.empty:
            title_label = _task_title(ILLEGAL_TASK)

            # (a) 分别：每个模型一个颜色
            p = fig_dir / f"vector_skin_ternary_sora_split_{ILLEGAL_TASK}.png"
            ternary_scatter(
                sora_illegal, SORA_MODELS, p,
                title=f"Skin Colour Ternary (Sora 与 Sora2 分别) — {title_label}",
            )
            fig_paths[f"skin_ternary_sora_split_{ILLEGAL_TASK}"] = p

            # (b) 合并：将 Sora 与 Sora2 的计数按指标池化
            sora_pooled = _pool_skin_by_indicator(sora_illegal)
            if not sora_pooled.empty:
                sora_pooled = sora_pooled.copy()
                sora_pooled["model"] = "Sora + Sora2"
                p = fig_dir / f"vector_skin_ternary_sora_merged_{ILLEGAL_TASK}.png"
                ternary_scatter(
                    sora_pooled, ["Sora + Sora2"], p,
                    title=f"Skin Colour Ternary (Sora + Sora2 合并) — {title_label}",
                )
                fig_paths[f"skin_ternary_sora_merged_{ILLEGAL_TASK}"] = p

        # Per-task per-model plots
        for task in skin_tasks:
            task_sub = skin_df[skin_df["task"] == task]
            safe = task.replace(" ", "_").replace("/", "_")
            title_label = _task_title(task)

            p = fig_dir / f"vector_skin_ternary_{safe}.png"
            ternary_scatter(task_sub, model_order, p,
                            title=f"Skin Colour Ternary — {title_label}")
            fig_paths[f"skin_ternary_{task}"] = p

            p = fig_dir / f"vector_skin_helmert_{safe}.png"
            helmert_scatter(task_sub, model_order, p,
                            title=f"Helmert Projection — {title_label}")
            fig_paths[f"skin_helmert_{task}"] = p

    # 3-D joint scatter (SPD × c1 × c2)  — requires both gender & skin data
    if not gender_df.empty and not skin_df.empty:
        joint = gender_df[["task", "indicator", "model", "SPD"]].merge(
            skin_df[["task", "indicator", "model", "c1", "c2"]],
            on=["task", "indicator", "model"],
        )
        if not joint.empty:
            joint_tasks = joint["task"].unique().tolist()
            for task in joint_tasks:
                task_sub = joint[joint["task"] == task]
                safe = task.replace(" ", "_").replace("/", "_")
                title_label = _task_title(task)
                p = fig_dir / f"vector_joint_3d_{safe}.png"
                joint_3d_scatter(task_sub, model_order, p,
                                 title=f"Gender × Skin Joint Scatter — {title_label}")
                fig_paths[f"joint_3d_{task}"] = p

    # Build markdown
    md: list[str] = []
    md.append("# 向量偏见指标分析\n")
    md.append(_vector_metric_definition_md())

    # --- Gender section ---
    md.append("\n\n## 性别偏见向量分析（SPD）\n")
    if gender_df.empty:
        md.append("（数据中无性别偏见记录）\n")
    else:
        md.append("### 1) 各指标 SPD（逐指标 × 模型宽表）\n")
        md.append("正值 → 女性过度代表；负值 → 男性过度代表。\n")
        md.append(gender_wide.to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 2) 逐指标详细数据\n")
        detail_cols = ["task", "indicator", "model", "p_female", "p_male", "SPD"]
        md.append(gender_df[detail_cols].to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 3) 分任务 SPD 汇总\n")
        md.append(gender_task_sum.to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 4) 模型总体 SPD 汇总\n")
        md.append(gender_overall.to_markdown(index=False, floatfmt=".2f"))

        if "gender_butterfly" in fig_paths:
            rel = fig_paths["gender_butterfly"].relative_to(outdir)
            md.append(f"\n\n### 性别 SPD 蝴蝶图\n\n![Gender SPD Butterfly Chart]({rel})\n")
        if "gender_heatmap" in fig_paths:
            rel = fig_paths["gender_heatmap"].relative_to(outdir)
            md.append(f"\n### 性别 SPD 热力图\n\n![Gender SPD Heatmap]({rel})\n")

    # --- Skin section ---
    md.append("\n\n## 肤色偏见向量分析（Helmert 投影）\n")
    if skin_df.empty:
        md.append("（数据中无肤色偏见记录）\n")
    else:
        md.append("### 1) Helmert 偏离度 $r$（逐指标 × 模型宽表）\n")
        md.append(skin_wide_r.to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 2) Helmert $c_1$（White-Black 轴，逐指标 × 模型宽表）\n")
        md.append(skin_wide_c1.to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 3) Helmert $c_2$（Yellow vs Others 轴，逐指标 × 模型宽表）\n")
        md.append(skin_wide_c2.to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 4) 逐指标详细数据\n")
        detail_cols = ["task", "indicator", "model", "p_white", "p_yellow", "p_black",
                       "delta_w", "delta_y", "delta_b", "c1", "c2", "helmert_r"]
        md.append(skin_df[detail_cols].to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 5) 分任务 Helmert 汇总\n")
        md.append(skin_task_sum.to_markdown(index=False, floatfmt=".2f"))

        md.append("\n\n### 6) 模型总体 Helmert 汇总\n")
        md.append(skin_overall.to_markdown(index=False, floatfmt=".2f"))

        # Models-merged plots (per task)
        skin_tasks = skin_df["task"].unique().tolist()
        for task in skin_tasks:
            title_label = _task_title(task)
            mk_t = f"skin_ternary_merged_{task}"
            mk_h = f"skin_helmert_merged_{task}"
            if mk_t in fig_paths:
                rel = fig_paths[mk_t].relative_to(outdir)
                md.append(f"\n\n### 肤色三元散点图（合并模型）— {title_label}\n\n![Ternary merged — {title_label}]({rel})\n")
            # Sora / Sora2 specific ternary plots, only for illegal_behavior
            if task == "illegal_behavior":
                sora_split_key = f"skin_ternary_sora_split_{task}"
                sora_merged_key = f"skin_ternary_sora_merged_{task}"
                if sora_split_key in fig_paths:
                    rel = fig_paths[sora_split_key].relative_to(outdir)
                    md.append(f"\n### 肤色三元散点图（Sora 与 Sora2 分别）— {title_label}\n\n![Ternary Sora split — {title_label}]({rel})\n")
                if sora_merged_key in fig_paths:
                    rel = fig_paths[sora_merged_key].relative_to(outdir)
                    md.append(f"\n### 肤色三元散点图（Sora + Sora2 合并）— {title_label}\n\n![Ternary Sora merged — {title_label}]({rel})\n")
            if mk_h in fig_paths:
                rel = fig_paths[mk_h].relative_to(outdir)
                md.append(f"\n### Helmert 投影散点图（合并模型）— {title_label}\n\n![Helmert merged — {title_label}]({rel})\n")

        # Per-task per-model plots
        for task in skin_tasks:
            title_label = _task_title(task)
            ternary_key = f"skin_ternary_{task}"
            helmert_key = f"skin_helmert_{task}"
            if ternary_key in fig_paths:
                rel = fig_paths[ternary_key].relative_to(outdir)
                md.append(f"\n\n### 肤色三元散点图（按模型）— {title_label}\n\n![Skin Ternary — {title_label}]({rel})\n")
            if helmert_key in fig_paths:
                rel = fig_paths[helmert_key].relative_to(outdir)
                md.append(f"\n### Helmert 投影散点图（按模型）— {title_label}\n\n![Helmert — {title_label}]({rel})\n")

    # --- Joint 3-D section ---
    joint_keys = [k for k in fig_paths if k.startswith("joint_3d_")]
    if joint_keys:
        md.append("\n\n## 性别 × 肤色联合三维散点图\n")
        md.append("> **注意**：SPD（性别）与 Helmert $c_1, c_2$（肤色）来自不同概率空间，")
        md.append("> 三轴间的欧氏距离 **不具备** 统计学意义。此图仅作为探索性展示，")
        md.append("> 帮助直观观察同一指标在性别与肤色两个维度上偏见的联合分布。\n")
        for k in joint_keys:
            task = k.removeprefix("joint_3d_")
            title_label = _task_title(task)
            rel = fig_paths[k].relative_to(outdir)
            md.append(f"\n### 联合三维散点图 — {title_label}\n\n![Joint 3D — {title_label}]({rel})\n")

    report_path = outdir / "vector_report.md"
    report_path.write_text("\n".join(md).strip() + "\n", encoding="utf-8")
    return report_path
