"""GUI application for blurring faces in images and videos using deface.

This module provides a simple graphical interface for the deface library,
allowing users to select input files and output directories for face blurring.
"""

import argparse
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, Tuple

try:
    import customtkinter as ctk
except ImportError:
    print(
        "Error: customtkinter is not available.\n"
        "\n"
        "Installation instructions:\n"
        "  pip install customtkinter\n"
        "\n"
        "For more information, see: https://github.com/TomSchimansky/CustomTkinter"
    )
    sys.exit(1)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    print(
        "Error: tkinterdnd2 is not available.\n"
        "\n"
        "Installation instructions:\n"
        "  pip install tkinterdnd2\n"
        "\n"
        "For more information, see: https://github.com/pmgagne/tkinterdnd2"
    )
    sys.exit(1)

from config_manager import get_default_config, load_config, save_config
from dialogs import ConfigDialog, LogDialog
from progress_parser import ProgressParser
from views import BatchProcessingView, HomeView
from views.base_view import BaseView

# Version information
__version__ = "1.0.0"

# Application constants
WINDOW_WIDTH = 1080
WINDOW_HEIGHT = 720
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 480
FILE_LIST_HEIGHT = 300
MAX_FILENAME_DISPLAY_LENGTH = 35
MAX_BATCH_SIZE = 8
PROGRESS_CHECK_INTERVAL_MS = 50

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}

# Status colors for file processing
STATUS_COLORS = {
    "pending": ("gray", "Pending"),
    "processing": ("blue", "Processing"),
    "success": ("green", "Success"),
    "failed": ("red", "Failed"),
}

# Keywords for error detection in logs
ERROR_KEYWORDS = ["error", "warning", "exception", "failed", "traceback"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],  # Ensure logs go to stderr
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="GUI application for blurring faces in images and videos using deface."
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Write logs to a file in addition to console (default: console only)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def get_resource_path(relative_path: str) -> str:
    """Get the absolute path to a resource file.

    Works both in development and when bundled with PyInstaller.

    Args:
        relative_path: Relative path to the resource file.

    Returns:
        Absolute path to the resource file.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        # Running in development mode
        base_path = Path(__file__).parent.absolute()

    return str(Path(base_path) / relative_path)


# Set customtkinter appearance mode and color theme
# Use Dark mode to match Sightline brand guidelines
ctk.set_appearance_mode("Dark")
# Load custom Sightline theme
theme_path = get_resource_path("sightline_theme.json")
if Path(theme_path).exists():
    ctk.set_default_color_theme(theme_path)
else:
    logger.warning(f"Sightline theme file not found at {theme_path}, using default theme")
    ctk.set_default_color_theme("blue")


def build_deface_args(config: Dict[str, Any]) -> List[str]:
    """Build command-line arguments from configuration dictionary.

    Args:
        config: Dictionary containing deface configuration options.

    Returns:
        List of command-line argument strings.
    """
    args = []

    # Detection threshold
    if config.get("thresh") is not None:
        args.extend(["--thresh", str(config["thresh"])])

    # Scale (WxH format)
    if config.get("scale"):
        args.extend(["--scale", config["scale"]])

    # Use boxes instead of ellipse masks
    if config.get("boxes", False):
        args.append("--boxes")

    # Mask scale factor
    if config.get("mask_scale") is not None:
        args.extend(["--mask-scale", str(config["mask_scale"])])

    # Replace with mode
    if config.get("replacewith"):
        args.extend(["--replacewith", config["replacewith"]])

    # Keep audio (default: True)
    if config.get("keep_audio", True):
        args.append("--keep-audio")

    # Keep metadata (default: True)
    if config.get("keep_metadata", True):
        args.append("--keep-metadata")

    return args


def _find_deface_command() -> List[str]:
    """Locate the `deface` CLI command in both dev and bundled environments.

    Resolution order:
      1. If running from a PyInstaller bundle, use a bundled `deface`
         binary next to the main executable.
      2. Otherwise (or as a fallback), use `deface` from PATH, as long
         as it is not this GUI executable itself.

    Returns:
        A list representing the command prefix to invoke `deface`.

    Raises:
        FileNotFoundError: If no suitable `deface` executable can be found.
    """
    exe_path = Path(sys.executable).resolve()

    # 1. When bundled, prefer a dedicated CLI binary shipped next to the app
    #    (e.g. dist/Deface/deface-cli, Deface.app/Contents/MacOS/deface-cli,
    #    or Deface.app/Contents/Frameworks/deface-cli on macOS).
    is_bundled = getattr(sys, "_MEIPASS", None) is not None
    if is_bundled:
        candidates: List[Path] = []

        # Prefer the new, explicitly named CLI binary first, but keep the old
        # `deface` name as a fallback for backward compatibility.
        candidate_names = ["deface-cli", "deface"]

        if sys.platform == "win32":
            # PyInstaller one-folder / one-file style
            for name in candidate_names:
                candidates.append(exe_path.parent / f"{name}.exe")
                candidates.append(exe_path.parent / name)
        elif sys.platform == "darwin":
            # macOS .app layout:
            #   .../Deface.app/Contents/MacOS/Deface       (sys.executable)
            #   .../Deface.app/Contents/Frameworks/deface-cli  (bundled CLI)
            contents_dir = exe_path.parent.parent
            for name in candidate_names:
                candidates.append(contents_dir / "Frameworks" / name)
                candidates.append(exe_path.parent / name)
        else:
            # Linux / other POSIX layouts
            for name in candidate_names:
                candidates.append(exe_path.parent / name)

        for candidate in candidates:
            if candidate.exists() and os.access(candidate, os.X_OK):
                logger.info(f"Using bundled deface binary: {candidate}")
                return [str(candidate)]

    # 2. Fallback to a `deface` found on PATH, but avoid resolving to
    #    this GUI executable itself (which can happen on case-insensitive
    #    filesystems where `Deface` == `deface`).
    path_cmd = shutil.which("deface")
    if path_cmd:
        try:
            if Path(path_cmd).resolve() != exe_path:
                logger.info(f"Using deface from PATH: {path_cmd}")
                return [path_cmd]
            else:
                logger.warning(
                    "Resolved `deface` on PATH is the GUI executable itself; "
                    "ignoring to avoid recursion."
                )
        except Exception:
            # If anything goes wrong with samefile/resolve, still prefer PATH
            logger.info(f"Using deface from PATH (fallback): {path_cmd}")
            return [path_cmd]

    # Nothing found – raise a helpful error
    raise FileNotFoundError(
        "Could not find the 'deface' executable. "
        "Please ensure it is installed in your environment (e.g. `pip install deface`) "
        "or rebuild the app in an environment where `deface` is available."
    )


def run_deface(
    input_path: str, output_path: str, config: Optional[Dict[str, Any]] = None
) -> subprocess.Popen:
    """Run the deface command as a subprocess.

    Args:
        input_path: Path to the input image or video file.
        output_path: Path where the output file should be saved.
        config: Optional dictionary containing deface configuration options.

    Returns:
        A subprocess.Popen object representing the running process.

    Raises:
        FileNotFoundError: If the deface command cannot be found.
        OSError: If the subprocess cannot be started.
    """
    cmd = _find_deface_command()
    cmd.extend([input_path, "--output", output_path])

    if config:
        cmd.extend(build_deface_args(config))

    logger.info(f"Running deface command: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc
    except FileNotFoundError:
        logger.error("deface command not found. Please ensure deface is installed.")
        raise
    except OSError as e:
        logger.error(f"Failed to start deface process: {e}")
        raise


def get_desktop_path() -> str:
    """Get the user's Desktop folder path.

    Works on Windows, macOS, and Linux. Falls back to home directory
    if Desktop folder doesn't exist.

    Returns:
        Path to the Desktop folder, or home directory as fallback.
    """
    desktop = Path.home() / "Desktop"
    if desktop.exists() and desktop.is_dir():
        return str(desktop)

    # Fallback: return home directory if Desktop doesn't exist
    # (shouldn't happen on Windows/macOS, but possible on some Linux setups)
    return str(Path.home())


def validate_paths(input_path: str, output_dir: str) -> Tuple[bool, Optional[str]]:
    """Validate input file and output directory paths.

    Args:
        input_path: Path to the input file.
        output_dir: Path to the output directory.

    Returns:
        A tuple of (is_valid, error_message). If valid, error_message is None.
    """
    if not input_path:
        return False, "Please select an input file."

    if not output_dir:
        return False, "Please select an output directory."

    input_file = Path(input_path)
    if not input_file.exists():
        return False, f"Input file does not exist: {input_path}"

    if not input_file.is_file():
        return False, f"Input path is not a file: {input_path}"

    output_path = Path(output_dir)
    if not output_path.exists():
        return False, f"Output directory does not exist: {output_dir}"

    if not output_path.is_dir():
        return False, f"Output path is not a directory: {output_dir}"

    return True, None


class DefaceApp(ctk.CTk, TkinterDnD.Tk):
    """Main application window for the Deface GUI.

    This class acts as the main application container and router,
    managing navigation between different views/pages.
    """

    def __init__(self):
        # Initialize CustomTkinter first (creates the Tk instance)
        ctk.CTk.__init__(self)

        # Initialize TkinterDnD on the existing Tk instance
        try:
            # Load tkdnd package into the Tcl interpreter
            # This makes the tkdnd commands available
            TkinterDnD._require(self)
            logger.debug("TkinterDnD initialized successfully")
        except Exception as e:
            logger.error(f"Could not initialize TkinterDnD: {e}")
            print(f"Error: Could not initialize TkinterDnD: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

        self.title(f"Sightline v{__version__}")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self.icon_image = None
        try:
            # Platform-specific icon loading
            if sys.platform == "darwin":
                # macOS: prefer .icns, fall back to .png
                icon_icns_path = get_resource_path("icon.icns")
                icon_png_path = get_resource_path("icon.png")

                if Path(icon_icns_path).exists():
                    try:
                        self.iconbitmap(icon_icns_path)
                    except Exception:
                        # Fall back to PNG if ICNS fails
                        if Path(icon_png_path).exists():
                            self.icon_image = tk.PhotoImage(file=icon_png_path)
                            self.iconphoto(False, self.icon_image)
                elif Path(icon_png_path).exists():
                    self.icon_image = tk.PhotoImage(file=icon_png_path)
                    self.iconphoto(False, self.icon_image)
            else:
                # Windows/Linux: try .ico first, then .png
                icon_ico_path = get_resource_path("icon.ico")
                icon_png_path = get_resource_path("icon.png")

                if Path(icon_ico_path).exists():
                    # Use iconbitmap for .ico files (works on Windows)
                    try:
                        self.iconbitmap(icon_ico_path)
                    except Exception:
                        # If iconbitmap fails, fall back to PNG
                        if Path(icon_png_path).exists():
                            self.icon_image = tk.PhotoImage(file=icon_png_path)
                            self.iconphoto(False, self.icon_image)
                elif Path(icon_png_path).exists():
                    # Use iconphoto for PNG files (works cross-platform)
                    self.icon_image = tk.PhotoImage(file=icon_png_path)
                    self.iconphoto(False, self.icon_image)
        except Exception as e:
            logger.warning(f"Could not load application icon: {e}")

        # Load configuration
        saved_config = load_config()
        default_config = get_default_config()

        self.config: Dict = saved_config.get(
            "deface_config", default_config["deface_config"]
        ).copy()
        self.saved_output_directory = saved_config.get("output_directory")

        # View management
        self.current_view: Optional[BaseView] = None
        self.views: Dict[str, BaseView] = {}

        # Initialize views
        self._initialize_views()

        # Show initial view (home)
        self.show_view("home")

        self._bring_to_front()

    def _initialize_views(self):
        """Initialize all application views."""
        # Create batch processing view
        self.views["batch_processing"] = BatchProcessingView(self, self)
        self.views["home"] = HomeView(self, self)

    def show_view(self, view_name: str):
        """Show a specific view by name.

        Args:
            view_name: Name of the view to show (must exist in self.views).
        """
        if view_name not in self.views:
            logger.error(f"View '{view_name}' not found")
            return

        # Hide current view
        if self.current_view:
            self.current_view.cleanup()
            self.current_view.hide()

        # Show new view
        self.current_view = self.views[view_name]
        self.current_view.show()
        
        # Ensure the view is properly updated and displayed
        self.update_idletasks()

    def get_desktop_path(self) -> str:
        """Get the user's Desktop folder path.

        Works on Windows, macOS, and Linux. Falls back to home directory
        if Desktop folder doesn't exist.

        Returns:
            Path to the Desktop folder, or home directory as fallback.
        """
        return get_desktop_path()

    def run_deface(
        self, input_path: str, output_path: str, config: Optional[Dict[str, Any]] = None
    ) -> subprocess.Popen:
        """Run the deface command as a subprocess.

        Args:
            input_path: Path to the input image or video file.
            output_path: Path where the output file should be saved.
            config: Optional dictionary containing deface configuration options.

        Returns:
            A subprocess.Popen object representing the running process.

        Raises:
            FileNotFoundError: If the deface command cannot be found.
            OSError: If the subprocess cannot be started.
        """
        return run_deface(input_path, output_path, config)

    def _save_config(self):
        """Save current configuration to disk."""
        # Get output directory from current view if it has one
        output_dir = None
        if self.current_view and hasattr(self.current_view, "output_entry"):
            output_dir = self.current_view.output_entry.get().strip() or None

        config_to_save = {
            "deface_config": self.config,
            "output_directory": output_dir or self.saved_output_directory,
        }
        save_config(config_to_save)
        if output_dir:
            self.saved_output_directory = output_dir

    def _open_face_smudge(self):
        """Open the Face Smudge window."""
        try:
            from face_smudge import FaceSmudgeWindow

            smudge_window = FaceSmudgeWindow(self)
            smudge_window.wait_window()  # Modal
        except ImportError as e:
            logger.error(f"Could not import face_smudge module: {e}")
            messagebox.showerror(
                "Error",
                "Face Smudge feature is not available.\n\n"
                "Please ensure all dependencies are installed:\n"
                "  pip install opencv-python numpy Pillow",
            )
        except Exception as e:
            logger.error(f"Error opening Face Smudge window: {e}")
            messagebox.showerror("Error", f"Could not open Face Smudge window:\n{str(e)}")

    def _on_closing(self):
        """Handle window closing event."""
        # Check if current view has active processing
        if self.current_view and hasattr(self.current_view, "is_processing"):
            if self.current_view.is_processing:
                if messagebox.askokcancel(
                    "Quit",
                    "Processing is running. Do you want to terminate all processes and quit?",
                ):
                    logger.info("Terminating running processes...")
                    # Cleanup will be handled by view's cleanup method
                    if self.current_view:
                        self.current_view.cleanup()
                    self.destroy()
                return

        self.destroy()

    def _bring_to_front(self):
        """Bring the window to the foreground and give it focus."""
        # Update the window to ensure it's fully rendered
        self.update_idletasks()

        # On macOS, use the topmost trick to bring window to front
        if sys.platform == "darwin":
            self.attributes("-topmost", True)
            self.after(1, lambda: self.attributes("-topmost", False))

        # Bring window to front
        self.lift()

        # Force focus to the window
        self.focus_force()

        # On Windows, also activate the window
        if sys.platform == "win32":
            self.after(1, lambda: self.attributes("-topmost", True))
            self.after(2, lambda: self.attributes("-topmost", False))

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)


def main():
    """Main entry point for the application."""
    # Parse command-line arguments
    args = parse_args()

    # Update logging level based on command-line argument
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)

    # Configure handlers
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    # Add file handler if log file is specified
    if args.log_file:
        try:
            file_handler = logging.FileHandler(
                args.log_file, mode="a", encoding="utf-8"
            )
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            handlers.append(file_handler)
            logger.info(f"Logging to file: {args.log_file}")
        except Exception as e:
            print(
                f"Warning: Could not create log file {args.log_file}: {e}",
                file=sys.stderr,
            )

    # Update root logger with new handlers
    root_logger = logging.getLogger()
    root_logger.handlers = handlers
    root_logger.setLevel(log_level)
    logger.setLevel(log_level)
    logger.info(f"Logging level set to {args.log_level}")

    app = DefaceApp()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        if app.current_view and hasattr(app.current_view, "is_processing"):
            if app.current_view.is_processing:
                app.current_view.cleanup()
    except Exception as e:
        logger.exception("Unexpected error in main loop")
        messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")
    finally:
        logger.info("Application closed")

if __name__ in ("__main__", "__mp_main__"):
    main()
