"""Interactive face smudging feature for video playback.

This module provides an interactive video editing interface that allows users
to blur faces in real-time during video playback by clicking and dragging.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter is required for face smudge feature")

from config_manager import get_default_config, load_config, save_config

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class SmudgeOperation:
    """Represents a single smudge operation on a video frame."""

    frame_number: int
    x: float  # X coordinate in frame (0-1 normalized)
    y: float  # Y coordinate in frame (0-1 normalized)
    radius: int  # Blur radius in pixels
    sigma: float  # Blur strength (sigma for Gaussian)
    timestamp: float  # When operation was created
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class VideoMetadata:
    """Metadata about a video file."""

    file_path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float
    codec: str
    has_audio: bool
    audio_codec: Optional[str] = None


@dataclass
class FrameCacheEntry:
    """Entry in the frame cache."""

    frame_number: int
    frame_data: np.ndarray  # BGR format from OpenCV
    modified: bool  # True if smudges have been applied
    last_accessed: float  # Timestamp for LRU eviction


# ============================================================================
# Video Processing
# ============================================================================


class VideoProcessor:
    """Handles video I/O, frame decoding, and encoding."""

    def __init__(self, video_path: str):
        """Initialize video processor.

        Args:
            video_path: Path to the video file.
        """
        self.video_path = video_path
        self.capture: Optional[cv2.VideoCapture] = None
        self.metadata: Optional[VideoMetadata] = None
        self._load_video()

    def _load_video(self):
        """Load video file and extract metadata."""
        try:
            # Check if file exists
            if not os.path.exists(self.video_path):
                raise FileNotFoundError(f"Video file does not exist: {self.video_path}")

            # Check file size
            file_size = os.path.getsize(self.video_path) / (1024 * 1024 * 1024)  # GB
            if file_size > 2:
                logger.warning(f"Large video file detected: {file_size:.2f} GB")

            self.capture = cv2.VideoCapture(self.video_path)
            if not self.capture.isOpened():
                raise ValueError(f"Could not open video file. The file may be corrupted or use an unsupported codec: {self.video_path}")

            # Extract metadata
            width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self.capture.get(cv2.CAP_PROP_FPS)
            frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))

            # Validate extracted values
            if width <= 0 or height <= 0:
                raise ValueError("Invalid video dimensions. The video may be corrupted.")
            if fps <= 0:
                logger.warning("Invalid FPS detected, using default 30 FPS")
                fps = 30.0
            if frame_count <= 0:
                raise ValueError("Invalid frame count. The video may be corrupted.")

            duration = frame_count / fps if fps > 0 else 0

            # Try to get codec
            fourcc = int(self.capture.get(cv2.CAP_PROP_FOURCC))
            codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            if not codec or codec.strip() == "":
                codec = "unknown"

            self.metadata = VideoMetadata(
                file_path=self.video_path,
                width=width,
                height=height,
                fps=fps,
                frame_count=frame_count,
                duration_seconds=duration,
                codec=codec,
                has_audio=False,  # OpenCV doesn't provide audio info directly
                audio_codec=None,
            )

            logger.info(f"Loaded video: {width}x{height}, {fps} FPS, {frame_count} frames")

        except FileNotFoundError:
            raise
        except ValueError as e:
            logger.error(f"Error loading video: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading video: {e}")
            raise ValueError(f"Unexpected error loading video: {str(e)}")

    def get_frame(self, frame_number: int) -> Optional[np.ndarray]:
        """Get a specific frame from the video.

        Args:
            frame_number: Frame index (0-based).

        Returns:
            Frame as numpy array in BGR format, or None if frame cannot be read.
        """
        if not self.capture:
            return None

        try:
            # Validate frame number
            if frame_number < 0:
                logger.warning(f"Invalid frame number: {frame_number}")
                return None

            # Set position to desired frame
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.capture.read()

            if not ret or frame is None:
                logger.warning(f"Could not read frame {frame_number} (may be end of video or corrupted)")
                return None

            # Validate frame dimensions
            if frame.shape[0] == 0 or frame.shape[1] == 0:
                logger.warning(f"Frame {frame_number} has invalid dimensions")
                return None

            return frame
        except Exception as e:
            logger.error(f"Error reading frame {frame_number}: {e}")
            return None

    def close(self):
        """Close the video capture."""
        if self.capture:
            self.capture.release()
            self.capture = None


# ============================================================================
# Frame Cache
# ============================================================================


class FrameCache:
    """LRU cache for video frames."""

    def __init__(self, max_size: int = 100, video_processor: Optional[VideoProcessor] = None):
        """Initialize frame cache.

        Args:
            max_size: Maximum number of frames to cache.
            video_processor: VideoProcessor instance for decoding frames.
        """
        self.cache: Dict[int, FrameCacheEntry] = {}
        self.max_size = max_size
        self.access_times: Dict[int, float] = {}
        self.video_processor = video_processor

    def get_frame(self, frame_number: int) -> Optional[np.ndarray]:
        """Get frame from cache or decode from video.

        Args:
            frame_number: Frame index to retrieve.

        Returns:
            Frame as numpy array, or None if unavailable.
        """
        # Update access time for LRU
        current_time = time.time()
        self.access_times[frame_number] = current_time

        if frame_number in self.cache:
            entry = self.cache[frame_number]
            entry.last_accessed = current_time
            return entry.frame_data.copy()

        # Frame not in cache, decode it
        if not self.video_processor:
            return None

        frame = self.video_processor.get_frame(frame_number)
        if frame is None:
            return None

        # Add to cache (evicting LRU if needed)
        self._add_to_cache(frame_number, frame)

        return frame.copy()

    def _add_to_cache(self, frame_number: int, frame: np.ndarray):
        """Add frame to cache, evicting LRU if necessary."""
        # Evict if cache is full
        if len(self.cache) >= self.max_size:
            self._evict_lru()

        # Add new entry
        self.cache[frame_number] = FrameCacheEntry(
            frame_number=frame_number,
            frame_data=frame.copy(),
            modified=False,
            last_accessed=time.time(),
        )

    def _evict_lru(self):
        """Evict least recently used frame from cache."""
        if not self.access_times:
            # Fallback: remove first entry
            if self.cache:
                first_key = next(iter(self.cache))
                del self.cache[first_key]
            return

        # Find least recently used frame that is actually in cache
        # Filter access_times to only include frames in cache
        valid_access_times = {
            frame: time for frame, time in self.access_times.items()
            if frame in self.cache
        }
        
        if not valid_access_times:
            # Fallback: remove first entry if no valid access times
            if self.cache:
                first_key = next(iter(self.cache))
                del self.cache[first_key]
                if first_key in self.access_times:
                    del self.access_times[first_key]
            return

        lru_frame = min(valid_access_times.items(), key=lambda x: x[1])[0]
        del self.cache[lru_frame]
        del self.access_times[lru_frame]

    def mark_modified(self, frame_number: int):
        """Mark a frame as modified (has smudges applied)."""
        if frame_number in self.cache:
            self.cache[frame_number].modified = True

    def invalidate_frame(self, frame_number: int):
        """Invalidate a cached frame (force reload from video)."""
        if frame_number in self.cache:
            del self.cache[frame_number]
        if frame_number in self.access_times:
            del self.access_times[frame_number]

    def clear(self):
        """Clear all cached frames."""
        self.cache.clear()
        self.access_times.clear()


# ============================================================================
# Undo Manager
# ============================================================================


class UndoManager:
    """Manages undo/redo operations for smudge operations."""

    def __init__(self):
        """Initialize undo manager."""
        self.undo_stack: List[SmudgeOperation] = []
        self.redo_stack: List[SmudgeOperation] = []

    def add_operation(self, operation: SmudgeOperation):
        """Add operation and clear redo stack.

        Args:
            operation: Smudge operation to add.
        """
        self.undo_stack.append(operation)
        self.redo_stack.clear()

    def undo(self) -> Optional[SmudgeOperation]:
        """Pop last operation for undo.

        Returns:
            Operation that was undone, or None if stack is empty.
        """
        if not self.undo_stack:
            return None

        op = self.undo_stack.pop()
        self.redo_stack.append(op)
        return op

    def redo(self) -> Optional[SmudgeOperation]:
        """Restore last undone operation.

        Returns:
            Operation that was redone, or None if stack is empty.
        """
        if not self.redo_stack:
            return None

        op = self.redo_stack.pop()
        self.undo_stack.append(op)
        return op

    def can_undo(self) -> bool:
        """Check if undo is possible."""
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if redo is possible."""
        return len(self.redo_stack) > 0

    def clear(self):
        """Clear both undo and redo stacks."""
        self.undo_stack.clear()
        self.redo_stack.clear()


# ============================================================================
# Blur Functions
# ============================================================================


def create_circular_mask(shape: Tuple[int, int], center_x: float, center_y: float, radius: int) -> np.ndarray:
    """Create a circular mask for blur region.

    Args:
        shape: Shape of the frame (height, width).
        center_x: X coordinate of center (0-1 normalized).
        center_y: Y coordinate of center (0-1 normalized).
        radius: Radius of the circle in pixels.

    Returns:
        Boolean mask array.
    """
    height, width = shape[:2]
    y, x = np.ogrid[:height, :width]

    # Convert normalized coordinates to pixel coordinates
    cx = int(center_x * width)
    cy = int(center_y * height)

    # Create circular mask
    mask = (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2

    return mask


def apply_smudge_to_frame(frame: np.ndarray, operation: SmudgeOperation) -> np.ndarray:
    """Apply Gaussian blur to a circular region of a frame.

    Args:
        frame: Input frame in BGR format.
        operation: SmudgeOperation specifying blur parameters.

    Returns:
        Modified frame with blur applied.
    """
    # Create mask for circular blur region
    mask = create_circular_mask(frame.shape, operation.x, operation.y, operation.radius)

    # Extract region to blur
    y_indices, x_indices = np.where(mask)
    if len(y_indices) == 0:
        return frame

    # Get bounding box for the region
    y_min, y_max = y_indices.min(), y_indices.max() + 1
    x_min, x_max = x_indices.min(), x_indices.max() + 1

    # Clip to frame bounds
    y_min = max(0, y_min)
    y_max = min(frame.shape[0], y_max)
    x_min = max(0, x_min)
    x_max = min(frame.shape[1], x_max)

    # Extract region
    region = frame[y_min:y_max, x_min:x_max].copy()

    # Apply Gaussian blur
    # Kernel size must be odd, calculate from sigma
    kernel_size = int(6 * operation.sigma + 1)
    if kernel_size % 2 == 0:
        kernel_size += 1

    blurred_region = cv2.GaussianBlur(region, (kernel_size, kernel_size), operation.sigma)

    # Create mask for the region
    region_mask = mask[y_min:y_max, x_min:x_max]

    # Composite blurred region back into frame
    frame[y_min:y_max, x_min:x_max][region_mask] = blurred_region[region_mask]

    return frame


# ============================================================================
# Coordinate Conversion
# ============================================================================


def display_to_frame_coords(
    display_x: int,
    display_y: int,
    display_width: int,
    display_height: int,
    video_width: int,
    video_height: int,
) -> Tuple[float, float]:
    """Convert mouse coordinates in display window to frame coordinates.

    Handles aspect ratio preservation and letterboxing/pillarboxing.

    Args:
        display_x: X coordinate in display window.
        display_y: Y coordinate in display window.
        display_width: Width of display area.
        display_height: Height of display area.
        video_width: Width of video frame.
        video_height: Height of video frame.

    Returns:
        Tuple of (frame_x, frame_y) as normalized coordinates (0-1).
    """
    logger.debug(f"Coordinate conversion: display=({display_x},{display_y}), display_size=({display_width},{display_height}), video_size=({video_width},{video_height})")
    
    # Handle invalid dimensions
    if display_width <= 0 or display_height <= 0:
        logger.warning(f"Invalid display dimensions: {display_width}x{display_height}")
        return (0.0, 0.0)
    if video_width <= 0 or video_height <= 0:
        logger.warning(f"Invalid video dimensions: {video_width}x{video_height}")
        return (0.0, 0.0)

    # Calculate aspect ratios
    video_aspect = video_width / video_height
    display_aspect = display_width / display_height

    logger.debug(f"Aspect ratios: video={video_aspect:.3f}, display={display_aspect:.3f}")

    # Calculate actual video display area (accounting for aspect ratio)
    if video_aspect > display_aspect:
        # Video is wider - letterboxing (black bars top/bottom)
        actual_width = display_width
        actual_height = int(display_width / video_aspect)
        offset_x = 0
        offset_y = (display_height - actual_height) // 2
    else:
        # Video is taller - pillarboxing (black bars left/right)
        actual_width = int(display_height * video_aspect)
        actual_height = display_height
        offset_x = (display_width - actual_width) // 2
        offset_y = 0

    logger.debug(f"Actual video area: {actual_width}x{actual_height}, offset=({offset_x},{offset_y})")

    # Check if click is within actual video area
    if display_x < offset_x or display_x >= offset_x + actual_width:
        logger.debug(f"Click outside bounds: x={display_x} not in [{offset_x}, {offset_x + actual_width})")
        return (0.0, 0.0)  # Outside bounds
    if display_y < offset_y or display_y >= offset_y + actual_height:
        logger.debug(f"Click outside bounds: y={display_y} not in [{offset_y}, {offset_y + actual_height})")
        return (0.0, 0.0)  # Outside bounds

    # Convert display coordinates to video coordinates
    video_x = (display_x - offset_x) / actual_width
    video_y = (display_y - offset_y) / actual_height

    # Clamp to [0, 1]
    video_x = max(0.0, min(1.0, video_x))
    video_y = max(0.0, min(1.0, video_y))

    logger.debug(f"Converted coordinates: ({video_x:.3f}, {video_y:.3f})")
    return (video_x, video_y)


# ============================================================================
# Main Window
# ============================================================================


class FaceSmudgeWindow(ctk.CTkToplevel):
    """Main window for interactive face smudging."""

    def __init__(self, parent):
        """Initialize face smudge window.

        Args:
            parent: Parent window (DefaceApp instance).
        """
        super().__init__(parent)

        self.parent = parent
        self.title("Face Smudge Mode")
        self.geometry("1200x800")

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # State
        self.video_processor: Optional[VideoProcessor] = None
        self.frame_cache: Optional[FrameCache] = None
        self.undo_manager = UndoManager()
        self.smudge_operations: Dict[int, List[SmudgeOperation]] = {}  # frame_number -> operations

        # Playback state
        self.current_frame = 0
        self.is_playing = False
        self.is_paused = False
        # playback_speed is loaded from config above
        self.playback_thread: Optional[threading.Thread] = None
        self.stop_playback = False

        # Smudge state
        self.is_dragging = False
        self.drag_start_frame: Optional[int] = None
        self.current_operation: Optional[SmudgeOperation] = None
        self.last_mouse_x: Optional[float] = None  # Last known mouse position (normalized)
        self.last_mouse_y: Optional[float] = None
        self.frames_with_drag: set[int] = set()  # Frames where mouse was held during playback

        # Configuration
        config = load_config()
        default_config = get_default_config()
        face_smudge_config = config.get("face_smudge_config", default_config.get("face_smudge_config", {}))
        self.blur_radius = face_smudge_config.get("blur_radius", 50)
        self.blur_sigma = face_smudge_config.get("blur_sigma", 25)
        self.cache_size = face_smudge_config.get("cache_size", 100)
        self.playback_speed = face_smudge_config.get("playback_speed", 1.0)

        # Video display state (will be set by _update_display)
        self.video_display_width = 0
        self.video_display_height = 0
        self.video_display_x = 0
        self.video_display_y = 0

        # UI components
        self.video_label: Optional[ctk.CTkLabel] = None
        self.current_image: Optional[ImageTk.PhotoImage] = None

        # Create UI
        self._create_widgets()

        # Center on parent
        self._center_on_parent()

        # Focus on dialog
        self.focus()

        # Bind keyboard shortcuts
        self.bind("<space>", lambda e: self._toggle_play_pause())
        self.bind("<Left>", lambda e: self._step_backward())
        self.bind("<Right>", lambda e: self._step_forward())
        self.bind("<Home>", lambda e: self._jump_to_start())
        self.bind("<End>", lambda e: self._jump_to_end())
        self.bind("<Control-z>", lambda e: self._undo() if sys.platform != "darwin" else None)
        self.bind("<Command-z>", lambda e: self._undo() if sys.platform == "darwin" else None)
        self.bind("<Control-s>", lambda e: self._save_video() if sys.platform != "darwin" else None)
        self.bind("<Command-s>", lambda e: self._save_video() if sys.platform == "darwin" else None)
        self.bind("<Escape>", lambda e: self._on_cancel())

        # Load video file
        self._load_video_file()

    def _center_on_parent(self):
        """Center the window on its parent."""
        self.update_idletasks()

        parent_x = self.master.winfo_x()
        parent_y = self.master.winfo_y()
        parent_width = self.master.winfo_width()
        parent_height = self.master.winfo_height()

        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()

        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)

        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create and layout all UI widgets."""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Header
        header_frame = ctk.CTkFrame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header_frame, text="Face Smudge Mode", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left", padx=10, pady=10)

        self.file_label = ctk.CTkLabel(
            header_frame, text="No video loaded", font=ctk.CTkFont(size=12), text_color="#8ea4c7"  # Mist Blue
        )
        self.file_label.pack(side="left", padx=10, pady=10)

        self.duration_label = ctk.CTkLabel(
            header_frame, text="", font=ctk.CTkFont(size=12), text_color="#8ea4c7"  # Mist Blue
        )
        self.duration_label.pack(side="right", padx=10, pady=10)

        # Video display area
        video_frame = ctk.CTkFrame(main_frame)
        video_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.video_label = ctk.CTkLabel(
            video_frame,
            text="Click 'Load Video' to select a video file",
            font=ctk.CTkFont(size=14),
            fg_color="#030922",  # Dark panel background
        )
        self.video_label.pack(fill="both", expand=True, padx=10, pady=10)

        # Bind mouse events to video label
        self.video_label.bind("<Button-1>", self._on_mouse_press)
        self.video_label.bind("<B1-Motion>", self._on_mouse_drag)
        self.video_label.bind("<Motion>", self._on_mouse_motion)  # Track mouse position even when not dragging
        self.video_label.bind("<ButtonRelease-1>", self._on_mouse_release)
        # Change cursor when over video area
        self.video_label.bind("<Enter>", lambda e: self.video_label.configure(cursor="crosshair"))
        self.video_label.bind("<Leave>", lambda e: self.video_label.configure(cursor=""))

        # Playback controls
        controls_frame = ctk.CTkFrame(main_frame)
        controls_frame.pack(fill="x", pady=(0, 10))

        # Transport controls
        transport_frame = ctk.CTkFrame(controls_frame)
        transport_frame.pack(side="left", padx=10, pady=10)

        self.jump_start_btn = ctk.CTkButton(
            transport_frame, text="◄◄", command=self._jump_to_start, width=40, height=30
        )
        self.jump_start_btn.pack(side="left", padx=2)

        self.step_back_btn = ctk.CTkButton(
            transport_frame, text="◄", command=self._step_backward, width=40, height=30
        )
        self.step_back_btn.pack(side="left", padx=2)

        self.play_pause_btn = ctk.CTkButton(
            transport_frame, text="⏸", command=self._toggle_play_pause, width=60, height=30
        )
        self.play_pause_btn.pack(side="left", padx=2)

        self.step_forward_btn = ctk.CTkButton(
            transport_frame, text="►", command=self._step_forward, width=40, height=30
        )
        self.step_forward_btn.pack(side="left", padx=2)

        self.jump_end_btn = ctk.CTkButton(
            transport_frame, text="►►", command=self._jump_to_end, width=40, height=30
        )
        self.jump_end_btn.pack(side="left", padx=2)

        # Playback speed
        speed_frame = ctk.CTkFrame(controls_frame)
        speed_frame.pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(speed_frame, text="Speed:", font=ctk.CTkFont(size=12)).pack(side="left", padx=5)

        # Set initial speed based on config
        speed_map_reverse = {0.25: "0.25x", 0.5: "0.5x", 1.0: "1x", 2.0: "2x", 4.0: "4x"}
        initial_speed_str = speed_map_reverse.get(self.playback_speed, "1x")
        self.speed_var = tk.StringVar(value=initial_speed_str)
        speed_menu = ctk.CTkOptionMenu(
            speed_frame,
            values=["0.25x", "0.5x", "1x", "2x", "4x"],
            variable=self.speed_var,
            command=self._on_speed_changed,
            width=80,
        )
        speed_menu.pack(side="left", padx=5)

        # Settings button
        settings_btn = ctk.CTkButton(
            controls_frame, text="Settings", command=self._open_settings, width=100, height=30
        )
        settings_btn.pack(side="right", padx=10, pady=10)

        # Timeline scrubber
        timeline_frame = ctk.CTkFrame(main_frame)
        timeline_frame.pack(fill="x", pady=(0, 10))

        self.scrubber = ctk.CTkSlider(
            timeline_frame, from_=0, to=100, command=self._on_scrubber_changed
        )
        self.scrubber.pack(fill="x", padx=10, pady=10)

        self.time_label = ctk.CTkLabel(
            timeline_frame, text="00:00 / 00:00", font=ctk.CTkFont(size=11), text_color="#8ea4c7"  # Mist Blue
        )
        self.time_label.pack(pady=(0, 10))

        # Progress and status
        status_frame = ctk.CTkFrame(main_frame)
        status_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(status_frame, text="Progress:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=10, pady=10
        )

        self.progress_bar = ctk.CTkProgressBar(status_frame, width=300)
        self.progress_bar.pack(side="left", padx=10, pady=10)
        self.progress_bar.set(0)

        self.operations_label = ctk.CTkLabel(
            status_frame, text="Operations: 0 smudges", font=ctk.CTkFont(size=11), text_color="#8ea4c7"  # Mist Blue
        )
        self.operations_label.pack(side="left", padx=10, pady=10)

        # Status indicator for debugging
        self.status_indicator = ctk.CTkLabel(
            status_frame,
            text="Status: Ready | Mouse: -- | Dragging: No",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        )
        self.status_indicator.pack(side="right", padx=10, pady=10)

        # Action buttons
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x")

        self.undo_btn = ctk.CTkButton(
            button_frame, text="Undo", command=self._undo, width=100, height=30, state="disabled"
        )
        self.undo_btn.pack(side="left", padx=10, pady=10)

        clear_btn = ctk.CTkButton(
            button_frame, text="Clear All", command=self._clear_all, width=100, height=30
        )
        clear_btn.pack(side="left", padx=10, pady=10)

        save_btn = ctk.CTkButton(
            button_frame, text="Save Video...", command=self._save_video, width=120, height=30
        )
        save_btn.pack(side="right", padx=10, pady=10)

        cancel_btn = ctk.CTkButton(
            button_frame, text="Cancel", command=self._on_cancel, width=100, height=30, fg_color="#1a253a"  # Border subtle
        )
        cancel_btn.pack(side="right", padx=10, pady=10)

    def _load_video_file(self):
        """Open file dialog to load video."""
        filename = filedialog.askopenfilename(
            parent=self,
            title="Select video file",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv"),
                ("MP4", "*.mp4"),
                ("AVI", "*.avi"),
                ("MOV", "*.mov"),
                ("MKV", "*.mkv"),
                ("All files", "*.*"),
            ],
        )

        if not filename:
            # User cancelled, close window
            self.destroy()
            return

        try:
            self.video_processor = VideoProcessor(filename)
            self.frame_cache = FrameCache(max_size=self.cache_size, video_processor=self.video_processor)

            # Update UI
            filename_short = os.path.basename(filename)
            if len(filename_short) > 40:
                filename_short = filename_short[:37] + "..."
            self.file_label.configure(text=f"File: {filename_short}")

            if self.video_processor.metadata:
                duration = self.video_processor.metadata.duration_seconds
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                self.duration_label.configure(text=f"Duration: {minutes:02d}:{seconds:02d}")

                # Update scrubber
                self.scrubber.configure(to=self.video_processor.metadata.frame_count - 1)

            # Load first frame
            self.current_frame = 0
            self._update_display()

        except Exception as e:
            logger.error(f"Error loading video: {e}")
            messagebox.showerror("Error", f"Could not load video file:\n{str(e)}")
            self.destroy()

    def _update_display(self):
        """Update video display with current frame."""
        if not self.video_processor or not self.frame_cache:
            return

        # Get frame
        frame = self.frame_cache.get_frame(self.current_frame)
        if frame is None:
            return

        # Apply saved smudges for this frame
        if self.current_frame in self.smudge_operations:
            num_ops = len(self.smudge_operations[self.current_frame])
            logger.debug(f"Applying {num_ops} saved operation(s) to frame {self.current_frame}")
            for operation in self.smudge_operations[self.current_frame]:
                frame = apply_smudge_to_frame(frame, operation)

        # Apply current operation for preview (if dragging)
        if self.current_operation and self.current_operation.frame_number == self.current_frame:
            logger.debug(f"Applying current operation preview to frame {self.current_frame}")
            frame = apply_smudge_to_frame(frame, self.current_operation)

        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert to PIL Image
        pil_image = Image.fromarray(frame_rgb)

        # Get display size
        self.update_idletasks()
        display_width = self.video_label.winfo_width()
        display_height = self.video_label.winfo_height()

        if display_width <= 1 or display_height <= 1:
            # Widget not yet sized, use default
            display_width = 800
            display_height = 600

        # Calculate aspect-ratio-preserving size
        video_width = self.video_processor.metadata.width
        video_height = self.video_processor.metadata.height
        video_aspect = video_width / video_height
        display_aspect = display_width / display_height

        if video_aspect > display_aspect:
            # Video is wider
            new_width = display_width
            new_height = int(display_width / video_aspect)
        else:
            # Video is taller
            new_width = int(display_height * video_aspect)
            new_height = display_height

        # Resize image
        pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Convert to PhotoImage
        self.current_image = ImageTk.PhotoImage(pil_image)

        # Update label
        self.video_label.configure(image=self.current_image, text="")

        # Store display dimensions for coordinate conversion
        self.video_display_width = new_width
        self.video_display_height = new_height
        self.video_display_x = (display_width - new_width) // 2
        self.video_display_y = (display_height - new_height) // 2
        
        
        logger.debug(
            f"Updated video display: size=({new_width}, {new_height}), "
            f"offset=({self.video_display_x}, {self.video_display_y}), "
            f"widget_size=({display_width}, {display_height})"
        )

        # Update time label
        if self.video_processor.metadata:
            current_time = self.current_frame / self.video_processor.metadata.fps
            total_time = self.video_processor.metadata.duration_seconds
            current_min = int(current_time // 60)
            current_sec = int(current_time % 60)
            total_min = int(total_time // 60)
            total_sec = int(total_time % 60)
            self.time_label.configure(text=f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}")

        # Update scrubber
        if self.video_processor.metadata:
            max_frame = self.video_processor.metadata.frame_count - 1
            if max_frame > 0:
                self.scrubber.set(self.current_frame)

        # Update progress and status
        self._update_progress()


    def _update_progress(self):
        """Update progress bar based on processed frames."""
        if not self.video_processor or not self.video_processor.metadata:
            return

        # Count frames with operations
        processed_frames = len(self.smudge_operations)
        total_frames = self.video_processor.metadata.frame_count

        if total_frames > 0:
            progress = processed_frames / total_frames
            self.progress_bar.set(progress)

        # Update operations count
        total_operations = sum(len(ops) for ops in self.smudge_operations.values())
        self.operations_label.configure(text=f"Operations: {total_operations} smudges")

        # Update status indicator
        mouse_status = "Tracked" if (self.last_mouse_x is not None and self.last_mouse_y is not None) else "None"
        drag_status = "Yes" if self.is_dragging else "No"
        current_op = "Active" if self.current_operation else "None"
        mouse_pos = f"({self.last_mouse_x:.2f},{self.last_mouse_y:.2f})" if self.last_mouse_x is not None else "--"
        self.status_indicator.configure(
            text=f"Status: {current_op} | Mouse: {mouse_pos} | Dragging: {drag_status}"
        )

    def _on_mouse_press(self, event):
        """Handle mouse button press on video display."""
        logger.info(f"Mouse press: event.x={event.x}, event.y={event.y}")
        if not self.video_processor or not self.video_processor.metadata:
            logger.warning("Mouse press: No video processor or metadata")
            return

        try:
            # Event coordinates are already relative to the video display area
            # Get current video display size for normalization
            if self.video_display_width == 0 or self.video_display_height == 0:
                logger.warning("Video display dimensions not set, forcing update")
                self._update_display()
                if self.video_display_width == 0 or self.video_display_height == 0:
                    logger.error("Still no video display dimensions after update")
                    return
            
            # event.x and event.y are already in video display coordinates
            rel_x = event.x
            rel_y = event.y
            
            logger.info(
                f"Click: event=({event.x}, {event.y}), "
                f"video_size=({self.video_display_width}, {self.video_display_height})"
            )
            
            # Check if click is within video display area
            if rel_x < 0 or rel_x >= self.video_display_width or rel_y < 0 or rel_y >= self.video_display_height:
                logger.warning(
                    f"Click outside video area: "
                    f"event=({event.x}, {event.y}), "
                    f"video_size=({self.video_display_width}, {self.video_display_height})"
                )
                return
            
            # Convert to normalized coordinates (0-1)
            frame_x = rel_x / self.video_display_width
            frame_y = rel_y / self.video_display_height
            
            # Clamp to [0, 1]
            frame_x = max(0.0, min(1.0, frame_x))
            frame_y = max(0.0, min(1.0, frame_y))

            logger.info(f"Converted coordinates: frame_x={frame_x:.3f}, frame_y={frame_y:.3f}")

            # Validate coordinates
            if frame_x < 0 or frame_x > 1 or frame_y < 0 or frame_y > 1:
                logger.warning(f"Mouse press: Invalid coordinates: {frame_x}, {frame_y}")
                return

            # Start smudge operation
            self.is_dragging = True
            self.drag_start_frame = self.current_frame
            self.frames_with_drag.clear()  # Reset frame tracking

            # Store mouse position
            self.last_mouse_x = frame_x
            self.last_mouse_y = frame_y

            logger.info(f"Starting drag: frame={self.current_frame}, pos=({frame_x:.3f}, {frame_y:.3f})")

            # Create operation for current frame
            self._create_operation_for_current_frame(frame_x, frame_y)

            # Update display to show preview
            self._update_display()
            self._update_progress()  # Update status indicator
        except Exception as e:
            logger.error(f"Error in mouse press handler: {e}", exc_info=True)
            # Don't show error to user for mouse events, just log

    def _on_mouse_motion(self, event):
        """Handle mouse motion (track position even when not dragging)."""
        if not self.video_processor or not self.video_processor.metadata:
            return

        try:
            # Event coordinates are already relative to the video display area
            if self.video_display_width == 0 or self.video_display_height == 0:
                return
            
            # event.x and event.y are already in video display coordinates
            rel_x = event.x
            rel_y = event.y
            
            # Check if within video display area
            if rel_x < 0 or rel_x >= self.video_display_width or rel_y < 0 or rel_y >= self.video_display_height:
                return  # Outside video area
            
            # Convert to normalized coordinates (0-1)
            frame_x = rel_x / self.video_display_width
            frame_y = rel_y / self.video_display_height
            
            # Clamp to [0, 1]
            frame_x = max(0.0, min(1.0, frame_x))
            frame_y = max(0.0, min(1.0, frame_y))

            # Store last known position
            self.last_mouse_x = frame_x
            self.last_mouse_y = frame_y

            # If dragging, update current operation
            if self.is_dragging:
                logger.debug(f"Mouse motion while dragging: frame={self.current_frame}, pos=({frame_x:.3f}, {frame_y:.3f})")
                if self.current_operation:
                    self.current_operation.x = frame_x
                    self.current_operation.y = frame_y
                self._update_display()
                self._update_progress()  # Update status indicator
        except Exception as e:
            logger.error(f"Error in mouse motion handler: {e}", exc_info=True)

    def _on_mouse_drag(self, event):
        """Handle mouse drag on video display."""
        # Mouse motion is handled by _on_mouse_motion
        # This is kept for compatibility but mainly just calls motion handler
        self._on_mouse_motion(event)

    def _on_mouse_release(self, event):
        """Handle mouse button release on video display."""
        logger.info(f"Mouse release: is_dragging={self.is_dragging}")
        if not self.is_dragging:
            return

        # Save current operation if it exists
        if self.current_operation:
            logger.info(f"Saving operation on release: frame={self.current_operation.frame_number}, pos=({self.current_operation.x:.3f}, {self.current_operation.y:.3f})")
            self._save_operation(self.current_operation)
        else:
            logger.warning("Mouse release: No current operation to save")

        # Save all operations created during playback
        # Operations are already saved as frames advance, but ensure current one is saved
        total_ops = sum(len(ops) for ops in self.smudge_operations.values())
        logger.info(f"Mouse release: Total operations saved: {total_ops}, frames with operations: {len(self.smudge_operations)}")

        self.is_dragging = False
        self.current_operation = None
        self.drag_start_frame = None
        self.frames_with_drag.clear()

        # Update display
        self._update_display()
        self._update_progress()  # Update status indicator

    def _create_operation_for_current_frame(self, frame_x: float, frame_y: float):
        """Create a smudge operation for the current frame.

        Args:
            frame_x: X coordinate in frame (0-1 normalized).
            frame_y: Y coordinate in frame (0-1 normalized).
        """
        logger.info(f"Creating operation: frame={self.current_frame}, pos=({frame_x:.3f}, {frame_y:.3f}), radius={self.blur_radius}, sigma={self.blur_sigma}")
        if not self.video_processor or not self.video_processor.metadata:
            logger.warning("Cannot create operation: No video processor or metadata")
            return

        # If we already have an operation for this frame, update it
        if self.current_operation and self.current_operation.frame_number == self.current_frame:
            logger.debug(f"Updating existing operation for frame {self.current_frame}")
            self.current_operation.x = frame_x
            self.current_operation.y = frame_y
        else:
            # Save previous operation if it exists
            if self.current_operation:
                logger.debug(f"Saving previous operation for frame {self.current_operation.frame_number}")
                self._save_operation(self.current_operation)

            # Create new operation for current frame
            self.current_operation = SmudgeOperation(
                frame_number=self.current_frame,
                x=frame_x,
                y=frame_y,
                radius=self.blur_radius,
                sigma=self.blur_sigma,
                timestamp=time.time(),
            )

            logger.info(f"Created new operation: id={self.current_operation.operation_id}, frame={self.current_frame}")

            # Mark this frame as having a drag operation
            self.frames_with_drag.add(self.current_frame)

            # Save operation immediately (so it persists even if mouse is released)
            self._save_operation(self.current_operation)

    def _save_operation(self, operation: SmudgeOperation):
        """Save a smudge operation to the operations dictionary.

        Args:
            operation: The smudge operation to save.
        """
        logger.info(f"Saving operation: frame={operation.frame_number}, id={operation.operation_id}, pos=({operation.x:.3f}, {operation.y:.3f})")
        if operation.frame_number not in self.smudge_operations:
            self.smudge_operations[operation.frame_number] = []
            logger.debug(f"Created new list for frame {operation.frame_number}")

        # Check if operation with same ID already exists
        existing_ids = {op.operation_id for op in self.smudge_operations[operation.frame_number]}
        if operation.operation_id not in existing_ids:
            self.smudge_operations[operation.frame_number].append(operation)
            self.undo_manager.add_operation(operation)
            self.frame_cache.invalidate_frame(operation.frame_number)
            self.undo_btn.configure(state="normal")
            logger.info(f"Operation saved successfully. Frame {operation.frame_number} now has {len(self.smudge_operations[operation.frame_number])} operation(s)")
        else:
            logger.debug(f"Operation {operation.operation_id} already exists for frame {operation.frame_number}, skipping")

    def _toggle_play_pause(self):
        """Toggle play/pause state."""
        if not self.video_processor:
            return

        if self.is_playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        """Start playback."""
        if not self.video_processor or self.is_playing:
            return

        self.is_playing = True
        self.is_paused = False
        self.stop_playback = False
        self.play_pause_btn.configure(text="⏸")

        # Start playback thread
        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

    def _pause(self):
        """Pause playback."""
        self.is_playing = False
        self.is_paused = True
        self.play_pause_btn.configure(text="►")

    def _stop(self):
        """Stop playback and return to beginning."""
        self.stop_playback = True
        self.is_playing = False
        self.is_paused = False
        self.play_pause_btn.configure(text="►")
        self.current_frame = 0
        self._update_display()

    def _playback_loop(self):
        """Playback loop running in separate thread."""
        if not self.video_processor or not self.video_processor.metadata:
            return

        try:
            fps = self.video_processor.metadata.fps
            if fps <= 0:
                fps = 30.0  # Default FPS if invalid
            frame_delay = 1.0 / (fps * self.playback_speed)

            while self.is_playing and not self.stop_playback:
                start_time = time.time()

                # Advance frame
                self.current_frame += 1
                if self.current_frame >= self.video_processor.metadata.frame_count:
                    # End of video
                    self.after(0, self._pause)
                    self.current_frame = self.video_processor.metadata.frame_count - 1
                    break

                # If mouse is held down, create operation for this frame
                if self.is_dragging and self.last_mouse_x is not None and self.last_mouse_y is not None:
                    logger.info(f"Playback: Creating operation for frame {self.current_frame} while dragging")
                    # Capture values in closure
                    mouse_x = self.last_mouse_x
                    mouse_y = self.last_mouse_y
                    self.after(0, lambda: self._create_operation_for_current_frame(mouse_x, mouse_y))
                else:
                    if self.is_dragging:
                        logger.warning(f"Playback: Dragging but no mouse position: x={self.last_mouse_x}, y={self.last_mouse_y}")

                # Update display (in main thread)
                try:
                    self.after(0, self._update_display)
                except Exception as e:
                    logger.error(f"Error updating display: {e}")
                    break

                # Sleep to maintain frame rate
                elapsed = time.time() - start_time
                sleep_time = max(0, frame_delay - elapsed)
                time.sleep(sleep_time)
        except Exception as e:
            logger.error(f"Error in playback loop: {e}")
            self.after(0, lambda: self._pause())

    def _step_forward(self):
        """Step forward one frame."""
        if not self.video_processor or not self.video_processor.metadata:
            return

        if self.current_frame < self.video_processor.metadata.frame_count - 1:
            self.current_frame += 1
            self._update_display()

    def _step_backward(self):
        """Step backward one frame."""
        if self.current_frame > 0:
            self.current_frame -= 1
            self._update_display()

    def _jump_to_start(self):
        """Jump to beginning of video."""
        self.current_frame = 0
        self._update_display()

    def _jump_to_end(self):
        """Jump to end of video."""
        if self.video_processor and self.video_processor.metadata:
            self.current_frame = self.video_processor.metadata.frame_count - 1
            self._update_display()

    def _on_speed_changed(self, value: str):
        """Handle playback speed change."""
        speed_map = {"0.25x": 0.25, "0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0}
        self.playback_speed = speed_map.get(value, 1.0)
        # Save the new speed preference
        self._save_settings()

    def _on_scrubber_changed(self, value: float):
        """Handle scrubber position change."""
        if not self.video_processor or not self.video_processor.metadata:
            return

        # Only update if user is dragging (not programmatic update)
        frame = int(value)
        if frame != self.current_frame:
            self.current_frame = frame
            self._update_display()

    def _undo(self):
        """Undo last smudge operation."""
        operation = self.undo_manager.undo()
        if operation:
            # Remove from operations
            if operation.frame_number in self.smudge_operations:
                self.smudge_operations[operation.frame_number] = [
                    op for op in self.smudge_operations[operation.frame_number] if op.operation_id != operation.operation_id
                ]
                if not self.smudge_operations[operation.frame_number]:
                    del self.smudge_operations[operation.frame_number]

            # Invalidate frame cache
            self.frame_cache.invalidate_frame(operation.frame_number)

            # Update display
            self._update_display()
            self._update_progress()

            # Update undo button state
            if not self.undo_manager.can_undo():
                self.undo_btn.configure(state="disabled")

    def _clear_all(self):
        """Clear all smudge operations."""
        if not self.smudge_operations:
            return

        if messagebox.askyesno("Clear All", "Remove all smudge operations?"):
            self.smudge_operations.clear()
            self.undo_manager.clear()
            self.frame_cache.clear()
            self.undo_btn.configure(state="disabled")
            self._update_display()
            self._update_progress()

    def _open_settings(self):
        """Open settings dialog."""
        # Create simple settings dialog
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Face Smudge Settings")
        settings_window.geometry("400x500")
        settings_window.transient(self)
        settings_window.grab_set()

        main_frame = ctk.CTkFrame(settings_window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(main_frame, text="Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 20))

        # Blur radius
        radius_frame = ctk.CTkFrame(main_frame)
        radius_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(radius_frame, text=f"Blur Radius: {self.blur_radius}", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        radius_var = tk.IntVar(value=self.blur_radius)
        radius_slider = ctk.CTkSlider(radius_frame, from_=10, to=200, variable=radius_var, command=lambda v: self._update_radius_label(radius_label, v))
        radius_slider.pack(fill="x", padx=10, pady=(0, 5))

        radius_label = ctk.CTkLabel(radius_frame, text=str(self.blur_radius), font=ctk.CTkFont(size=11), text_color="#8ea4c7")  # Mist Blue
        radius_label.pack(anchor="w", padx=10, pady=(0, 10))

        # Blur sigma
        sigma_frame = ctk.CTkFrame(main_frame)
        sigma_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(sigma_frame, text=f"Blur Strength (Sigma): {self.blur_sigma}", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        sigma_var = tk.DoubleVar(value=self.blur_sigma)
        sigma_slider = ctk.CTkSlider(sigma_frame, from_=5, to=100, variable=sigma_var, command=lambda v: self._update_sigma_label(sigma_label, v))
        sigma_slider.pack(fill="x", padx=10, pady=(0, 5))

        sigma_label = ctk.CTkLabel(sigma_frame, text=str(int(self.blur_sigma)), font=ctk.CTkFont(size=11), text_color="#8ea4c7")  # Mist Blue
        sigma_label.pack(anchor="w", padx=10, pady=(0, 10))

        # Buttons
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=20)

        def on_ok():
            self.blur_radius = int(radius_var.get())
            self.blur_sigma = float(sigma_var.get())
            # Save to config
            self._save_settings()
            settings_window.destroy()

        ok_btn = ctk.CTkButton(button_frame, text="OK", command=on_ok, width=100)
        ok_btn.pack(side="right", padx=10)

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=settings_window.destroy, width=100, fg_color="#1a253a")  # Border subtle
        cancel_btn.pack(side="right", padx=10)

        settings_window.focus()

    def _update_radius_label(self, label, value):
        """Update radius label in settings dialog."""
        label.configure(text=str(int(value)))

    def _update_sigma_label(self, label, value):
        """Update sigma label in settings dialog."""
        label.configure(text=str(int(value)))

    def _save_settings(self):
        """Save settings to config."""
        config = load_config()
        if "face_smudge_config" not in config:
            config["face_smudge_config"] = {}
        config["face_smudge_config"]["blur_radius"] = self.blur_radius
        config["face_smudge_config"]["blur_sigma"] = self.blur_sigma
        config["face_smudge_config"]["cache_size"] = self.cache_size
        config["face_smudge_config"]["playback_speed"] = self.playback_speed
        save_config(config)

    def _save_video(self):
        """Save video with smudge operations applied."""
        if not self.video_processor or not self.smudge_operations:
            messagebox.showinfo("No Operations", "No smudge operations to save.")
            return

        # Get output filename
        input_path = Path(self.video_processor.video_path)
        default_name = f"{input_path.stem}_smudged{input_path.suffix}"

        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Save smudged video",
            defaultextension=input_path.suffix,
            initialfile=default_name,
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv"),
                ("MP4", "*.mp4"),
                ("All files", "*.*"),
            ],
        )

        if not filename:
            return

        # Show progress dialog
        progress_window = ctk.CTkToplevel(self)
        progress_window.title("Encoding Video")
        progress_window.geometry("400x150")
        progress_window.transient(self)
        progress_window.grab_set()

        progress_frame = ctk.CTkFrame(progress_window)
        progress_frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(progress_frame, text="Encoding video...", font=ctk.CTkFont(size=14)).pack(pady=10)

        progress_bar = ctk.CTkProgressBar(progress_frame, width=300)
        progress_bar.pack(pady=10)
        progress_bar.set(0)

        status_label = ctk.CTkLabel(progress_frame, text="Starting...", font=ctk.CTkFont(size=11), text_color="#8ea4c7")  # Mist Blue
        status_label.pack(pady=5)

        progress_window.update()

        # Encode video in thread
        def encode_video():
            try:
                metadata = self.video_processor.metadata
                if not metadata:
                    raise ValueError("No video metadata available")

                # Check disk space (rough estimate)
                estimated_size = metadata.width * metadata.height * metadata.frame_count * 3 / (1024 * 1024)  # MB
                try:
                    stat = os.statvfs(os.path.dirname(filename))
                    free_space = stat.f_bavail * stat.f_frsize / (1024 * 1024)  # MB
                    if free_space < estimated_size * 1.5:
                        raise ValueError(f"Insufficient disk space. Estimated need: {estimated_size:.1f} MB, Available: {free_space:.1f} MB")
                except (OSError, AttributeError):
                    # statvfs not available on all platforms, skip check
                    pass

                # Check write permissions
                try:
                    test_file = filename + ".test"
                    with open(test_file, "w") as f:
                        f.write("test")
                    os.remove(test_file)
                except (OSError, PermissionError) as e:
                    raise ValueError(f"Cannot write to output location: {str(e)}")

                # Create temporary video file first
                temp_video_fd, temp_video = tempfile.mkstemp(suffix=".mp4", prefix="deface_smudge_")
                os.close(temp_video_fd)  # Close file descriptor, we'll use the path with VideoWriter

                try:
                    # Open video writer to temporary file
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(temp_video, fourcc, metadata.fps, (metadata.width, metadata.height))

                    if not writer.isOpened():
                        raise ValueError("Could not initialize video writer. The codec may not be supported.")

                    total_frames = metadata.frame_count
                    frames_written = 0
                    for frame_num in range(total_frames):
                        # Check for cancellation (if we add cancel button)
                        # Update progress
                        progress = (frame_num + 1) / total_frames
                        progress_bar.set(progress)
                        status_label.configure(text=f"Processing frame {frame_num + 1} / {total_frames}")
                        progress_window.update()

                        # Get frame
                        frame = self.frame_cache.get_frame(frame_num)
                        if frame is None:
                            # Skip if frame cannot be read, but log warning
                            logger.warning(f"Skipping frame {frame_num} (could not be read)")
                            continue

                        # Apply smudges for this frame
                        if frame_num in self.smudge_operations:
                            for operation in self.smudge_operations[frame_num]:
                                try:
                                    frame = apply_smudge_to_frame(frame, operation)
                                except Exception as e:
                                    logger.warning(f"Error applying smudge to frame {frame_num}: {e}")
                                    # Continue with unmodified frame

                        # Write frame
                        writer.write(frame)
                        frames_written += 1

                    writer.release()

                    if frames_written == 0:
                        raise ValueError("No frames were written to the output video")
                except Exception:
                    # Clean up temporary file on error
                    try:
                        if os.path.exists(temp_video):
                            os.remove(temp_video)
                    except OSError:
                        pass
                    raise

                # Verify temporary video exists and has reasonable size
                if not os.path.exists(temp_video):
                    raise ValueError("Temporary video file was not created")
                temp_size = os.path.getsize(temp_video)
                if temp_size < 1024:  # Less than 1KB is suspicious
                    raise ValueError(f"Temporary video file is suspiciously small ({temp_size} bytes)")

                # Try to preserve audio using ffmpeg
                has_audio = False
                temp_audio = None  # Will be set if audio extraction is attempted
                try:
                    # Check if ffmpeg is available
                    result = subprocess.run(
                        ["ffmpeg", "-version"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=5,
                    )
                    if result.returncode != 0:
                        raise FileNotFoundError("ffmpeg command failed")

                    # Check if original video has audio stream
                    status_label.configure(text="Checking for audio track...")
                    progress_window.update()

                    check_audio_cmd = [
                        "ffprobe",
                        "-v", "error",
                        "-select_streams", "a:0",
                        "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0",
                        self.video_processor.video_path,
                    ]

                    result = subprocess.run(
                        check_audio_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=10,
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        has_audio = True
                        logger.info("Audio stream detected in original video")

                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"Could not check for audio (ffmpeg may not be installed): {e}")
                    has_audio = False
                except Exception as e:
                    logger.warning(f"Error checking for audio: {e}")
                    has_audio = False

                # If audio exists, combine it with the processed video
                if has_audio:
                    try:
                        status_label.configure(text="Extracting audio and combining...")
                        progress_window.update()

                        # Create temporary audio file
                        temp_audio_fd, temp_audio = tempfile.mkstemp(suffix=".m4a", prefix="deface_audio_")
                        os.close(temp_audio_fd)

                        # Extract audio from original video
                        extract_audio_cmd = [
                            "ffmpeg",
                            "-i", self.video_processor.video_path,
                            "-vn",  # No video
                            "-acodec", "copy",  # Copy audio codec
                            "-y",  # Overwrite output file
                            temp_audio,
                        ]

                        result = subprocess.run(
                            extract_audio_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=60,
                        )

                        if result.returncode != 0:
                            logger.warning(f"Failed to extract audio: {result.stderr.decode()}")
                            has_audio = False
                        elif not os.path.exists(temp_audio) or os.path.getsize(temp_audio) < 1024:
                            logger.warning("Extracted audio file is missing or too small")
                            has_audio = False
                        else:
                            # Combine video and audio
                            status_label.configure(text="Combining video and audio...")
                            progress_window.update()

                            combine_cmd = [
                                "ffmpeg",
                                "-i", temp_video,
                                "-i", temp_audio,
                                "-c:v", "copy",  # Copy video codec
                                "-c:a", "aac",  # Encode audio as AAC for compatibility
                                "-shortest",  # Finish encoding when the shortest input stream ends
                                "-y",  # Overwrite output file
                                filename,
                            ]

                            result = subprocess.run(
                                combine_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                timeout=300,  # 5 minutes max
                            )

                            if result.returncode == 0 and os.path.exists(filename):
                                logger.info("Successfully combined video and audio")
                                # Clean up temporary files
                                try:
                                    os.remove(temp_video)
                                    os.remove(temp_audio)
                                except OSError as e:
                                    logger.warning(f"Could not remove temporary files: {e}")
                            else:
                                logger.warning(f"Failed to combine video and audio: {result.stderr.decode()}")
                                # Fall back to video without audio
                                has_audio = False
                                if os.path.exists(filename):
                                    os.remove(filename)

                    except subprocess.TimeoutExpired:
                        logger.error("Audio processing timed out")
                        has_audio = False
                    except Exception as e:
                        logger.error(f"Error processing audio: {e}", exc_info=True)
                        has_audio = False

                # If no audio or audio processing failed, copy video without audio to final location
                if not has_audio:
                    if os.path.exists(temp_video):
                        shutil.copy2(temp_video, filename)
                        logger.info("Saved video without audio track")

                # Clean up temporary files (only if they still exist)
                # Note: If audio combination succeeded, temp_video and temp_audio were already removed
                for temp_file in [temp_video, temp_audio]:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except OSError as e:
                            logger.warning(f"Could not remove temporary file {temp_file}: {e}")

                # Verify final output file exists and has reasonable size
                if not os.path.exists(filename):
                    raise ValueError("Output file was not created")
                output_size = os.path.getsize(filename)
                if output_size < 1024:  # Less than 1KB is suspicious
                    raise ValueError(f"Output file is suspiciously small ({output_size} bytes)")

                progress_window.after(0, lambda: progress_window.destroy())
                if has_audio:
                    messagebox.showinfo("Success", f"Video saved successfully with audio:\n{filename}")
                else:
                    messagebox.showinfo("Success", f"Video saved successfully:\n{filename}\n\nNote: Audio track was not preserved (original video may not have audio, or ffmpeg is not available).")

            except ValueError as e:
                logger.error(f"Error encoding video: {e}")
                progress_window.after(0, lambda: progress_window.destroy())
                messagebox.showerror("Error", f"Failed to encode video:\n{str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error encoding video: {e}", exc_info=True)
                progress_window.after(0, lambda: progress_window.destroy())
                messagebox.showerror("Error", f"Unexpected error encoding video:\n{str(e)}")

        encode_thread = threading.Thread(target=encode_video, daemon=True)
        encode_thread.start()

    def _on_cancel(self):
        """Handle cancel/close."""
        if self.smudge_operations:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved smudge operations. Close anyway?"):
                return

        # Stop playback if running
        self.stop_playback = True
        self.is_playing = False
        if self.playback_thread and self.playback_thread.is_alive():
            # Wait a bit for thread to finish
            self.playback_thread.join(timeout=0.5)

        # Clean up video processor
        if self.video_processor:
            self.video_processor.close()

        self.destroy()

