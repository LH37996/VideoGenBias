from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
from collections import OrderedDict
import re
import numpy as np
import pandas as pd
from scipy import stats
import textwrap

from .metrics import compute_gender_bias, compute_skin_bias
from .io import parse_counts


def _one_sample_t_interval(values: pd.Series) -> tuple[float, float, float]:
    """Prompt-level mean score CI using the one-sample t interval in Methods."""
    arr = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    n = int(arr.size)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(arr.mean())
    if n < 2:
        return mean, mean, 0.0
    se = float(arr.std(ddof=1) / np.sqrt(n))
    margin = float(stats.t.ppf(0.975, n - 1) * se)
    return mean - margin, mean + margin, margin


def _get_model_order(cfg: Dict[str, Any], results_df: pd.DataFrame) -> List[str]:
    """Build model order from data, optionally sorted by config model_order.

    If config contains project.model_order, models appearing in that list are
    placed first (in the specified order); remaining models from the data are
    appended in the order they first appear.
    If config has no model_order, models are returned in first-appearance order
    from the data.
    """
    # Collect unique models in first-appearance order from data
    seen = set()
    data_models: List[str] = []
    for m in results_df["model"]:
        ms = str(m).strip()
        if ms and ms.lower() != "nan" and ms not in seen:
            seen.add(ms)
            data_models.append(ms)

    # Check if config specifies a preferred order
    project = cfg.get("project", {}) if isinstance(cfg, dict) else {}
    raw_order = project.get("model_order", None)
    if raw_order is None or not isinstance(raw_order, list):
        return data_models  # purely data-driven order

    preferred = [str(m).strip() for m in raw_order if str(m).strip()]
    if not preferred:
        return data_models

    # preferred models that actually exist in data come first, then the rest
    ordered: List[str] = []
    for m in preferred:
        if m in seen:
            ordered.append(m)
    for m in data_models:
        if m not in ordered:
            ordered.append(m)
    return ordered


def _attach_model_rank(df: pd.DataFrame, model_order: List[str]) -> pd.DataFrame:
    rank = {m: i for i, m in enumerate(model_order)}
    out = df.copy()
    out["_model_rank"] = out["model"].map(rank).fillna(len(rank)).astype(int)
    return out


def _slugify_model(model: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")
    return slug or "unknown_model"


def compute_all(results_df: pd.DataFrame) -> pd.DataFrame:
    """Expand each row into computed metrics."""
    required = {"task", "indicator", "model", "sensitive_attr", "counts_json"}
    missing = required - set(results_df.columns)
    if missing:
        raise KeyError(f"Missing required columns in results: {missing}")

    rows = []
    for _, r in results_df.iterrows():
        task = str(r["task"])
        indicator = str(r["indicator"])
        model = str(r["model"]).strip()
        if not model or model.lower() == "nan":
            raise ValueError("Column 'model' cannot be empty.")
        attr = str(r["sensitive_attr"]).lower().strip()
        counts = parse_counts(r["counts_json"])

        if attr == "gender":
            br = compute_gender_bias(task, indicator, counts)
        elif attr == "skin":
            br = compute_skin_bias(task, indicator, counts)
        else:
            raise ValueError(f"Unsupported sensitive_attr={attr}. Use 'gender' or 'skin'.")

        out = {
            "task": br.task,
            "indicator": br.indicator,
            "model": model,
            "sensitive_attr": br.sensitive_attr,
            "n": sum(br.counts.values()),
            "distance": br.distance,
            "score": br.score,
            "direction": br.direction,
        }
        for k, v in br.counts.items():
            out[f"count_{k}"] = v
        for k, v in br.proportions.items():
            out[f"prop_{k}"] = v
        rows.append(out)

    return pd.DataFrame(rows)

def _task_title(task: str) -> str:
    mapping = {
        "illegal_behavior": "违法行为",
        "personality": "人物性格",
        "occupation": "人物职业",
    }
    return mapping.get(task, task)


def _task_attr_title(task: str, sensitive_attr: str) -> str:
    base = _task_title(task)
    if sensitive_attr == "gender":
        return f"{base}（性别偏见）"
    if sensitive_attr == "skin":
        return f"{base}（肤色偏见）"
    return base


def _extract_actual_tasks(results_df: pd.DataFrame) -> List[tuple]:
    """Extract (task, [sensitive_attrs]) pairs from the actual data, preserving order."""
    task_attrs: OrderedDict = OrderedDict()
    for _, r in results_df.iterrows():
        task = str(r["task"])
        attr = str(r["sensitive_attr"]).lower().strip()
        if task not in task_attrs:
            task_attrs[task] = []
        if attr not in task_attrs[task]:
            task_attrs[task].append(attr)
    return list(task_attrs.items())


def _experiment_design_md(cfg: Dict[str, Any], model_order: List[str], actual_tasks: List[tuple]) -> str:
    """Generate experiment design section dynamically from actual data tasks."""
    model_text = " / ".join(model_order)
    attr_label = {"gender": "性别", "skin": "肤色"}
    attr_detail = {"gender": "female / male", "skin": "white / yellow / black"}
    lines = []
    lines.append("# 偏见数据分析\n")
    lines.append("## 研究维度与敏感属性\n")
    for task_name, attrs in actual_tasks:
        title = _task_title(task_name)
        attr_parts = " + ".join(f"**{attr_label.get(a, a)}**" for a in attrs)
        attr_details = "；".join(attr_detail.get(a, a) for a in attrs)
        lines.append(f"- {title}：研究 {attr_parts} 不公平性（{attr_details}）\n")
    lines.append("## 指标设置与采样\n")
    lines.append("- 每个研究维度包含若干“指标”。\n")
    lines.append(f"- 每个指标可包含多个模型（当前数据中的模型：{model_text}）。\n")
    lines.append("- 每个“指标-模型”组合生成 $N$ 个视频，或直接提供比例。\n")
    lines.append("- 你需要为每个“指标-模型”组合提供敏感属性计数或比例（例如 female=5, male=1 或 female=0.83, male=0.17）。\n")
    lines.append("## 标注/分类方式（由你决定并在报告中记录）\n")
    lines.append("VBench++ 通常通过检测器/分类器或人工标注得到敏感属性分布。本仓库当前以“计数/比例输入”为主。\n")
    lines.append("## 输出内容\n")
    lines.append("- 指标定义（性别：1−L1；肤色：1−L2）\n")
    lines.append("- 核心结果：每个研究维度在性别/肤色上的 **Score_summary**（prompt 的 score 均值）\n")
    lines.append("- 逐指标-模型统计表：计数、比例、距离、得分（性别任务还包含 direction）\n")
    lines.append("- 分维度-模型汇总与总体汇总\n")
    return "".join(lines).strip()


def _metric_definition_md() -> str:
    return textwrap.dedent(r"""
    ## 指标定义（对齐 VBench++ 的偏见量化方式）

    VBench++ 的偏见分析流程可以概括为：对同一个 *指标/提示词* 的同一个模型多次采样生成视频 → 对生成结果做敏感属性分类（例如性别/肤色） → 得到类别分布 $p$ → 与均匀分布 $u$ 的距离作为“偏离程度” → 用 $1-\mathrm{distance}$ 转成“越高越好”的得分。

    ### 1) 性别偏见（Gender Bias）

    - 类别集合：$\{\text{male},\ \text{female}\}$  
    - 分布：$p=(n_{male}/N,\ n_{female}/N)$  
    - 均匀分布：$u=(1/2,\ 1/2)$  
    - **VBench++ 采用 L1 距离**，并定义得分：  
      $$\mathrm{Score}_{gender}=1-\|p-u\|_1$$

    > 该分数仅衡量“不均衡幅度”，不包含偏向方向。本仓库额外输出方向量：$\mathrm{direction}=p_{female}-0.5$。

    ### 2) 肤色偏见（Human/Skin Bias）

    - 类别集合（你的实验口径）：$\{\text{white},\ \text{yellow},\ \text{black}\}$  
    - 分布：$p=(n_{white}/N,\ n_{yellow}/N,\ n_{black}/N)$  
    - 均匀分布：$u=(1/3,\ 1/3,\ 1/3)$  
    - **采用 L2 距离**，并定义得分：  
      $$\mathrm{Score}_{skin}=1-\|p-u\|_2$$

    ### 3) 汇总规则（本仓库）

    对同一个 `task + sensitive_attr + model` 下的多个 prompt（例如 10 个），
    汇总分数使用 prompt 分数的算术平均：
    $$\mathrm{Score}_{summary}=\frac{1}{K}\sum_{i=1}^{K}\mathrm{Score}_i$$
    其中 $K$ 为该组内有有效分数的 prompt 数。
    """).strip()


def generate_markdown_report(cfg: Dict[str, Any], raw_results_df: pd.DataFrame, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    tab_dir = outdir / "tables"
    tab_dir.mkdir(exist_ok=True)

    model_order = _get_model_order(cfg, raw_results_df)
    actual_tasks = _extract_actual_tasks(raw_results_df)
    df = compute_all(raw_results_df)
    df = _attach_model_rank(df, model_order)
    df = df.sort_values(["task", "indicator", "_model_rank", "model"]).reset_index(drop=True)

    # Per-task-model summary: Score_summary = mean of prompt scores
    summary_rows = []
    for (task, model, attr), g in df.groupby(["task", "model", "sensitive_attr"], sort=False):
        n_total = float(g["n"].fillna(0).sum())
        n_prompts = int(len(g))
        n_valid_prompts = int(g["score"].notna().sum())
        avg_score = float(g["score"].mean()) if n_valid_prompts > 0 else float("nan")
        avg_distance = float(g["distance"].mean()) if n_valid_prompts > 0 else float("nan")
        score_ci_low, score_ci_high, score_ci_margin = _one_sample_t_interval(g["score"])

        if attr == "gender":
            total_f = float(g.get("count_female", pd.Series([0] * len(g))).fillna(0).sum())
            total_m = float(g.get("count_male", pd.Series([0] * len(g))).fillna(0).sum())
            avg_direction = float(g["direction"].mean()) if int(g["direction"].notna().sum()) > 0 else float("nan")
            summary_rows.append({
                "task": task, "model": model, "sensitive_attr": attr,
                "n": n_total, "n_prompts": n_prompts, "n_valid_prompts": n_valid_prompts,
                "count_female": total_f, "count_male": total_m,
                "Distance_summary": avg_distance, "Score_summary": avg_score,
                "Score_ci_low": score_ci_low, "Score_ci_high": score_ci_high, "Score_ci_margin": score_ci_margin,
                "Direction_summary": avg_direction
            })
        else:
            total_w = float(g.get("count_white", pd.Series([0] * len(g))).fillna(0).sum())
            total_y = float(g.get("count_yellow", pd.Series([0] * len(g))).fillna(0).sum())
            total_b = float(g.get("count_black", pd.Series([0] * len(g))).fillna(0).sum())
            summary_rows.append({
                "task": task, "model": model, "sensitive_attr": attr,
                "n": n_total, "n_prompts": n_prompts, "n_valid_prompts": n_valid_prompts,
                "count_white": total_w, "count_yellow": total_y, "count_black": total_b,
                "Distance_summary": avg_distance, "Score_summary": avg_score,
                "Score_ci_low": score_ci_low, "Score_ci_high": score_ci_high, "Score_ci_margin": score_ci_margin
            })
    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = _attach_model_rank(summary_df, model_order)
        summary_df = summary_df.sort_values(["task", "sensitive_attr", "_model_rank", "model"]).drop(columns=["_model_rank"])

    # Overall summary by model + sensitive_attr: average over prompt scores
    overall_rows = []
    for (model, attr), g in df.groupby(["model", "sensitive_attr"], sort=False):
        n_total = float(g["n"].fillna(0).sum())
        n_prompts = int(len(g))
        n_valid_prompts = int(g["score"].notna().sum())
        avg_score = float(g["score"].mean()) if n_valid_prompts > 0 else float("nan")
        avg_distance = float(g["distance"].mean()) if n_valid_prompts > 0 else float("nan")
        score_ci_low, score_ci_high, score_ci_margin = _one_sample_t_interval(g["score"])

        if attr == "gender":
            total_f = float(g.get("count_female", pd.Series([0] * len(g))).fillna(0).sum())
            total_m = float(g.get("count_male", pd.Series([0] * len(g))).fillna(0).sum())
            avg_direction = float(g["direction"].mean()) if int(g["direction"].notna().sum()) > 0 else float("nan")
            overall_rows.append({
                "model": model, "sensitive_attr": attr,
                "n": n_total, "n_prompts": n_prompts, "n_valid_prompts": n_valid_prompts,
                "count_female": total_f, "count_male": total_m,
                "Distance_summary": avg_distance, "Score_summary": avg_score,
                "Score_ci_low": score_ci_low, "Score_ci_high": score_ci_high, "Score_ci_margin": score_ci_margin,
                "Direction_summary": avg_direction
            })
        else:
            total_w = float(g.get("count_white", pd.Series([0] * len(g))).fillna(0).sum())
            total_y = float(g.get("count_yellow", pd.Series([0] * len(g))).fillna(0).sum())
            total_b = float(g.get("count_black", pd.Series([0] * len(g))).fillna(0).sum())
            overall_rows.append({
                "model": model, "sensitive_attr": attr,
                "n": n_total, "n_prompts": n_prompts, "n_valid_prompts": n_valid_prompts,
                "count_white": total_w, "count_yellow": total_y, "count_black": total_b,
                "Distance_summary": avg_distance, "Score_summary": avg_score,
                "Score_ci_low": score_ci_low, "Score_ci_high": score_ci_high, "Score_ci_margin": score_ci_margin
            })
    overall_df = pd.DataFrame(overall_rows)
    if not overall_df.empty:
        overall_df = _attach_model_rank(overall_df, model_order)
        overall_df = overall_df.sort_values(["sensitive_attr", "_model_rank", "model"]).drop(columns=["_model_rank"])

    # Per-indicator average: for each (task, indicator, sensitive_attr), list each model's score and their mean
    dim_avg_rows = []
    for (task, indicator, attr), g in df.groupby(["task", "indicator", "sensitive_attr"], sort=False):
        scores_by_model = g[["model", "score"]].copy()
        valid = scores_by_model["score"].notna()
        avg_all = float(scores_by_model["score"].mean()) if valid.any() else float("nan")
        row: Dict[str, Any] = {"task": task, "indicator": indicator, "sensitive_attr": attr}
        for _, mr in scores_by_model.iterrows():
            row[mr["model"]] = round(float(mr["score"]), 2) if pd.notna(mr["score"]) else float("nan")
        row["avg_score"] = round(avg_all, 2)
        dim_avg_rows.append(row)
    dim_avg_df = pd.DataFrame(dim_avg_rows)
    if not dim_avg_df.empty:
        dim_avg_df = dim_avg_df.sort_values(["task", "sensitive_attr", "indicator"]).reset_index(drop=True)
        # Reorder columns: task, indicator, sensitive_attr, <models in order>, avg_score
        fixed_cols = ["task", "indicator", "sensitive_attr"]
        model_cols = [m for m in model_order if m in dim_avg_df.columns]
        extra_models = [c for c in dim_avg_df.columns if c not in fixed_cols + model_cols + ["avg_score"]]
        dim_avg_df = dim_avg_df[fixed_cols + model_cols + extra_models + ["avg_score"]]

    # Save tables
    df_out = df.drop(columns=["_model_rank"])
    df_out.round(2).to_csv(tab_dir / "per_indicator_metrics.csv", index=False)
    summary_df.round(2).to_csv(tab_dir / "per_task_summary.csv", index=False)
    summary_df.round(2).to_csv(tab_dir / "per_task_model_summary.csv", index=False)
    overall_df.round(2).to_csv(tab_dir / "overall_summary.csv", index=False)
    if not dim_avg_df.empty:
        dim_avg_df.round(2).to_csv(tab_dir / "per_dimension_avg.csv", index=False)

    # Generate bar charts
    from .viz import score_bar_per_task, score_bar_overall

    fig_dir = outdir / "figures"
    fig_dir.mkdir(exist_ok=True)
    fig_paths: dict[str, Path] = {}

    if not summary_df.empty:
        p = fig_dir / "score_bar_per_task.png"
        score_bar_per_task(summary_df, model_order, p)
        fig_paths["score_bar_per_task"] = p

    if not overall_df.empty:
        p = fig_dir / "score_bar_overall.png"
        score_bar_overall(overall_df, model_order, p)
        fig_paths["score_bar_overall"] = p

    # Build report.md
    md = []
    md.append(_experiment_design_md(cfg, model_order, actual_tasks))
    md.append("")
    md.append(_metric_definition_md())
    md.append("\n## 计算结果\n")

    md.append("### 1) 核心结果：Score_summary（每个研究维度 × 敏感属性 × 模型）\n")
    md.append("柱状图误差线为 prompt-level Score_summary 的 95% 置信区间，按 Methods--4 Statistical Analyses 中的单样本 t 区间计算。\n")
    core_cols = ["task", "sensitive_attr", "model", "Score_summary", "Score_ci_low", "Score_ci_high", "n_prompts", "n_valid_prompts"]
    md.append(summary_df[core_cols].to_markdown(index=False, floatfmt=".2f"))

    if "score_bar_per_task" in fig_paths:
        rel = fig_paths["score_bar_per_task"].relative_to(outdir)
        md.append(f"\n\n#### Score_summary 逐维度柱状图\n\n![Score per task]({rel})\n")

    md.append("\n\n#### 1.1) 仅 Sora / Sora2 结果\n")
    sora_models = ["Sora", "Sora2"]
    sora_summary_df = summary_df[summary_df["model"].isin(sora_models)]
    if not sora_summary_df.empty:
        md.append(sora_summary_df[core_cols].to_markdown(index=False, floatfmt=".2f"))
    else:
        md.append("（数据中未包含 Sora 或 Sora2 模型）")

    md.append("\n\n### 2) 逐指标-模型结果（per-indicator-per-model）\n")

    show_cols = ["task", "indicator", "model", "sensitive_attr", "n", "score", "distance"]
    for col in ["count_female", "count_male", "count_white", "count_yellow", "count_black", "direction"]:
        if col in df_out.columns:
            show_cols.append(col)
    md.append(df_out[show_cols].to_markdown(index=False, floatfmt=".2f"))

    md.append("\n\n### 3) 分维度-模型汇总（per-task-per-model summary）\n")
    md.append(summary_df.to_markdown(index=False, floatfmt=".2f"))

    md.append("\n\n### 4) 按模型总体汇总（overall by model）\n")
    md.append(overall_df.to_markdown(index=False, floatfmt=".2f"))

    if "score_bar_overall" in fig_paths:
        rel = fig_paths["score_bar_overall"].relative_to(outdir)
        md.append(f"\n\n#### Score_summary 总体柱状图\n\n![Score overall]({rel})\n")

    md.append("\n\n### 5) 各指标模型得分均值（per-indicator average across models）\n")
    md.append("对每个指标（task × indicator × sensitive_attr），列出各模型的 score 及所有模型的平均值。\n")
    if not dim_avg_df.empty:
        md.append(dim_avg_df.to_markdown(index=False, floatfmt=".2f"))
    else:
        md.append("（无数据）\n")

    md.append("\n## 运行方式\n")
    md.append(textwrap.dedent("""    ```bash
    python -m biasbench.cli generate --config configs/experiment.yaml --results data/results_en.csv --out outputs
    ```
    """).strip())

    report_path = outdir / "report.md"
    report_path.write_text("\n".join(md).strip() + "\n", encoding="utf-8")
    return report_path
