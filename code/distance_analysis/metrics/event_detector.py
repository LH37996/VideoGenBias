"""
Passing Event Detection Module

Detects when the pedestrian passes by each confederate group.
A "passing event" is characterized by the distance curve forming
a valley shape (distance decreases then increases).
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class PassingEvent:
    """A single passing event between pedestrian and a confederate group."""
    group_id: int
    race: str
    closest_frame: int
    closest_distance: float
    start_frame: int
    end_frame: int
    pedestrian_pos_at_closest: Tuple[float, float]
    confederate_pos_at_closest: Tuple[float, float]
    confederate_height_at_closest: float = 0.0  # Body height in pixels


def euclidean_distance(
    point_a: Tuple[float, float],
    point_b: Tuple[float, float]
) -> float:
    """Calculate Euclidean distance between two points."""
    return np.sqrt(
        (point_a[0] - point_b[0]) ** 2 +
        (point_a[1] - point_b[1]) ** 2
    )


def detect_passing_events(
    pedestrian_track: List[Tuple[int, float, float]],
    confederate_groups: Dict[int, dict],
    confederate_tracks: Dict[int, List[Tuple[int, float, float]]],
    confederate_heights: Optional[Dict[int, Dict[int, float]]] = None
) -> List[PassingEvent]:
    """
    Detect passing events for each confederate group.
    
    A passing event is detected when the pedestrian-confederate
    distance curve has a minimum (valley) - indicating the
    pedestrian approached and then moved away.
    
    Args:
        pedestrian_track: List of (frame_id, x, y) for pedestrian
        confederate_groups: Dict mapping group_id to group info
            Each group has: track_ids, race, first_frame, last_frame
        confederate_tracks: Dict mapping track_id to trajectory
        confederate_heights: Dict mapping track_id to {frame_id: height}
        
    Returns:
        List of PassingEvent objects, one per group
    """
    events = []
    
    # Create pedestrian position lookup
    ped_positions = {frame: (x, y) for frame, x, y in pedestrian_track}
    
    for group_id, group_info in confederate_groups.items():
        # Get all positions for this group
        group_positions = {}  # frame -> averaged position of group members
        
        for track_id in group_info["track_ids"]:
            if track_id in confederate_tracks:
                for frame, x, y in confederate_tracks[track_id]:
                    if frame not in group_positions:
                        group_positions[frame] = []
                    group_positions[frame].append((x, y))
        
        # Average positions when multiple confederates in group
        avg_positions = {}
        for frame, positions in group_positions.items():
            avg_x = np.mean([p[0] for p in positions])
            avg_y = np.mean([p[1] for p in positions])
            avg_positions[frame] = (avg_x, avg_y)
        
        # Find overlapping frames
        common_frames = sorted(
            set(ped_positions.keys()) & set(avg_positions.keys())
        )
        
        if not common_frames:
            continue
        
        # Calculate distance curve
        distances = []
        for frame in common_frames:
            ped_pos = ped_positions[frame]
            conf_pos = avg_positions[frame]
            dist = euclidean_distance(ped_pos, conf_pos)
            distances.append((frame, dist, ped_pos, conf_pos))
        
        # Find the minimum distance (closest point)
        min_idx = np.argmin([d[1] for d in distances])
        closest_frame = distances[min_idx][0]
        closest_distance = distances[min_idx][1]
        ped_pos_closest = distances[min_idx][2]
        conf_pos_closest = distances[min_idx][3]
        
        # Determine event boundaries (start and end frames)
        start_frame = common_frames[0]
        end_frame = common_frames[-1]
        
        # Calculate average height of confederates at closest frame
        conf_height_at_closest = 0.0
        if confederate_heights:
            heights_at_frame = []
            for track_id in group_info["track_ids"]:
                if track_id in confederate_heights:
                    track_heights = confederate_heights[track_id]
                    if closest_frame in track_heights:
                        heights_at_frame.append(track_heights[closest_frame])
                    elif track_heights:
                        # Use average height for this track
                        heights_at_frame.append(np.mean(list(track_heights.values())))
            if heights_at_frame:
                conf_height_at_closest = np.mean(heights_at_frame)
        
        event = PassingEvent(
            group_id=group_id,
            race=group_info["race"],
            closest_frame=closest_frame,
            closest_distance=closest_distance,
            start_frame=start_frame,
            end_frame=end_frame,
            pedestrian_pos_at_closest=ped_pos_closest,
            confederate_pos_at_closest=conf_pos_closest,
            confederate_height_at_closest=conf_height_at_closest
        )
        
        events.append(event)
    
    # Sort events by closest frame (chronological order)
    events.sort(key=lambda e: e.closest_frame)
    
    return events


def get_group_trajectory(
    group_info: dict,
    confederate_tracks: Dict[int, List[Tuple[int, float, float]]]
) -> List[Tuple[int, float, float]]:
    """
    Get averaged trajectory for a confederate group.
    
    When a group has multiple members (e.g., two people talking),
    returns the averaged position.
    
    Args:
        group_info: Group information with track_ids
        confederate_tracks: All confederate trajectories
        
    Returns:
        List of (frame_id, x, y) with averaged positions
    """
    # Collect all positions by frame
    positions_by_frame = {}
    
    for track_id in group_info["track_ids"]:
        if track_id in confederate_tracks:
            for frame, x, y in confederate_tracks[track_id]:
                if frame not in positions_by_frame:
                    positions_by_frame[frame] = []
                positions_by_frame[frame].append((x, y))
    
    # Average positions
    trajectory = []
    for frame in sorted(positions_by_frame.keys()):
        positions = positions_by_frame[frame]
        avg_x = np.mean([p[0] for p in positions])
        avg_y = np.mean([p[1] for p in positions])
        trajectory.append((frame, avg_x, avg_y))
    
    return trajectory
