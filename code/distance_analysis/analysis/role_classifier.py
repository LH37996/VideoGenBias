"""
Role Classification Module

Classifies detected persons as either:
- Pedestrian (P): The person being followed by the camera
- Confederate (C): People being passed by the pedestrian

For follow-camera perspective videos, the pedestrian appears
throughout most of the video, while confederates only appear
during passing events.
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class RoleAssignment:
    """Role assignment for a tracked person."""
    track_id: int
    role: str  # "pedestrian" or "confederate"
    duration: int  # Number of frames the person appears


def classify_roles(
    tracks: Dict[int, List[Tuple[int, float, float]]]
) -> Dict[int, RoleAssignment]:
    """
    Classify roles based on track duration.
    
    For follow-camera perspective:
    - The person with the longest track duration is the Pedestrian
    - All other persons are Confederates
    
    Args:
        tracks: Dictionary mapping track_id to list of (frame_id, x, y) tuples
        
    Returns:
        Dictionary mapping track_id to RoleAssignment
    """
    if not tracks:
        return {}
    
    # Calculate duration for each track
    track_durations = {
        track_id: len(positions)
        for track_id, positions in tracks.items()
    }
    
    # Find the track with the longest duration (the pedestrian)
    pedestrian_id = max(track_durations, key=track_durations.get)
    
    # Create role assignments
    roles = {}
    for track_id, duration in track_durations.items():
        if track_id == pedestrian_id:
            role = "pedestrian"
        else:
            role = "confederate"
        
        roles[track_id] = RoleAssignment(
            track_id=track_id,
            role=role,
            duration=duration
        )
    
    return roles


def get_pedestrian_id(roles: Dict[int, RoleAssignment]) -> int:
    """
    Get the track ID of the pedestrian.
    
    Args:
        roles: Role assignments from classify_roles
        
    Returns:
        Track ID of the pedestrian
        
    Raises:
        ValueError: If no pedestrian is found
    """
    for track_id, assignment in roles.items():
        if assignment.role == "pedestrian":
            return track_id
    raise ValueError("No pedestrian found in role assignments")


def get_confederate_ids(roles: Dict[int, RoleAssignment]) -> List[int]:
    """
    Get the track IDs of all confederates.
    
    Args:
        roles: Role assignments from classify_roles
        
    Returns:
        List of track IDs for confederates
    """
    return [
        track_id
        for track_id, assignment in roles.items()
        if assignment.role == "confederate"
    ]
