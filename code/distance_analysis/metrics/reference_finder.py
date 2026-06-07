"""
Reference Point Finder Module

Automatically finds reference points at the same depth
as confederates for SPD calculation.

Two methods are supported:
1. Depth-based: Use depth estimation to find equal-depth points
2. Horizontal offset: Simple fallback using fixed offset
"""

import numpy as np
from typing import Tuple, Optional, List, Dict


def find_reference_by_depth(
    depth_map: np.ndarray,
    conf_foot_pos: Tuple[float, float],
    person_mask: Optional[np.ndarray] = None,
    search_range: int = 100,
    depth_threshold: float = 0.1
) -> Optional[Tuple[float, float]]:
    """
    Find a reference point at the same depth as the confederate.
    
    Searches horizontally from the confederate's foot position
    to find a background point with similar depth.
    
    Args:
        depth_map: Normalized depth map (H, W), values 0-1
        conf_foot_pos: Confederate foot position (x, y)
        person_mask: Optional binary mask of person regions to avoid
        search_range: Horizontal search range in pixels
        depth_threshold: Maximum depth difference for "same depth"
        
    Returns:
        Reference point (x, y) or None if not found
    """
    h, w = depth_map.shape
    x_conf, y_conf = int(conf_foot_pos[0]), int(conf_foot_pos[1])
    
    # Clamp to valid range
    x_conf = max(0, min(x_conf, w - 1))
    y_conf = max(0, min(y_conf, h - 1))
    
    # Get target depth
    target_depth = depth_map[y_conf, x_conf]
    
    # Search in both directions, preferring points farther from confederate
    best_point = None
    best_distance = 0
    
    for dx in range(-search_range, search_range + 1):
        x = x_conf + dx
        
        # Skip invalid positions
        if x < 0 or x >= w:
            continue
        
        # Skip if too close to confederate
        if abs(dx) < 20:
            continue
        
        # Skip if on a person
        if person_mask is not None and person_mask[y_conf, x]:
            continue
        
        # Check depth similarity
        point_depth = depth_map[y_conf, x]
        if abs(point_depth - target_depth) < depth_threshold:
            # Prefer points farther from confederate
            if abs(dx) > best_distance:
                best_point = (float(x), float(y_conf))
                best_distance = abs(dx)
    
    return best_point


def find_reference_by_offset(
    conf_foot_pos: Tuple[float, float],
    offset: int = 150,
    frame_width: Optional[int] = None,
    pedestrian_pos: Optional[Tuple[float, float]] = None
) -> Tuple[float, float]:
    """
    Find reference point using horizontal offset.
    
    The reference point is placed on the OPPOSITE side of the Confederate
    from the Pedestrian. This ensures SPD measures how much the pedestrian
    deviates from a straight path to avoid the Confederate.
    
    Args:
        conf_foot_pos: Confederate foot position (x, y)
        offset: Horizontal offset in pixels
        frame_width: Optional frame width for boundary checking
        pedestrian_pos: Pedestrian position to determine offset direction
        
    Returns:
        Reference point (x, y)
    """
    x_conf, y_conf = conf_foot_pos
    
    # Determine offset direction based on pedestrian position
    if pedestrian_pos is not None:
        ped_x = pedestrian_pos[0]
        if ped_x < x_conf:
            # Pedestrian is on the LEFT of Confederate
            # Place reference on the RIGHT (away from pedestrian)
            x_ref = x_conf + offset
        else:
            # Pedestrian is on the RIGHT of Confederate
            # Place reference on the LEFT (away from pedestrian)
            x_ref = x_conf - offset
    else:
        # Fallback: offset to the right
        x_ref = x_conf + offset
    
    # Boundary checking
    if frame_width is not None:
        if x_ref >= frame_width:
            x_ref = x_conf - offset
        elif x_ref < 0:
            x_ref = x_conf + offset
    
    # Final clamp
    if x_ref < 0:
        x_ref = 0
    if frame_width is not None and x_ref >= frame_width:
        x_ref = frame_width - 1
    
    return (float(x_ref), float(y_conf))


class ReferenceFinder:
    """
    Manages reference point finding for SPD calculation.
    
    Supports both depth-based and offset-based methods,
    with automatic fallback.
    """
    
    def __init__(
        self,
        use_depth: bool = True,
        horizontal_offset: int = 150,
        search_range: int = 100,
        depth_threshold: float = 0.1
    ):
        """
        Initialize the reference finder.
        
        Args:
            use_depth: Whether to try depth-based method first
            horizontal_offset: Offset for fallback method
            search_range: Search range for depth method
            depth_threshold: Depth similarity threshold
        """
        self.use_depth = use_depth
        self.horizontal_offset = horizontal_offset
        self.search_range = search_range
        self.depth_threshold = depth_threshold
    
    def find_reference(
        self,
        conf_foot_pos: Tuple[float, float],
        depth_map: Optional[np.ndarray] = None,
        person_mask: Optional[np.ndarray] = None,
        frame_width: Optional[int] = None,
        pedestrian_pos: Optional[Tuple[float, float]] = None
    ) -> Tuple[float, float]:
        """
        Find reference point for a confederate.
        
        Tries depth-based method first if available,
        falls back to offset method.
        
        Args:
            conf_foot_pos: Confederate foot position (x, y)
            depth_map: Optional depth map for depth-based method
            person_mask: Optional person mask to avoid
            frame_width: Optional frame width for bounds checking
            pedestrian_pos: Pedestrian position to determine offset direction
            
        Returns:
            Reference point (x, y)
        """
        # Try depth-based method
        if self.use_depth and depth_map is not None:
            ref_point = find_reference_by_depth(
                depth_map=depth_map,
                conf_foot_pos=conf_foot_pos,
                person_mask=person_mask,
                search_range=self.search_range,
                depth_threshold=self.depth_threshold
            )
            
            if ref_point is not None:
                return ref_point
        
        # Fallback to offset method
        return find_reference_by_offset(
            conf_foot_pos=conf_foot_pos,
            offset=self.horizontal_offset,
            frame_width=frame_width,
            pedestrian_pos=pedestrian_pos
        )
    
    def find_references_for_trajectory(
        self,
        confederate_trajectory: List[Tuple[int, float, float]],
        depth_maps: Optional[Dict[int, np.ndarray]] = None,
        person_masks: Optional[Dict[int, np.ndarray]] = None,
        frame_width: Optional[int] = None,
        pedestrian_trajectory: Optional[List[Tuple[int, float, float]]] = None
    ) -> Dict[int, Tuple[float, float]]:
        """
        Find reference points for all frames in a trajectory.
        
        Args:
            confederate_trajectory: List of (frame_id, x, y)
            depth_maps: Optional dict of frame_id -> depth_map
            person_masks: Optional dict of frame_id -> person_mask
            frame_width: Optional frame width
            pedestrian_trajectory: Optional pedestrian positions for direction
            
        Returns:
            Dictionary mapping frame_id to reference point
        """
        references = {}
        
        # Create pedestrian position lookup
        ped_positions = {}
        if pedestrian_trajectory:
            ped_positions = {frame: (x, y) for frame, x, y in pedestrian_trajectory}
        
        for frame_id, x, y in confederate_trajectory:
            conf_pos = (x, y)
            
            depth_map = depth_maps.get(frame_id) if depth_maps else None
            person_mask = person_masks.get(frame_id) if person_masks else None
            ped_pos = ped_positions.get(frame_id)
            
            ref_point = self.find_reference(
                conf_foot_pos=conf_pos,
                depth_map=depth_map,
                person_mask=person_mask,
                frame_width=frame_width,
                pedestrian_pos=ped_pos
            )
            
            references[frame_id] = ref_point
        
        return references
