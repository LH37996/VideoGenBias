"""
Video Pairwise Distance Detector

Detects all persons in a video and computes pairwise minimum
distances using Height-Normalized Distance (HND) for perspective
correction, following the Closest Point paradigm from the
Nature Human Behaviour methodology.
"""

from .pipeline import VideoDistanceAnalyzer, PipelineConfig, PairwiseDistanceResult, PersonSummary

__version__ = "0.2.0"
__all__ = ["VideoDistanceAnalyzer", "PipelineConfig", "PairwiseDistanceResult", "PersonSummary"]
