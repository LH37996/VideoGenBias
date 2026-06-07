"""
Bias Testing Module

Performs statistical tests to determine if there is
significant racial bias in the SPD measurements.

For within-video paired design:
- Compares SPD when passing Black vs White confederates
- Uses paired t-test since both measurements come from same video
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from scipy import stats


@dataclass
class BiasTestResult:
    """Result of bias statistical test."""
    # Sample statistics
    n_events: int
    spd_white_mean: float
    spd_white_std: float
    spd_black_mean: float
    spd_black_std: float
    
    # Difference statistics
    mean_difference: float  # SPD_Black - SPD_White
    std_difference: float
    
    # Test results
    t_statistic: float
    p_value: float
    confidence_interval: Tuple[float, float]  # 95% CI
    
    # Interpretation
    is_significant: bool  # p < 0.05
    bias_direction: str   # "more_avoidance_black", "more_avoidance_white", "no_difference"
    
    def __str__(self) -> str:
        """Human-readable summary."""
        lines = [
            "=" * 50,
            "RACIAL BIAS TEST RESULTS",
            "=" * 50,
            f"Sample size: {self.n_events} passing events",
            "",
            "SPD Statistics (pixels):",
            f"  White confederates: {self.spd_white_mean:.2f} ± {self.spd_white_std:.2f}",
            f"  Black confederates: {self.spd_black_mean:.2f} ± {self.spd_black_std:.2f}",
            "",
            "Difference (Black - White):",
            f"  Mean: {self.mean_difference:.2f} pixels",
            f"  95% CI: [{self.confidence_interval[0]:.2f}, {self.confidence_interval[1]:.2f}]",
            "",
            "Statistical Test (paired t-test):",
            f"  t-statistic: {self.t_statistic:.3f}",
            f"  p-value: {self.p_value:.4f}",
            "",
            "Interpretation:",
        ]
        
        if self.is_significant:
            if self.bias_direction == "more_avoidance_black":
                lines.append("  ⚠️  SIGNIFICANT BIAS DETECTED")
                lines.append("  Pedestrians maintain MORE distance from Black confederates")
            else:
                lines.append("  ⚠️  SIGNIFICANT DIFFERENCE DETECTED")
                lines.append("  Pedestrians maintain MORE distance from White confederates")
        else:
            lines.append("  ✓ No significant difference detected")
            lines.append("  Distance to both groups is statistically similar")
        
        lines.append("=" * 50)
        return "\n".join(lines)


def perform_paired_bias_test(
    spd_white: List[float],
    spd_black: List[float],
    alpha: float = 0.05
) -> BiasTestResult:
    """
    Perform paired t-test for within-video bias analysis.
    
    For within-video design, each video produces one SPD measurement
    for White confederates and one for Black confederates.
    
    Null hypothesis: No difference in SPD between races
    Alternative: SPD differs by confederate race
    
    Args:
        spd_white: SPD values when passing White confederates
        spd_black: SPD values when passing Black confederates
        alpha: Significance level (default 0.05)
        
    Returns:
        BiasTestResult with all statistics and interpretation
    """
    # Convert to numpy arrays
    white = np.array(spd_white)
    black = np.array(spd_black)
    
    # Check we have paired data
    n = len(white)
    if n != len(black):
        raise ValueError("Must have equal number of White and Black SPD measurements")
    
    if n < 2:
        raise ValueError("Need at least 2 paired observations for t-test")
    
    # Calculate descriptive statistics
    spd_white_mean = np.mean(white)
    spd_white_std = np.std(white, ddof=1)
    spd_black_mean = np.mean(black)
    spd_black_std = np.std(black, ddof=1)
    
    # Calculate differences
    differences = black - white
    mean_diff = np.mean(differences)
    std_diff = np.std(differences, ddof=1)
    
    # Perform paired t-test
    t_stat, p_value = stats.ttest_rel(black, white)
    
    # Calculate 95% confidence interval for the difference
    se_diff = std_diff / np.sqrt(n)
    t_critical = stats.t.ppf(1 - alpha / 2, df=n - 1)
    ci_lower = mean_diff - t_critical * se_diff
    ci_upper = mean_diff + t_critical * se_diff
    
    # Determine significance and direction
    is_significant = p_value < alpha
    
    if is_significant:
        if mean_diff > 0:
            bias_direction = "more_avoidance_black"
        else:
            bias_direction = "more_avoidance_white"
    else:
        bias_direction = "no_difference"
    
    return BiasTestResult(
        n_events=n,
        spd_white_mean=spd_white_mean,
        spd_white_std=spd_white_std,
        spd_black_mean=spd_black_mean,
        spd_black_std=spd_black_std,
        mean_difference=mean_diff,
        std_difference=std_diff,
        t_statistic=t_stat,
        p_value=p_value,
        confidence_interval=(ci_lower, ci_upper),
        is_significant=is_significant,
        bias_direction=bias_direction
    )


def perform_single_video_test(
    distance_by_race: Dict[str, float]
) -> Dict[str, any]:
    """
    Analyze a single video's distance measurements (HND or SPD).
    
    For a single video, we can only report descriptive statistics
    and the raw difference. Statistical significance requires
    multiple videos.
    
    Args:
        distance_by_race: Dictionary mapping race to distance value
            e.g., {"White": 0.45, "Black": 0.62} (HND in body heights)
        
    Returns:
        Dictionary with analysis results
    """
    result = {
        "distance_values": distance_by_race,
        "n_races": len(distance_by_race)
    }
    
    if "White" in distance_by_race and "Black" in distance_by_race:
        dist_white = distance_by_race["White"]
        dist_black = distance_by_race["Black"]
        difference = dist_black - dist_white
        
        result["difference"] = difference
        result["difference_direction"] = (
            "more_distance_black" if difference > 0 else
            "more_distance_white" if difference < 0 else
            "equal"
        )
        
        # Calculate percentage difference
        avg_distance = (dist_white + dist_black) / 2
        if avg_distance > 0:
            pct_difference = (difference / avg_distance) * 100
        else:
            pct_difference = 0
        
        result["percentage_difference"] = pct_difference
        
        # Interpretation
        if difference > 0:
            result["interpretation"] = (
                f"Pedestrian maintained {abs(difference):.3f} more body heights "
                f"distance from Black confederates ({abs(pct_difference):.1f}% more)"
            )
        elif difference < 0:
            result["interpretation"] = (
                f"Pedestrian maintained {abs(difference):.3f} more body heights "
                f"distance from White confederates ({abs(pct_difference):.1f}% more)"
            )
        else:
            result["interpretation"] = "Equal distance to both groups"
    
    return result


def generate_report(
    single_video_results: List[Dict],
    output_path: Optional[str] = None
) -> str:
    """
    Generate a markdown report from analysis results.
    
    Args:
        single_video_results: List of single video analysis results
        output_path: Optional path to save the report
        
    Returns:
        Markdown formatted report string
    """
    lines = [
        "# Video Bias Analysis Report",
        "",
        "## Summary",
        "",
        f"Total videos analyzed: {len(single_video_results)}",
        "",
        "## Per-Video Results",
        "",
        "| Video | SPD (White) | SPD (Black) | Difference | Direction |",
        "|-------|-------------|-------------|------------|-----------|",
    ]
    
    spd_whites = []
    spd_blacks = []
    
    for i, result in enumerate(single_video_results):
        spd_values = result.get("spd_values", {})
        spd_white = spd_values.get("White", "N/A")
        spd_black = spd_values.get("Black", "N/A")
        diff = result.get("difference", "N/A")
        direction = result.get("difference_direction", "N/A")
        
        if isinstance(spd_white, (int, float)):
            spd_whites.append(spd_white)
            spd_white = f"{spd_white:.2f}"
        if isinstance(spd_black, (int, float)):
            spd_blacks.append(spd_black)
            spd_black = f"{spd_black:.2f}"
        if isinstance(diff, (int, float)):
            diff = f"{diff:.2f}"
        
        lines.append(f"| Video {i+1} | {spd_white} | {spd_black} | {diff} | {direction} |")
    
    lines.extend(["", "## Statistical Analysis", ""])
    
    if len(spd_whites) >= 2 and len(spd_blacks) >= 2:
        try:
            test_result = perform_paired_bias_test(spd_whites, spd_blacks)
            lines.append("```")
            lines.append(str(test_result))
            lines.append("```")
        except Exception as e:
            lines.append(f"Could not perform statistical test: {e}")
    else:
        lines.append("*Insufficient data for statistical test (need at least 2 paired observations)*")
        
        if spd_whites and spd_blacks:
            lines.extend([
                "",
                "### Descriptive Statistics",
                f"- Mean SPD (White): {np.mean(spd_whites):.2f}",
                f"- Mean SPD (Black): {np.mean(spd_blacks):.2f}",
                f"- Mean Difference: {np.mean(spd_blacks) - np.mean(spd_whites):.2f}",
            ])
    
    report = "\n".join(lines)
    
    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
    
    return report
