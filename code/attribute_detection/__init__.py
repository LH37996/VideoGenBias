"""Face attribute detection for VideoGenBias.

This package contains the paper-facing implementation for gender and
race/skin-tone attribute extraction from generated videos. Heavy vision
dependencies are imported lazily by :mod:`attribute_detection.detector`.
"""

from .detector import AttributeDetectionConfig, VideoAttributeDetector

__all__ = ["AttributeDetectionConfig", "VideoAttributeDetector"]
