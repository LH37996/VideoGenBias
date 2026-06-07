"""
Depth Estimation Module

Uses Depth Anything V2 for monocular depth estimation.
This is used to find reference points at the same depth
as confederates for SPD calculation.
"""

import numpy as np
from typing import Optional, Tuple
import torch


class DepthEstimator:
    """
    Estimates depth from monocular images using Depth Anything V2.
    
    The depth map is used to find reference points at the same
    depth plane as confederates, which is crucial for accurate
    SPD calculation.
    """
    
    def __init__(
        self,
        model_name: str = "depth-anything-v2-small",
        device: str = "auto"
    ):
        """
        Initialize the depth estimator.
        
        Args:
            model_name: Depth Anything model variant
            device: Device for inference ("auto", "cpu", "cuda:0")
        """
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.device = self._get_device(device)
        self._initialized = False
    
    def _get_device(self, device: str) -> str:
        """Determine the device to use."""
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda:0"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        return device
    
    def initialize(self):
        """
        Lazy initialization of the model.
        
        Called automatically on first use.
        """
        if self._initialized:
            return
        
        try:
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation
            
            # Load model and processor
            self.processor = AutoImageProcessor.from_pretrained(
                f"depth-anything/{self.model_name}-hf"
            )
            self.model = AutoModelForDepthEstimation.from_pretrained(
                f"depth-anything/{self.model_name}-hf"
            )
            self.model.to(self.device)
            self.model.eval()
            self._initialized = True
            
        except Exception as e:
            print(f"Warning: Could not initialize depth model: {e}")
            print("Falling back to horizontal offset method for reference points.")
            self._initialized = False
    
    def estimate_depth(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Estimate depth for a single frame.
        
        Args:
            frame: BGR image as numpy array (H, W, 3)
            
        Returns:
            Depth map as numpy array (H, W), or None if model unavailable
        """
        if not self._initialized:
            self.initialize()
        
        if self.model is None:
            return None
        
        try:
            # Convert BGR to RGB
            rgb_frame = frame[:, :, ::-1]
            
            # Process image
            inputs = self.processor(images=rgb_frame, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Run inference
            with torch.no_grad():
                outputs = self.model(**inputs)
                predicted_depth = outputs.predicted_depth
            
            # Interpolate to original size
            prediction = torch.nn.functional.interpolate(
                predicted_depth.unsqueeze(1),
                size=frame.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()
            
            # Convert to numpy and normalize
            depth_map = prediction.cpu().numpy()
            
            # Normalize to 0-1 range
            depth_min = depth_map.min()
            depth_max = depth_map.max()
            if depth_max > depth_min:
                depth_map = (depth_map - depth_min) / (depth_max - depth_min)
            
            return depth_map
            
        except Exception as e:
            print(f"Warning: Depth estimation failed: {e}")
            return None
    
    def get_depth_at_point(
        self, 
        depth_map: np.ndarray, 
        point: Tuple[float, float]
    ) -> float:
        """
        Get depth value at a specific point.
        
        Args:
            depth_map: Depth map from estimate_depth
            point: (x, y) coordinates
            
        Returns:
            Depth value at that point
        """
        x, y = int(point[0]), int(point[1])
        
        # Clamp to valid range
        h, w = depth_map.shape
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        
        return float(depth_map[y, x])
    
    def is_available(self) -> bool:
        """Check if depth estimation is available."""
        if not self._initialized:
            self.initialize()
        return self.model is not None
