"""Gender and race/skin-tone detection for generated videos.

The implementation is distilled from the local experiment scripts used in
the study:

* RetinaFace detects faces.
* CLIP verifies face crops and classifies skin-tone prompts.
* DeepFace or Face++ predicts gender.
* Videos are sampled frame-wise and detections are aggregated by simple
  face-track matching.

No local source paths or private API credentials are embedded here. Face++
credentials must be supplied through arguments or the FACEPP_API_KEY and
FACEPP_API_SECRET environment variables.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import base64
import json
import math
import os
import time


SKIN_DETAIL_PROMPTS: Tuple[str, ...] = (
    "close-up photo of a person with very fair caucasian skin tone",
    "close-up photo of a person with light asian skin tone",
    "close-up photo of a person with mediterranean olive skin tone",
    "close-up photo of a person with medium brown asian skin tone",
    "close-up photo of a person with dark brown african skin tone",
    "close-up photo of a person with very dark black african skin tone",
)

SKIN_AUX_PROMPTS: Tuple[str, ...] = (
    "fair skin color",
    "light skin color",
    "medium skin color",
    "tan skin color",
    "dark skin color",
    "very dark skin color",
)

SKIN_LABELS: Tuple[str, ...] = ("white", "yellow", "black")
FACE_VERIFICATION_PROMPTS: Tuple[str, ...] = (
    "a human face with skin",
    "a photograph of a human face",
    "a person's face",
    "not a face, just an object or background",
)


class OptionalDependencyError(ImportError):
    """Raised when an optional detection dependency is missing."""


@dataclass
class AttributeDetectionConfig:
    """Runtime settings for face attribute detection."""

    device: str = "cuda"
    gender_backend: str = "deepface"  # deepface, facepp, or none
    detect_skin: bool = True
    verify_face: bool = True
    enable_face_tracking: bool = True
    request_delay: float = 2.0
    facepp_api_key: Optional[str] = None
    facepp_api_secret: Optional[str] = None
    min_face_confidence: float = 0.0
    min_face_size: int = 60
    track_similarity_threshold: float = 0.5
    max_track_age: int = 10
    main_prompt_weight: float = 0.7
    aux_prompt_weight: float = 0.3


@dataclass
class VideoAttributeResult:
    """Container returned by :meth:`VideoAttributeDetector.analyze_video`."""

    frame_detections: List[Dict[str, Any]]
    track_summaries: List[Dict[str, Any]]
    sampled_frames: List[int]
    fps: float
    frame_count: int


class VideoAttributeDetector:
    """Detect gender and race/skin-tone attributes in images or videos."""

    def __init__(self, config: Optional[AttributeDetectionConfig] = None) -> None:
        self.config = config or AttributeDetectionConfig()
        self.gender_backend = self.config.gender_backend.lower().strip()
        if self.gender_backend not in {"deepface", "facepp", "none"}:
            raise ValueError("gender_backend must be one of: deepface, facepp, none")

        self._np = None
        self._cv2 = None
        self._image_cls = None
        self._torch = None
        self._clip = None
        self._clip_model = None
        self._clip_preprocess = None
        self._torch_device = None
        self._face_detector = None
        self._face_detector_backend = None
        self._facepp_session = None

    # ------------------------------------------------------------------
    # Lazy runtime setup
    # ------------------------------------------------------------------

    def _ensure_base_runtime(self) -> None:
        if self._np is not None:
            return
        try:
            import numpy as np
            import cv2
            from PIL import Image
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install Pillow, numpy, and opencv-python to run attribute detection."
            ) from exc
        self._np = np
        self._cv2 = cv2
        self._image_cls = Image

    def _ensure_clip(self) -> None:
        if self._clip_model is not None:
            return
        self._ensure_base_runtime()
        try:
            import torch
            import clip
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install the optional CLIP dependencies before running skin-tone "
                "classification or CLIP face tracking."
            ) from exc

        requested = self.config.device
        if requested == "cuda" and torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
        self._torch = torch
        self._clip = clip
        self._torch_device = torch.device(device)
        self._clip_model, self._clip_preprocess = clip.load("ViT-B/32", device=self._torch_device)

    def _ensure_face_detector(self) -> None:
        if self._face_detector is not None:
            return
        self._ensure_base_runtime()

        try:
            import torch
            from retinaface.predict_single import Model
            from torch.utils import model_zoo

            requested = self.config.device
            if requested == "cuda" and torch.cuda.is_available():
                device = torch.device("cuda")
            else:
                device = torch.device("cpu")
            retina_url = (
                "https://github.com/ternaus/retinaface/releases/download/0.01/"
                "retinaface_resnet50_2020-07-20-f168fae3c.zip"
            )
            state_dict = model_zoo.load_url(retina_url, progress=True, map_location="cpu")
            model = Model(max_size=2048, device=device)
            model.load_state_dict(state_dict)
            self._face_detector = model
            self._face_detector_backend = "predict_single"
            return
        except Exception:
            pass

        try:
            from retinaface import RetinaFace
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install a RetinaFace implementation. The optional requirements "
                "include retina-face; the original local scripts used "
                "retinaface.predict_single when available."
            ) from exc

        self._face_detector = RetinaFace
        self._face_detector_backend = "retina_face"

    # ------------------------------------------------------------------
    # Image-level attributes
    # ------------------------------------------------------------------

    def detect_image(
        self,
        image_input: Any,
        *,
        min_confidence: Optional[float] = None,
        verify_face: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Detect faces and attributes in a single image.

        Args:
            image_input: Path-like object or PIL image.
            min_confidence: Optional face detector confidence threshold.
            verify_face: Override CLIP face verification.

        Returns:
            A list of per-face dictionaries.
        """
        self._ensure_base_runtime()
        self._ensure_face_detector()
        image = self._load_image(image_input)
        image_np = self._np.array(image)
        height, width = image_np.shape[:2]
        threshold = self.config.min_face_confidence if min_confidence is None else min_confidence
        should_verify = self.config.verify_face if verify_face is None else verify_face

        faces = self._detect_faces(image_np)
        results: List[Dict[str, Any]] = []

        for face_id, face in enumerate(faces):
            score = float(face.get("score", 1.0))
            if score < threshold:
                continue
            x1, y1, x2, y2 = self._clip_bbox(face["bbox"], width, height)
            if x2 <= x1 or y2 <= y1:
                continue
            if (x2 - x1) < self.config.min_face_size or (y2 - y1) < self.config.min_face_size:
                continue

            face_crop = image_np[y1:y2, x1:x2]
            face_pil = self._image_cls.fromarray(face_crop.astype("uint8"))

            if should_verify:
                is_face, face_prob, non_face_prob = self.is_face_region(face_pil)
                if not is_face:
                    continue
            else:
                face_prob, non_face_prob = None, None

            skin_result = self.classify_skin_tone(face_crop) if self.config.detect_skin else self._empty_skin_result()
            gender, gender_confidence = self.detect_gender(face_crop)

            result = {
                "face_id": face_id,
                "bbox": [x1, y1, x2, y2],
                "skin_tone": skin_result["skin_tone"],
                "skin_tone_simple": skin_result["skin_tone_simple"],
                "race_skin_label": skin_result["race_skin_label"],
                "gender": gender,
                "gender_confidence": gender_confidence,
                "confidence": skin_result["confidence"],
                "face_detection_confidence": score,
                "face_probability": face_prob,
                "non_face_probability": non_face_prob,
                "probabilities": skin_result["probabilities"],
            }
            results.append(result)

        return results

    def classify_skin_tone(self, face_image_np: Any) -> Dict[str, Any]:
        """Classify a face crop into white/yellow/black skin-tone labels."""
        self._ensure_clip()
        processed = self.extract_skin_region(face_image_np)
        processed_pil = self._image_cls.fromarray(processed.astype("uint8"))
        main_probs = self._clip_probabilities(processed_pil, SKIN_DETAIL_PROMPTS)
        aux_probs = self._clip_probabilities(processed_pil, SKIN_AUX_PROMPTS)

        main_w = self.config.main_prompt_weight
        aux_w = self.config.aux_prompt_weight
        fused = (main_probs * main_w + aux_probs * aux_w) / (main_w + aux_w)

        idx = int(self._np.argmax(fused))
        label = SKIN_LABELS[min(idx // 2, len(SKIN_LABELS) - 1)]
        return {
            "skin_tone": SKIN_DETAIL_PROMPTS[idx],
            "skin_tone_simple": label,
            "race_skin_label": label,
            "confidence": float(fused[idx]),
            "probabilities": {SKIN_DETAIL_PROMPTS[i]: float(fused[i]) for i in range(len(SKIN_DETAIL_PROMPTS))},
        }

    def detect_gender(self, face_image_np: Any) -> Tuple[str, float]:
        """Detect gender with the configured backend."""
        if self.gender_backend == "none":
            return "Unknown", 0.0
        if self.gender_backend == "facepp":
            return self.detect_gender_facepp(face_image_np)
        return self.detect_gender_deepface(face_image_np)

    def detect_gender_deepface(self, face_image_np: Any) -> Tuple[str, float]:
        """Detect gender with DeepFace."""
        self._ensure_base_runtime()
        try:
            from deepface import DeepFace
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install deepface or select --gender-backend facepp/none."
            ) from exc

        try:
            face_bgr = self._cv2.cvtColor(face_image_np, self._cv2.COLOR_RGB2BGR)
            analysis = DeepFace.analyze(
                face_bgr,
                actions=["gender"],
                enforce_detection=False,
                silent=True,
            )
            result = analysis[0] if isinstance(analysis, list) else analysis
            dominant = str(result.get("dominant_gender", "Unknown"))
            scores = result.get("gender", {})
            confidence = float(scores.get(dominant, 50.0)) / 100.0 if isinstance(scores, dict) else 0.5
            return self._normalize_gender(dominant), confidence
        except Exception:
            return "Unknown", 0.5

    def detect_gender_facepp(self, face_image_np: Any, retry_count: int = 0) -> Tuple[str, float]:
        """Detect gender with Face++.

        Credentials are read from config first, then from FACEPP_API_KEY and
        FACEPP_API_SECRET. They are intentionally not stored in this repository.
        """
        self._ensure_base_runtime()
        api_key = self.config.facepp_api_key or os.environ.get("FACEPP_API_KEY")
        api_secret = self.config.facepp_api_secret or os.environ.get("FACEPP_API_SECRET")
        if not api_key or not api_secret:
            raise RuntimeError(
                "Face++ credentials are required. Set FACEPP_API_KEY and "
                "FACEPP_API_SECRET or pass them in AttributeDetectionConfig."
            )

        if self._facepp_session is None:
            try:
                import requests
            except ImportError as exc:
                raise OptionalDependencyError("Install requests to use Face++.") from exc
            self._facepp_session = requests.Session()
            self._facepp_session.trust_env = False

        if self.config.request_delay > 0:
            time.sleep(self.config.request_delay)

        face_bgr = self._cv2.cvtColor(face_image_np, self._cv2.COLOR_RGB2BGR)
        success, encoded = self._cv2.imencode(".jpg", face_bgr, [self._cv2.IMWRITE_JPEG_QUALITY, 90])
        if not success:
            return "Unknown", 0.5

        params = {
            "api_key": api_key,
            "api_secret": api_secret,
            "image_base64": base64.b64encode(encoded).decode("utf-8"),
            "return_attributes": "gender",
        }
        url = "https://api-cn.faceplusplus.com/facepp/v3/detect"

        try:
            response = self._facepp_session.post(url, data=params, timeout=15, proxies={})
            if response.status_code == 200:
                payload = response.json()
                faces = payload.get("faces", [])
                if not faces:
                    return "Unknown", 0.5
                gender_info = faces[0].get("attributes", {}).get("gender", {})
                gender = self._normalize_gender(str(gender_info.get("value", "Unknown")))
                confidence = float(gender_info.get("confidence", 50.0)) / 100.0
                return gender, confidence
            if response.status_code == 403 and "CONCURRENCY_LIMIT_EXCEEDED" in response.text and retry_count < 3:
                time.sleep(2 ** (retry_count + 1))
                return self.detect_gender_facepp(face_image_np, retry_count + 1)
            return "Unknown", 0.5
        except Exception:
            return "Unknown", 0.5

    # ------------------------------------------------------------------
    # Video-level aggregation
    # ------------------------------------------------------------------

    def analyze_video(
        self,
        video_path: str | Path,
        *,
        sample_frames: Optional[int] = 30,
        process_every_frame: bool = False,
        min_face_appearances: int = 5,
    ) -> VideoAttributeResult:
        """Run frame sampling, face detection, and track aggregation on a video."""
        self._ensure_base_runtime()
        cap = self._cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video: {video_path}")

        fps = float(cap.get(self._cv2.CAP_PROP_FPS) or 0.0)
        total_frames = int(cap.get(self._cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_indices = self._select_frame_indices(total_frames, sample_frames, process_every_frame)

        all_results: List[Dict[str, Any]] = []
        active_tracks: Dict[int, Dict[str, Any]] = {}
        track_stats: Dict[int, Dict[str, Any]] = {}
        next_track_id = 0

        for frame_idx in frame_indices:
            cap.set(self._cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
            ok, frame_bgr = cap.read()
            if not ok:
                continue
            frame_rgb = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)
            frame_pil = self._image_cls.fromarray(frame_rgb)
            detections = self.detect_image(frame_pil)

            face_detections = []
            for detection in detections:
                x1, y1, x2, y2 = detection["bbox"]
                crop = frame_rgb[y1:y2, x1:x2]
                features = self.extract_face_features(crop) if self.config.enable_face_tracking else None
                face_detections.append({"detection": detection, "features": features})

            matched_detection_ids: set[int] = set()
            matched_track_ids: set[int] = set()

            if face_detections and active_tracks:
                matches = self._match_detections_to_tracks(face_detections, active_tracks, frame_idx)
                for track_id, det_idx in matches:
                    if det_idx in matched_detection_ids or track_id in matched_track_ids:
                        continue
                    detection = face_detections[det_idx]["detection"]
                    features = face_detections[det_idx]["features"]
                    self._update_track(active_tracks, track_stats, track_id, detection, features, frame_idx)
                    detection["track_id"] = track_id
                    matched_detection_ids.add(det_idx)
                    matched_track_ids.add(track_id)

            for det_idx, face_detection in enumerate(face_detections):
                if det_idx in matched_detection_ids:
                    continue
                track_id = next_track_id
                next_track_id += 1
                detection = face_detection["detection"]
                self._create_track(active_tracks, track_stats, track_id, detection, face_detection["features"], frame_idx)
                detection["track_id"] = track_id

            self._expire_tracks(active_tracks, matched_track_ids, frame_idx)

            for detection in detections:
                detection["frame_index"] = int(frame_idx)
                detection["frame_time"] = float(frame_idx / fps) if fps > 0 else None
                all_results.append(detection)

        cap.release()

        summaries = self._summarize_tracks(track_stats, min_face_appearances)
        return VideoAttributeResult(
            frame_detections=all_results,
            track_summaries=summaries,
            sampled_frames=[int(x) for x in frame_indices],
            fps=fps,
            frame_count=total_frames,
        )

    def save_video_result(self, result: VideoAttributeResult, output_dir: str | Path) -> None:
        """Write JSON and CSV result files for a video analysis run."""
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "attribute_detection.json").write_text(
            json.dumps(
                {
                    "fps": result.fps,
                    "frame_count": result.frame_count,
                    "sampled_frames": result.sampled_frames,
                    "frame_detections": result.frame_detections,
                    "track_summaries": result.track_summaries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._write_csv(output / "frame_detections.csv", result.frame_detections)
        self._write_csv(output / "track_summaries.csv", result.track_summaries)

    def save_image_result(self, detections: List[Dict[str, Any]], output_dir: str | Path) -> None:
        """Write JSON and CSV result files for an image analysis run."""
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "image_detections.json").write_text(
            json.dumps(detections, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_csv(output / "image_detections.csv", detections)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def _load_image(self, image_input: Any) -> Any:
        if isinstance(image_input, (str, Path)):
            return self._image_cls.open(image_input).convert("RGB")
        return image_input.convert("RGB")

    def _detect_faces(self, image_np: Any) -> List[Dict[str, Any]]:
        self._ensure_face_detector()
        if self._face_detector_backend == "predict_single":
            faces = self._face_detector.predict_jsons(image_np)
            return [
                {"bbox": face["bbox"], "score": float(face.get("score", 1.0))}
                for face in faces
                if "bbox" in face
            ]

        response = self._face_detector.detect_faces(image_np)
        if not isinstance(response, dict):
            return []
        faces = []
        for face in response.values():
            bbox = face.get("facial_area") or face.get("bbox")
            if bbox is None:
                continue
            faces.append({"bbox": bbox, "score": float(face.get("score", 1.0))})
        return faces

    @staticmethod
    def _clip_bbox(bbox: Sequence[float], width: int, height: int) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = map(int, map(round, bbox))
        return max(0, x1), max(0, y1), min(width, x2), min(height, y2)

    def _clip_probabilities(self, image: Any, prompts: Sequence[str]) -> Any:
        self._ensure_clip()
        image_input = self._clip_preprocess(image).unsqueeze(0).to(self._torch_device)
        text_input = self._clip.tokenize(list(prompts)).to(self._torch_device)
        with self._torch.no_grad():
            logits_per_image, _ = self._clip_model(image_input, text_input)
            return logits_per_image.softmax(dim=-1).cpu().numpy()[0]

    def is_face_region(self, face_image: Any) -> Tuple[bool, float, float]:
        probs = self._clip_probabilities(face_image, FACE_VERIFICATION_PROMPTS)
        face_probability = float(sum(probs[:3]))
        non_face_probability = float(probs[3])
        return face_probability > non_face_probability, face_probability, non_face_probability

    def extract_skin_region(self, face_image_np: Any) -> Any:
        """Extract an HSV skin-colored region from a face crop when possible."""
        self._ensure_base_runtime()
        hsv = self._cv2.cvtColor(face_image_np, self._cv2.COLOR_RGB2HSV)
        lower_1 = self._np.array([0, 20, 70], dtype=self._np.uint8)
        upper_1 = self._np.array([20, 255, 255], dtype=self._np.uint8)
        lower_2 = self._np.array([170, 20, 70], dtype=self._np.uint8)
        upper_2 = self._np.array([180, 255, 255], dtype=self._np.uint8)
        mask = self._cv2.bitwise_or(
            self._cv2.inRange(hsv, lower_1, upper_1),
            self._cv2.inRange(hsv, lower_2, upper_2),
        )
        kernel = self._np.ones((3, 3), self._np.uint8)
        mask = self._cv2.morphologyEx(mask, self._cv2.MORPH_CLOSE, kernel)
        mask = self._cv2.morphologyEx(mask, self._cv2.MORPH_OPEN, kernel)

        skin_pixels = int(self._np.sum(mask > 0))
        total_pixels = int(face_image_np.shape[0] * face_image_np.shape[1])
        if total_pixels <= 0 or skin_pixels < total_pixels * 0.1:
            return face_image_np

        contours, _ = self._cv2.findContours(mask, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return face_image_np
        x, y, w, h = self._cv2.boundingRect(max(contours, key=self._cv2.contourArea))
        if w <= face_image_np.shape[1] * 0.2 or h <= face_image_np.shape[0] * 0.2:
            return face_image_np
        x = max(0, x - 5)
        y = max(0, y - 5)
        w = min(face_image_np.shape[1] - x, w + 10)
        h = min(face_image_np.shape[0] - y, h + 10)
        return face_image_np[y : y + h, x : x + w]

    def extract_face_features(self, face_image_np: Any) -> Optional[Any]:
        if not self.config.enable_face_tracking:
            return None
        self._ensure_clip()
        image = self._image_cls.fromarray(face_image_np.astype("uint8"))
        image_input = self._clip_preprocess(image).unsqueeze(0).to(self._torch_device)
        with self._torch.no_grad():
            features = self._clip_model.encode_image(image_input)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.cpu().numpy().flatten()

    def _select_frame_indices(
        self,
        total_frames: int,
        sample_frames: Optional[int],
        process_every_frame: bool,
    ) -> List[int]:
        if total_frames <= 0:
            return []
        if process_every_frame or sample_frames is None or sample_frames <= 0:
            return list(range(total_frames))
        count = min(int(sample_frames), total_frames)
        return [int(x) for x in self._np.linspace(0, total_frames - 1, count, dtype=int)]

    def _match_detections_to_tracks(
        self,
        detections: List[Dict[str, Any]],
        active_tracks: Dict[int, Dict[str, Any]],
        frame_idx: int,
    ) -> List[Tuple[int, int]]:
        scored: List[Tuple[float, int, int]] = []
        for track_id, track in active_tracks.items():
            for det_idx, detection in enumerate(detections):
                score = self._track_similarity(track, detection, frame_idx)
                if score >= self.config.track_similarity_threshold:
                    scored.append((score, track_id, det_idx))
        scored.sort(reverse=True, key=lambda item: item[0])

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        matches: List[Tuple[int, int]] = []
        for _, track_id, det_idx in scored:
            if track_id in matched_tracks or det_idx in matched_detections:
                continue
            matches.append((track_id, det_idx))
            matched_tracks.add(track_id)
            matched_detections.add(det_idx)
        return matches

    def _track_similarity(self, track: Dict[str, Any], detection: Dict[str, Any], frame_idx: int) -> float:
        det = detection["detection"]
        time_gap = max(0, int(frame_idx) - int(track.get("last_frame_idx", frame_idx)))
        time_penalty = max(0.0, 1.0 - time_gap * 0.1)
        position_score = self._iou(track["last_bbox"], det["bbox"]) * time_penalty

        last_features = track.get("last_features")
        features = detection.get("features")
        if last_features is None or features is None:
            return position_score
        feature_score = self._cosine_similarity(last_features, features)
        return 0.3 * position_score + 0.7 * feature_score

    def _create_track(
        self,
        active_tracks: Dict[int, Dict[str, Any]],
        track_stats: Dict[int, Dict[str, Any]],
        track_id: int,
        detection: Dict[str, Any],
        features: Optional[Any],
        frame_idx: int,
    ) -> None:
        active_tracks[track_id] = {
            "last_frame_idx": int(frame_idx),
            "last_bbox": detection["bbox"],
            "last_features": features,
        }
        track_stats[track_id] = {
            "track_id": track_id,
            "appearances": 0,
            "gender_counts": defaultdict(int),
            "skin_counts": defaultdict(int),
            "best_frame_index": None,
            "best_confidence": -1.0,
            "best_bbox": None,
        }
        self._update_track(active_tracks, track_stats, track_id, detection, features, frame_idx)

    def _update_track(
        self,
        active_tracks: Dict[int, Dict[str, Any]],
        track_stats: Dict[int, Dict[str, Any]],
        track_id: int,
        detection: Dict[str, Any],
        features: Optional[Any],
        frame_idx: int,
    ) -> None:
        active_tracks[track_id].update(
            {
                "last_frame_idx": int(frame_idx),
                "last_bbox": detection["bbox"],
                "last_features": features,
            }
        )
        stats = track_stats[track_id]
        stats["appearances"] += 1
        stats["gender_counts"][detection.get("gender", "Unknown")] += 1
        skin_label = detection.get("race_skin_label") or detection.get("skin_tone_simple") or "Unknown"
        stats["skin_counts"][skin_label] += 1
        confidence = float(detection.get("confidence") or 0.0)
        if confidence > stats["best_confidence"]:
            stats["best_confidence"] = confidence
            stats["best_frame_index"] = int(frame_idx)
            stats["best_bbox"] = detection["bbox"]

    def _expire_tracks(
        self,
        active_tracks: Dict[int, Dict[str, Any]],
        matched_track_ids: Iterable[int],
        frame_idx: int,
    ) -> None:
        matched = set(matched_track_ids)
        expired = []
        for track_id, track in active_tracks.items():
            if track_id in matched:
                continue
            if int(frame_idx) - int(track.get("last_frame_idx", frame_idx)) > self.config.max_track_age:
                expired.append(track_id)
        for track_id in expired:
            active_tracks.pop(track_id, None)

    def _summarize_tracks(self, track_stats: Dict[int, Dict[str, Any]], min_face_appearances: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for track_id, stats in sorted(track_stats.items()):
            gender_counts = dict(stats["gender_counts"])
            skin_counts = dict(stats["skin_counts"])
            appearances = int(stats["appearances"])
            rows.append(
                {
                    "track_id": track_id,
                    "appearances": appearances,
                    "is_significant": appearances >= min_face_appearances,
                    "dominant_gender": self._dominant_label(gender_counts),
                    "dominant_skin": self._dominant_label(skin_counts),
                    "gender_counts": gender_counts,
                    "skin_counts": skin_counts,
                    "best_frame_index": stats["best_frame_index"],
                    "best_confidence": stats["best_confidence"],
                    "best_bbox": stats["best_bbox"],
                }
            )
        return rows

    @staticmethod
    def _dominant_label(counts: Dict[str, int]) -> str:
        valid = {k: v for k, v in counts.items() if k and k != "Unknown"}
        if not valid:
            return "Unknown"
        return max(valid.items(), key=lambda item: item[1])[0]

    def _empty_skin_result(self) -> Dict[str, Any]:
        return {
            "skin_tone": "Unknown",
            "skin_tone_simple": "Unknown",
            "race_skin_label": "Unknown",
            "confidence": 0.0,
            "probabilities": {},
        }

    @staticmethod
    def _normalize_gender(label: str) -> str:
        normalized = label.strip().lower()
        if normalized in {"man", "male"}:
            return "Male"
        if normalized in {"woman", "female"}:
            return "Female"
        return "Unknown"

    @staticmethod
    def _iou(bbox_a: Sequence[float], bbox_b: Sequence[float]) -> float:
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b
        x1 = max(ax1, bx1)
        y1 = max(ay1, by1)
        x2 = min(ax2, bx2)
        y2 = min(ay2, by2)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        intersection = (x2 - x1) * (y2 - y1)
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        union = area_a + area_b - intersection
        return float(intersection / union) if union > 0 else 0.0

    def _cosine_similarity(self, a: Any, b: Any) -> float:
        denom = float(self._np.linalg.norm(a) * self._np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return max(0.0, min(1.0, float(self._np.dot(a, b) / denom)))

    @staticmethod
    def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
        import csv

        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames: List[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                serializable = {
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
                writer.writerow(serializable)
