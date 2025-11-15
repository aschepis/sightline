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

from progress_parser import ProgressParser
from config_manager import load_config, save_config, get_default_config

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
        "Warning: tkinterdnd2 is not available. Drag and drop will not work.\n"
        "\n"
        "Installation instructions:\n"
        "  pip install tkinterdnd2\n"
    )
    DND_FILES = None
    TkinterDnD = None

# Version information
__version__ = "1.0.0"

# Configure logging (will be updated by parse_args if called)
# Default: console only
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr)  # Ensure logs go to stderr
    ]
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

# Set customtkinter appearance mode and color theme
ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"


def build_deface_args(config: Dict[str, Any]) -> list:
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
    # Build base command (deface executable + required args)
    cmd = _find_deface_command()
    cmd.extend(
        [
            input_path,
            "--output",
            output_path,
        ]
    )

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


class LogDialog(ctk.CTkToplevel):
    """Dialog for displaying error logs."""

    def __init__(self, parent, filename: str, log_text: str):
        super().__init__(parent)

        self.title(f"Error Logs - {filename}")
        self.geometry("800x600")
        self.resizable(True, True)

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Create widgets
        self._create_widgets(log_text)

        # Center dialog on parent
        self._center_on_parent()

        # Focus on dialog
        self.focus()

    def _center_on_parent(self):
        """Center the dialog on its parent window."""
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

    def _create_widgets(self, log_text: str):
        """Create and layout all dialog widgets."""
        # Main container
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Error Logs",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(pady=(0, 10))

        # Textbox for logs
        log_textbox = ctk.CTkTextbox(
            main_frame,
            font=("Courier", 11),
            wrap="word",
        )
        log_textbox.pack(fill="both", expand=True, pady=(0, 10))
        log_textbox.insert("1.0", log_text)
        log_textbox.configure(state="disabled")  # Make read-only

        # Close button
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x")

        close_btn = ctk.CTkButton(
            button_frame,
            text="Close",
            command=self.destroy,
            width=100,
        )
        close_btn.pack(side="right", padx=10)

        # Bind Escape key to close
        self.bind("<Escape>", lambda e: self.destroy())


class ConfigDialog(ctk.CTkToplevel):
    """Configuration dialog for deface options."""

    def __init__(self, parent, config: Dict[str, Any]):
        super().__init__(parent)

        self.title("Deface Configuration")
        self.geometry("600x650")
        self.resizable(False, False)

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Store configuration
        self.config = config.copy()
        self.result: Optional[Dict[str, Any]] = None

        # Create widgets
        self._create_widgets()

        # Center dialog on parent
        self._center_on_parent()

        # Focus on dialog
        self.focus()

    def _center_on_parent(self):
        """Center the dialog on its parent window."""
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
        """Create and layout all dialog widgets."""
        # Main container with scrollable frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Deface Configuration",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(pady=(0, 20))

        # Scrollable frame for options
        scrollable_frame = ctk.CTkScrollableFrame(main_frame)
        scrollable_frame.pack(fill="both", expand=True, pady=(0, 20))

        # Detection threshold
        thresh_frame = ctk.CTkFrame(scrollable_frame)
        thresh_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            thresh_frame, text="Detection Threshold:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            thresh_frame,
            text="Tune this to trade off between false positive and false negative rate",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        thresh_entry = ctk.CTkEntry(thresh_frame, width=150)
        thresh_entry.insert(0, str(self.config.get("thresh", 0.2)))
        thresh_entry.pack(anchor="w", padx=10, pady=(0, 10))
        self.thresh_entry = thresh_entry

        # Scale (WxH)
        scale_frame = ctk.CTkFrame(scrollable_frame)
        scale_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(scale_frame, text="Scale (WxH):", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        ctk.CTkLabel(
            scale_frame,
            text="Downscale images for network inference (e.g., 640x360). Leave empty for no scaling.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        scale_entry = ctk.CTkEntry(
            scale_frame, width=150, placeholder_text="e.g., 640x360"
        )
        if self.config.get("scale"):
            scale_entry.insert(0, self.config["scale"])
        scale_entry.pack(anchor="w", padx=10, pady=(0, 10))
        self.scale_entry = scale_entry

        # Use boxes
        boxes_frame = ctk.CTkFrame(scrollable_frame)
        boxes_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(boxes_frame, text="Use Boxes:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        ctk.CTkLabel(
            boxes_frame,
            text="Use boxes instead of ellipse masks",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        boxes_var = tk.BooleanVar(value=self.config.get("boxes", False))
        boxes_checkbox = ctk.CTkCheckBox(
            boxes_frame, text="Use boxes", variable=boxes_var
        )
        boxes_checkbox.pack(anchor="w", padx=10, pady=(0, 10))
        self.boxes_var = boxes_var

        # Mask scale
        mask_scale_frame = ctk.CTkFrame(scrollable_frame)
        mask_scale_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            mask_scale_frame, text="Mask Scale Factor:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            mask_scale_frame,
            text="Scale factor for face masks to ensure complete face coverage",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        mask_scale_entry = ctk.CTkEntry(mask_scale_frame, width=150)
        mask_scale_entry.insert(0, str(self.config.get("mask_scale", 1.3)))
        mask_scale_entry.pack(anchor="w", padx=10, pady=(0, 10))
        self.mask_scale_entry = mask_scale_entry

        # Replace with mode
        replace_frame = ctk.CTkFrame(scrollable_frame)
        replace_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            replace_frame, text="Anonymization Mode:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            replace_frame,
            text="Filter mode for face regions",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        replace_options = ["blur", "solid", "none", "img", "mosaic"]
        replace_var = tk.StringVar(value=self.config.get("replacewith", "blur"))
        replace_menu = ctk.CTkOptionMenu(
            replace_frame, values=replace_options, variable=replace_var, width=150
        )
        replace_menu.pack(anchor="w", padx=10, pady=(0, 10))
        self.replace_var = replace_var

        # Keep audio
        audio_frame = ctk.CTkFrame(scrollable_frame)
        audio_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(audio_frame, text="Keep Audio:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        ctk.CTkLabel(
            audio_frame,
            text="Keep audio from video source file (only applies to videos)",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        audio_var = tk.BooleanVar(value=self.config.get("keep_audio", True))
        audio_checkbox = ctk.CTkCheckBox(
            audio_frame, text="Keep audio", variable=audio_var
        )
        audio_checkbox.pack(anchor="w", padx=10, pady=(0, 10))
        self.audio_var = audio_var

        # Keep metadata
        metadata_frame = ctk.CTkFrame(scrollable_frame)
        metadata_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            metadata_frame, text="Keep Metadata:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            metadata_frame,
            text="Keep metadata of the original image",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        metadata_var = tk.BooleanVar(value=self.config.get("keep_metadata", True))
        metadata_checkbox = ctk.CTkCheckBox(
            metadata_frame, text="Keep metadata", variable=metadata_var
        )
        metadata_checkbox.pack(anchor="w", padx=10, pady=(0, 10))
        self.metadata_var = metadata_var

        # Batch size
        batch_size_frame = ctk.CTkFrame(scrollable_frame)
        batch_size_frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            batch_size_frame, text="Batch Size:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            batch_size_frame,
            text="Number of files to process concurrently (1-8)",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        batch_size_entry = ctk.CTkEntry(batch_size_frame, width=150)
        batch_size_entry.insert(0, str(self.config.get("batch_size", 1)))
        batch_size_entry.pack(anchor="w", padx=10, pady=(0, 10))
        self.batch_size_entry = batch_size_entry

        # Buttons
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=(0, 0))

        ok_btn = ctk.CTkButton(button_frame, text="OK", command=self._on_ok, width=100)
        ok_btn.pack(side="right", padx=10)

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self._on_cancel,
            width=100,
            fg_color="gray",
        )
        cancel_btn.pack(side="right", padx=10)

        # Bind Enter key to OK
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _on_ok(self):  # noqa: C901
        """Handle OK button click."""
        try:
            # Validate and collect configuration
            config: Dict[str, Any] = {}

            # Thresh
            try:
                thresh_val = float(self.thresh_entry.get().strip())
                if thresh_val < 0 or thresh_val > 1:
                    messagebox.showerror(
                        "Error", "Detection threshold must be between 0 and 1."
                    )
                    return
                config["thresh"] = thresh_val
            except ValueError:
                messagebox.showerror(
                    "Error", "Detection threshold must be a valid number."
                )
                return

            # Scale
            scale_val = self.scale_entry.get().strip()
            if scale_val:
                # Validate format (WxH)
                if "x" not in scale_val.lower():
                    messagebox.showerror(
                        "Error", "Scale must be in format WxH (e.g., 640x360)."
                    )
                    return
                try:
                    parts = scale_val.lower().split("x")
                    if len(parts) != 2:
                        raise ValueError
                    int(parts[0])
                    int(parts[1])
                except ValueError:
                    messagebox.showerror(
                        "Error",
                        "Scale must be in format WxH with valid integers (e.g., 640x360).",
                    )
                    return
                config["scale"] = scale_val

            # Boxes
            config["boxes"] = self.boxes_var.get()

            # Mask scale
            try:
                mask_scale_val = float(self.mask_scale_entry.get().strip())
                if mask_scale_val <= 0:
                    messagebox.showerror(
                        "Error", "Mask scale factor must be greater than 0."
                    )
                    return
                config["mask_scale"] = mask_scale_val
            except ValueError:
                messagebox.showerror(
                    "Error", "Mask scale factor must be a valid number."
                )
                return

            # Replace with
            config["replacewith"] = self.replace_var.get()

            # Keep audio
            config["keep_audio"] = self.audio_var.get()

            # Keep metadata
            config["keep_metadata"] = self.metadata_var.get()

            # Batch size
            try:
                batch_size_val = int(self.batch_size_entry.get().strip())
                if batch_size_val < 1 or batch_size_val > 8:
                    messagebox.showerror(
                        "Error", "Batch size must be between 1 and 8."
                    )
                    return
                config["batch_size"] = batch_size_val
            except ValueError:
                messagebox.showerror(
                    "Error", "Batch size must be a valid integer."
                )
                return

            self.result = config
            self.destroy()

        except Exception as e:
            logger.error(f"Error validating configuration: {e}")
            messagebox.showerror("Error", f"Error validating configuration: {str(e)}")

    def _on_cancel(self):
        """Handle Cancel button click."""
        self.result = None
        self.destroy()


# Create a base class that supports DnD if available
if TkinterDnD:
    class DefaceAppBase(ctk.CTk, TkinterDnD.Tk):
        """Base class for DefaceApp with DnD support."""
        pass
else:
    class DefaceAppBase(ctk.CTk):
        """Base class for DefaceApp without DnD support."""
        pass


class DefaceApp(DefaceAppBase):
    """Main application window for the Deface GUI."""

    def __init__(self):
        # Initialize CustomTkinter first (creates the Tk instance)
        ctk.CTk.__init__(self)

        # Then initialize TkinterDnD on the existing Tk instance if available
        if TkinterDnD:
            try:
                # Load tkdnd package into the Tcl interpreter
                # This makes the tkdnd commands available
                TkinterDnD._require(self)
                logger.debug("TkinterDnD initialized successfully")
            except Exception as e:
                logger.warning(f"Could not initialize TkinterDnD: {e}")
                print(f"Warning: Could not initialize TkinterDnD: {e}")
                import traceback
                traceback.print_exc()

        self.title(f"Deface — Batch Processing v{__version__}")
        self.geometry("1100x750")

        # Set application icon
        self.icon_image = None  # Keep reference to prevent garbage collection
        try:
            # Try icon.ico first (better for Windows), then fall back to icon.png
            icon_ico_path = get_resource_path("icon.ico")
            icon_png_path = get_resource_path("icon.png")

            if Path(icon_ico_path).exists():
                # Use iconbitmap for .ico files (works on Windows)
                try:
                    self.iconbitmap(icon_ico_path)
                except Exception:
                    # If iconbitmap fails (e.g., on non-Windows), fall back to PNG
                    if Path(icon_png_path).exists():
                        self.icon_image = tk.PhotoImage(file=icon_png_path)
                        self.iconphoto(False, self.icon_image)
            elif Path(icon_png_path).exists():
                # Use iconphoto for PNG files (works cross-platform)
                self.icon_image = tk.PhotoImage(file=icon_png_path)
                self.iconphoto(False, self.icon_image)
        except Exception as e:
            logger.warning(f"Could not load application icon: {e}")

        # Process tracking
        self.proc: Optional[subprocess.Popen] = None
        self.process_thread: Optional[threading.Thread] = None
        self.output_queue: queue.Queue = queue.Queue()
        self.progress_parser = ProgressParser()

        # File queue for batch processing
        self.file_queue: list = []  # List of dicts with file info
        self.currently_processing: set = set()  # Set of file paths currently being processed
        self.is_processing: bool = False
        self.stop_requested: bool = False
        self.file_widgets: dict = {}  # Maps file path to UI widgets
        self.active_processes: dict = {}  # Maps file path to subprocess.Popen

        # Load configuration from disk
        saved_config = load_config()
        default_config = get_default_config()

        # Configuration (defaults match deface defaults, with keep-audio and keep-metadata True)
        # Load deface config from saved config or use defaults
        self.config: Dict = saved_config.get("deface_config", default_config["deface_config"]).copy()

        # Store saved output directory for use in _create_widgets
        self.saved_output_directory = saved_config.get("output_directory")

        # Create UI elements
        self._create_widgets()

        # Bring window to foreground
        self._bring_to_front()

        # Schedule periodic check for process output from queue
        self._check_process_output()

    def _create_widgets(self):
        """Create and layout all GUI widgets."""
        # Main container
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Deface",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(pady=(0, 20))

        # Output directory selection
        output_frame = ctk.CTkFrame(main_frame)
        output_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            output_frame, text="Output folder:", font=ctk.CTkFont(size=14)
        ).pack(anchor="w", padx=10, pady=10)

        output_row = ctk.CTkFrame(output_frame)
        output_row.pack(fill="x", padx=10, pady=(0, 10))

        # Set default output folder from saved config or Desktop
        if self.saved_output_directory and Path(self.saved_output_directory).exists():
            default_output = self.saved_output_directory
        else:
            default_output = get_desktop_path()
        self.output_entry = ctk.CTkEntry(
            output_row, placeholder_text="Select output folder..."
        )
        self.output_entry.insert(0, default_output)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Bind to save config when output directory changes
        self.output_entry.bind("<FocusOut>", self._on_output_directory_changed)

        output_browse_btn = ctk.CTkButton(
            output_row, text="Browse", command=self._browse_output_folder, width=100
        )
        output_browse_btn.pack(side="right")

        # File list section
        files_frame = ctk.CTkFrame(main_frame)
        files_frame.pack(fill="both", expand=True, pady=10)

        # Header with label and buttons
        files_header = ctk.CTkFrame(files_frame)
        files_header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            files_header, text="Files to process:", font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=5)

        self.add_files_btn = ctk.CTkButton(
            files_header, text="Add Files", command=self._add_files, width=100, height=30
        )
        self.add_files_btn.pack(side="right", padx=5)

        self.remove_files_btn = ctk.CTkButton(
            files_header, text="Remove", command=self._remove_files, width=100, height=30
        )
        self.remove_files_btn.pack(side="right", padx=5)

        # Scrollable frame for file list
        self.files_list_frame = ctk.CTkScrollableFrame(
            files_frame, height=300, fg_color="transparent"
        )
        self.files_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Placeholder text when no files
        self.no_files_label = ctk.CTkLabel(
            self.files_list_frame,
            text="No files added. Click 'Add Files' to select files.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.no_files_label.pack(pady=50)

        # Buttons
        self.button_frame = ctk.CTkFrame(main_frame)
        self.button_frame.pack(fill="x", pady=10)

        self.start_btn = ctk.CTkButton(
            self.button_frame, text="Start", command=self._start_processing, width=120, height=40
        )
        self.start_btn.pack(side="left", padx=10)
        self.start_btn.configure(state="disabled")  # Disabled until files are added

        self.stop_btn = ctk.CTkButton(
            self.button_frame, text="Stop", command=self._stop_processing, width=120, height=40,
            fg_color="red"
        )
        self.stop_btn.pack(side="left", padx=10)
        self.stop_btn.configure(state="disabled")

        settings_btn = ctk.CTkButton(
            self.button_frame,
            text="Settings",
            command=self._open_settings,
            width=120,
            height=40,
        )
        settings_btn.pack(side="left", padx=10)

        quit_btn = ctk.CTkButton(
            self.button_frame,
            text="Quit",
            command=self._on_closing,
            width=120,
            height=40,
            fg_color="gray",
        )
        quit_btn.pack(side="right", padx=10)

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Setup drag and drop
        self._setup_drag_drop()

    def _create_file_row(self, file_info: Dict[str, Any]) -> ctk.CTkFrame:
        """Create a UI row for a file in the queue.

        Args:
            file_info: Dictionary containing file information.

        Returns:
            Frame containing the file row widgets.
        """
        file_path = file_info['path']

        # Main row frame
        row_frame = ctk.CTkFrame(self.files_list_frame)
        row_frame.pack(fill="x", pady=5, padx=5)

        # Checkbox for selection
        checkbox_var = tk.BooleanVar(value=False)
        checkbox = ctk.CTkCheckBox(row_frame, text="", variable=checkbox_var, width=30)
        checkbox.pack(side="left", padx=5)

        # Filename label (left-aligned, truncated if too long)
        filename = os.path.basename(file_path)
        if len(filename) > 35:
            display_name = filename[:32] + "..."
        else:
            display_name = filename

        filename_label = ctk.CTkLabel(
            row_frame,
            text=display_name,
            font=ctk.CTkFont(size=11),
            width=250,
            anchor="w"
        )
        filename_label.pack(side="left", padx=5)

        # Status label
        status_label = ctk.CTkLabel(
            row_frame,
            text="Pending",
            font=ctk.CTkFont(size=10),
            width=70,
            text_color="gray"
        )
        status_label.pack(side="left", padx=5)

        # Progress bar
        progress_bar = ctk.CTkProgressBar(row_frame, width=150)
        progress_bar.pack(side="left", padx=5)
        progress_bar.set(0)

        # ETA label
        eta_label = ctk.CTkLabel(
            row_frame,
            text="--:--",
            font=ctk.CTkFont(size=10),
            width=50,
            text_color="gray"
        )
        eta_label.pack(side="left", padx=3)

        # Elapsed label
        elapsed_label = ctk.CTkLabel(
            row_frame,
            text="00:00",
            font=ctk.CTkFont(size=10),
            width=50,
            text_color="gray"
        )
        elapsed_label.pack(side="left", padx=3)

        # Speed label
        speed_label = ctk.CTkLabel(
            row_frame,
            text="--",
            font=ctk.CTkFont(size=10),
            width=60,
            text_color="gray"
        )
        speed_label.pack(side="left", padx=3)

        # Show logs button (hidden by default, shown on failure)
        show_logs_btn = ctk.CTkButton(
            row_frame,
            text="Logs",
            command=lambda: self._show_file_logs(file_path),
            width=60,
            height=25,
            fg_color="orange"
        )
        # Don't pack it yet, will show on failure

        # Store widget references
        self.file_widgets[file_path] = {
            'row_frame': row_frame,
            'checkbox': checkbox,
            'checkbox_var': checkbox_var,
            'filename_label': filename_label,
            'status_label': status_label,
            'progress_bar': progress_bar,
            'eta_label': eta_label,
            'elapsed_label': elapsed_label,
            'speed_label': speed_label,
            'show_logs_btn': show_logs_btn
        }

        return row_frame

    def _update_file_row(self, file_path: str):
        """Update the UI for a specific file row based on its current state.

        Args:
            file_path: Path to the file whose row should be updated.
        """
        if file_path not in self.file_widgets:
            return

        # Find file info
        file_info = None
        for f in self.file_queue:
            if f['path'] == file_path:
                file_info = f
                break

        if not file_info:
            return

        widgets = self.file_widgets[file_path]
        status = file_info['status']
        progress = file_info['progress']

        # Update status label and color
        status_colors = {
            'pending': ('gray', 'Pending'),
            'processing': ('blue', 'Processing'),
            'success': ('green', 'Success'),
            'failed': ('red', 'Failed')
        }

        color, text = status_colors.get(status, ('gray', 'Unknown'))
        widgets['status_label'].configure(text=text, text_color=color)

        # Update progress bar
        widgets['progress_bar'].set(progress)

        # Disable checkbox if file is currently processing
        if status == 'processing':
            widgets['checkbox'].configure(state="disabled")
        else:
            widgets['checkbox'].configure(state="normal")

        # Show logs button only for failed files
        if status == 'failed' and file_info.get('error_log'):
            widgets['show_logs_btn'].pack(side="left", padx=5)
        else:
            widgets['show_logs_btn'].pack_forget()

    def _refresh_file_list_display(self):
        """Refresh the entire file list display."""
        # Clear existing widgets
        for widgets in self.file_widgets.values():
            widgets['row_frame'].destroy()
        self.file_widgets.clear()

        # Show/hide placeholder
        if not self.file_queue:
            self.no_files_label.pack(pady=50)
            self.start_btn.configure(state="disabled")
        else:
            self.no_files_label.pack_forget()
            if not self.is_processing:
                self.start_btn.configure(state="normal")

            # Create rows for all files
            for file_info in self.file_queue:
                self._create_file_row(file_info)
                self._update_file_row(file_info['path'])

    def _add_files(self):
        """Open file dialog to select multiple input files and add them to the queue."""
        # Ensure we have focus before opening dialog
        self.focus()
        filenames = filedialog.askopenfilenames(
            parent=self,
            title="Select input images or videos",
            filetypes=[
                (
                    "All supported",
                    "*.jpg *.jpeg *.png *.bmp *.tiff *.mp4 *.avi *.mov *.mkv",
                ),
                ("Images", "*.jpg *.jpeg *.png *.bmp *.tiff"),
                ("Videos", "*.mp4 *.avi *.mov *.mkv"),
                ("All files", "*.*"),
            ],
        )
        if filenames:
            self._add_files_to_queue(filenames)

    def _add_files_to_queue(self, file_paths: tuple):
        """Add multiple files to the processing queue.

        Args:
            file_paths: Tuple or list of file paths to add.
        """
        output_dir = self.output_entry.get().strip()

        for file_path in file_paths:
            # Skip if already in queue
            if any(f['path'] == file_path for f in self.file_queue):
                logger.info(f"File already in queue: {file_path}")
                continue

            # Validate file exists
            if not Path(file_path).exists():
                logger.warning(f"File does not exist: {file_path}")
                continue

            # Generate output path
            input_filename = os.path.basename(file_path)
            name, ext = os.path.splitext(input_filename)
            output_filename = f"{name}_anonymized{ext}"
            output_path = os.path.join(output_dir, output_filename)

            # Add to queue
            file_info = {
                'path': file_path,
                'status': 'pending',
                'progress': 0.0,
                'output_path': output_path,
                'error_log': '',
                'parser': ProgressParser(),  # Each file has its own progress parser
                'eta': '--:--',
                'elapsed': '00:00',
                'speed': '--'
            }
            self.file_queue.append(file_info)
            logger.info(f"Added file to queue: {file_path}")

        # Refresh display
        self._refresh_file_list_display()

    def _remove_files(self):
        """Remove selected files from the queue."""
        # Don't allow removal while processing
        if self.is_processing:
            messagebox.showwarning(
                "Processing",
                "Cannot remove files while processing. Stop the process first."
            )
            return

        # Find selected files
        files_to_remove = []
        for file_path, widgets in self.file_widgets.items():
            if widgets['checkbox_var'].get():
                files_to_remove.append(file_path)

        if not files_to_remove:
            messagebox.showinfo("No Selection", "Please select files to remove.")
            return

        # Remove from queue
        self.file_queue = [f for f in self.file_queue if f['path'] not in files_to_remove]

        logger.info(f"Removed {len(files_to_remove)} file(s) from queue")

        # Refresh display
        self._refresh_file_list_display()

    def _setup_drag_drop(self):
        """Setup drag and drop support for the file list frame."""
        if not TkinterDnD or not DND_FILES:
            logger.warning("tkinterdnd2 not available, drag and drop disabled")
            print("Warning: tkinterdnd2 not available, drag and drop disabled")
            return

        try:
            # After _require() was called in __init__, the widget has dnd methods available
            # Register drop target on root window
            self.drop_target_register(DND_FILES)

            # Bind the drop event using dnd_bind
            # The handler should return an action (like "copy")
            def drop_handler(event):
                logger.info("Drop event triggered!")
                print("Drop event triggered!")
                try:
                    self._on_drop(event)
                except Exception as e:
                    logger.error(f"Error in drop handler: {e}", exc_info=True)
                return "copy"  # Return action for tkinterdnd2

            # Use dnd_bind method directly on self (available after _require)
            self.dnd_bind('<<Drop>>', drop_handler)

            logger.info("Drag and drop enabled on root window")
            print("Drag and drop enabled on root window")

            # Also try to enable on the files list frame canvas for better UX
            try:
                canvas = self.files_list_frame._parent_canvas
                if canvas:
                    # Call _require on canvas to make it DnD-capable
                    TkinterDnD._require(canvas)
                    canvas.drop_target_register(DND_FILES)
                    canvas.dnd_bind('<<Drop>>', drop_handler)
                    logger.info("Drag and drop also enabled on files list canvas")
                    print("Drag and drop also enabled on files list canvas")
            except (AttributeError, Exception) as e:
                logger.debug(f"Could not enable DnD on canvas (root window DnD will handle it): {e}")
                # This is okay - root window DnD will still work

        except Exception as e:
            logger.error(f"Failed to setup drag and drop: {e}", exc_info=True)
            print(f"Error setting up drag and drop: {e}")
            import traceback
            traceback.print_exc()

    def _on_drop(self, event):
        """Handle file drop event.

        Args:
            event: Drop event containing file paths.
        """
        try:
            # Parse dropped file paths
            # tkinterdnd2 provides paths as a string, separated by spaces
            # Paths with spaces are wrapped in curly braces {}
            files_str = event.data
            logger.info(f"Drop event received, data: {files_str[:200]}...")  # Log first 200 chars
            print(f"Drop event received! Data length: {len(files_str)} chars")
            print(f"First 200 chars: {files_str[:200]}")

            # Parse the file paths
            # tkinterdnd2 formats paths differently on different platforms
            # On macOS/Linux: space-separated, paths with spaces wrapped in {}
            # On Windows: semicolon-separated or space-separated

            file_paths = []

            # Try to parse as space-separated with {} for paths with spaces
            current_path = ""
            in_braces = False

            i = 0
            while i < len(files_str):
                char = files_str[i]

                if char == '{':
                    in_braces = True
                    i += 1
                    continue
                elif char == '}':
                    in_braces = False
                    if current_path:
                        file_paths.append(current_path)
                        current_path = ""
                    i += 1
                    continue
                elif char == ' ' and not in_braces:
                    if current_path:
                        file_paths.append(current_path)
                        current_path = ""
                    i += 1
                    continue
                else:
                    current_path += char
                    i += 1

            # Add the last path if any
            if current_path:
                file_paths.append(current_path)

            # If no paths found with braces parsing, try splitting by common separators
            if not file_paths:
                # Try semicolon (Windows)
                if ';' in files_str:
                    file_paths = [p.strip() for p in files_str.split(';') if p.strip()]
                # Try newline
                elif '\n' in files_str:
                    file_paths = [p.strip() for p in files_str.split('\n') if p.strip()]
                # Otherwise, split by space and hope for the best
                else:
                    file_paths = [p.strip() for p in files_str.split() if p.strip()]

            logger.info(f"Parsed {len(file_paths)} path(s) from drop event")

            # Filter to only include files (not directories) and valid extensions
            valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.mp4', '.avi', '.mov', '.mkv'}
            valid_files = []

            for file_path in file_paths:
                # Remove any surrounding whitespace
                file_path = file_path.strip()

                # Skip empty paths
                if not file_path:
                    continue

                # Check if it's a file (not a directory)
                path_obj = Path(file_path)
                if not path_obj.exists():
                    logger.warning(f"Dropped path does not exist: {file_path}")
                    continue

                if path_obj.is_dir():
                    # If it's a directory, recursively find all valid files
                    for ext in valid_extensions:
                        valid_files.extend(path_obj.rglob(f"*{ext}"))
                        valid_files.extend(path_obj.rglob(f"*{ext.upper()}"))
                elif path_obj.is_file():
                    # Check if it's a valid file extension
                    if path_obj.suffix.lower() in valid_extensions:
                        valid_files.append(file_path)
                    else:
                        logger.info(f"Skipping unsupported file type: {file_path}")

            # Add files to queue
            if valid_files:
                logger.info(f"Adding {len(valid_files)} file(s) from drag and drop")
                print(f"Adding {len(valid_files)} file(s) from drag and drop")
                self._add_files_to_queue(tuple(valid_files))
            else:
                logger.info("No valid files found in drop")
                print("No valid files found in drop")
                messagebox.showinfo(
                    "No Valid Files",
                    "No supported image or video files were found in the dropped items.\n\n"
                    "Supported formats: JPG, PNG, BMP, TIFF, MP4, AVI, MOV, MKV"
                )

        except Exception as e:
            logger.error(f"Error handling file drop: {e}", exc_info=True)
            print(f"Error handling file drop: {e}")
            messagebox.showerror("Drop Error", f"Error processing dropped files: {str(e)}")

    def _show_file_logs(self, file_path: str):
        """Show error logs for a specific file in a separate dialog.

        Args:
            file_path: Path to the file whose logs should be displayed.
        """
        # Find file info
        file_info = None
        for f in self.file_queue:
            if f['path'] == file_path:
                file_info = f
                break

        if not file_info or not file_info.get('error_log'):
            messagebox.showinfo("No Logs", "No error logs available for this file.")
            return

        # Display the error log in a separate dialog
        filename = os.path.basename(file_path)
        log_text = f"=== Error log for {filename} ===\n\n{file_info['error_log']}\n\n"

        dialog = LogDialog(self, filename, log_text)
        self.wait_window(dialog)

    def _save_config(self):
        """Save current configuration to disk."""
        config_to_save = {
            "deface_config": self.config,
            "output_directory": self.output_entry.get().strip() or None,
        }
        save_config(config_to_save)

    def _on_output_directory_changed(self, event=None):
        """Handle output directory change event.

        Args:
            event: Optional event parameter.
        """
        self._save_config()

    def _browse_output_folder(self, event=None):
        """Open folder dialog to select output directory.

        Args:
            event: Optional event parameter (for compatibility with bindings).
        """
        # Ensure we have focus before opening dialog
        self.focus()
        folder = filedialog.askdirectory(parent=self, title="Select output folder")
        if folder:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, folder)
            self._save_config()

    def _open_settings(self):
        """Open the configuration settings dialog."""
        dialog = ConfigDialog(self, self.config)
        self.wait_window(dialog)

        if dialog.result is not None:
            self.config = dialog.result
            logger.info(f"Configuration updated: {self.config}")
            self._save_config()

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

    def _start_processing(self):
        """Start processing all pending/failed files in the queue."""
        if self.is_processing:
            messagebox.showwarning(
                "Process Running",
                "A process is already running. Please wait for it to complete.",
            )
            return

        # Validate output directory
        output_dir = self.output_entry.get().strip()
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory.")
            return

        output_path = Path(output_dir)
        if not output_path.exists():
            messagebox.showerror("Error", f"Output directory does not exist: {output_dir}")
            return

        if not output_path.is_dir():
            messagebox.showerror("Error", f"Output path is not a directory: {output_dir}")
            return

        # Check if there are any files to process
        files_to_process = [f for f in self.file_queue if f['status'] in ('pending', 'failed')]
        if not files_to_process:
            messagebox.showinfo(
                "Nothing to Process",
                "All files have been processed successfully. Add new files or clear successful files to process again."
            )
            return

        # Update UI state
        self.is_processing = True
        self.stop_requested = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.add_files_btn.configure(state="disabled")
        self.remove_files_btn.configure(state="disabled")

        logger.info(f"Starting batch processing of {len(files_to_process)} file(s)")

        # Start processing thread
        self.process_thread = threading.Thread(
            target=self._process_queue, daemon=True
        )
        self.process_thread.start()

    def _stop_processing(self):
        """Stop all current processing and mark files as failed."""
        if not self.is_processing:
            return

        logger.info("Stop requested by user")
        self.stop_requested = True

        # Terminate all active subprocesses
        for file_path, proc in list(self.active_processes.items()):
            if proc and proc.poll() is None:
                logger.info(f"Terminating subprocess for: {file_path}")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Process did not terminate, killing: {file_path}")
                    proc.kill()

                # Mark file as failed
                for file_info in self.file_queue:
                    if file_info['path'] == file_path:
                        file_info['status'] = 'failed'
                        file_info['error_log'] = 'Processing stopped by user'
                        file_info['progress'] = 0.0
                        self.output_queue.put(("file_update", file_path))
                        break

        # Update UI state
        self.stop_btn.configure(state="disabled")

    def _process_queue(self):
        """Process files from the queue with concurrent batch processing."""
        try:
            batch_size = self.config.get('batch_size', 1)
            logger.info(f"Starting batch processing with batch size: {batch_size}")

            # Get list of files to process
            files_to_process = [f for f in self.file_queue if f['status'] in ('pending', 'failed')]

            # Track active processing threads
            active_threads = {}

            # Process files
            while not self.stop_requested and (files_to_process or active_threads):
                # Start new processes up to batch_size
                while len(active_threads) < batch_size and files_to_process and not self.stop_requested:
                    file_info = files_to_process.pop(0)
                    file_path = file_info['path']

                    # Start processing thread for this file
                    thread = threading.Thread(
                        target=self._process_file, args=(file_info,), daemon=True
                    )
                    active_threads[file_path] = thread
                    self.currently_processing.add(file_path)
                    thread.start()
                    logger.info(f"Started processing: {file_path}")

                # Check for completed threads
                for file_path in list(active_threads.keys()):
                    thread = active_threads[file_path]
                    if not thread.is_alive():
                        # Thread finished
                        del active_threads[file_path]
                        if file_path in self.currently_processing:
                            self.currently_processing.remove(file_path)
                        logger.info(f"Finished processing: {file_path}")

                # Small delay to avoid busy waiting
                threading.Event().wait(0.1)

            # Wait for remaining threads to complete
            for thread in active_threads.values():
                thread.join(timeout=1)

            # Queue completion message
            self.output_queue.put(("batch_done", None))

        except Exception as e:
            logger.error(f"Error in queue processing: {e}")
            self.output_queue.put(("batch_error", str(e)))
        finally:
            self.currently_processing.clear()

    def _process_file(self, file_info: Dict[str, Any]):
        """Process a single file.

        Args:
            file_info: Dictionary containing file information.
        """
        file_path = file_info['path']
        output_path = file_info['output_path']

        logger.info(f"Processing file: {file_path}")

        # Update status to processing
        file_info['status'] = 'processing'
        file_info['progress'] = 0.0
        file_info['error_log'] = ''
        file_info['parser'] = ProgressParser()  # Reset progress parser for this file
        self.output_queue.put(("file_update", file_path))

        try:
            # Start the subprocess with current configuration
            proc = run_deface(file_path, output_path, self.config)
            self.active_processes[file_path] = proc

            # Start threads to read stdout and stderr concurrently
            stdout_thread = threading.Thread(
                target=self._read_stream, args=(proc.stdout, "stdout", file_path), daemon=True
            )
            stderr_thread = threading.Thread(
                target=self._read_stream, args=(proc.stderr, "stderr", file_path), daemon=True
            )

            stdout_thread.start()
            stderr_thread.start()

            # Wait for process to complete
            return_code = proc.wait()

            # Wait for both reading threads to finish
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

            # Update file status based on return code
            if return_code == 0:
                file_info['status'] = 'success'
                file_info['progress'] = 1.0
                logger.info(f"Successfully processed: {file_path}")
            else:
                file_info['status'] = 'failed'
                file_info['progress'] = 0.0
                file_info['error_log'] += f"\nProcess exited with code {return_code}"
                logger.error(f"Failed to process {file_path} (exit code: {return_code})")

            self.output_queue.put(("file_update", file_path))

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            file_info['status'] = 'failed'
            file_info['progress'] = 0.0
            file_info['error_log'] += f"\nException: {str(e)}"
            self.output_queue.put(("file_update", file_path))
            if file_path in self.currently_processing:
                self.currently_processing.remove(file_path)
        finally:
            # Clean up process tracking
            if file_path in self.active_processes:
                del self.active_processes[file_path]

    def _read_stream(self, stream, stream_type: str, file_path: str):
        """Read from a stream (stdout or stderr) and queue output.

        Args:
            stream: The stream to read from.
            stream_type: Type of stream ('stdout' or 'stderr').
            file_path: Path of the file being processed.
        """
        try:
            for line in iter(stream.readline, ""):
                if line:
                    self.output_queue.put((stream_type, line, file_path))
        except Exception as e:
            logger.error(f"Error reading {stream_type}: {e}")
        finally:
            stream.close()

    def _check_process_output(self):  # noqa: C901
        """Periodically check for process output from queue and update UI."""
        try:
            # Process all available messages from the queue
            while True:
                try:
                    message = self.output_queue.get_nowait()
                    msg_type = message[0]

                    if msg_type == "stdout":
                        _, line, file_path = message
                        # Try to parse progress from stdout
                        self._update_file_progress(line, file_path)
                        # Store output for error logging if needed
                        self._append_to_file_log(file_path, line)

                    elif msg_type == "stderr":
                        _, line, file_path = message
                        # Try to parse progress from stderr (tqdm often outputs to stderr)
                        self._update_file_progress(line, file_path)
                        # Store output for error logging
                        self._append_to_file_log(file_path, line)

                    elif msg_type == "file_update":
                        file_path = message[1]
                        # Update the file row display
                        self._update_file_row(file_path)

                    elif msg_type == "batch_done":
                        # All files processed
                        logger.info("Batch processing completed")
                        self._finalize_batch_processing()

                    elif msg_type == "batch_error":
                        error_msg = message[1]
                        logger.error(f"Batch processing error: {error_msg}")
                        self._finalize_batch_processing()

                except queue.Empty:
                    break
        except Exception as e:
            logger.error(f"Error processing output queue: {e}")
            self._finalize_batch_processing()

        # Schedule next check
        self.after(50, self._check_process_output)

    def _update_file_progress(self, line: str, file_path: str):
        """Update progress bar for a specific file from a line of output.

        Args:
            line: A line of output that may contain progress information.
            file_path: Path to the file being processed.
        """
        # Find the file info
        file_info = None
        for f in self.file_queue:
            if f['path'] == file_path:
                file_info = f
                break

        if not file_info:
            return

        # Use this file's own progress parser
        parser = file_info.get('parser')
        if not parser:
            return

        if parser.parse(line):
            # Update file progress
            progress_fraction = parser.get_progress_fraction()
            file_info['progress'] = progress_fraction

            # Update progress text values
            file_info['eta'] = parser.format_eta()
            file_info['elapsed'] = parser.format_elapsed()
            file_info['speed'] = parser.format_rate()

            # Update the individual file progress bar and stats widgets
            if file_path in self.file_widgets:
                widgets = self.file_widgets[file_path]
                widgets['progress_bar'].set(progress_fraction)
                widgets['eta_label'].configure(text=file_info['eta'])
                widgets['elapsed_label'].configure(text=file_info['elapsed'])
                widgets['speed_label'].configure(text=file_info['speed'])

    def _append_to_file_log(self, file_path: str, line: str):
        """Append a line to the error log for a file.

        Args:
            file_path: Path to the file.
            line: Line to append to the log.
        """
        # Find the file info
        for file_info in self.file_queue:
            if file_info['path'] == file_path:
                # Only append if it looks like an error or warning
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in ['error', 'warning', 'exception', 'failed', 'traceback']):
                    file_info['error_log'] += line
                break

    def _finalize_batch_processing(self):
        """Finalize batch processing and update UI state."""
        self.is_processing = False
        self.stop_requested = False
        self.currently_processing.clear()
        self.active_processes.clear()
        self.proc = None
        self.process_thread = None

        # Update UI buttons
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.add_files_btn.configure(state="normal")
        self.remove_files_btn.configure(state="normal")

        # Check if there are any failed files
        failed_files = [f for f in self.file_queue if f['status'] == 'failed']
        success_files = [f for f in self.file_queue if f['status'] == 'success']

        if failed_files:
            logger.info(f"Batch processing completed: {len(success_files)} succeeded, {len(failed_files)} failed")
        else:
            logger.info(f"Batch processing completed successfully: {len(success_files)} file(s)")

    def _on_closing(self):
        """Handle window closing event."""
        if self.process_thread and self.process_thread.is_alive():
            if messagebox.askokcancel(
                "Quit", "Processing is running. Do you want to terminate all processes and quit?"
            ):
                logger.info("Terminating running processes...")
                # Terminate all active processes
                for file_path, proc in list(self.active_processes.items()):
                    if proc and proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                # Wait for thread to finish
                self.process_thread.join(timeout=1)
                self.destroy()
        else:
            self.destroy()


def main() -> None:
    """Main entry point for the application."""
    # Parse command-line arguments
    args = parse_args()

    # Update logging level based on command-line argument
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)

    # Configure handlers
    handlers = [logging.StreamHandler(sys.stderr)]

    # Add file handler if log file is specified
    if args.log_file:
        try:
            file_handler = logging.FileHandler(args.log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            handlers.append(file_handler)
            logger.info(f"Logging to file: {args.log_file}")
        except Exception as e:
            print(f"Warning: Could not create log file {args.log_file}: {e}", file=sys.stderr)

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
        if app.process_thread and app.process_thread.is_alive():
            for file_path, proc in list(app.active_processes.items()):
                if proc and proc.poll() is None:
                    proc.terminate()
    except Exception as e:
        logger.exception("Unexpected error in main loop")
        messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")
    finally:
        logger.info("Application closed")


if __name__ in ("__main__", "__mp_main__"):
    main()
