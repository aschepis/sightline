"""Generic batch processing view for the Sightline application.

This module provides a reusable base class for batch processing files with
configurable processing logic, file types, and UI elements.
"""

import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from abc import ABC, abstractmethod
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

from views.dialogs import LogDialog
from progress_parser import ProgressParser
from views.base_view import BaseView

logger = logging.getLogger(__name__)

# View constants
FILE_LIST_HEIGHT = 300
MAX_FILENAME_DISPLAY_LENGTH = 35
PROGRESS_CHECK_INTERVAL_MS = 50

# Status colors for file processing - Sightline brand colors
STATUS_COLORS = {
    "pending": ("#8ea4c7", "Pending"),  # Mist Blue
    "processing": ("#00a6ff", "Processing"),  # Primary Accent
    "success": ("#4caf50", "Success"),  # Standard success green
    "failed": ("#ff3b30", "Failed"),  # Ember Red
}

# Keywords for error detection in logs
ERROR_KEYWORDS = ["error", "warning", "exception", "failed", "traceback"]

class GenericBatchView(BaseView, ABC):
    """Generic base view for batch processing files.

    This class provides common UI and logic for batch processing, with
    configurable processing logic, file types, and custom widgets.
    """

    def __init__(
        self,
        parent: ctk.CTk,
        app: Any,
        page_title: str,
        supported_extensions: Set[str],
        generate_output_filename: Optional[Callable[[str], str]] = None,
    ):
        """Initialize the generic batch processing view.

        Args:
            parent: The parent widget (main application window).
            app: Reference to the main application instance.
            page_title: Title to display at the top of the page.
            supported_extensions: Set of valid file extensions (e.g., {".mp4", ".mp3"}).
            generate_output_filename: Optional function to generate output filename from input path.
                                     If None, uses default pattern: {name}_processed{ext}
        """
        super().__init__(parent, app)

        # Configuration
        self.page_title = page_title
        self.supported_extensions = supported_extensions
        self.generate_output_filename = generate_output_filename or self._default_output_filename

        # File queue for batch processing
        self.file_queue: List[Dict[str, Any]] = []
        self.currently_processing: set[str] = set()
        self.is_processing: bool = False
        self.stop_requested: bool = False
        self.file_widgets: Dict[str, Dict[str, Any]] = {}
        self.active_processes: Dict[str, subprocess.Popen] = {}

        # Process tracking
        self.output_queue: queue.Queue = queue.Queue()

        # Create widgets
        self.create_widgets()

        # Drag and drop will be set up when view is shown
        self._drop_handler = None
        self._drag_drop_setup = False

        # Start checking for process output
        self._check_process_output()

    def _default_output_filename(self, input_path: str) -> str:
        """Generate default output filename from input path.

        Args:
            input_path: Path to the input file.

        Returns:
            Output filename with _processed suffix.
        """
        input_filename = os.path.basename(input_path)
        name, ext = os.path.splitext(input_filename)
        return f"{name}_processed{ext}"

    def create_widgets(self) -> None:
        """Create and layout all GUI widgets."""
        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header Section ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        # Back button
        back_btn = ctk.CTkButton(
            header_frame,
            text="< Back",
            command=self._go_to_home,
            width=80,
            height=30,
            fg_color="transparent",
            text_color=("black", "white"),
            hover=False,
            font=ctk.CTkFont(size=16),
        )
        back_btn.pack(side="left")

        # Title
        title_label = ctk.CTkLabel(
            header_frame,
            text=self.page_title,
            font=ctk.CTkFont(size=36, weight="bold"),
        )
        title_label.pack(side="left", expand=True)

        # Spacer to balance center title
        ctk.CTkLabel(header_frame, text="       ", width=80).pack(side="right")

        # --- Main Content Area ---
        content_frame = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        content_frame.grid_columnconfigure(0, weight=0)  # Left sidebar
        content_frame.grid_columnconfigure(1, weight=1)  # Right list area
        content_frame.grid_rowconfigure(0, weight=1)

        # --- Left Column: Output Config ---
        left_frame = ctk.CTkFrame(content_frame, fg_color="transparent", width=300, border_width=0)
        left_frame.grid(row=0, column=0, sticky="n", padx=(0, 20), pady=10)

        ctk.CTkLabel(
            left_frame,
            text="Output Destination",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        output_row = ctk.CTkFrame(left_frame, fg_color="transparent", border_width=0)
        output_row.pack(fill="x")

        saved_output = self.app.saved_output_directory
        if saved_output and Path(saved_output).exists():
            default_output = saved_output
        else:
            default_output = self.app.get_desktop_path()

        self.output_entry = ctk.CTkEntry(
            output_row,
            width=200,
            placeholder_text="/path/to/output"
        )
        self.output_entry.insert(0, default_output)
        self.output_entry.pack(side="left", padx=(0, 10))
        self.output_entry.bind("<FocusOut>", self._on_output_directory_changed)

        output_browse_btn = ctk.CTkButton(
            output_row,
            text="Browse",
            command=self._browse_output_folder,
            width=80,
            fg_color="transparent",
            border_width=2,
            text_color=("black", "white")
        )
        output_browse_btn.pack(side="left")

        # Custom widgets hook - subclasses can add widgets here
        self._create_custom_widgets(left_frame)

        # --- Right Column: File List ---
        self.right_frame = ctk.CTkFrame(content_frame, fg_color="transparent", border_width=0)
        self.right_frame.grid(row=0, column=1, sticky="nsew")

        # Scrollable list
        self.files_list_frame = ctk.CTkScrollableFrame(
            self.right_frame,
            fg_color="transparent"
        )
        self.files_list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Placeholder
        self.no_files_label = ctk.CTkLabel(
            self.files_list_frame,
            text="Drag and drop files here",
            font=ctk.CTkFont(size=16),
            text_color="#8ea4c7",
        )
        self.no_files_label.pack(pady=100)

        # --- Bottom Controls ---
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=2, column=0, sticky="e", padx=20, pady=20)

        select_files_btn = ctk.CTkButton(
            button_frame,
            text="Select Files",
            command=self._select_files,
            width=120,
            height=40,
            fg_color="transparent",
            border_width=2,
            text_color=("black", "white")
        )
        select_files_btn.pack(side="left", padx=(0, 10))

        self.start_stop_btn = ctk.CTkButton(
            button_frame,
            text="Start",
            command=self._start_processing,
            width=120,
            height=40,
            fg_color="transparent",
            border_width=2,
            text_color=("black", "white")
        )
        self.start_stop_btn.pack(side="left")

    def _create_custom_widgets(self, parent: ctk.CTkFrame) -> None:
        """Create custom widgets in the left panel below output folder selection.

        Subclasses can override this method to add custom widgets.

        Args:
            parent: The parent frame (left panel) where widgets should be added.
        """
        pass

    def _create_file_row(self, file_info: Dict[str, Any]) -> ctk.CTkFrame:
        """Create a UI row for a file in the queue.

        Args:
            file_info: Dictionary containing file information.

        Returns:
            Frame containing the file row widgets.
        """
        file_path = file_info["path"]
        filename = os.path.basename(file_path)

        # Card Frame with border and rounded corners
        row_frame = ctk.CTkFrame(self.files_list_frame, border_width=2, corner_radius=15)
        row_frame.pack(fill="x", pady=5, padx=5)

        # Inner padding frame
        inner = ctk.CTkFrame(row_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=10, pady=5)

        # Top Row: Icon + Name + Status
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 5))

        # Icon (Placeholder - simple text or emoji)
        icon_char = self._get_file_icon(file_path)
        icon_label = ctk.CTkLabel(top_row, text=icon_char, width=30, font=ctk.CTkFont(size=20))
        icon_label.pack(side="left")

        # Filename
        display_name = filename
        if len(filename) > MAX_FILENAME_DISPLAY_LENGTH:
            display_name = filename[: MAX_FILENAME_DISPLAY_LENGTH - 3] + "..."

        name_label = ctk.CTkLabel(
            top_row,
            text=display_name,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        name_label.pack(side="left", padx=5, fill="x", expand=True)

        # Status (Clickable)
        status = file_info.get("status", "pending")
        color, text = STATUS_COLORS.get(status, ("gray", "Pending"))
        if text == "Success":
            text = "complete"

        status_label = ctk.CTkLabel(
            top_row,
            text=text,
            font=ctk.CTkFont(size=12),
            text_color=("black", "white"),
            cursor="hand2"
        )
        status_label.pack(side="right")

        # Bind click to show logs
        status_label.bind("<Button-1>", lambda e: self._show_file_logs(file_path))

        # Progress Bar
        progress_bar = ctk.CTkProgressBar(inner)
        progress_bar.pack(fill="x", pady=(0, 5))
        progress_bar.set(file_info.get("progress", 0.0))

        # Bottom Row: Details
        details_row = ctk.CTkFrame(inner, fg_color="transparent")
        details_row.pack(fill="x")

        # Duration / Remaining
        eta_text = "--:--"
        if file_info.get("status") == "success":
            eta_text = f"duration: {file_info.get('elapsed', '00:00')}"
        elif file_info.get("status") == "processing":
            eta_text = f"Remaining: {file_info.get('eta', '--:--')}"

        eta_label = ctk.CTkLabel(
            details_row,
            text=eta_text,
            font=ctk.CTkFont(size=11),
        )
        eta_label.pack(side="left")

        # Speed
        speed = file_info.get("speed", "--")
        if speed == "--":
            speed_text = f"Speed {speed} it/s"
        else:
            speed_text = f"Speed {speed}"

        speed_label = ctk.CTkLabel(
            details_row,
            text=speed_text,
            font=ctk.CTkFont(size=11),
        )
        speed_label.pack(side="right")

        # Store widget references
        self.file_widgets[file_path] = {
            "row_frame": row_frame,
            "status_label": status_label,
            "progress_bar": progress_bar,
            "eta_label": eta_label,
            "speed_label": speed_label,
        }

        return row_frame

    def _get_file_icon(self, file_path: str) -> str:
        """Get an icon character for a file based on its extension.

        Args:
            file_path: Path to the file.

        Returns:
            Icon character (emoji or text).
        """
        filename = file_path.lower()
        if filename.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
            return "🎬"
        elif filename.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif')):
            return "📷"
        elif filename.endswith(('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a')):
            return "🎵"
        else:
            return "📄"

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
            if f["path"] == file_path:
                file_info = f
                break

        if not file_info:
            return

        widgets = self.file_widgets[file_path]
        status = file_info["status"]
        progress = file_info["progress"]

        color, text = STATUS_COLORS.get(status, ("gray", "Unknown"))
        if text == "Success":
            text = "complete"

        # Update status text
        widgets["status_label"].configure(text=text)
        widgets["progress_bar"].set(progress)

        # Update progress bar color
        if status == "success":
            widgets["progress_bar"].configure(progress_color="#00FF9C")
        elif status == "failed":
            widgets["progress_bar"].configure(progress_color="#ff3b30")
        else:
            widgets["progress_bar"].configure(progress_color="#00a6ff")

        # Update details
        eta = file_info.get("eta", "--:--")
        elapsed = file_info.get("elapsed", "00:00")
        speed = file_info.get("speed", "--")

        if status == "processing":
            widgets["eta_label"].configure(text=f"Remaining: {eta}")
        elif status == "success":
            widgets["eta_label"].configure(text=f"duration: {elapsed}")
        elif status == "failed":
            widgets["eta_label"].configure(text="failed")
        else:
            widgets["eta_label"].configure(text="--:--")

        if speed == "--":
            widgets["speed_label"].configure(text=f"Speed {speed} it/s")
        else:
            widgets["speed_label"].configure(text=f"Speed {speed}")

    def _refresh_file_list_display(self):
        """Refresh the entire file list display."""
        # Clear existing widgets
        for widgets in self.file_widgets.values():
            widgets["row_frame"].destroy()
        self.file_widgets.clear()

        # Show/hide placeholder
        if not self.file_queue:
            self.no_files_label.pack(pady=100)
            self.start_stop_btn.configure(state="disabled")
        else:
            self.no_files_label.pack_forget()
            if not self.is_processing:
                self.start_stop_btn.configure(state="normal", text="Start", command=self._start_processing)

            # Create rows for all files
            for file_info in self.file_queue:
                self._create_file_row(file_info)
                self._update_file_row(file_info["path"])

    def _add_files_to_queue(self, file_paths: Tuple[str, ...]):
        """Add multiple files to the processing queue.

        Args:
            file_paths: Tuple or list of file paths to add.
        """
        output_dir = self.output_entry.get().strip()

        for file_path in file_paths:
            # Skip if already in queue
            if any(f["path"] == file_path for f in self.file_queue):
                logger.info(f"File already in queue: {file_path}")
                continue

            # Validate file exists
            if not Path(file_path).exists():
                logger.warning(f"File does not exist: {file_path}")
                continue

            # Generate output path
            output_filename = self.generate_output_filename(file_path)
            output_path = os.path.join(output_dir, output_filename)

            # Add to queue
            file_info = {
                "path": file_path,
                "status": "pending",
                "progress": 0.0,
                "output_path": output_path,
                "error_log": "",
                "parser": self._create_progress_parser(),  # Each file has its own progress parser
                "eta": "--:--",
                "elapsed": "00:00",
                "speed": "--",
            }
            self.file_queue.append(file_info)
            logger.info(f"Added file to queue: {file_path}")

        # Refresh display
        self._refresh_file_list_display()

    def _create_progress_parser(self) -> Any:
        """Create a progress parser instance for a file.

        Subclasses can override this to provide custom progress parsing.

        Returns:
            A progress parser instance (default: ProgressParser).
        """
        return ProgressParser()

    def _setup_drag_drop(self):
        """Setup drag and drop support for the file list frame."""
        if self._drag_drop_setup:
            return  # Already set up

        try:
            def drop_handler(event):
                # Only process drops if this view is the current active view
                if not hasattr(self.app, "current_view") or self.app.current_view != self:
                    logger.debug(f"Drop event ignored - not the active view")
                    return "copy"

                logger.info("Drop event triggered!")
                try:
                    self._on_drop(event)
                except Exception as e:
                    logger.error(f"Error in drop handler: {e}", exc_info=True)
                return "copy"

            self._drop_handler = drop_handler

            # Platform-specific registration:
            # - Windows: register on the widget (more reliable)
            # - macOS/Linux: register on root window (works better)
            if sys.platform == "win32":
                # Windows: register on the specific widget
                drop_widget = self.right_frame.tk
                drop_widget.drop_target_register(DND_FILES)
                drop_widget.dnd_bind("<<Drop>>", drop_handler)
                logger.info("Drag and drop enabled on file list widget (Windows)")
            else:
                # macOS/Linux: register on root window
                if hasattr(self.app, "drop_target_register"):
                    self.app.drop_target_register(DND_FILES)
                if hasattr(self.app, "dnd_bind"):
                    self.app.dnd_bind("<<Drop>>", drop_handler)
                logger.info("Drag and drop enabled on root window (macOS/Linux)")

            self._drag_drop_setup = True

        except Exception as e:
            logger.error(f"Failed to setup drag and drop: {e}", exc_info=True)

    def _teardown_drag_drop(self):
        """Remove drag and drop handlers."""
        # Note: tkinterdnd2 doesn't have a clean unbind, but the handler
        # will check if this view is active, so it's safe to leave it registered
        # We just mark it as not set up so it can be re-registered if needed
        self._drag_drop_setup = False
        # The handler itself will ignore drops if we're not the active view

    def _on_drop(self, event):
        """Handle file drop event.

        Args:
            event: Drop event containing file paths.
        """
        try:
            files_str = event.data
            logger.info(f"Drop event received, data: {files_str[:200]}...")

            # Parse the file paths
            file_paths = []
            current_path = ""
            in_braces = False

            i = 0
            while i < len(files_str):
                char = files_str[i]

                if char == "{":
                    in_braces = True
                    i += 1
                    continue
                elif char == "}":
                    in_braces = False
                    if current_path:
                        file_paths.append(current_path)
                        current_path = ""
                    i += 1
                    continue
                elif char == " " and not in_braces:
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
                if ";" in files_str:
                    file_paths = [p.strip() for p in files_str.split(";") if p.strip()]
                elif "\n" in files_str:
                    file_paths = [p.strip() for p in files_str.split("\n") if p.strip()]
                else:
                    file_paths = [p.strip() for p in files_str.split() if p.strip()]

            logger.info(f"Parsed {len(file_paths)} path(s) from drop event")

            # Filter to only include files (not directories) and valid extensions
            valid_files: list[str] = []

            for file_path in file_paths:
                file_path = file_path.strip()
                if not file_path:
                    continue

                path_obj = Path(file_path)
                if not path_obj.exists():
                    logger.warning(f"Dropped path does not exist: {file_path}")
                    continue

                if path_obj.is_dir():
                    # If it's a directory, recursively find all valid files
                    for ext in self.supported_extensions:
                        valid_files.extend(str(p) for p in path_obj.rglob(f"*{ext}"))
                        valid_files.extend(
                            str(p) for p in path_obj.rglob(f"*{ext.upper()}")
                        )
                elif path_obj.is_file():
                    if path_obj.suffix.lower() in self.supported_extensions:
                        valid_files.append(file_path)
                    else:
                        logger.info(f"Skipping unsupported file type: {file_path}")

            # Add files to queue
            if valid_files:
                logger.info(f"Adding {len(valid_files)} file(s) from drag and drop")
                self._add_files_to_queue(tuple(valid_files))
            else:
                logger.info("No valid files found in drop")
                extensions_str = ", ".join(self.supported_extensions).upper()
                messagebox.showinfo(
                    "No Valid Files",
                    f"No supported files were found in the dropped items.\n\n"
                    f"Supported formats: {extensions_str}",
                )

        except Exception as e:
            logger.error(f"Error handling file drop: {e}", exc_info=True)
            messagebox.showerror(
                "Drop Error", f"Error processing dropped files: {str(e)}"
            )

    def _show_file_logs(self, file_path: str):
        """Show error logs for a specific file in a separate dialog.

        Args:
            file_path: Path to the file whose logs should be displayed.
        """
        # Find file info
        file_info = None
        for f in self.file_queue:
            if f["path"] == file_path:
                file_info = f
                break

        if not file_info or not file_info.get("error_log"):
            messagebox.showinfo("No Logs", "No error logs available for this file.")
            return

        # Display the error log in a separate dialog
        filename = os.path.basename(file_path)
        log_text = f"=== Error log for {filename} ===\n\n{file_info['error_log']}\n\n"

        dialog = LogDialog(self.app, filename, log_text)
        self.app.wait_window(dialog)

    def _on_output_directory_changed(self, event: Optional[Any] = None):
        """Handle output directory change event.

        Args:
            event: Optional event parameter for compatibility with bindings.
        """
        self.app._save_config()

    def _browse_output_folder(self, event: Optional[Any] = None):
        """Open folder dialog to select output directory.

        Args:
            event: Optional event parameter for compatibility with bindings.
        """
        # Ensure we have focus before opening dialog
        self.app.focus()
        folder = filedialog.askdirectory(parent=self.app, title="Select output folder")
        if folder:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, folder)
            self.app._save_config()

    def _select_files(self, event: Optional[Any] = None):
        """Open file dialog to select files for processing with multiselect.

        Args:
            event: Optional event parameter for compatibility with bindings.
        """
        # Build file type filter from supported extensions
        # Format: [("Description", "*.ext1 *.ext2"), ("All files", "*.*")]
        file_types = []
        
        # Group extensions by category for better UX
        image_exts = []
        video_exts = []
        audio_exts = []
        other_exts = []
        
        for ext in self.supported_extensions:
            ext_lower = ext.lower()
            if ext_lower in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif', '.webp'):
                image_exts.append(ext_lower)
            elif ext_lower in ('.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.m4p'):
                video_exts.append(ext_lower)
            elif ext_lower in ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'):
                audio_exts.append(ext_lower)
            else:
                other_exts.append(ext_lower)
        
        # Build file type list
        if image_exts:
            pattern = " ".join(f"*{ext}" for ext in sorted(set(image_exts)))
            file_types.append(("Image files", pattern))
        
        if video_exts:
            pattern = " ".join(f"*{ext}" for ext in sorted(set(video_exts)))
            file_types.append(("Video files", pattern))
        
        if audio_exts:
            pattern = " ".join(f"*{ext}" for ext in sorted(set(audio_exts)))
            file_types.append(("Audio files", pattern))
        
        if other_exts:
            pattern = " ".join(f"*{ext}" for ext in sorted(set(other_exts)))
            file_types.append(("Other files", pattern))
        
        # Add combined pattern for all supported files
        all_pattern = " ".join(f"*{ext}" for ext in sorted(self.supported_extensions))
        file_types.insert(0, ("All supported files", all_pattern))
        
        # Always add "All files" as last option
        file_types.append(("All files", "*.*"))
        
        # Ensure we have focus before opening dialog
        self.app.focus()
        filenames = filedialog.askopenfilenames(
            parent=self.app,
            title="Select files to process",
            filetypes=file_types
        )
        
        if filenames:
            logger.info(f"User selected {len(filenames)} file(s) via file dialog")
            self._add_files_to_queue(filenames)

    def _go_to_home(self):
        """Navigate back to the home view, stopping any running processes if needed."""
        # Check if there are any running processes
        has_running_processes = (
            self.is_processing
            or any(
                proc and proc.poll() is None
                for proc in self.active_processes.values()
            )
        )

        if has_running_processes:
            # Warn user and ask for confirmation
            response = messagebox.askyesno(
                "Stop Processing?",
                "There are processes currently running. "
                "Returning to the home screen will stop all running processes.\n\n"
                "Do you want to continue?",
                icon="warning",
            )

            if not response:
                # User cancelled, don't navigate away
                return

            # User confirmed, stop all processes
            logger.info("User confirmed stop and return to home")
            self._stop_processing()

            # Wait a moment for processes to terminate
            time.sleep(0.5)

            # Terminate any remaining processes
            for file_path, proc in list(self.active_processes.items()):
                if proc and proc.poll() is None:
                    logger.info(f"Terminating remaining process for: {file_path}")
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()

        # Navigate to home view
        if hasattr(self.app, "show_view"):
            self.app.show_view("home")

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
            messagebox.showerror(
                "Error", f"Output directory does not exist: {output_dir}"
            )
            return

        if not output_path.is_dir():
            messagebox.showerror(
                "Error", f"Output path is not a directory: {output_dir}"
            )
            return

        # Check if there are any files to process
        files_to_process = [
            f for f in self.file_queue if f["status"] in ("pending", "failed")
        ]
        if not files_to_process:
            messagebox.showinfo(
                "Nothing to Process",
                "All files have been processed successfully. Add new files or clear successful files to process again.",
            )
            return

        # Update UI state
        self.is_processing = True
        self.stop_requested = False
        self.start_stop_btn.configure(
            text="Stop",
            command=self._stop_processing,
            fg_color="#ff3b30",
            text_color="white",
            state="normal"
        )

        logger.info(f"Starting batch processing of {len(files_to_process)} file(s)")

        # Start processing thread
        process_thread = threading.Thread(target=self._process_queue, daemon=True)
        process_thread.start()

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
                    if file_info["path"] == file_path:
                        file_info["status"] = "failed"
                        file_info["error_log"] = "Processing stopped by user"
                        file_info["progress"] = 0.0
                        self.output_queue.put(("file_update", file_path))
                        break

        # Update UI state
        self.start_stop_btn.configure(state="disabled")

    def _process_queue(self):
        """Process files from the queue with concurrent batch processing."""
        try:
            batch_size = self.app.config.get("batch_size", 1)
            logger.info(f"Starting batch processing with batch size: {batch_size}")

            # Get list of files to process
            files_to_process = [
                f for f in self.file_queue if f["status"] in ("pending", "failed")
            ]

            # Track active processing threads
            active_threads: dict[str, threading.Thread] = {}

            # Process files
            while not self.stop_requested and (files_to_process or active_threads):
                # Start new processes up to batch_size
                while (
                    len(active_threads) < batch_size
                    and files_to_process
                    and not self.stop_requested
                ):
                    file_info = files_to_process.pop(0)
                    file_path = file_info["path"]

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

    @abstractmethod
    def _process_file(self, file_info: Dict[str, Any]):
        """Process a single file.

        This method must be implemented by subclasses to define how files are processed.

        Args:
            file_info: Dictionary containing file information including:
                - path: Input file path
                - output_path: Output file path
                - status: Current status (will be "processing" when called)
                - progress: Current progress (0.0 to 1.0)
                - parser: Progress parser instance
                - error_log: Error log string
        """
        pass

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

    def _handle_stream_message(self, line: str, file_path: str):
        """Handle stdout/stderr message from subprocess.

        Args:
            line: Output line from subprocess.
            file_path: Path to the file being processed.
        """
        self._update_file_progress(line, file_path)
        self._append_to_file_log(file_path, line)

    def _handle_queue_message(self, message: Tuple):
        """Handle a single message from the output queue.

        Args:
            message: Tuple containing (message_type, *args).
        """
        msg_type = message[0]

        if msg_type in ("stdout", "stderr"):
            _, line, file_path = message
            self._handle_stream_message(line, file_path)
        elif msg_type == "file_update":
            file_path = message[1]
            self._update_file_row(file_path)
        elif msg_type == "batch_done":
            logger.info("Batch processing completed")
            self._finalize_batch_processing()
        elif msg_type == "batch_error":
            error_msg = message[1]
            logger.error(f"Batch processing error: {error_msg}")
            self._finalize_batch_processing()

    def _check_process_output(self):
        """Periodically check for process output from queue and update UI."""
        try:
            while True:
                try:
                    message = self.output_queue.get_nowait()
                    self._handle_queue_message(message)
                except queue.Empty:
                    break
        except Exception as e:
            logger.error(f"Error processing output queue: {e}")
            self._finalize_batch_processing()

        self.after(PROGRESS_CHECK_INTERVAL_MS, self._check_process_output)

    def _update_file_progress(self, line: str, file_path: str):
        """Update progress bar for a specific file from a line of output.

        Args:
            line: A line of output that may contain progress information.
            file_path: Path to the file being processed.
        """
        # Find the file info
        file_info = None
        for f in self.file_queue:
            if f["path"] == file_path:
                file_info = f
                break

        if not file_info:
            return

        # Use this file's own progress parser
        parser = file_info.get("parser")
        if not parser:
            return

        if parser.parse(line):
            # Update file progress
            progress_fraction = parser.get_progress_fraction()
            file_info["progress"] = progress_fraction

            # Update progress text values
            file_info["eta"] = parser.format_eta()
            file_info["elapsed"] = parser.format_elapsed()
            file_info["speed"] = parser.format_rate()

            # Queue update for UI thread
            self.output_queue.put(("file_update", file_path))

    def _append_to_file_log(self, file_path: str, line: str):
        """Append a line to the error log for a file.

        Args:
            file_path: Path to the file.
            line: Line to append to the log.
        """
        # Find the file info
        for file_info in self.file_queue:
            if file_info["path"] == file_path:
                # Only append if it looks like an error or warning
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in ERROR_KEYWORDS):
                    file_info["error_log"] += line
                break

    def _finalize_batch_processing(self):
        """Finalize batch processing and update UI state."""
        self.is_processing = False
        self.stop_requested = False
        self.currently_processing.clear()
        self.active_processes.clear()

        # Update UI buttons
        self.start_stop_btn.configure(
            state="normal",
            text="Start",
            command=self._start_processing,
            fg_color="transparent",
            text_color=("black", "white")
        )

        # Check if there are any failed files
        failed_files = [f for f in self.file_queue if f["status"] == "failed"]
        success_files = [f for f in self.file_queue if f["status"] == "success"]

        if failed_files:
            logger.info(
                f"Batch processing completed: {len(success_files)} succeeded, {len(failed_files)} failed"
            )
        else:
            logger.info(
                f"Batch processing completed successfully: {len(success_files)} file(s)"
            )

    def show(self) -> None:
        """Show this view and set up drag and drop."""
        super().show()
        # Set up drag and drop when view becomes active
        self._setup_drag_drop()

    def hide(self) -> None:
        """Hide this view and tear down drag and drop."""
        # Remove drag and drop handlers when view is hidden
        self._teardown_drag_drop()
        super().hide()

    def cleanup(self) -> None:
        """Clean up resources when the view is being removed."""
        # Remove drag and drop handlers
        self._teardown_drag_drop()

        # Stop any ongoing processing
        if self.is_processing:
            self._stop_processing()

        # Terminate any remaining processes
        for file_path, proc in list(self.active_processes.items()):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
