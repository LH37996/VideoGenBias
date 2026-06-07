"""
Video I/O Utilities

Handles video reading, writing, and frame extraction.
"""

import cv2
import numpy as np
import sys
from typing import Iterator, Tuple, Optional, List
from pathlib import Path


def _preferred_capture_backends() -> List[int]:
    """Return backend preferences that avoid noisy fallback probing."""
    backends: List[int] = []

    if sys.platform == "darwin":
        avfoundation = getattr(cv2, "CAP_AVFOUNDATION", None)
        if avfoundation is not None:
            backends.append(avfoundation)
    elif sys.platform.startswith("win"):
        msmf = getattr(cv2, "CAP_MSMF", None)
        if msmf is not None:
            backends.append(msmf)
    else:
        ffmpeg = getattr(cv2, "CAP_FFMPEG", None)
        if ffmpeg is not None:
            backends.append(ffmpeg)

    backends.append(cv2.CAP_ANY)
    return backends


def open_video_capture(video_path: str) -> cv2.VideoCapture:
    """
    Open a video with an explicit backend preference to reduce warning spam.

    OpenCV's default CAP_ANY probing can try unavailable backends such as
    GStreamer first, which emits warnings even when the video later opens
    successfully. Selecting the likely working backend up front avoids that.
    """
    last_cap: Optional[cv2.VideoCapture] = None

    for backend in _preferred_capture_backends():
        if backend == cv2.CAP_ANY:
            cap = cv2.VideoCapture(video_path)
        else:
            cap = cv2.VideoCapture(video_path, backend)

        if cap.isOpened():
            return cap

        cap.release()
        last_cap = cap

    return last_cap if last_cap is not None else cv2.VideoCapture(video_path)


class VideoReader:
    """
    Reads video frames with metadata.
    
    Supports iteration over frames with automatic resource cleanup.
    """
    
    def __init__(self, video_path: str):
        """
        Initialize video reader.
        
        Args:
            video_path: Path to video file
        """
        self.video_path = video_path
        self.cap = None
        self._opened = False
    
    def open(self):
        """Open the video file."""
        if self._opened:
            return
        
        self.cap = open_video_capture(self.video_path)
        if not self.cap.isOpened():
            raise ValueError(f"Could not open video: {self.video_path}")
        
        self._opened = True
    
    def close(self):
        """Close the video file."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self._opened = False
    
    @property
    def frame_count(self) -> int:
        """Total number of frames."""
        self.open()
        return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    @property
    def fps(self) -> float:
        """Frames per second."""
        self.open()
        return self.cap.get(cv2.CAP_PROP_FPS)
    
    @property
    def width(self) -> int:
        """Frame width in pixels."""
        self.open()
        return int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    
    @property
    def height(self) -> int:
        """Frame height in pixels."""
        self.open()
        return int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    @property
    def size(self) -> Tuple[int, int]:
        """Frame size as (width, height)."""
        return (self.width, self.height)
    
    def read_frame(self, frame_idx: int) -> Optional[np.ndarray]:
        """
        Read a specific frame by index.
        
        Args:
            frame_idx: Frame index (0-based)
            
        Returns:
            Frame as BGR numpy array, or None if failed
        """
        self.open()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        return frame if ret else None
    
    def __iter__(self) -> Iterator[Tuple[int, np.ndarray]]:
        """Iterate over all frames."""
        self.open()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        frame_idx = 0
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            yield frame_idx, frame
            frame_idx += 1
    
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class VideoWriter:
    """
    Writes frames to a video file.
    """
    
    def __init__(
        self,
        output_path: str,
        fps: float,
        size: Tuple[int, int],
        codec: str = "mp4v"
    ):
        """
        Initialize video writer.
        
        Args:
            output_path: Path for output video
            fps: Frames per second
            size: Frame size as (width, height)
            codec: FourCC codec code
        """
        self.output_path = output_path
        self.fps = fps
        self.size = size
        self.codec = codec
        self.writer = None
        self._opened = False
    
    def open(self):
        """Open the video file for writing."""
        if self._opened:
            return
        
        fourcc = cv2.VideoWriter_fourcc(*self.codec)
        self.writer = cv2.VideoWriter(
            self.output_path,
            fourcc,
            self.fps,
            self.size
        )
        
        if not self.writer.isOpened():
            raise ValueError(f"Could not open video writer: {self.output_path}")
        
        self._opened = True
    
    def write(self, frame: np.ndarray):
        """Write a frame to the video."""
        self.open()
        self.writer.write(frame)
    
    def close(self):
        """Close the video file."""
        if self.writer is not None:
            self.writer.release()
            self.writer = None
        self._opened = False
    
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def extract_keyframes(
    video_path: str,
    frame_indices: List[int],
    output_dir: str,
    prefix: str = "frame"
) -> List[str]:
    """
    Extract specific frames as images.
    
    Args:
        video_path: Path to video file
        frame_indices: List of frame indices to extract
        output_dir: Directory to save images
        prefix: Filename prefix
        
    Returns:
        List of saved image paths
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    saved_paths = []
    
    with VideoReader(video_path) as reader:
        for idx in frame_indices:
            frame = reader.read_frame(idx)
            if frame is not None:
                filename = f"{prefix}_{idx:06d}.jpg"
                filepath = str(Path(output_dir) / filename)
                cv2.imwrite(filepath, frame)
                saved_paths.append(filepath)
    
    return saved_paths
