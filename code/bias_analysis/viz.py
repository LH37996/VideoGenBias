from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import FancyArrowPatch

def _set_academic_font():
    """Set Times New Roman as the primary font with CJK fallback.

    Produces publication-quality typography.  Uses direct font.family list
    so matplotlib can fall back to a CJK font for Chinese glyphs that
    Times New Roman does not cover.
    """
    try:
        from matplotlib import font_manager
        available = {f.name for f in font_manager.fontManager.ttflist}

        family_list: list[str] = []
        if "Times New Roman" in available:
            family_list.append("Times New Roman")
        elif "DejaVu Serif" in available:
            family_list.append("DejaVu Serif")

        cjk_candidates = [
            "PingFang SC", "Noto Sans CJK SC", "Noto Sans CJK JP",
            "SimHei", "Microsoft YaHei", "STSong",
            "WenQuanYi Zen Hei",
        ]
        for name in cjk_candidates:
            if name in available:
                family_list.append(name)
                break

        if family_list:
            plt.rcParams["font.family"] = family_list
        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["mathtext.fontset"] = "stix"
    except Exception:
        return

# Keep old name as alias so callers do not break
_set_cjk_font_if_available = _set_academic_font

def radar_chart(labels: List[str], values: List[float], title: str, outpath: Path,
                rmin: float = 0.0, rmax: float = 1.0, reference_r: Optional[List[float]] = None):
    """Simple radar chart for bias scores per indicator."""
    _set_cjk_font_if_available()
    labels = list(labels)
    values = list(values)
    n = len(labels)
    if n == 0:
        raise ValueError("labels is empty.")
    angles = np.linspace(0, 2*np.pi, n, endpoint=False).tolist()
    values_loop = values + [values[0]]
    angles_loop = angles + [angles[0]]

    plt.figure(figsize=(8, 8))
    ax = plt.subplot(111, polar=True)
    ax.plot(angles_loop, values_loop, linewidth=2)
    ax.fill(angles_loop, values_loop, alpha=0.15)
    ax.set_thetagrids(np.degrees(angles), labels)
    ax.set_ylim(rmin, rmax)
    ax.set_title(title, va="bottom")

    if reference_r:
        for rr in reference_r:
            ax.plot(angles_loop, [rr] * len(angles_loop), linewidth=1, alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# Color palette helper
# ---------------------------------------------------------------------------

_MODEL_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
]


def _model_color_map(model_order: List[str]) -> Dict[str, str]:
    return {m: _MODEL_COLORS[i % len(_MODEL_COLORS)] for i, m in enumerate(model_order)}


# ---------------------------------------------------------------------------
# 1) Butterfly chart — Gender SPD per indicator
# ---------------------------------------------------------------------------

def butterfly_chart(
    gender_df: pd.DataFrame,
    model_order: List[str],
    outpath: Path,
    figsize: tuple = (12, 0),  # height auto-scaled
) -> None:
    """Horizontal diverging-bar (butterfly) chart of Gender SPD per indicator.

    Bars extend left (male-biased, SPD < 0) or right (female-biased, SPD > 0).
    """
    _set_cjk_font_if_available()
    if gender_df.empty:
        return

    cmap = _model_color_map(model_order)
    tasks = gender_df["task"].unique()

    indicators = gender_df.drop_duplicates(subset=["task", "indicator"])[["task", "indicator"]]
    labels = [f"{_short_task(row['task'])}|{row['indicator']}" for _, row in indicators.iterrows()]
    n_indicators = len(labels)
    n_models = len(model_order)
    bar_height = 0.8 / max(n_models, 1)

    fig_h = max(4, n_indicators * 0.55 + 1.5)
    fig, ax = plt.subplots(figsize=(figsize[0], fig_h))

    y_positions = np.arange(n_indicators)

    for mi, model in enumerate(model_order):
        vals = []
        for _, row in indicators.iterrows():
            mask = (gender_df["task"] == row["task"]) & (gender_df["indicator"] == row["indicator"]) & (gender_df["model"] == model)
            sub = gender_df.loc[mask, "SPD"]
            vals.append(float(sub.iloc[0]) if len(sub) > 0 and pd.notna(sub.iloc[0]) else 0.0)
        offsets = y_positions - 0.4 + bar_height * (mi + 0.5)
        ax.barh(offsets, vals, height=bar_height * 0.9, color=cmap.get(model, "#999"),
                label=model, edgecolor="white", linewidth=0.5)

    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("SPD  (← male-biased | female-biased →)")
    ax.set_title("Gender SPD Butterfly Chart")
    ax.legend(loc="best", fontsize=8)
    ax.invert_yaxis()

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# 2) Ternary scatter — Skin proportions on simplex
# ---------------------------------------------------------------------------

def _simplex_to_cartesian(pw: float, py_: float, pb: float):
    """Convert (p_white, p_yellow, p_black) to 2D Cartesian for ternary plot.

    Vertices: white=(0,0), black=(1,0), yellow=(0.5, sqrt(3)/2).
    """
    x = pb + 0.5 * py_
    y = (math.sqrt(3) / 2.0) * py_
    return x, y


def ternary_scatter(
    skin_df: pd.DataFrame,
    model_order: List[str],
    outpath: Path,
    figsize: tuple = (8, 7),
    title: Optional[str] = None,
) -> None:
    """Ternary scatter plot of skin colour proportions, coloured by model."""
    _set_cjk_font_if_available()
    if skin_df.empty:
        return

    cmap = _model_color_map(model_order)
    fig, ax = plt.subplots(figsize=figsize)

    # Draw triangle
    h = math.sqrt(3) / 2.0
    triangle = plt.Polygon([(0, 0), (1, 0), (0.5, h)], fill=False, edgecolor="gray", linewidth=1.2)
    ax.add_patch(triangle)

    # Vertex labels
    ax.text(0 - 0.04, 0 - 0.04, "White", ha="center", fontsize=10, fontweight="bold")
    ax.text(1 + 0.04, 0 - 0.04, "Black", ha="center", fontsize=10, fontweight="bold")
    ax.text(0.5, h + 0.04, "Yellow", ha="center", fontsize=10, fontweight="bold")

    # Grid lines (internal lines at 1/3 and 2/3)
    for frac in [1 / 3, 2 / 3]:
        # Lines of constant p_white
        x0, y0 = _simplex_to_cartesian(frac, 1 - frac, 0)
        x1, y1 = _simplex_to_cartesian(frac, 0, 1 - frac)
        ax.plot([x0, x1], [y0, y1], color="lightgray", linewidth=0.5, zorder=0)
        # Lines of constant p_yellow
        x0, y0 = _simplex_to_cartesian(1 - frac, frac, 0)
        x1, y1 = _simplex_to_cartesian(0, frac, 1 - frac)
        ax.plot([x0, x1], [y0, y1], color="lightgray", linewidth=0.5, zorder=0)
        # Lines of constant p_black
        x0, y0 = _simplex_to_cartesian(0, 1 - frac, frac)
        x1, y1 = _simplex_to_cartesian(1 - frac, 0, frac)
        ax.plot([x0, x1], [y0, y1], color="lightgray", linewidth=0.5, zorder=0)

    # Uniform point
    cx, cy = _simplex_to_cartesian(1 / 3, 1 / 3, 1 / 3)
    ax.plot(cx, cy, marker="+", markersize=14, color="red", zorder=5, markeredgewidth=2)

    # Scatter points
    for model in model_order:
        sub = skin_df[skin_df["model"] == model]
        if sub.empty:
            continue
        xs, ys = [], []
        for _, row in sub.iterrows():
            x, y = _simplex_to_cartesian(row["p_white"], row["p_yellow"], row["p_black"])
            xs.append(x)
            ys.append(y)
        ax.scatter(xs, ys, color=cmap.get(model, "#999"), label=model, s=50, alpha=0.75, edgecolors="white", linewidth=0.5, zorder=3)

    ax.set_xlim(-0.1, 1.1)
    ax.set_ylim(-0.1, h + 0.1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title or "Skin Colour Ternary Scatter", pad=16)
    ax.legend(loc="upper right", fontsize=8)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# 3) Helmert scatter — c1 vs c2
# ---------------------------------------------------------------------------

def helmert_scatter(
    skin_df: pd.DataFrame,
    model_order: List[str],
    outpath: Path,
    figsize: tuple = (8, 7),
    title: Optional[str] = None,
) -> None:
    """Scatter plot of Helmert coordinates (c1, c2), coloured by model.

    Origin = uniform distribution; c1 axis = White-Black; c2 axis = Yellow vs Others.
    """
    _set_cjk_font_if_available()
    if skin_df.empty:
        return

    cmap = _model_color_map(model_order)
    fig, ax = plt.subplots(figsize=figsize)

    # Reference lines
    ax.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax.axvline(0, color="gray", linewidth=0.6, linestyle="--")
    # Reference circle at r = 0.1, 0.2
    for r in [0.1, 0.2, 0.3]:
        circle = plt.Circle((0, 0), r, fill=False, color="lightgray", linewidth=0.5, linestyle=":")
        ax.add_patch(circle)

    for model in model_order:
        sub = skin_df[skin_df["model"] == model]
        if sub.empty:
            continue
        c1_vals = sub["c1"].dropna().values
        c2_vals = sub["c2"].dropna().values
        ax.scatter(c1_vals, c2_vals, color=cmap.get(model, "#999"), label=model,
                   s=55, alpha=0.75, edgecolors="white", linewidth=0.5, zorder=3)

    ax.set_xlabel("$c_1$ (White–Black axis: + = White-biased)")
    ax.set_ylabel("$c_2$ (Yellow vs Others: + = Yellow-biased)")
    ax.set_title(title or "Helmert Contrast Projection Scatter")
    ax.set_aspect("equal")
    ax.legend(loc="best", fontsize=8)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# 4) SPD heatmap — indicator × model
# ---------------------------------------------------------------------------

def spd_heatmap(
    gender_df: pd.DataFrame,
    model_order: List[str],
    outpath: Path,
    figsize: tuple = (10, 0),  # height auto-scaled
) -> None:
    """Heatmap of Gender SPD values, rows = (task | indicator), columns = model.

    Diverging colour map: blue (male-biased) ↔ white (parity) ↔ red (female-biased).
    """
    _set_cjk_font_if_available()
    if gender_df.empty:
        return

    indicators = gender_df.drop_duplicates(subset=["task", "indicator"])[["task", "indicator"]]
    labels = [f"{_short_task(row['task'])}|{row['indicator']}" for _, row in indicators.iterrows()]

    matrix = []
    for _, irow in indicators.iterrows():
        row_vals = []
        for model in model_order:
            mask = (gender_df["task"] == irow["task"]) & (gender_df["indicator"] == irow["indicator"]) & (gender_df["model"] == model)
            sub = gender_df.loc[mask, "SPD"]
            row_vals.append(float(sub.iloc[0]) if len(sub) > 0 and pd.notna(sub.iloc[0]) else float("nan"))
        matrix.append(row_vals)

    arr = np.array(matrix)
    vmax = max(abs(np.nanmin(arr)), abs(np.nanmax(arr)), 0.1)

    fig_h = max(4, len(labels) * 0.4 + 2)
    fig, ax = plt.subplots(figsize=(figsize[0], fig_h))
    cax = ax.imshow(arr, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax, interpolation="nearest")
    fig.colorbar(cax, ax=ax, label="SPD", shrink=0.8)

    ax.set_xticks(range(len(model_order)))
    ax.set_xticklabels(model_order, fontsize=9)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_title("Gender SPD Heatmap (Blue=Male-biased, Red=Female-biased)")

    # Annotate cells
    for i in range(len(labels)):
        for j in range(len(model_order)):
            val = arr[i, j]
            if not np.isnan(val):
                color = "white" if abs(val) > vmax * 0.6 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# 5) 3-D joint scatter — SPD × Helmert (c1, c2)
# ---------------------------------------------------------------------------

_MARKERS = ["o", "s", "D", "^", "v", "P", "*", "X", "h", "p"]


def joint_3d_scatter(
    merged_df: pd.DataFrame,
    model_order: List[str],
    outpath: Path,
    title: str | None = None,
) -> None:
    """3-D scatter plot with axes SPD (gender), c1 (White-Black), c2 (Yellow-Others).

    ``merged_df`` must contain columns: model, SPD, c1, c2.
    Each point is one (task, indicator, model) that has *both* gender and skin
    annotations.

    .. note::
       This is an **exploratory visualisation only**: SPD and Helmert live in
       different probability spaces and cannot be combined into a single
       meaningful distance metric.
    """
    _set_cjk_font_if_available()
    if merged_df.empty:
        return

    # Drop rows that cannot be plotted in 3-D; vector reports may legitimately
    # contain missing SPD / Helmert coordinates for some model-prompt pairs.
    plot_df = merged_df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["SPD", "c1", "c2"]
    )

    if plot_df.empty:
        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            "No finite joint points available.",
            ha="center",
            va="center",
            fontsize=12,
        )
        ax.set_title(title or "Gender x Skin Joint Scatter", pad=12)
        outpath.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(outpath, dpi=200, bbox_inches="tight")
        plt.close()
        return

    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 – registers projection

    cmap = _model_color_map(model_order)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    def _safe_lim(values: np.ndarray, baseline: float = 0.1, pad: float = 0.1) -> tuple[float, float]:
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if finite.size == 0:
            return (-0.2, 0.2)
        lower = min(float(finite.min()), -baseline) - pad
        upper = max(float(finite.max()), baseline) + pad
        if not np.isfinite(lower) or not np.isfinite(upper):
            return (-0.2, 0.2)
        if math.isclose(lower, upper):
            lower -= pad
            upper += pad
        return (lower, upper)

    # Axis limits with a small pad.
    spd_vals = plot_df["SPD"].to_numpy(dtype=float)
    c1_vals = plot_df["c1"].to_numpy(dtype=float)
    c2_vals = plot_df["c2"].to_numpy(dtype=float)
    xlim = _safe_lim(spd_vals)
    ylim = _safe_lim(c1_vals)
    zlim = _safe_lim(c2_vals)

    # Draw wall projections (shadows) — grey dots on 3 back planes
    shadow_kw = dict(color="#aaaaaa", s=12, alpha=0.45, marker=".", linewidths=0)
    ax.scatter(spd_vals, c1_vals, zlim[0], **shadow_kw)  # floor (XY)
    ax.scatter(xlim[0], c1_vals, c2_vals, **shadow_kw)    # left wall (YZ)
    ax.scatter(spd_vals, ylim[1], c2_vals, **shadow_kw)   # back wall (XZ)

    # ---- Coordinate axes through origin with arrows on positive side ----
    arrow_len = 0.06  # fraction of axis range for arrowhead offset
    ax_col = {"x": "#C0392B", "y": "#2471A3", "z": "#1E8449"}  # academic muted

    # Draw axis lines (full range)
    axis_kw = dict(linewidth=1.6, alpha=0.9, zorder=3)
    ax.plot(xlim, [0, 0], [0, 0], color=ax_col["x"], **axis_kw)
    ax.plot([0, 0], ylim, [0, 0], color=ax_col["y"], **axis_kw)
    ax.plot([0, 0], [0, 0], zlim, color=ax_col["z"], **axis_kw)

    # Arrowheads on positive direction (cone approximation via a short thick segment)
    def _arrow_seg(start, end, color):
        """Draw a tapered 'arrow' using multiple overlapping lines."""
        for w in (5.0, 3.5, 2.0):
            ax.plot(*zip(start, end), color=color, linewidth=w, alpha=0.9,
                    solid_capstyle="round", zorder=4)

    dx = (xlim[1] - xlim[0]) * arrow_len
    dy = (ylim[1] - ylim[0]) * arrow_len
    dz = (zlim[1] - zlim[0]) * arrow_len
    _arrow_seg((xlim[1] - dx, 0, 0), (xlim[1], 0, 0), ax_col["x"])
    _arrow_seg((0, ylim[1] - dy, 0), (0, ylim[1], 0), ax_col["y"])
    _arrow_seg((0, 0, zlim[1] - dz), (0, 0, zlim[1]), ax_col["z"])

    # Axis-direction labels at the positive/negative tips
    tip_kw = dict(fontsize=7.5, fontstyle="italic", alpha=0.9)
    ax.text(xlim[1], 0, 0, "  Female +", color=ax_col["x"], ha="left", **tip_kw)
    ax.text(xlim[0], 0, 0, "Male +  ", color=ax_col["x"], ha="right", **tip_kw)
    ax.text(0, ylim[1], 0, "  White +", color=ax_col["y"], ha="left", **tip_kw)
    ax.text(0, ylim[0], 0, "Black +  ", color=ax_col["y"], ha="right", **tip_kw)
    ax.text(0, 0, zlim[1], "  Yellow +", color=ax_col["z"], ha="left", **tip_kw)
    ax.text(0, 0, zlim[0], "Others +  ", color=ax_col["z"], ha="right", **tip_kw)

    # ---- Semi-transparent coordinate planes through origin ----
    plane_alpha = 0.08
    # XY plane (z=0)
    xx_plane = np.array([xlim[0], xlim[1]])
    yy_plane = np.array([ylim[0], ylim[1]])
    Xp, Yp = np.meshgrid(xx_plane, yy_plane)
    Zp = np.zeros_like(Xp)
    ax.plot_surface(Xp, Yp, Zp, color="#cccccc", alpha=plane_alpha, zorder=0,
                    edgecolor="#bbbbbb", linewidth=0.3)
    # XZ plane (y=0)
    zz_plane = np.array([zlim[0], zlim[1]])
    Xp2, Zp2 = np.meshgrid(xx_plane, zz_plane)
    Yp2 = np.zeros_like(Xp2)
    ax.plot_surface(Xp2, Yp2, Zp2, color="#cccccc", alpha=plane_alpha, zorder=0,
                    edgecolor="#bbbbbb", linewidth=0.3)
    # YZ plane (x=0)
    Yp3, Zp3 = np.meshgrid(yy_plane, zz_plane)
    Xp3 = np.zeros_like(Yp3)
    ax.plot_surface(Xp3, Yp3, Zp3, color="#cccccc", alpha=plane_alpha, zorder=0,
                    edgecolor="#bbbbbb", linewidth=0.3)

    # Scatter per model with distinct markers + stem lines to floor
    for i, model in enumerate(model_order):
        sub = plot_df[plot_df["model"] == model]
        if sub.empty:
            continue
        xs, ys, zs = sub["SPD"].values, sub["c1"].values, sub["c2"].values
        marker = _MARKERS[i % len(_MARKERS)]
        color = cmap.get(model, "grey")

        # Stem lines from each point down to the floor plane
        for x, y, z in zip(xs, ys, zs):
            ax.plot([x, x], [y, y], [zlim[0], z],
                    color=color, linewidth=0.7, alpha=0.5, linestyle=":")

        ax.scatter(
            xs, ys, zs,
            label=model,
            color=color,
            marker=marker,
            s=70,
            alpha=0.85,
            edgecolors="k",
            linewidths=0.4,
            zorder=5,
        )

    # Origin marker (parity point)
    ax.scatter([0], [0], [0], marker="x", color="black", s=100,
               linewidths=2.5, zorder=10, label="Parity")

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_zlim(zlim)
    ax.set_xlabel("SPD  (Male $\\leftarrow$ | $\\rightarrow$ Female)", fontsize=10, labelpad=10)
    ax.set_ylabel("$c_1$  (Black $\\leftarrow$ | $\\rightarrow$ White)", fontsize=10, labelpad=10)
    ax.set_zlabel("$c_2$  (Others $\\leftarrow$ | $\\rightarrow$ Yellow)", fontsize=10, labelpad=10)
    ax.set_title(title or "Gender $\\times$ Skin Joint Scatter (SPD, $c_1$, $c_2$)",
                fontsize=12, pad=14)
    ax.tick_params(labelsize=8)
    ax.view_init(elev=25, azim=-50)
    ax.legend(fontsize=7.5, loc="upper left", framealpha=0.9, ncol=2,
             edgecolor="#888888", fancybox=False)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# 6) Score bar charts — per-task and overall
# ---------------------------------------------------------------------------

_TASK_LABEL = {
    "illegal_behavior": "违法行为",
    "personality": "人物性格",
    "occupation": "人物职业",
}

_ATTR_LABEL = {"gender": "性别", "skin": "肤色"}


def score_bar_per_task(
    summary_df: pd.DataFrame,
    model_order: List[str],
    outpath: Path,
    figsize: tuple | None = None,
) -> None:
    """Grouped bar chart: Score_summary per (task × sensitive_attr), grouped by model.

    Parameters
    ----------
    summary_df : pd.DataFrame
        Must contain columns: task, sensitive_attr, model, Score_summary.
    model_order : list[str]
        Models in display order.
    outpath : Path
        Output PNG path.
    """
    _set_academic_font()
    if summary_df.empty:
        return

    cmap = _model_color_map(model_order)

    # Build group labels: (task, sensitive_attr) in data order
    groups = (
        summary_df.drop_duplicates(subset=["task", "sensitive_attr"])
        [["task", "sensitive_attr"]]
        .values.tolist()
    )
    group_labels = [
        f"{_TASK_LABEL.get(t, t)}\n({_ATTR_LABEL.get(a, a)})" for t, a in groups
    ]
    n_groups = len(groups)
    n_models = len(model_order)
    if n_groups == 0 or n_models == 0:
        return

    bar_width = 0.8 / n_models
    x = np.arange(n_groups)

    if figsize is None:
        figsize = (max(8, n_groups * 1.8), 5)
    fig, ax = plt.subplots(figsize=figsize)

    for mi, model in enumerate(model_order):
        vals = []
        yerr_low = []
        yerr_high = []
        for t, a in groups:
            row = summary_df[
                (summary_df["task"] == t)
                & (summary_df["sensitive_attr"] == a)
                & (summary_df["model"] == model)
            ]
            v = float(row["Score_summary"].iloc[0]) if len(row) > 0 and pd.notna(row["Score_summary"].iloc[0]) else 0.0
            vals.append(v)
            if len(row) > 0 and {"Score_ci_low", "Score_ci_high"}.issubset(row.columns) and pd.notna(row["Score_ci_low"].iloc[0]):
                yerr_low.append(max(0.0, v - float(row["Score_ci_low"].iloc[0])))
                yerr_high.append(max(0.0, float(row["Score_ci_high"].iloc[0]) - v))
            else:
                yerr_low.append(0.0)
                yerr_high.append(0.0)
        offset = x - 0.4 + bar_width * (mi + 0.5)
        bars = ax.bar(
            offset, vals, width=bar_width * 0.9,
            color=cmap.get(model, "#999"), label=model,
            edgecolor="white", linewidth=0.5,
            yerr=np.array([yerr_low, yerr_high]),
            error_kw={"ecolor": "#333333", "elinewidth": 0.7, "capsize": 2.0, "capthick": 0.7},
        )
        # Value labels on top of bars
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{v:.2f}", ha="center", va="bottom", fontsize=6, rotation=90,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(group_labels, fontsize=9)
    ax.set_ylabel("Score_summary  (95% CI, one-sample t)", fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.set_title("Score_summary 逐维度对比（越高越公平）", fontsize=12, pad=12)
    ax.legend(fontsize=7, loc="upper right", ncol=min(n_models, 4))
    ax.axhline(1.0, color="grey", linewidth=0.6, linestyle="--", alpha=0.5)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


def score_bar_overall(
    overall_df: pd.DataFrame,
    model_order: List[str],
    outpath: Path,
    figsize: tuple | None = None,
) -> None:
    """Grouped bar chart: overall Score_summary per model, grouped by sensitive_attr.

    Parameters
    ----------
    overall_df : pd.DataFrame
        Must contain columns: model, sensitive_attr, Score_summary.
    model_order : list[str]
        Models in display order.
    outpath : Path
        Output PNG path.
    """
    _set_academic_font()
    if overall_df.empty:
        return

    attrs = overall_df["sensitive_attr"].unique().tolist()
    attr_colors = {"gender": "#4C72B0", "skin": "#DD8452"}
    n_attrs = len(attrs)
    n_models = len(model_order)
    if n_models == 0 or n_attrs == 0:
        return

    bar_width = 0.8 / n_attrs
    x = np.arange(n_models)

    if figsize is None:
        figsize = (max(8, n_models * 1.2), 5)
    fig, ax = plt.subplots(figsize=figsize)

    for ai, attr in enumerate(attrs):
        vals = []
        yerr_low = []
        yerr_high = []
        for model in model_order:
            row = overall_df[
                (overall_df["model"] == model) & (overall_df["sensitive_attr"] == attr)
            ]
            v = float(row["Score_summary"].iloc[0]) if len(row) > 0 and pd.notna(row["Score_summary"].iloc[0]) else 0.0
            vals.append(v)
            if len(row) > 0 and {"Score_ci_low", "Score_ci_high"}.issubset(row.columns) and pd.notna(row["Score_ci_low"].iloc[0]):
                yerr_low.append(max(0.0, v - float(row["Score_ci_low"].iloc[0])))
                yerr_high.append(max(0.0, float(row["Score_ci_high"].iloc[0]) - v))
            else:
                yerr_low.append(0.0)
                yerr_high.append(0.0)
        offset = x - 0.4 + bar_width * (ai + 0.5)
        bars = ax.bar(
            offset, vals, width=bar_width * 0.9,
            color=attr_colors.get(attr, _MODEL_COLORS[ai % len(_MODEL_COLORS)]),
            label=_ATTR_LABEL.get(attr, attr),
            edgecolor="white", linewidth=0.5,
            yerr=np.array([yerr_low, yerr_high]),
            error_kw={"ecolor": "#333333", "elinewidth": 0.8, "capsize": 2.2, "capthick": 0.8},
        )
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{v:.2f}", ha="center", va="bottom", fontsize=8,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(model_order, fontsize=9)
    ax.set_ylabel("Score_summary  (95% CI, one-sample t)", fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.set_title("Score_summary 总体对比（越高越公平）", fontsize=12, pad=12)
    ax.legend(fontsize=9, loc="upper right")
    ax.axhline(1.0, color="grey", linewidth=0.6, linestyle="--", alpha=0.5)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _short_task(task: str) -> str:
    mapping = {
        "illegal_behavior": "illegal",
        "personality": "personality",
        "occupation": "occupation",
    }
    return mapping.get(task, task)
