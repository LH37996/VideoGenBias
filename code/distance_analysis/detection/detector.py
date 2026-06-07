"""
Person Detection, Tracking, and Pose Estimation Module

Uses YOLOv8-Pose for combined detection and pose estimation,
with Ultralytics MOT trackers (BoT-SORT / ByteTrack) for multi-object tracking.

Reference: ultralytics official API
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
import torch
import yaml
from ultralytics import YOLO
from ultralytics.utils.checks import check_yaml


@dataclass
class PersonDetection:
    """Single person detection with tracking and pose info."""
    track_id: int
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float
    keypoints: np.ndarray  # Shape: (17, 2)
    keypoint_confidences: np.ndarray  # Shape: (17,)
    position_point: Tuple[float, float]  # Distance anchor point (x, y)
    frame_id: int

    @property
    def ground_point(self) -> Tuple[float, float]:
        """Backward-compatible alias for older visualization/output code."""
        return self.position_point


class PersonDetector:
    """
    Detects, tracks, and estimates pose for all persons in video frames.
    
    Uses YOLOv8-Pose model which provides both bounding boxes and 
    17 COCO keypoints simultaneously.
    """
    
    VALID_POSITION_MODES = ("feet", "head")

    # COCO keypoint indices
    NOSE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    LEFT_EAR = 3
    RIGHT_EAR = 4
    LEFT_ANKLE = 15
    RIGHT_ANKLE = 16
    HEAD_KEYPOINTS = (NOSE, LEFT_EYE, RIGHT_EYE, LEFT_EAR, RIGHT_EAR)

    HEAD_KEYPOINT_CONF_THRESHOLD = 0.5
    HEAD_BBOX_FALLBACK_RATIO = 0.12
    
    def __init__(
        self,
        model_path: str = "yolov8n-pose.pt",
        tracker_config: str = "botsort.yaml",
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.7,
        position_mode: str = "feet",
        tracker_overrides: Optional[Dict[str, Any]] = None,
        device: str = "auto"
    ):
        """
        Initialize the detector.
        
        Args:
            model_path: Path to YOLOv8-Pose model weights
            tracker_config: Tracker configuration file
            confidence_threshold: Minimum detection confidence
            iou_threshold: IoU threshold passed to YOLO NMS during tracking
            position_mode: Distance anchor mode ("feet" or "head")
            tracker_overrides: Optional tracker YAML overrides applied at runtime
            device: Device to run inference on ("auto", "cpu", "cuda:0", "mps", etc.)
        """
        self.model_path = model_path
        self.tracker_config = tracker_config
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.position_mode = self.validate_position_mode(position_mode)
        self.tracker_overrides = dict(tracker_overrides or {})
        self.requested_device = str(device).strip() if device is not None else "auto"
        self.device = self._resolve_device(self.requested_device)
        self._tracker_temp_dir = tempfile.TemporaryDirectory(prefix="ped_distance_exp_tracker_")
        self._runtime_tracker_config = self._build_runtime_tracker_config(
            self.tracker_config,
            self.tracker_overrides,
        )
        self._install_device_aware_reid_patch()
        self.model = YOLO(model_path)
        self._move_model_to_device()

        # Store all tracks across frames
        self.tracks: Dict[int, List[PersonDetection]] = {}
        self.current_frame_id = 0

    @classmethod
    def validate_position_mode(cls, position_mode: str) -> str:
        """Normalize and validate the configured position mode."""
        normalized = str(position_mode).strip().lower()
        if normalized not in cls.VALID_POSITION_MODES:
            allowed = ", ".join(cls.VALID_POSITION_MODES)
            raise ValueError(
                f"Invalid detection.position_mode '{position_mode}'. "
                f"Expected one of: {allowed}"
            )
        return normalized
    
    def process_frame(self, frame: np.ndarray) -> List[PersonDetection]:
        """
        Process a single frame and return all person detections.
        
        Args:
            frame: BGR image as numpy array
            
        Returns:
            List of PersonDetection objects for this frame
        """
        # Run detection with tracking
        results = self.model.track(
            frame,
            persist=True,
            tracker=self._runtime_tracker_config,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False
        )
        
        detections = []
        
        if results and len(results) > 0:
            result = results[0]
            
            if result.boxes is not None and result.boxes.id is not None:
                boxes = result.boxes
                keypoints_data = result.keypoints
                
                for i in range(len(boxes)):
                    track_id = int(boxes.id[i].item())
                    bbox = boxes.xyxy[i].cpu().numpy()
                    conf = float(boxes.conf[i].item())
                    
                    # Get keypoints for this person
                    if keypoints_data is not None and len(keypoints_data.xy) > i:
                        kpts = keypoints_data.xy[i].cpu().numpy()
                        if keypoints_data.conf is not None and len(keypoints_data.conf) > i:
                            kpt_conf = keypoints_data.conf[i].cpu().numpy()
                        else:
                            kpt_conf = np.zeros(len(kpts), dtype=float)
                    else:
                        kpts = np.zeros((17, 2), dtype=float)
                        kpt_conf = np.zeros(17, dtype=float)
                    
                    position_point = self._get_position_point(kpts, kpt_conf, bbox)
                    
                    detection = PersonDetection(
                        track_id=track_id,
                        bbox=tuple(bbox),
                        confidence=conf,
                        keypoints=kpts,
                        keypoint_confidences=kpt_conf,
                        position_point=position_point,
                        frame_id=self.current_frame_id
                    )
                    
                    detections.append(detection)
                    
                    # Update tracks
                    if track_id not in self.tracks:
                        self.tracks[track_id] = []
                    self.tracks[track_id].append(detection)
        
        self.current_frame_id += 1
        return detections

    @staticmethod
    def _resolve_device(device: str) -> str:
        """Resolve a user-facing device string into a concrete torch device."""
        normalized = str(device).strip().lower()
        if normalized and normalized != "auto":
            return normalized
        if torch.cuda.is_available():
            return "cuda:0"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _resolve_tracker_base_path(tracker_config: str) -> str:
        """Resolve tracker YAML from local filesystem or Ultralytics package assets."""
        candidate = Path(tracker_config).expanduser()
        if candidate.exists():
            return str(candidate.resolve())
        return check_yaml(tracker_config)

    def _build_runtime_tracker_config(
        self,
        tracker_config: str,
        tracker_overrides: Dict[str, Any],
    ) -> str:
        """Create a concrete tracker YAML with repository/config overrides applied."""
        resolved_base = self._resolve_tracker_base_path(tracker_config)
        if not tracker_overrides:
            return resolved_base

        with open(resolved_base, "r", encoding="utf-8") as f:
            tracker_data = yaml.safe_load(f) or {}

        if tracker_overrides.get("with_reid") and tracker_data.get("tracker_type") != "botsort":
            raise ValueError("tracking.with_reid=True requires a BoT-SORT tracker configuration.")

        for key, value in tracker_overrides.items():
            if value is None:
                continue
            tracker_data[key] = value

        runtime_name = f"{Path(resolved_base).stem}_runtime.yaml"
        runtime_path = Path(self._tracker_temp_dir.name) / runtime_name
        with open(runtime_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(tracker_data, f, sort_keys=False)

        return str(runtime_path)

    def _move_model_to_device(self) -> None:
        """Best-effort move of the detector model to the selected device."""
        try:
            self.model.to(self.device)
        except Exception:
            # Ultralytics will still receive `device=` during inference.
            pass

    def _install_device_aware_reid_patch(self) -> None:
        """Ensure BoT-SORT ReID encoders warm up on the selected device."""
        if not self.tracker_overrides.get("with_reid"):
            return

        try:
            from ultralytics.trackers import bot_sort as bot_sort_module
        except Exception:
            return

        current = getattr(bot_sort_module, "ReID", None)
        if current is None:
            return

        base_reid_cls = getattr(current, "_video_bias_base_reid_cls", current)

        if getattr(current, "_video_bias_device", None) == self.device:
            return

        device = self.device

        class DeviceAwareReID(base_reid_cls):
            _video_bias_base_reid_cls = base_reid_cls
            _video_bias_device = device

            def __init__(self, model: str):
                self.model = YOLO(model)
                embed_layer = [len(self.model.model.model) - 2 if ".pt" in model else -1]
                warmup_source = np.zeros((64, 64, 3), dtype=np.uint8)
                self.model(
                    source=warmup_source,
                    embed=embed_layer,
                    verbose=False,
                    save=False,
                    device=device,
                )

        bot_sort_module.ReID = DeviceAwareReID

    def _get_position_point(
        self,
        keypoints: np.ndarray,
        keypoint_confidences: np.ndarray,
        bbox: np.ndarray
    ) -> Tuple[float, float]:
        """Return the configured distance anchor point for a person."""
        if self.position_mode == "head":
            return self._get_head_point(keypoints, keypoint_confidences, bbox)
        return self._get_feet_point(keypoints, bbox)

    @classmethod
    def _get_feet_point(
        cls,
        keypoints: np.ndarray,
        bbox: np.ndarray
    ) -> Tuple[float, float]:
        """
        Calculate the feet-based distance anchor for a person.

        Priority:
        1. Midpoint of ankles (if both visible)
        2. Single visible ankle
        3. Bottom center of bounding box (fallback)
        """
        left_ankle = keypoints[cls.LEFT_ANKLE]
        right_ankle = keypoints[cls.RIGHT_ANKLE]
        
        # Check if ankles are valid (not zero)
        left_valid = np.any(left_ankle > 0)
        right_valid = np.any(right_ankle > 0)
        
        if left_valid and right_valid:
            # Midpoint of both ankles
            return (
                (left_ankle[0] + right_ankle[0]) / 2,
                (left_ankle[1] + right_ankle[1]) / 2
            )
        elif left_valid:
            return (float(left_ankle[0]), float(left_ankle[1]))
        elif right_valid:
            return (float(right_ankle[0]), float(right_ankle[1]))
        else:
            # Fallback: bottom center of bbox
            return (
                (bbox[0] + bbox[2]) / 2,  # center x
                bbox[3]  # bottom y
            )

    @classmethod
    def _get_head_point(
        cls,
        keypoints: np.ndarray,
        keypoint_confidences: np.ndarray,
        bbox: np.ndarray
    ) -> Tuple[float, float]:
        """
        Calculate a head-center distance anchor from facial pose keypoints.

        Valid points are COCO nose/eyes/ears with confidence >= 0.5.
        Falls back to the upper-center region of the bbox when none are usable.
        """
        valid_points = []
        valid_weights = []

        for idx in cls.HEAD_KEYPOINTS:
            point = keypoints[idx]
            conf = float(keypoint_confidences[idx]) if len(keypoint_confidences) > idx else 0.0
            if conf >= cls.HEAD_KEYPOINT_CONF_THRESHOLD and np.any(point > 0):
                valid_points.append(point.astype(float))
                valid_weights.append(conf)

        if len(valid_points) >= 2:
            points = np.asarray(valid_points, dtype=float)
            weights = np.asarray(valid_weights, dtype=float)
            center = np.average(points, axis=0, weights=weights)
            return (float(center[0]), float(center[1]))

        if len(valid_points) == 1:
            point = valid_points[0]
            return (float(point[0]), float(point[1]))

        return cls._get_head_bbox_fallback(bbox)

    @classmethod
    def _get_head_bbox_fallback(cls, bbox: np.ndarray) -> Tuple[float, float]:
        """Fallback head anchor near the top-center of the person bbox."""
        x1, y1, x2, y2 = bbox
        bbox_height = y2 - y1
        return (
            float((x1 + x2) / 2),
            float(y1 + cls.HEAD_BBOX_FALLBACK_RATIO * bbox_height),
        )
    
    def get_all_tracks(self) -> Dict[int, List[PersonDetection]]:
        """
        Get all accumulated tracks.
        
        Returns:
            Dictionary mapping track_id to list of detections
        """
        return self.tracks
    
    def get_track_positions(self) -> Dict[int, List[Tuple[int, float, float]]]:
        """
        Get simplified position data for all tracks.
        
        Returns:
            Dictionary mapping track_id to list of (frame_id, x, y) tuples
        """
        positions = {}
        for track_id, detections in self.tracks.items():
            positions[track_id] = [
                (d.frame_id, d.position_point[0], d.position_point[1])
                for d in detections
            ]
        return positions
    
    def get_track_heights(self) -> Dict[int, Dict[int, float]]:
        """
        Get bounding box heights for all tracks.
        
        Returns:
            Dictionary mapping track_id to dict of {frame_id: height}
        """
        heights = {}
        for track_id, detections in self.tracks.items():
            heights[track_id] = {}
            for d in detections:
                # bbox is (x1, y1, x2, y2)
                bbox_height = d.bbox[3] - d.bbox[1]
                heights[track_id][d.frame_id] = bbox_height
        return heights
    
    def reset(self):
        """Reset all tracking state."""
        self.tracks = {}
        self.current_frame_id = 0
        # Reset YOLO tracker state
        self.model = YOLO(self.model_path)
        self._move_model_to_device()
