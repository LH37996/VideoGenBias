#!/usr/bin/env python3
"""Run gender and race/skin-tone detection on one image or video."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))

from attribute_detection.detector import AttributeDetectionConfig, VideoAttributeDetector


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".gif"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect face gender and race/skin-tone attributes for VideoGenBias."
    )
    parser.add_argument("--input", required=True, help="Input image or video path.")
    parser.add_argument(
        "--output-dir",
        default="results/reports/attribute_detection",
        help="Directory for CSV/JSON outputs.",
    )
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument(
        "--gender-backend",
        default="deepface",
        choices=["deepface", "facepp", "none"],
        help="Gender detector backend.",
    )
    parser.add_argument("--facepp-api-key", default=None, help="Face++ API key. Prefer env var FACEPP_API_KEY.")
    parser.add_argument(
        "--facepp-api-secret",
        default=None,
        help="Face++ API secret. Prefer env var FACEPP_API_SECRET.",
    )
    parser.add_argument("--no-skin", action="store_true", help="Disable CLIP skin-tone/race classification.")
    parser.add_argument("--no-face-verification", action="store_true", help="Disable CLIP face-region verification.")
    parser.add_argument("--no-face-tracking", action="store_true", help="Disable CLIP feature matching across frames.")
    parser.add_argument("--sample-frames", type=int, default=30, help="Number of uniformly sampled video frames.")
    parser.add_argument("--process-every-frame", action="store_true", help="Process every video frame.")
    parser.add_argument("--min-face-appearances", type=int, default=5)
    parser.add_argument("--min-face-confidence", type=float, default=0.0)
    parser.add_argument("--min-face-size", type=int, default=60)
    parser.add_argument("--request-delay", type=float, default=2.0, help="Delay between Face++ API calls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    suffix = input_path.suffix.lower()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = AttributeDetectionConfig(
        device=args.device,
        gender_backend=args.gender_backend,
        detect_skin=not args.no_skin,
        verify_face=not args.no_face_verification,
        enable_face_tracking=not args.no_face_tracking,
        request_delay=args.request_delay,
        facepp_api_key=args.facepp_api_key,
        facepp_api_secret=args.facepp_api_secret,
        min_face_confidence=args.min_face_confidence,
        min_face_size=args.min_face_size,
    )
    detector = VideoAttributeDetector(config)

    if suffix in VIDEO_EXTS:
        result = detector.analyze_video(
            input_path,
            sample_frames=args.sample_frames,
            process_every_frame=args.process_every_frame,
            min_face_appearances=args.min_face_appearances,
        )
        detector.save_video_result(result, output_dir)
        print(f"[ok] Wrote video attribute outputs to {output_dir}")
        return

    if suffix in IMAGE_EXTS:
        detections = detector.detect_image(input_path)
        detector.save_image_result(detections, output_dir)
        print(f"[ok] Wrote image attribute outputs to {output_dir}")
        return

    raise ValueError(f"Unsupported input extension: {suffix}")


if __name__ == "__main__":
    main()
