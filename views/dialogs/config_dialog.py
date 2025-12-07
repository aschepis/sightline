"""Configuration dialog for Sightline options."""

import importlib
import logging
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Any, Dict, Optional

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter is required for dialog windows")

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Get the application version from main module."""
    try:
        if "main" in sys.modules:
            main_module = sys.modules["main"]
            return getattr(main_module, "__version__", "1.0.0")
        else:
            # Try to import it
            main_module = importlib.import_module("main")
            return getattr(main_module, "__version__", "1.0.0")
    except (ImportError, AttributeError):
        return "1.0.0"


class ConfigDialog(ctk.CTkToplevel):
    """Configuration dialog for Sightline options."""

    MAX_BATCH_SIZE = 8

    def __init__(self, parent, config: Dict[str, Any], full_config: Optional[Dict[str, Any]] = None):
        super().__init__(parent)

        self.title("Sightline Configuration")
        self.geometry("600x700")
        self.resizable(False, False)

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Store configuration
        self.config = config.copy()
        self.full_config = full_config or {}
        self.result: Optional[Dict[str, Any]] = None
        self.hugging_face_token: str = ""

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
        main_frame = ctk.CTkFrame(self, border_width=0)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(
            main_frame,
            text="Sightline Configuration",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(pady=(0, 20))

        scrollable_frame = ctk.CTkScrollableFrame(main_frame)
        scrollable_frame.pack(fill="both", expand=True, pady=(0, 20))


        self._create_section_header(scrollable_frame, "Face Blur Settings")

        # Detection threshold
        self._create_threshold_section(scrollable_frame)

        # Scale (WxH)
        self._create_scale_section(scrollable_frame)

        # Use boxes
        self._create_boxes_section(scrollable_frame)

        # Mask scale
        self._create_mask_scale_section(scrollable_frame)

        # Replace with mode
        self._create_replace_section(scrollable_frame)

        # Keep audio
        self._create_audio_section(scrollable_frame)

        # Keep metadata
        self._create_metadata_section(scrollable_frame)

        self._create_section_header(scrollable_frame, "Transcription Settings")

        # Hugging Face token
        self._create_hugging_face_token_section(scrollable_frame)

        self._create_section_header(scrollable_frame, "Batch Processing Settings")

        # Batch size
        self._create_batch_size_section(scrollable_frame)

        # Buttons
        self._create_button_section(main_frame)

        # Bind keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _create_threshold_section(self, parent):
        """Create detection threshold configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            frame, text="Detection Threshold:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            frame,
            text="Tune this to trade off between false positive and false negative rate",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.thresh_entry = ctk.CTkEntry(frame, width=150)
        self.thresh_entry.insert(0, str(self.config.get("thresh", 0.2)))
        self.thresh_entry.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_scale_section(self, parent):
        """Create scale configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(frame, text="Scale (WxH):", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        ctk.CTkLabel(
            frame,
            text="Downscale images for network inference (e.g., 640x360). Leave empty for no scaling.",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.scale_entry = ctk.CTkEntry(
            frame, width=150, placeholder_text="e.g., 640x360"
        )
        if self.config.get("scale"):
            self.scale_entry.insert(0, self.config["scale"])
        self.scale_entry.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_boxes_section(self, parent):
        """Create boxes configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(frame, text="Use Boxes:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        ctk.CTkLabel(
            frame,
            text="Use boxes instead of ellipse masks",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.boxes_var = tk.BooleanVar(value=self.config.get("boxes", False))
        boxes_checkbox = ctk.CTkCheckBox(
            frame, text="Use boxes", variable=self.boxes_var
        )
        boxes_checkbox.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_mask_scale_section(self, parent):
        """Create mask scale configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            frame, text="Mask Scale Factor:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            frame,
            text="Scale factor for face masks to ensure complete face coverage",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.mask_scale_entry = ctk.CTkEntry(frame, width=150)
        self.mask_scale_entry.insert(0, str(self.config.get("mask_scale", 1.3)))
        self.mask_scale_entry.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_replace_section(self, parent):
        """Create anonymization mode configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            frame, text="Anonymization Mode:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            frame,
            text="Filter mode for face regions",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        replace_options = ["blur", "solid", "none", "img", "mosaic"]
        self.replace_var = tk.StringVar(value=self.config.get("replacewith", "blur"))
        replace_menu = ctk.CTkOptionMenu(
            frame, values=replace_options, variable=self.replace_var, width=150
        )
        replace_menu.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_audio_section(self, parent):
        """Create keep audio configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(frame, text="Keep Audio:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        ctk.CTkLabel(
            frame,
            text="Keep audio from video source file (only applies to videos)",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.audio_var = tk.BooleanVar(value=self.config.get("keep_audio", True))
        audio_checkbox = ctk.CTkCheckBox(
            frame, text="Keep audio", variable=self.audio_var
        )
        audio_checkbox.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_metadata_section(self, parent):
        """Create keep metadata configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            frame, text="Keep Metadata:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            frame,
            text="Keep metadata of the original image",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.metadata_var = tk.BooleanVar(value=self.config.get("keep_metadata", True))
        metadata_checkbox = ctk.CTkCheckBox(
            frame, text="Keep metadata", variable=self.metadata_var
        )
        metadata_checkbox.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_batch_size_section(self, parent):
        """Create batch size configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            frame, text="Batch Size:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            frame,
            text=f"Number of files to process concurrently (1-{self.MAX_BATCH_SIZE})",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.batch_size_entry = ctk.CTkEntry(frame, width=150)
        self.batch_size_entry.insert(0, str(self.config.get("batch_size", 1)))
        self.batch_size_entry.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_hugging_face_token_section(self, parent):
        """Create Hugging Face token configuration section."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            frame, text="Hugging Face Token:", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            frame,
            text="Token for accessing Hugging Face models (required for transcription features)",
            font=ctk.CTkFont(size=10),
            text_color="#8ea4c7",  # Mist Blue
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.hf_token_entry = ctk.CTkEntry(frame, width=400)
        current_token = self.full_config.get("hugging_face_token", "")
        if current_token:
            self.hf_token_entry.insert(0, current_token)
        self.hf_token_entry.pack(anchor="w", padx=10, pady=(0, 10))

    def _create_button_section(self, parent):
        """Create dialog button section."""
        button_frame = ctk.CTkFrame(parent, border_width=0, fg_color="transparent")
        button_frame.pack(fill="x", pady=(0, 0))

        ok_btn = ctk.CTkButton(button_frame, text="OK", command=self._on_ok, width=100)
        ok_btn.pack(side="right", padx=10)

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self._on_cancel,
            width=100,
            fg_color="#1a253a",  # Border subtle
        )
        cancel_btn.pack(side="right", padx=10)

    def _validate_threshold(self) -> Optional[float]:
        """Validate threshold input.

        Returns:
            Threshold value if valid, None otherwise.
        """
        try:
            thresh_val = float(self.thresh_entry.get().strip())
            if thresh_val < 0 or thresh_val > 1:
                messagebox.showerror(
                    "Error", "Detection threshold must be between 0 and 1."
                )
                return None
            return thresh_val
        except ValueError:
            messagebox.showerror(
                "Error", "Detection threshold must be a valid number."
            )
            return None

    def _validate_scale(self) -> Optional[str]:
        """Validate scale input.

        Returns:
            Scale value if valid (empty string for no scaling), None if invalid.
        """
        scale_val: str = self.scale_entry.get().strip()
        if not scale_val:
            return ""

        if "x" not in scale_val.lower():
            messagebox.showerror(
                "Error", "Scale must be in format WxH (e.g., 640x360)."
            )
            return None

        try:
            parts = scale_val.lower().split("x")
            if len(parts) != 2:
                raise ValueError
            int(parts[0])
            int(parts[1])
            return scale_val
        except ValueError:
            messagebox.showerror(
                "Error",
                "Scale must be in format WxH with valid integers (e.g., 640x360).",
            )
            return None

    def _validate_mask_scale(self) -> Optional[float]:
        """Validate mask scale input.

        Returns:
            Mask scale value if valid, None otherwise.
        """
        try:
            mask_scale_val = float(self.mask_scale_entry.get().strip())
            if mask_scale_val <= 0:
                messagebox.showerror(
                    "Error", "Mask scale factor must be greater than 0."
                )
                return None
            return mask_scale_val
        except ValueError:
            messagebox.showerror(
                "Error", "Mask scale factor must be a valid number."
            )
            return None

    def _validate_batch_size(self) -> Optional[int]:
        """Validate batch size input.

        Returns:
            Batch size value if valid, None otherwise.
        """
        try:
            batch_size_val = int(self.batch_size_entry.get().strip())
            if batch_size_val < 1 or batch_size_val > self.MAX_BATCH_SIZE:
                messagebox.showerror(
                    "Error", f"Batch size must be between 1 and {self.MAX_BATCH_SIZE}."
                )
                return None
            return batch_size_val
        except ValueError:
            messagebox.showerror(
                "Error", "Batch size must be a valid integer."
            )
            return None

    def _on_ok(self):
        """Handle OK button click."""
        try:
            config: Dict[str, Any] = {}

            # Validate and collect all configuration values
            thresh = self._validate_threshold()
            if thresh is None:
                return
            config["thresh"] = thresh

            scale = self._validate_scale()
            if scale is None:
                return
            if scale:
                config["scale"] = scale

            config["boxes"] = self.boxes_var.get()

            mask_scale = self._validate_mask_scale()
            if mask_scale is None:
                return
            config["mask_scale"] = mask_scale

            config["replacewith"] = self.replace_var.get()
            config["keep_audio"] = self.audio_var.get()
            config["keep_metadata"] = self.metadata_var.get()

            batch_size = self._validate_batch_size()
            if batch_size is None:
                return
            config["batch_size"] = batch_size

            # Store Hugging Face token separately (it's not part of sightline_config)
            # TODO: it IS part of sightline_config. Figure out whats happening here and fix/remove this.
            self.hugging_face_token = self.hf_token_entry.get().strip()

            self.result = config
            self.destroy()

        except Exception as e:
            logger.error(f"Error validating configuration: {e}")
            messagebox.showerror("Error", f"Error validating configuration: {str(e)}")

    def _on_cancel(self):
        """Handle Cancel button click."""
        self.result = None
        self.destroy()

    def _create_section_header(self, parent, text):
        """Create a section header."""
        header = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=16, weight="bold"))
        header.pack(anchor="w", padx=10, pady=(0, 10))
