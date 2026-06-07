"""
Pairwise Distance Calculation Module

Implements Height-Normalized Distance (HND) for perspective-corrected
distance measurement between all pairs of detected persons.

HND adapts the perspective correction principle from the Nature Human
Behaviour SPD methodology: instead of using an external reference point
at the same depth, HND uses persons' body heights as intrinsic scale
references. Since real human height is roughly constant (~1.7m), pixel
height directly reflects the perspective scaling factor at that depth.

When a reference person is specified, ALL pairs use that person's pixel
height at the closest-point frame for normalization, ensuring cross-pair
comparability:

    HND = pixel_distance / ref_height_at_frame

When no reference is specified, each pair uses the average height of its
two members (suitable for single-pair analysis but not cross-pair comparison).

The "Closest Point" paradigm from the paper is preserved: for each pair,
the frame with minimum pixel distance is used as the primary measurement.
"""

import numpy as np
from itertools import combinations
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass


@dataclass
class PairwiseResult:
    """Result of pairwise distance calculation for one pair of persons."""
    person_a: int
    person_b: int
    min_pixel_distance: float
    min_distance_frame: int
    height_a: float
    height_b: float
    avg_height: float
    hnd: float
    ref_height: float
    common_frames: int
    pos_a: Tuple[float, float]
    pos_b: Tuple[float, float]


def euclidean_distance(
    point_a: Tuple[float, float],
    point_b: Tuple[float, float]
) -> float:
    """Calculate Euclidean distance between two 2D points."""
    return np.sqrt(
        (point_a[0] - point_b[0]) ** 2 +
        (point_a[1] - point_b[1]) ** 2
    )


def compute_pairwise_min_distances(
    tracks: Dict[int, List[Tuple[int, float, float]]],
    heights: Dict[int, Dict[int, float]],
    frame_range: Optional[Tuple[int, int]] = None,
    reference_track_id: Optional[int] = None,
) -> List[PairwiseResult]:
    """
    Compute the minimum distance between all pairs of tracked persons.

    For each pair (A, B):
    1. Find all frames where both A and B are present
    2. Compute pixel distance (configured position points) for each common frame
    3. Select the "Closest Point" frame (minimum pixel distance)
    4. Compute HND using either:
       - The reference person's height at that frame (if reference_track_id
         is set), ensuring all pairs share the same scale basis
       - The average height of A and B at that frame (fallback)

    Args:
        tracks: Dict mapping track_id to list of (frame_id, x, y) tuples,
                where (x, y) is the configured position point for that mode.
        heights: Dict mapping track_id to {frame_id: bbox_height} dict.
        frame_range: Optional (start_frame, end_frame) inclusive. When set,
                     only frames within this range are considered for
                     distance computation.
        reference_track_id: Optional track ID of the reference person whose
                            height is used to normalize ALL pairs. This
                            ensures cross-pair comparability.

    Returns:
        List of PairwiseResult, one per pair, sorted by (person_a, person_b).
    """
    results = []
    track_ids = sorted(tracks.keys())

    for id_a, id_b in combinations(track_ids, 2):
        pos_a_by_frame = {frame: (x, y) for frame, x, y in tracks[id_a]}
        pos_b_by_frame = {frame: (x, y) for frame, x, y in tracks[id_b]}

        common_frames = sorted(set(pos_a_by_frame.keys()) & set(pos_b_by_frame.keys()))

        if frame_range is not None:
            f_start, f_end = frame_range
            common_frames = [f for f in common_frames if f_start <= f <= f_end]

        if not common_frames:
            continue

        min_dist = float('inf')
        best_frame = common_frames[0]
        best_pos_a = pos_a_by_frame[best_frame]
        best_pos_b = pos_b_by_frame[best_frame]

        for frame in common_frames:
            pa = pos_a_by_frame[frame]
            pb = pos_b_by_frame[frame]
            dist = euclidean_distance(pa, pb)
            if dist < min_dist:
                min_dist = dist
                best_frame = frame
                best_pos_a = pa
                best_pos_b = pb

        h_a = _get_height(heights, id_a, best_frame)
        h_b = _get_height(heights, id_b, best_frame)
        avg_h = (h_a + h_b) / 2.0

        if reference_track_id is not None:
            ref_h = _get_height(heights, reference_track_id, best_frame)
        else:
            ref_h = avg_h

        hnd = min_dist / ref_h if ref_h > 0 else min_dist

        results.append(PairwiseResult(
            person_a=id_a,
            person_b=id_b,
            min_pixel_distance=float(min_dist),
            min_distance_frame=best_frame,
            height_a=float(h_a),
            height_b=float(h_b),
            avg_height=float(avg_h),
            hnd=float(hnd),
            ref_height=float(ref_h),
            common_frames=len(common_frames),
            pos_a=best_pos_a,
            pos_b=best_pos_b,
        ))

    results.sort(key=lambda r: (r.person_a, r.person_b))
    return results


def _get_height(
    heights: Dict[int, Dict[int, float]],
    track_id: int,
    frame_id: int
) -> float:
    """Get bbox height for a track at a specific frame, with fallbacks."""
    track_heights = heights.get(track_id, {})
    if frame_id in track_heights:
        return track_heights[frame_id]
    if track_heights:
        return float(np.mean(list(track_heights.values())))
    return 200.0
