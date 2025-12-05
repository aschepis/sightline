"""Face blur batch processing view for the Sightline application.

This module contains the UI and logic for batch processing files with face blurring.
"""

import logging
import os
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Any, Dict

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter is required for views")

from views.generic_batch_view import GenericBatchView

logger = logging.getLogger(__name__)

# Supported file extensions for face blurring
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
    ".webm",
    ".m4p",
    ".m4v",
}


class FaceBlurView(GenericBatchView):
    """View for batch processing files with face blurring."""

    def __init__(self, parent: ctk.CTk, app: Any):
        """Initialize the face blur batch processing view.

        Args:
            parent: The parent widget (main application window).
            app: Reference to the main application instance.
        """
        super().__init__(
            parent=parent,
            app=app,
            page_title="B L U R   F A C E S",
            supported_extensions=SUPPORTED_EXTENSIONS,
            generate_output_filename=self._generate_output_filename,
        )

    def _generate_output_filename(self, input_path: str) -> str:
        """Generate output filename for face blurring.

        Args:
            input_path: Path to the input file.

        Returns:
            Output filename with _anonymized suffix.
        """
        input_filename = os.path.basename(input_path)
        name, ext = os.path.splitext(input_filename)
        return f"{name}_anonymized{ext}"

    def _process_file(self, file_info: Dict[str, Any]):
        """Process a single file with face blurring.

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
        file_info["parser"] = self._create_progress_parser()  # Reset progress parser for this file
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
