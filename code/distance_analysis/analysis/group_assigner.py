"""
Group Assignment Module

Groups confederates by their appearance time and assigns
race labels from configuration.

Confederates that appear close together in time (e.g., two people
having a conversation) are grouped together.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ConfederateGroup:
    """A group of confederates with assigned race label."""
    group_id: int
    track_ids: List[int]
    race: str
    first_frame: int
    last_frame: int


def assign_groups_and_race(
    confederate_tracks: Dict[int, List[Tuple[int, float, float]]],
    race_order: List[str],
    time_proximity_threshold: int = 30
) -> Dict[int, ConfederateGroup]:
    """
    Group confederates by appearance time and assign race labels.
    
    Confederates that first appear within `time_proximity_threshold` frames
    of each other are grouped together (e.g., two people talking).
    
    Args:
        confederate_tracks: Dictionary mapping track_id to positions
        race_order: List of race labels in order of appearance ["White", "Black"]
        time_proximity_threshold: Max frame difference to be same group
        
    Returns:
        Dictionary mapping group_id to ConfederateGroup
    """
    if not confederate_tracks:
        return {}
    
    # Get first appearance frame for each confederate
    first_appearances = {}
    last_appearances = {}
    
    for track_id, positions in confederate_tracks.items():
        if positions:
            frames = [p[0] for p in positions]
            first_appearances[track_id] = min(frames)
            last_appearances[track_id] = max(frames)
    
    # Sort by first appearance
    sorted_tracks = sorted(first_appearances.items(), key=lambda x: x[1])
    
    # Group by time proximity
    groups: List[List[int]] = []
    current_group: List[int] = []
    current_group_start: Optional[int] = None
    
    for track_id, first_frame in sorted_tracks:
        if current_group_start is None:
            # Start new group
            current_group = [track_id]
            current_group_start = first_frame
        elif first_frame - current_group_start <= time_proximity_threshold:
            # Add to current group
            current_group.append(track_id)
        else:
            # Save current group and start new one
            groups.append(current_group)
            current_group = [track_id]
            current_group_start = first_frame
    
    # Don't forget the last group
    if current_group:
        groups.append(current_group)
    
    # Create ConfederateGroup objects with race labels
    result = {}
    for group_idx, track_ids in enumerate(groups):
        # Get race from config (or "Unknown" if not enough labels)
        race = race_order[group_idx] if group_idx < len(race_order) else "Unknown"
        
        # Calculate group time range
        first_frame = min(first_appearances[tid] for tid in track_ids)
        last_frame = max(last_appearances[tid] for tid in track_ids)
        
        group = ConfederateGroup(
            group_id=group_idx + 1,
            track_ids=track_ids,
            race=race,
            first_frame=first_frame,
            last_frame=last_frame
        )
        
        result[group_idx + 1] = group
    
    return result


def get_track_to_group_mapping(
    groups: Dict[int, ConfederateGroup]
) -> Dict[int, Tuple[int, str]]:
    """
    Create a mapping from track_id to (group_id, race).
    
    Args:
        groups: Confederate groups from assign_groups_and_race
        
    Returns:
        Dictionary mapping track_id to (group_id, race) tuple
    """
    mapping = {}
    for group_id, group in groups.items():
        for track_id in group.track_ids:
            mapping[track_id] = (group_id, group.race)
    return mapping
