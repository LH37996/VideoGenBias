"""
Visualization Module

Draws annotations on video frames: bounding boxes with track IDs,
position points, and pairwise distance lines between all persons
visible in each frame.
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple

from ..detection.detector import PersonDetection
from ..metrics.distance import euclidean_distance


# 10-color palette (BGR) for up to 10 distinct tracks; wraps around for more
_PALETTE = [
    (0, 255, 0),      # green
    (255, 0, 0),      # blue
    (0, 0, 255),      # red
    (255, 255, 0),    # cyan
    (0, 255, 255),    # yellow
    (255, 0, 255),    # magenta
    (128, 255, 0),    # spring green
    (255, 128, 0),    # light blue
    (0, 128, 255),    # orange
    (128, 0, 255),    # purple
]


def _color_for_track(track_id: int) -> Tuple[int, int, int]:
    return _PALETTE[track_id % len(_PALETTE)]


def annotate_frame(
    frame: np.ndarray,
    detections: List[PersonDetection],
    all_heights: Dict[int, Dict[int, float]],
    frame_idx: int,
) -> np.ndarray:
    """
    Draw all annotations on a single frame.

    For each detected person: bounding box + label + position point.
    For each pair of persons in the frame: distance line with pixel distance.

    Args:
        frame: BGR image
        detections: PersonDetection list for this frame
        all_heights: track_id -> {frame_id: height} dict (for HND overlay)
        frame_idx: current frame index

    Returns:
        Annotated copy of the frame
    """
    annotated = frame.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX

    for det in detections:
        color = _color_for_track(det.track_id)
        x1, y1, x2, y2 = [int(v) for v in det.bbox]

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        label = f"ID:{det.track_id}"
        (tw, th), _ = cv2.getTextSize(label, font, 0.6, 1)
        cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw + 10, y1), color, -1)
        cv2.putText(annotated, label, (x1 + 5, y1 - 5), font, 0.6, (255, 255, 255), 1)

        px, py = int(det.position_point[0]), int(det.position_point[1])
        cv2.circle(annotated, (px, py), 5, color, -1)

    # Draw pairwise distance lines
    for i in range(len(detections)):
        for j in range(i + 1, len(detections)):
            da, db = detections[i], detections[j]
            pa = da.position_point
            pb = db.position_point
            dist = euclidean_distance(pa, pb)

            ax, ay = int(pa[0]), int(pa[1])
            bx, by = int(pb[0]), int(pb[1])

            cv2.line(annotated, (ax, ay), (bx, by), (255, 255, 255), 1, cv2.LINE_AA)

            mx, my = (ax + bx) // 2, (ay + by) // 2
            dist_label = f"{dist:.0f}px"
            (tw, th), _ = cv2.getTextSize(dist_label, font, 0.4, 1)
            cv2.rectangle(annotated, (mx - 2, my - th - 2), (mx + tw + 2, my + 2), (0, 0, 0), -1)
            cv2.putText(annotated, dist_label, (mx, my), font, 0.4, (255, 255, 255), 1)

    return annotated
