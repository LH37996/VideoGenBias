"""
Video Pairwise Distance Analysis Pipeline

Orchestrates the complete workflow:
1. Person detection and tracking (YOLOv8-Pose + BoT-SORT/ByteTrack)
2. Pairwise minimum distance computation (Closest Point + HND)
3. Results output (CSV + console matrix + optional annotated video)
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field, replace
import yaml
import numpy as np
import cv2
import pandas as pd
from tqdm import tqdm

from .detection import PersonDetector, PersonDetection
from .metrics.distance import PairwiseResult, compute_pairwise_min_distances
from .utils.video_io import open_video_capture


@dataclass
class PersonSummary:
    """Summary information for one detected person."""
    track_id: int
    first_frame: int
    last_frame: int
    total_frames: int
    best_frame: int
    best_bbox: Tuple[float, float, float, float]


@dataclass
class PipelineConfig:
    """Configuration for the analysis pipeline."""
    # Input
    input_video_path: str = ""

    # Models
    yolo_pose_model: str = "yolov8n-pose.pt"
    tracker: str = "botsort.yaml"
    device: str = "auto"

    # Tracking
    tracking_with_reid: bool = True
    tracking_reid_model: str = "yolo26s-cls.pt"
    tracking_gmc_method: str = "sparseOptFlow"
    tracking_track_buffer: int = 60
    tracking_track_high_thresh: float = 0.25
    tracking_track_low_thresh: float = 0.10
    tracking_new_track_thresh: float = 0.25
    tracking_match_thresh: float = 0.80
    tracking_fuse_score: bool = True
    tracking_proximity_thresh: float = 0.50
    tracking_appearance_thresh: float = 0.65

    # Detection
    confidence_threshold: float = 0.5
    iou_threshold: float = 0.7
    position_mode: str = "feet"

    # Output
    save_annotated_video: bool = True

    def __post_init__(self):
        self.position_mode = PersonDetector.validate_position_mode(self.position_mode)

    @classmethod
    def from_yaml(cls, path: str) -> "PipelineConfig":
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        config = cls()
        base_dir = Path(path).resolve().parent
        tracking_with_reid_explicit = False

        def resolve_existing_path(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            candidate = Path(value).expanduser()
            if candidate.is_absolute() and candidate.exists():
                return str(candidate)
            relative_candidate = (base_dir / value).resolve()
            if relative_candidate.exists():
                return str(relative_candidate)
            return value

        if "input" in data:
            i = data["input"]
            if "video_path" in i:
                config.input_video_path = str(i["video_path"]).strip()

        if "models" in data:
            m = data["models"]
            if "yolo_pose" in m:
                config.yolo_pose_model = resolve_existing_path(m["yolo_pose"])
            if "tracker" in m:
                config.tracker = resolve_existing_path(m["tracker"])
            if "device" in m:
                config.device = str(m["device"]).strip()

        if "tracking" in data:
            t = data["tracking"]
            if "with_reid" in t:
                tracking_with_reid_explicit = True
                config.tracking_with_reid = bool(t["with_reid"])
            if "reid_model" in t:
                config.tracking_reid_model = resolve_existing_path(t["reid_model"])
            if "gmc_method" in t:
                config.tracking_gmc_method = str(t["gmc_method"]).strip()
            if "track_buffer" in t:
                config.tracking_track_buffer = int(t["track_buffer"])
            if "track_high_thresh" in t:
                config.tracking_track_high_thresh = float(t["track_high_thresh"])
            if "track_low_thresh" in t:
                config.tracking_track_low_thresh = float(t["track_low_thresh"])
            if "new_track_thresh" in t:
                config.tracking_new_track_thresh = float(t["new_track_thresh"])
            if "match_thresh" in t:
                config.tracking_match_thresh = float(t["match_thresh"])
            if "fuse_score" in t:
                config.tracking_fuse_score = bool(t["fuse_score"])
            if "proximity_thresh" in t:
                config.tracking_proximity_thresh = float(t["proximity_thresh"])
            if "appearance_thresh" in t:
                config.tracking_appearance_thresh = float(t["appearance_thresh"])

        if "detection" in data:
            d = data["detection"]
            if "confidence_threshold" in d:
                config.confidence_threshold = d["confidence_threshold"]
            if "iou_threshold" in d:
                config.iou_threshold = d["iou_threshold"]
            if "position_mode" in d:
                config.position_mode = PersonDetector.validate_position_mode(d["position_mode"])

        if "output" in data:
            o = data["output"]
            if "save_annotated_video" in o:
                config.save_annotated_video = o["save_annotated_video"]

        tracker_name = Path(str(config.tracker)).name.lower()
        if not tracking_with_reid_explicit and tracker_name == "bytetrack.yaml":
            config.tracking_with_reid = False

        return config


@dataclass
class PairwiseDistanceResult:
    """Complete result of pairwise distance analysis."""
    video_path: str
    total_frames: int
    total_persons: int
    pairwise_results: List[PairwiseResult]
    person_summaries: List[PersonSummary] = field(default_factory=list)
    analysis_frame_range: Optional[Tuple[int, int]] = None
    reference_track_id: Optional[int] = None
    position_mode: str = "feet"


class VideoDistanceAnalyzer:
    """
    Detects all persons in a video and computes pairwise minimum distances.

    Uses YOLOv8-Pose for detection/pose estimation, BoT-SORT/ByteTrack for tracking,
    and HND (Height-Normalized Distance) for perspective-corrected distance
    measurement following the Closest Point paradigm from the Nature Human
    Behaviour methodology.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self._detector = None

    @property
    def detector(self) -> PersonDetector:
        if self._detector is None:
            self._detector = PersonDetector(
                model_path=self.config.yolo_pose_model,
                tracker_config=self.config.tracker,
                confidence_threshold=self.config.confidence_threshold,
                iou_threshold=self.config.iou_threshold,
                position_mode=self.config.position_mode,
                tracker_overrides={
                    "with_reid": self.config.tracking_with_reid,
                    "model": self.config.tracking_reid_model,
                    "gmc_method": self.config.tracking_gmc_method,
                    "track_buffer": self.config.tracking_track_buffer,
                    "track_high_thresh": self.config.tracking_track_high_thresh,
                    "track_low_thresh": self.config.tracking_track_low_thresh,
                    "new_track_thresh": self.config.tracking_new_track_thresh,
                    "match_thresh": self.config.tracking_match_thresh,
                    "fuse_score": self.config.tracking_fuse_score,
                    "proximity_thresh": self.config.tracking_proximity_thresh,
                    "appearance_thresh": self.config.tracking_appearance_thresh,
                },
                device=self.config.device,
            )
        return self._detector

    def analyze_video(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        visualize: bool = False,
        verbose: bool = True,
        confirm_callback: Optional[Callable[
            [List[PersonSummary], str],
            List[Tuple[int, int]],
        ]] = None,
        choose_time_range_callback: Optional[Callable[
            [int, float],
            Optional[Tuple[int, int]],
        ]] = None,
        choose_reference_callback: Optional[Callable[
            [List[PersonSummary], Optional[int], str],
            Optional[int],
        ]] = None,
        analysis_frame_range: Optional[Tuple[int, int]] = None,
    ) -> PairwiseDistanceResult:
        """
        Analyze a video to compute pairwise minimum distances.

        Args:
            video_path: Path to input video file
            output_dir: Directory for output files
            visualize: Whether to generate annotated video
            verbose: Whether to print progress
            confirm_callback: Optional function called after detection for
                manual review. Receives (person_summaries, snapshot_dir) and
                returns a list of (keep_id, remove_id) pairs to merge.
                Return [] to keep all tracks as-is.
            choose_time_range_callback: Optional function called after full
                detection/tracking to choose the analysis frame range.
                Receives (total_frames, fps) and returns a (start_frame,
                end_frame) tuple inclusive, or None for the full video.
            choose_reference_callback: Optional function called after track
                confirmation to choose the reference person used for HND.
                Receives (person_summaries, auto_reference_track_id,
                snapshot_dir) and returns a chosen track ID. Return None to
                keep the auto-selected default.
            analysis_frame_range: Optional (start_frame, end_frame) inclusive.
                Detection runs on the full video, but distance computation
                only uses frames within this range.

        Returns:
            PairwiseDistanceResult with all pairwise distances
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"Analyzing: {video_path}")
            print(f"{'='*60}")

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        self.detector.reset()

        # --- Step 1: Detect and track all persons ---
        if verbose:
            print("\n[1/6] Detecting and tracking persons...")
            print(f"   Position mode: {self.config.position_mode}")
            print(f"   Tracker: {Path(self.config.tracker).name}")
            if self.config.tracking_with_reid:
                print(
                    f"   ReID: enabled ({Path(self.config.tracking_reid_model).name})"
                )
            else:
                print("   ReID: disabled")
            print(f"   Inference device: {self.detector.device}")

        cap = open_video_capture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        frames_for_viz = []
        frame_detections = {}

        frame_iter = tqdm(range(total_frames), desc="Processing frames") if verbose else range(total_frames)

        for frame_idx in frame_iter:
            ret, frame = cap.read()
            if not ret:
                break

            detections = self.detector.process_frame(frame)
            frame_detections[frame_idx] = detections

            if visualize:
                frames_for_viz.append(frame.copy())

        cap.release()

        tracks = self.detector.get_track_positions()
        all_heights = self.detector.get_track_heights()
        all_tracks = self.detector.get_all_tracks()

        person_summaries = self._build_person_summaries(all_tracks)

        if verbose:
            print(f"   Detected {len(tracks)} unique persons across {total_frames} frames")
            print("\n   Person summary:")
            for ps in person_summaries:
                print(f"     ID {ps.track_id}: frames {ps.first_frame}-{ps.last_frame} "
                      f"({ps.total_frames} frames visible)")

        snap_dir = ""
        if output_dir:
            snap_dir = os.path.join(output_dir, "person_snapshots")
            self._save_person_snapshots(
                person_summaries, all_tracks, video_path, output_dir, verbose
            )

        # --- Step 2: Analysis time range selection ---
        if verbose:
            print("\n[2/6] Analysis time range selection...")

        if analysis_frame_range is None and choose_time_range_callback is not None:
            analysis_frame_range = choose_time_range_callback(total_frames, fps)

        if verbose:
            if analysis_frame_range is None:
                print("   Analysis range: full video")
            else:
                print(
                    f"   Analysis range: frames {analysis_frame_range[0]}-"
                    f"{analysis_frame_range[1]}"
                )

        # --- Step 3: Manual confirmation & merge ---
        if verbose:
            print("\n[3/6] Manual confirmation...")

        if confirm_callback is not None:
            merge_pairs = confirm_callback(person_summaries, snap_dir)
            if merge_pairs:
                tracks, all_heights = self._merge_tracks(
                    merge_pairs, tracks, all_heights, verbose
                )
                merged_all_tracks = self._rebuild_all_tracks_from_positions(
                    tracks, all_tracks, merge_pairs
                )
                merged_all_tracks = self._harmonize_merged_track_bboxes(
                    merged_all_tracks, verbose
                )
                tracks = self._build_track_positions_from_detections(merged_all_tracks)
                all_heights = self._build_track_heights_from_detections(merged_all_tracks)
                frame_detections = self._build_frame_detections_from_tracks(merged_all_tracks)
                person_summaries = self._build_person_summaries(merged_all_tracks)
        elif verbose:
            print("   (skipped, no confirmation callback)")

        if len(tracks) < 2:
            if verbose:
                print("   WARNING: Less than 2 persons detected, no pairwise distances to compute.")
            return PairwiseDistanceResult(
                video_path=video_path,
                total_frames=total_frames,
                total_persons=len(tracks),
                pairwise_results=[],
                person_summaries=person_summaries,
                position_mode=self.config.position_mode,
            )

        # Auto-select reference person: the one with the most visible frames
        reference_track_id: Optional[int] = None
        auto_reference_track_id: Optional[int] = None
        if person_summaries:
            ref_ps = max(person_summaries, key=lambda ps: ps.total_frames)
            auto_reference_track_id = ref_ps.track_id
            reference_track_id = auto_reference_track_id

        # --- Step 4: Reference person selection ---
        if verbose:
            print("\n[4/6] Reference person selection...")

        if choose_reference_callback is not None and person_summaries:
            chosen_reference_track_id = choose_reference_callback(
                person_summaries,
                auto_reference_track_id,
                snap_dir,
            )
            if chosen_reference_track_id is not None:
                valid_ids = {ps.track_id for ps in person_summaries}
                if chosen_reference_track_id not in valid_ids:
                    raise ValueError(
                        f"Invalid reference person ID {chosen_reference_track_id}. "
                        f"Valid IDs: {sorted(valid_ids)}"
                    )
                reference_track_id = chosen_reference_track_id

        if verbose and reference_track_id is not None:
            ref_ps_lookup = {ps.track_id: ps for ps in person_summaries}
            ref_ps = ref_ps_lookup[reference_track_id]
            selection_source = (
                "auto-selected"
                if reference_track_id == auto_reference_track_id
                else "user-selected"
            )
            print(
                f"   Reference person for HND: ID {reference_track_id} "
                f"({ref_ps.total_frames} frames, {selection_source})"
            )

        # --- Step 5: Compute pairwise minimum distances ---
        if verbose:
            print("\n[5/6] Computing pairwise minimum distances (Closest Point + HND)...")
            if analysis_frame_range:
                print(f"   Analysis restricted to frames {analysis_frame_range[0]}-{analysis_frame_range[1]}")

        pairwise_results = compute_pairwise_min_distances(
            tracks, all_heights,
            frame_range=analysis_frame_range,
            reference_track_id=reference_track_id,
        )

        # Filter person summaries to only persons visible in the analysis range
        if analysis_frame_range:
            f_start, f_end = analysis_frame_range
            visible_in_range = set()
            for tid, positions in tracks.items():
                for frame, _, _ in positions:
                    if f_start <= frame <= f_end:
                        visible_in_range.add(tid)
                        break
            person_summaries = [ps for ps in person_summaries if ps.track_id in visible_in_range]

        if verbose:
            print(f"   Computed {len(pairwise_results)} pairwise distances")
            for pr in pairwise_results:
                print(f"   Person {pr.person_a} <-> Person {pr.person_b}: "
                      f"{pr.min_pixel_distance:.1f}px / HND={pr.hnd:.3f} "
                      f"(frame {pr.min_distance_frame}, {pr.common_frames} common frames)")

        # --- Step 6: Save results ---
        if verbose:
            print("\n[6/6] Saving results...")

        result = PairwiseDistanceResult(
            video_path=video_path,
            total_frames=total_frames,
            total_persons=len(person_summaries),
            pairwise_results=pairwise_results,
            person_summaries=person_summaries,
            analysis_frame_range=analysis_frame_range,
            reference_track_id=reference_track_id,
            position_mode=self.config.position_mode,
        )

        if output_dir:
            self._save_results(result, output_dir, verbose)

        if visualize and output_dir and frames_for_viz:
            self._save_annotated_video(
                frames_for_viz, frame_detections, pairwise_results,
                output_dir, fps, width, height, verbose
            )

        return result

    @staticmethod
    def _merge_tracks(
        merge_pairs: List[Tuple[int, int]],
        tracks: Dict[int, List[Tuple[int, float, float]]],
        heights: Dict[int, Dict[int, float]],
        verbose: bool = True,
    ) -> Tuple[Dict, Dict]:
        """Merge track pairs: absorb the second ID into the first."""
        # Build a mapping: each id -> its canonical root
        canonical = {}
        for keep_id, remove_id in merge_pairs:
            # Follow chains
            while keep_id in canonical:
                keep_id = canonical[keep_id]
            while remove_id in canonical:
                remove_id = canonical[remove_id]
            if keep_id == remove_id:
                continue
            canonical[remove_id] = keep_id

        # Apply merges
        for remove_id, keep_id in canonical.items():
            if remove_id in tracks and keep_id in tracks:
                existing_frames = {f for f, _, _ in tracks[keep_id]}
                for entry in tracks[remove_id]:
                    if entry[0] not in existing_frames:
                        tracks[keep_id].append(entry)
                tracks[keep_id].sort(key=lambda e: e[0])

            if remove_id in heights and keep_id in heights:
                for frame, h in heights[remove_id].items():
                    if frame not in heights[keep_id]:
                        heights[keep_id][frame] = h

            tracks.pop(remove_id, None)
            heights.pop(remove_id, None)

            if verbose:
                print(f"   Merged ID {remove_id} -> ID {keep_id}")

        return tracks, heights

    @staticmethod
    def _rebuild_all_tracks_from_positions(
        tracks: Dict[int, List[Tuple[int, float, float]]],
        original_all_tracks: Dict[int, List[PersonDetection]],
        merge_pairs: List[Tuple[int, int]],
    ) -> Dict[int, List[PersonDetection]]:
        """Rebuild a PersonDetection-based track dict after merges."""
        canonical = {}
        for keep_id, remove_id in merge_pairs:
            while keep_id in canonical:
                keep_id = canonical[keep_id]
            while remove_id in canonical:
                remove_id = canonical[remove_id]
            if keep_id != remove_id:
                canonical[remove_id] = keep_id

        result: Dict[int, List[PersonDetection]] = {}
        for track_id, detections in original_all_tracks.items():
            target_id = track_id
            while target_id in canonical:
                target_id = canonical[target_id]
            if target_id not in tracks:
                continue
            if target_id not in result:
                result[target_id] = []
            result[target_id].extend(detections)

        for tid in result:
            result[tid].sort(key=lambda d: d.frame_id)
        return result

    def _harmonize_merged_track_bboxes(
        self,
        all_tracks: Dict[int, List[PersonDetection]],
        verbose: bool = True,
    ) -> Dict[int, List[PersonDetection]]:
        """
        Align merged track bbox geometry so split IDs share one box style.

        This uses the merged track's full-body detections as a template and
        expands detections from absorbed IDs when they only contain partial
        bodies. It is more stable than re-running the same detector on the
        same cropped frames.
        """
        harmonized_tracks: Dict[int, List[PersonDetection]] = {}

        for canonical_track_id, detections in all_tracks.items():
            source_groups: Dict[int, List[PersonDetection]] = {}
            for detection in detections:
                source_groups.setdefault(detection.track_id, []).append(detection)

            if len(source_groups) == 1:
                harmonized_tracks[canonical_track_id] = [
                    replace(detection, track_id=canonical_track_id)
                    for detection in sorted(detections, key=lambda d: d.frame_id)
                ]
                continue

            canonical_detections = source_groups.get(canonical_track_id, [])
            geometry_template = self._build_bbox_geometry_template(
                canonical_detections or detections
            )
            height_template = self._build_height_template(detections)

            adjusted_detections: List[PersonDetection] = []
            adjusted_count = 0

            for detection in sorted(detections, key=lambda d: d.frame_id):
                if detection.track_id == canonical_track_id:
                    adjusted_detections.append(
                        replace(detection, track_id=canonical_track_id)
                    )
                    continue

                adjusted_bbox = self._align_bbox_to_track_template(
                    detection,
                    geometry_template,
                    height_template,
                )
                adjusted_position = self.detector._get_position_point(
                    detection.keypoints,
                    detection.keypoint_confidences,
                    np.asarray(adjusted_bbox, dtype=float),
                )
                adjusted_detections.append(
                    replace(
                        detection,
                        track_id=canonical_track_id,
                        bbox=adjusted_bbox,
                        position_point=adjusted_position,
                    )
                )
                adjusted_count += 1

            if verbose:
                print(
                    f"   Harmonized {adjusted_count} detections into ID "
                    f"{canonical_track_id} using merged-track bbox alignment"
                )

            harmonized_tracks[canonical_track_id] = adjusted_detections

        return harmonized_tracks

    @staticmethod
    def _select_template_detections(
        detections: List[PersonDetection],
    ) -> List[PersonDetection]:
        """Prefer the largest detections as the track's full-body template."""
        if not detections:
            return []

        max_height = max(d.bbox[3] - d.bbox[1] for d in detections)
        near_full_body = [
            d for d in detections
            if (d.bbox[3] - d.bbox[1]) >= 0.75 * max_height
        ]
        if len(near_full_body) >= 2:
            return near_full_body

        ranked = sorted(
            detections,
            key=lambda d: d.bbox[3] - d.bbox[1],
            reverse=True,
        )
        keep_n = max(3, int(np.ceil(len(ranked) * 0.4)))
        keep_n = min(keep_n, len(ranked))
        return ranked[:keep_n]

    @classmethod
    def _build_bbox_geometry_template(
        cls,
        detections: List[PersonDetection],
    ) -> Dict[str, float]:
        """Extract canonical bbox geometry from the best detections."""
        template_detections = cls._select_template_detections(detections)
        heights = np.asarray(
            [max(d.bbox[3] - d.bbox[1], 1.0) for d in template_detections],
            dtype=float,
        )
        widths = np.asarray(
            [max(d.bbox[2] - d.bbox[0], 1.0) for d in template_detections],
            dtype=float,
        )

        head_margins = []
        foot_margins = []
        for detection in template_detections:
            head_anchor = cls._actual_head_anchor(detection)
            foot_anchor = cls._actual_feet_anchor(detection)
            if head_anchor is not None:
                head_margins.append(head_anchor[1] - detection.bbox[1])
            if foot_anchor is not None:
                foot_margins.append(detection.bbox[3] - foot_anchor[1])

        median_height = float(np.median(heights)) if len(heights) else 200.0
        return {
            "aspect_ratio": float(np.median(widths / heights)) if len(heights) else 0.4,
            "head_margin": float(np.median(head_margins)) if head_margins else median_height * 0.1,
            "foot_margin": float(np.median(foot_margins)) if foot_margins else 0.0,
        }

    @classmethod
    def _build_height_template(
        cls,
        detections: List[PersonDetection],
    ) -> Dict[str, np.ndarray]:
        """Build an interpolated height trend from the best merged detections."""
        template_detections = sorted(
            cls._select_template_detections(detections),
            key=lambda d: d.frame_id,
        )
        frames = np.asarray([d.frame_id for d in template_detections], dtype=float)
        heights = np.asarray(
            [max(d.bbox[3] - d.bbox[1], 1.0) for d in template_detections],
            dtype=float,
        )

        unique_frames, inverse = np.unique(frames, return_inverse=True)
        if len(unique_frames) != len(frames):
            averaged_heights = np.zeros_like(unique_frames, dtype=float)
            counts = np.zeros_like(unique_frames, dtype=float)
            for idx, inv in enumerate(inverse):
                averaged_heights[inv] += heights[idx]
                counts[inv] += 1.0
            heights = averaged_heights / np.maximum(counts, 1.0)
            frames = unique_frames

        return {"frames": frames, "heights": heights}

    def _align_bbox_to_track_template(
        self,
        detection: PersonDetection,
        geometry_template: Dict[str, float],
        height_template: Dict[str, np.ndarray],
    ) -> Tuple[float, float, float, float]:
        """Expand a partial-body bbox to the merged track's canonical geometry."""
        expected_height = self._interpolated_track_height(detection.frame_id, height_template)
        expected_width = max(1.0, expected_height * geometry_template["aspect_ratio"])

        current_center_x = float((detection.bbox[0] + detection.bbox[2]) / 2.0)
        current_center_y = float((detection.bbox[1] + detection.bbox[3]) / 2.0)

        head_anchor = self._actual_head_anchor(detection)
        feet_anchor = self._actual_feet_anchor(detection)

        top: Optional[float] = None
        bottom: Optional[float] = None

        if head_anchor is not None:
            top = float(head_anchor[1] - geometry_template["head_margin"])
        if feet_anchor is not None:
            bottom = float(feet_anchor[1] + geometry_template["foot_margin"])

        if top is not None and bottom is not None and bottom > top:
            expected_height = max(expected_height, bottom - top)

        if top is None and bottom is None:
            top = current_center_y - expected_height / 2.0
            bottom = current_center_y + expected_height / 2.0
        elif top is None:
            top = bottom - expected_height
        elif bottom is None:
            bottom = top + expected_height

        x_candidates = []
        if head_anchor is not None:
            x_candidates.append(head_anchor[0])
        if feet_anchor is not None:
            x_candidates.append(feet_anchor[0])
        center_x = float(np.mean(x_candidates)) if x_candidates else current_center_x

        return (
            float(center_x - expected_width / 2.0),
            float(top),
            float(center_x + expected_width / 2.0),
            float(bottom),
        )

    @staticmethod
    def _interpolated_track_height(
        frame_id: int,
        height_template: Dict[str, np.ndarray],
    ) -> float:
        """Interpolate the merged track's expected full-body height."""
        frames = height_template["frames"]
        heights = height_template["heights"]
        if len(frames) == 0:
            return 200.0
        if len(frames) == 1:
            return float(heights[0])
        return float(np.interp(frame_id, frames, heights))

    @staticmethod
    def _actual_head_anchor(
        detection: PersonDetection,
    ) -> Optional[Tuple[float, float]]:
        """Head anchor from visible head keypoints only, without bbox fallback."""
        valid_points = []
        valid_weights = []
        for idx in PersonDetector.HEAD_KEYPOINTS:
            conf = float(detection.keypoint_confidences[idx])
            point = detection.keypoints[idx]
            if conf >= PersonDetector.HEAD_KEYPOINT_CONF_THRESHOLD and np.any(point > 0):
                valid_points.append(point.astype(float))
                valid_weights.append(conf)

        if len(valid_points) >= 2:
            points = np.asarray(valid_points, dtype=float)
            weights = np.asarray(valid_weights, dtype=float)
            anchor = np.average(points, axis=0, weights=weights)
            return (float(anchor[0]), float(anchor[1]))
        if len(valid_points) == 1:
            point = valid_points[0]
            return (float(point[0]), float(point[1]))
        return None

    @staticmethod
    def _actual_feet_anchor(
        detection: PersonDetection,
    ) -> Optional[Tuple[float, float]]:
        """Feet anchor from visible ankle keypoints only, without bbox fallback."""
        left_ankle = detection.keypoints[PersonDetector.LEFT_ANKLE]
        right_ankle = detection.keypoints[PersonDetector.RIGHT_ANKLE]

        left_valid = np.any(left_ankle > 0)
        right_valid = np.any(right_ankle > 0)

        if left_valid and right_valid:
            return (
                float((left_ankle[0] + right_ankle[0]) / 2.0),
                float((left_ankle[1] + right_ankle[1]) / 2.0),
            )
        if left_valid:
            return (float(left_ankle[0]), float(left_ankle[1]))
        if right_valid:
            return (float(right_ankle[0]), float(right_ankle[1]))
        return None

    @staticmethod
    def _build_track_positions_from_detections(
        all_tracks: Dict[int, List[PersonDetection]],
    ) -> Dict[int, List[Tuple[int, float, float]]]:
        """Rebuild simplified positions from harmonized detections."""
        positions: Dict[int, List[Tuple[int, float, float]]] = {}
        for track_id, detections in all_tracks.items():
            positions[track_id] = [
                (d.frame_id, d.position_point[0], d.position_point[1])
                for d in sorted(detections, key=lambda d: d.frame_id)
            ]
        return positions

    @staticmethod
    def _build_track_heights_from_detections(
        all_tracks: Dict[int, List[PersonDetection]],
    ) -> Dict[int, Dict[int, float]]:
        """Rebuild bbox heights from harmonized detections."""
        heights: Dict[int, Dict[int, float]] = {}
        for track_id, detections in all_tracks.items():
            heights[track_id] = {
                d.frame_id: float(d.bbox[3] - d.bbox[1])
                for d in detections
            }
        return heights

    @staticmethod
    def _build_frame_detections_from_tracks(
        all_tracks: Dict[int, List[PersonDetection]],
    ) -> Dict[int, List[PersonDetection]]:
        """Re-index detections by frame after merge-time bbox harmonization."""
        frame_detections: Dict[int, List[PersonDetection]] = {}
        for detections in all_tracks.values():
            for detection in detections:
                frame_detections.setdefault(detection.frame_id, []).append(detection)
        for frame_id in frame_detections:
            frame_detections[frame_id].sort(key=lambda d: d.track_id)
        return frame_detections

    @staticmethod
    def _build_person_summaries(
        all_tracks: Dict[int, List[PersonDetection]]
    ) -> List[PersonSummary]:
        """Build a summary for each tracked person."""
        summaries = []
        for track_id in sorted(all_tracks.keys()):
            detections = all_tracks[track_id]
            frames = [d.frame_id for d in detections]
            # "Best" frame = largest bbox area (clearest / closest view)
            best_det = max(detections, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))
            summaries.append(PersonSummary(
                track_id=track_id,
                first_frame=min(frames),
                last_frame=max(frames),
                total_frames=len(frames),
                best_frame=best_det.frame_id,
                best_bbox=best_det.bbox,
            ))
        return summaries

    @staticmethod
    def _save_person_snapshots(
        summaries: List[PersonSummary],
        all_tracks: Dict[int, List[PersonDetection]],
        video_path: str,
        output_dir: str,
        verbose: bool = True,
    ):
        """Save a cropped reference image for each detected person."""
        from .utils.visualization import _color_for_track

        snap_dir = os.path.join(output_dir, "person_snapshots")
        os.makedirs(snap_dir, exist_ok=True)

        # Collect the set of frames we need to read
        frame_to_summaries: Dict[int, List[PersonSummary]] = {}
        for ps in summaries:
            frame_to_summaries.setdefault(ps.best_frame, []).append(ps)

        needed_frames = set(frame_to_summaries.keys())

        cap = open_video_capture(video_path)
        if not cap.isOpened():
            return

        frame_idx = 0
        while needed_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx in needed_frames:
                for ps in frame_to_summaries[frame_idx]:
                    x1, y1, x2, y2 = [int(v) for v in ps.best_bbox]
                    h, w = frame.shape[:2]
                    # Add padding
                    pad = 20
                    x1 = max(0, x1 - pad)
                    y1 = max(0, y1 - pad)
                    x2 = min(w, x2 + pad)
                    y2 = min(h, y2 + pad)
                    crop = frame[y1:y2, x1:x2].copy()

                    color = _color_for_track(ps.track_id)
                    cv2.rectangle(crop, (pad, pad),
                                  (crop.shape[1] - pad, crop.shape[0] - pad),
                                  color, 2)
                    label = f"ID:{ps.track_id}"
                    cv2.putText(crop, label, (pad + 4, pad + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                    path = os.path.join(snap_dir, f"person_{ps.track_id}.jpg")
                    cv2.imwrite(path, crop)

                needed_frames.discard(frame_idx)
            frame_idx += 1

        cap.release()

        if verbose:
            print(f"   Person snapshots saved to: {snap_dir}/")

    def _save_results(
        self,
        result: PairwiseDistanceResult,
        output_dir: str,
        verbose: bool = True
    ):
        """Save pairwise distance results to CSV."""
        csv_path = os.path.join(output_dir, "results.csv")

        rows = []
        for pr in result.pairwise_results:
            rows.append({
                "position_mode": result.position_mode,
                "person_a": pr.person_a,
                "person_b": pr.person_b,
                "min_pixel_distance": round(pr.min_pixel_distance, 2),
                "min_distance_frame": pr.min_distance_frame,
                "height_a": round(pr.height_a, 2),
                "height_b": round(pr.height_b, 2),
                "avg_height": round(pr.avg_height, 2),
                "ref_height": round(pr.ref_height, 2),
                "hnd": round(pr.hnd, 4),
                "common_frames": pr.common_frames,
            })

        df = pd.DataFrame(rows, columns=[
            "position_mode",
            "person_a",
            "person_b",
            "min_pixel_distance",
            "min_distance_frame",
            "height_a",
            "height_b",
            "avg_height",
            "ref_height",
            "hnd",
            "common_frames",
        ])
        df.to_csv(csv_path, index=False)

        if verbose:
            print(f"   Results saved to: {csv_path}")

    def _save_annotated_video(
        self,
        frames: list,
        frame_detections: dict,
        pairwise_results: List[PairwiseResult],
        output_dir: str,
        fps: float,
        width: int,
        height: int,
        verbose: bool = True
    ):
        """Generate annotated video with bounding boxes and distance lines."""
        from .utils.visualization import annotate_frame

        video_path = os.path.join(output_dir, "annotated_output.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

        all_tracks = self.detector.get_all_tracks()
        all_heights = self.detector.get_track_heights()

        for frame_idx, frame in enumerate(frames):
            detections = frame_detections.get(frame_idx, [])
            annotated = annotate_frame(frame, detections, all_heights, frame_idx)
            writer.write(annotated)

        writer.release()

        if verbose:
            print(f"   Annotated video saved to: {video_path}")
