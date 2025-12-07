"""Dialog for managing transcription models."""

import logging
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox
from typing import Any, Optional
import os
from pathlib import Path
from huggingface_hub import snapshot_download, login
from config_manager import get_models_path
import customtkinter as ctk

logger = logging.getLogger(__name__)

# Models that need to be downloaded
REQUIRED_MODELS = [
    "pyannote/voice-activity-detection",
    "pyannote/speaker-diarization-3.1",
    "pyannote/segmentation-3.0",
]

class ManageModelsDialog(ctk.CTkToplevel):
    """Dialog for managing transcription/diarization models and tokens."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.stop_download = False

        self.title("Manage Models")
        self.geometry("600x620")
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._center_on_parent()
        self.focus()

    def _center_on_parent(self):
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
        main_frame = ctk.CTkFrame(self, border_width=0)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(
            main_frame,
            text="Manage Transcription Models",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(0, 20))

        # Instructions
        info_text = (
            "Sightline uses open source models to perform speech-to-text and speaker diarization (who spoke when). While all processing is done locally one your machine, you need to download these models first.\n\n"
            "In order to do this, you need to download the models from a website called Hugging Face which is a community of AI researchers and engineers.\n\n"
            "The steps are as follows:\n"
            "1. Create a free account at huggingface.co\n"
            "2. Accept user conditions for 'pyannote/speaker-diarization-3.1' and 'pyannote/segmentation-3.0'\n"
            "3. Create a 'Read' access token in your settings"
            "4. Copy the token and paste it into the text box below sand save it"
            "5. Click the 'Download Models' button to download the models"
        )

        ctk.CTkLabel(
            main_frame,
            text=info_text,
            justify="left",
            wraplength=500
        ).pack(pady=(0, 10))

        # Link Button
        link_btn = ctk.CTkButton(
            main_frame,
            text="Open Hugging Face Token Settings",
            command=lambda: webbrowser.open("https://huggingface.co/settings/tokens"),
            fg_color="transparent",
            border_width=1,
            text_color=("blue", "lightblue")
        )
        link_btn.pack(pady=(0, 20))

        # Token Input
        token_frame = ctk.CTkFrame(main_frame, fg_color="transparent", border_width=0)
        token_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(token_frame, text="Hugging Face Token:").pack(anchor="w")

        token_input_frame = ctk.CTkFrame(token_frame, fg_color="transparent", border_width=0)
        token_input_frame.pack(fill="x", pady=(0, 0))

        # Layout: Token entry and Save button side by side
        self.token_entry = ctk.CTkEntry(token_input_frame, width=400)
        current_token = self.app.full_config.get("hugging_face_token", "") if hasattr(self.app, 'full_config') else ""
        self.token_entry.insert(0, current_token)
        self.token_entry.pack(side="left", fill="x", expand=True, pady=(5, 0))

        ctk.CTkButton(
            token_input_frame,
            text="Save Token",
            command=self._save_token,
            width=100
        ).pack(side="left", padx=10, pady=(5, 0))

        # Download Section
        download_frame = ctk.CTkFrame(main_frame)
        download_frame.pack(fill="x", pady=(0, 20), padx=5)

        ctk.CTkLabel(
            download_frame,
            text="Model Status",
            font=ctk.CTkFont(weight="bold")
        ).pack(pady=10)

        self.status_label = ctk.CTkLabel(download_frame, text="Checking status...")
        self.status_label.pack(pady=(0, 10))

        self.download_btn = ctk.CTkButton(
            download_frame,
            text="Download Models",
            command=self._start_download
        )
        self.download_btn.pack(pady=10)

        # Progress
        self.progress_bar = ctk.CTkProgressBar(download_frame)
        self.progress_bar.set(0)

        # Bottom Buttons
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent", border_width=0)
        btn_frame.pack(fill="x", side="bottom")

        ctk.CTkButton(
            btn_frame,
            text="Close",
            command=self._on_close,
            width=100
        ).pack(side="right")


        self._check_status()

    def _save_token(self):
        """Save the Hugging Face token to config."""
        token = self.token_entry.get().strip()
        if hasattr(self.app, 'full_config'):
            self.app.full_config["hugging_face_token"] = token
        else:
            # Fallback if full_config doesn't exist
            if not hasattr(self.app, 'full_config'):
                self.app.full_config = {}
            self.app.full_config["hugging_face_token"] = token
        self.app._save_config()
        messagebox.showinfo("Saved", "Token saved successfully!")
        self._check_status()

    def _check_status(self):
        """Check model and token status."""
        token = self.token_entry.get().strip()
        if not token:
            self.status_label.configure(
                text="Token missing. Please add token to download models.",
                text_color="orange"
            )
            self.download_btn.configure(state="disabled")
            return

        # Check if models exist on disk
        models_path = get_models_path()
        models_exist = self._check_models_exist(models_path)

        if models_exist:
            self.status_label.configure(
                text="✅ Models downloaded and ready!",
                text_color="green"
            )
            self.download_btn.configure(text="Re-download Models", state="normal")
        else:
            self.status_label.configure(
                text="Token present. Click 'Download Models' to download required models.",
                text_color="orange"
            )
            self.download_btn.configure(text="Download Models", state="normal")

    def _check_models_exist(self, models_path: Path) -> bool:
        """Check if required models exist on disk.

        Args:
            models_path: Path to the models directory.

        Returns:
            True if all required models exist, False otherwise.
        """
        for model_id in REQUIRED_MODELS:
            # Model ID format: "org/model-name"
            # HuggingFace stores models in: models_path/org--model-name
            model_name = model_id.replace("/", "--")
            model_dir = models_path / model_name
            if not model_dir.exists() or not any(model_dir.iterdir()):
                return False
        return True

    def _start_download(self):
        """Start downloading models in a background thread."""
        token = self.token_entry.get().strip()
        if not token:
            messagebox.showerror("Error", "Please enter a Hugging Face token first.")
            return

        self.download_btn.configure(state="disabled")
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)
        self.progress_bar.start()

        self.status_label.configure(
            text="Downloading models... This may take several minutes.",
            text_color="blue"
        )

        thread = threading.Thread(target=self._download_worker, args=(token,), daemon=True)
        thread.start()

    def _download_worker(self, token: str):
        """Download models in a background thread.

        Args:
            token: Hugging Face authentication token.
        """
        try:
            # Login with token
            login(token=token)

            models_path = get_models_path()
            total_models = len(REQUIRED_MODELS)

            for idx, model_id in enumerate(REQUIRED_MODELS):
                if self.stop_download:
                    self.after(0, lambda: self._on_download_complete(False, "Download cancelled"))
                    return

                # Update progress
                progress = (idx / total_models) * 0.9  # Reserve 10% for finalization
                self.after(0, lambda p=progress: self.progress_bar.set(p))

                # Update status
                self.after(0, lambda m=model_id: self.status_label.configure(
                    text=f"Downloading {m}...",
                    text_color="blue"
                ))

                # Download model
                snapshot_download(
                    repo_id=model_id,
                    local_dir=str(models_path / model_id.replace("/", "--")),
                    local_dir_use_symlinks=False,
                    token=token,
                )

            # Finalize
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self._on_download_complete(True))

        except Exception as e:
            logger.error(f"Error downloading models: {e}", exc_info=True)
            self.after(0, lambda: self._on_download_complete(False, str(e)))

    def _on_download_complete(self, success, error=None):
        """Handle download completion.

        Args:
            success: True if download succeeded, False otherwise.
            error: Error message if download failed.
        """
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.download_btn.configure(state="normal")
        self.stop_download = False

        if success:
            self.status_label.configure(
                text="✅ Models downloaded successfully!",
                text_color="green"
            )
            messagebox.showinfo("Success", "Models have been downloaded and are ready to use!")
            self._check_status()  # Refresh status
        else:
            self.status_label.configure(
                text=f"❌ Download failed: {error}",
                text_color="red"
            )
            messagebox.showerror("Error", f"Download failed: {error}")

    def _on_close(self):
        """Close the dialog."""
        self.stop_download = True
        self.destroy()
