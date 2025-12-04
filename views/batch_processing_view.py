"""Batch processing view for the Deface application.

This module contains the UI and logic for batch processing files with deface.
"""

import logging
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, Tuple

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter is required for views")

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    raise ImportError("tkinterdnd2 is required for drag and drop support")

from dialogs import ConfigDialog, LogDialog
from progress_parser import ProgressParser
from views.base_view import BaseView

logger = logging.getLogger(__name__)

# View constants
FILE_LIST_HEIGHT = 300
MAX_FILENAME_DISPLAY_LENGTH = 35
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

# Status colors for file processing - Sightline brand colors
STATUS_COLORS = {
    "pending": ("#8ea4c7", "Pending"),  # Mist Blue
    "processing": ("#00a6ff", "Processing"),  # Primary Accent
    "success": ("#4caf50", "Success"),  # Standard success green
    "failed": ("#ff3b30", "Failed"),  # Ember Red
}

# Keywords for error detection in logs
ERROR_KEYWORDS = ["error", "warning", "exception", "failed", "traceback"]


class BatchProcessingView(BaseView):
    """View for batch processing files with deface."""

    def __init__(self, parent: ctk.CTk, app: Any):
        """Initialize the batch processing view.

        Args:
            parent: The parent widget (main application window).
            app: Reference to the main application instance.
        """
        super().__init__(parent, app)

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

        # Setup drag and drop
        self._setup_drag_drop()

        # Start checking for process output
        self._check_process_output()

    def create_widgets(self) -> None:
        """Create and layout all GUI widgets."""
        # Main container
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title section with back button
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 20))

        # Back to Home button
        back_btn = ctk.CTkButton(
            title_frame,
            text="← Back to Home",
            command=self._go_to_home,
            width=120,
            height=30,
            font=ctk.CTkFont(size=12),
        )
        back_btn.pack(side="left", padx=(0, 10))

        # Title
        title_label = ctk.CTkLabel(
            title_frame,
            text="Deface",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(side="left")

        # Output directory selection
        output_frame = ctk.CTkFrame(main_frame)
        output_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            output_frame, text="Output folder:", font=ctk.CTkFont(size=14)
        ).pack(anchor="w", padx=10, pady=10)

        output_row = ctk.CTkFrame(output_frame)
        output_row.pack(fill="x", padx=10, pady=(0, 10))

        # Set default output folder from saved config or Desktop
        saved_output = self.app.saved_output_directory
        if saved_output and Path(saved_output).exists():
            default_output = saved_output
        else:
            default_output = self.app.get_desktop_path()
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
            files_header,
            text="Add Files",
            command=self._add_files,
            width=100,
            height=30,
        )
        self.add_files_btn.pack(side="right", padx=5)

        self.remove_files_btn = ctk.CTkButton(
            files_header,
            text="Remove",
            command=self._remove_files,
            width=100,
            height=30,
        )
        self.remove_files_btn.pack(side="right", padx=5)

        # Scrollable frame for file list
        self.files_list_frame = ctk.CTkScrollableFrame(
            files_frame, height=FILE_LIST_HEIGHT, fg_color="transparent"
        )
        self.files_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Placeholder text when no files
        self.no_files_label = ctk.CTkLabel(
            self.files_list_frame,
            text="No files added. Click 'Add Files' to select files.",
            font=ctk.CTkFont(size=12),
            text_color="#8ea4c7",  # Mist Blue
        )
        self.no_files_label.pack(pady=50)

        # Buttons
        self.button_frame = ctk.CTkFrame(main_frame)
        self.button_frame.pack(fill="x", pady=10)

        self.start_btn = ctk.CTkButton(
            self.button_frame,
            text="Start",
            command=self._start_processing,
            width=120,
            height=40,
        )
        self.start_btn.pack(side="left", padx=10)
        self.start_btn.configure(state="disabled")  # Disabled until files are added

        self.stop_btn = ctk.CTkButton(
            self.button_frame,
            text="Stop",
            command=self._stop_processing,
            width=120,
            height=40,
            fg_color="#ff3b30",  # Ember Red
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

        face_smudge_btn = ctk.CTkButton(
            self.button_frame,
            text="Face Smudge",
            command=self._open_face_smudge,
            width=120,
            height=40,
        )
        face_smudge_btn.pack(side="left", padx=10)

    def _create_file_row(self, file_info: Dict[str, Any]) -> ctk.CTkFrame:
        """Create a UI row for a file in the queue.

        Args:
            file_info: Dictionary containing file information.

        Returns:
            Frame containing the file row widgets.
        """
        file_path = file_info["path"]

        # Main row frame
        row_frame = ctk.CTkFrame(self.files_list_frame)
        row_frame.pack(fill="x", pady=5, padx=5)

        # Checkbox for selection
        checkbox_var = tk.BooleanVar(value=False)
        checkbox = ctk.CTkCheckBox(row_frame, text="", variable=checkbox_var, width=30)
        checkbox.pack(side="left", padx=5)

        filename = os.path.basename(file_path)
        if len(filename) > MAX_FILENAME_DISPLAY_LENGTH:
            display_name = filename[: MAX_FILENAME_DISPLAY_LENGTH - 3] + "..."
        else:
            display_name = filename

        filename_label = ctk.CTkLabel(
            row_frame,
            text=display_name,
            font=ctk.CTkFont(size=11),
            width=250,
            anchor="w",
        )
        filename_label.pack(side="left", padx=5)

        # Status label
        status_label = ctk.CTkLabel(
            row_frame,
            text="Pending",
            font=ctk.CTkFont(size=10),
            width=70,
            text_color="#8ea4c7",  # Mist Blue
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
            text_color="#8ea4c7",  # Mist Blue
        )
        eta_label.pack(side="left", padx=3)

        # Elapsed label
        elapsed_label = ctk.CTkLabel(
            row_frame,
            text="00:00",
            font=ctk.CTkFont(size=10),
            width=50,
            text_color="#8ea4c7",  # Mist Blue
        )
        elapsed_label.pack(side="left", padx=3)

        # Speed label
        speed_label = ctk.CTkLabel(
            row_frame, text="--", font=ctk.CTkFont(size=10), width=60, text_color="#8ea4c7"  # Mist Blue
        )
        speed_label.pack(side="left", padx=3)

        # Show logs button (hidden by default, shown on failure)
        show_logs_btn = ctk.CTkButton(
            row_frame,
            text="Logs",
            command=lambda: self._show_file_logs(file_path),
            width=60,
            height=25,
            fg_color="#00a6ff",  # Primary Accent
        )
        # Don't pack it yet, will show on failure

        # Store widget references
        self.file_widgets[file_path] = {
            "row_frame": row_frame,
            "checkbox": checkbox,
            "checkbox_var": checkbox_var,
            "filename_label": filename_label,
            "status_label": status_label,
            "progress_bar": progress_bar,
            "eta_label": eta_label,
            "elapsed_label": elapsed_label,
            "speed_label": speed_label,
            "show_logs_btn": show_logs_btn,
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
            if f["path"] == file_path:
                file_info = f
                break

        if not file_info:
            return

        widgets = self.file_widgets[file_path]
        status = file_info["status"]
        progress = file_info["progress"]

        color, text = STATUS_COLORS.get(status, ("gray", "Unknown"))
        widgets["status_label"].configure(text=text, text_color=color)
        widgets["progress_bar"].set(progress)

        # Update progress text values
        widgets["eta_label"].configure(text=file_info.get("eta", "--:--"))
        widgets["elapsed_label"].configure(text=file_info.get("elapsed", "00:00"))
        widgets["speed_label"].configure(text=file_info.get("speed", "--"))

        # Disable checkbox while processing
        if status == "processing":
            widgets["checkbox"].configure(state="disabled")
        else:
            widgets["checkbox"].configure(state="normal")

        if status == "failed" and file_info.get("error_log"):
            widgets["show_logs_btn"].pack(side="left", padx=5)
        else:
            widgets["show_logs_btn"].pack_forget()

    def _refresh_file_list_display(self):
        """Refresh the entire file list display."""
        # Clear existing widgets
        for widgets in self.file_widgets.values():
            widgets["row_frame"].destroy()
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
                self._update_file_row(file_info["path"])

    def _add_files(self):
        """Open file dialog to select multiple input files and add them to the queue."""
        # Ensure we have focus before opening dialog
        self.app.focus()
        filenames = filedialog.askopenfilenames(
            parent=self.app,
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
            input_filename = os.path.basename(file_path)
            name, ext = os.path.splitext(input_filename)
            output_filename = f"{name}_anonymized{ext}"
            output_path = os.path.join(output_dir, output_filename)

            # Add to queue
            file_info = {
                "path": file_path,
                "status": "pending",
                "progress": 0.0,
                "output_path": output_path,
                "error_log": "",
                "parser": ProgressParser(),  # Each file has its own progress parser
                "eta": "--:--",
                "elapsed": "00:00",
                "speed": "--",
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
                "Cannot remove files while processing. Stop the process first.",
            )
            return

        # Find selected files
        files_to_remove = []
        for file_path, widgets in self.file_widgets.items():
            if widgets["checkbox_var"].get():
                files_to_remove.append(file_path)

        if not files_to_remove:
            messagebox.showinfo("No Selection", "Please select files to remove.")
            return

        # Remove from queue
        self.file_queue = [
            f for f in self.file_queue if f["path"] not in files_to_remove
        ]

        logger.info(f"Removed {len(files_to_remove)} file(s) from queue")

        # Refresh display
        self._refresh_file_list_display()

    def _setup_drag_drop(self):
        """Setup drag and drop support for the file list frame."""
        try:
            # Register drop target on parent window (app)
            if hasattr(self.app, "drop_target_register"):
                self.app.drop_target_register(DND_FILES)

                def drop_handler(event):
                    logger.info("Drop event triggered!")
                    try:
                        self._on_drop(event)
                    except Exception as e:
                        logger.error(f"Error in drop handler: {e}", exc_info=True)
                    return "copy"

                if hasattr(self.app, "dnd_bind"):
                    self.app.dnd_bind("<<Drop>>", drop_handler)
                    logger.info("Drag and drop enabled on root window")

        except Exception as e:
            logger.error(f"Failed to setup drag and drop: {e}", exc_info=True)

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
                    for ext in SUPPORTED_EXTENSIONS:
                        valid_files.extend(str(p) for p in path_obj.rglob(f"*{ext}"))
                        valid_files.extend(
                            str(p) for p in path_obj.rglob(f"*{ext.upper()}")
                        )
                elif path_obj.is_file():
                    if path_obj.suffix.lower() in SUPPORTED_EXTENSIONS:
                        valid_files.append(file_path)
                    else:
                        logger.info(f"Skipping unsupported file type: {file_path}")

            # Add files to queue
            if valid_files:
                logger.info(f"Adding {len(valid_files)} file(s) from drag and drop")
                self._add_files_to_queue(tuple(valid_files))
            else:
                logger.info("No valid files found in drop")
                messagebox.showinfo(
                    "No Valid Files",
                    "No supported image or video files were found in the dropped items.\n\n"
                    "Supported formats: JPG, PNG, BMP, TIFF, MP4, AVI, MOV, MKV",
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

    def _open_settings(self):
        """Open the configuration settings dialog."""
        dialog = ConfigDialog(self.app, self.app.config)
        self.app.wait_window(dialog)

        if dialog.result is not None:
            self.app.config = dialog.result
            logger.info(f"Configuration updated: {self.app.config}")
            self.app._save_config()

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

    def _open_face_smudge(self):
        """Open the Face Smudge window."""
        self.app._open_face_smudge()

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
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.add_files_btn.configure(state="disabled")
        self.remove_files_btn.configure(state="disabled")

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
        self.stop_btn.configure(state="disabled")

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

    def _process_file(self, file_info: Dict[str, Any]):
        """Process a single file.

        Args:
            file_info: Dictionary containing file information.
        """
        file_path = file_info["path"]
        output_path = file_info["output_path"]

        logger.info(f"Processing file: {file_path}")

        # Update status to processing
        file_info["status"] = "processing"
        file_info["progress"] = 0.0
        file_info["error_log"] = ""
        file_info["parser"] = ProgressParser()  # Reset progress parser for this file
        self.output_queue.put(("file_update", file_path))

        try:
            # Start the subprocess with current configuration
            proc = self.app.run_deface(file_path, output_path, self.app.config)
            self.active_processes[file_path] = proc

            # Start threads to read stdout and stderr concurrently
            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(proc.stdout, "stdout", file_path),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(proc.stderr, "stderr", file_path),
                daemon=True,
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
                file_info["status"] = "success"
                file_info["progress"] = 1.0
                logger.info(f"Successfully processed: {file_path}")
            else:
                file_info["status"] = "failed"
                file_info["progress"] = 0.0
                file_info["error_log"] += f"\nProcess exited with code {return_code}"
                logger.error(
                    f"Failed to process {file_path} (exit code: {return_code})"
                )

            self.output_queue.put(("file_update", file_path))

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            file_info["status"] = "failed"
            file_info["progress"] = 0.0
            file_info["error_log"] += f"\nException: {str(e)}"
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
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.add_files_btn.configure(state="normal")
        self.remove_files_btn.configure(state="normal")

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

    def cleanup(self) -> None:
        """Clean up resources when the view is being removed."""
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

