#!/usr/bin/env python3
"""Run HND social-distance analysis for one video in this repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))

from distance_analysis.pipeline import PipelineConfig, VideoDistanceAnalyzer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze pairwise HND distances in a generated video.")
    parser.add_argument("--video", required=True, help="Video path, relative to the repository root or absolute.")
    parser.add_argument("--config", default=None, help="Optional YAML pipeline config.")
    parser.add_argument("--output", default="results/reports/distance_single_video", help="Output directory.")
    parser.add_argument("--visualize", action="store_true", help="Save an annotated video.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    return parser.parse_args()


def resolve_repo_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def main() -> None:
    args = parse_args()
    video_path = resolve_repo_path(args.video)
    output_dir = resolve_repo_path(args.output)
    config = PipelineConfig.from_yaml(args.config) if args.config else PipelineConfig()
    config.input_video_path = str(video_path)

    analyzer = VideoDistanceAnalyzer(config)
    result = analyzer.analyze_video(
        str(video_path),
        output_dir=str(output_dir),
        visualize=args.visualize,
        verbose=not args.quiet,
        confirm_callback=lambda _summaries, _snapshot_dir: [],
        choose_time_range_callback=lambda _total_frames, _fps: None,
        choose_reference_callback=lambda _summaries, _default_track_id, _snapshot_dir: None,
    )
    print(f"Analyzed {result.total_persons} persons across {result.total_frames} frames.")
    print(f"Pairwise results: {len(result.pairwise_results)}")


if __name__ == "__main__":
    main()
