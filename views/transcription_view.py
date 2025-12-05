"""Audio transcription batch processing view for the Sightline application.

This module contains the UI and logic for batch processing audio/video files for transcription.
"""

import logging
import os
import time
import threading
import traceback
from pathlib import Path
import pyannote.audio
from typing import Any, Dict
import customtkinter as ctk
import typing, collections
import torch, omegaconf, whisperx
from whisperx.diarize import DiarizationPipeline
from whisperx.utils import get_writer


from views.generic_batch_view import GenericBatchView
from views.dialogs import ManageModelsDialog

logger = logging.getLogger(__name__)

# Supported file extensions for transcription
SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".m4a",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
    ".m4p",
    ".m4v",
}


class TranscriptionView(GenericBatchView):
    """View for batch processing files for audio transcription."""

    def __init__(self, parent: ctk.CTk, app: Any):
        """Initialize the transcription batch processing view.

        Args:
            parent: The parent widget (main application window).
            app: Reference to the main application instance.
        """
        super().__init__(
            parent=parent,
            app=app,
            page_title="T R A N S C R I B E   A U D I O",
            supported_extensions=SUPPORTED_EXTENSIONS,
            generate_output_filename=self._generate_output_filename,
        )

    def _generate_output_filename(self, input_path: str) -> str:
        """Generate output filename for transcription.

        Args:
            input_path: Path to the input file.

        Returns:
            Output filename with .txt extension.
        """
        input_filename = os.path.basename(input_path)
        name, ext = os.path.splitext(input_filename)
        return f"{name}_transcription.txt"

    def _create_custom_widgets(self, parent: ctk.CTkFrame) -> None:
        """Create custom widgets in the left panel."""

        # Spacer
        ctk.CTkLabel(parent, text="", height=20).pack()

        warning_text = (
            "NOTE: Progress tracking for transcription and diarization is not yet implemented."
        )
        ctk.CTkLabel(
            parent,
            text=warning_text,
            text_color="orange",
            font=ctk.CTkFont(size=11, slant="italic"),
            wraplength=260,
            justify="left"
        ).pack(fill="x", pady=(5, 10))

        ctk.CTkLabel(parent, text="", height=20).pack()


        # Models Section
        ctk.CTkLabel(
            parent,
            text="Models & Setup",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        # Status Alert
        self.model_status_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.model_status_frame.pack(fill="x", pady=5)

        self.model_alert_label = ctk.CTkLabel(
            self.model_status_frame,
            text="⚠️ Models missing",
            text_color="orange",
            font=ctk.CTkFont(size=12)
        )
        self.model_alert_label.pack(anchor="w")

        # Manage Models Button
        ctk.CTkButton(
            parent,
            text="Manage Models",
            command=self._open_manage_models_dialog,
            fg_color="#3b8ed0",
            hover_color="#36719f"
        ).pack(fill="x", pady=10)

        self._check_models_status()

    def _check_models_status(self):
        """Check if models/token are configured and update UI."""
        from config_manager import get_models_path

        token = ""
        if hasattr(self.app, 'full_config'):
            token = self.app.full_config.get("hugging_face_token", "")

        if not token:
            self.model_alert_label.configure(text="⚠️ Token missing", text_color="orange")
            return

        # Check if models exist on disk
        models_path = get_models_path()
        from views.dialogs.manage_models_dialog import REQUIRED_MODELS

        models_exist = True
        for model_id in REQUIRED_MODELS:
            model_name = model_id.replace("/", "--")
            model_dir = models_path / model_name
            if not model_dir.exists() or not any(model_dir.iterdir()):
                models_exist = False
                break

        if models_exist:
            self.model_alert_label.configure(text="✅ Ready", text_color="green")
        else:
            self.model_alert_label.configure(text="⚠️ Models missing", text_color="orange")

    def _open_manage_models_dialog(self):
        """Open the Manage Models dialog."""
        dialog = ManageModelsDialog(self.app, self.app)
        self.app.wait_window(dialog)
        # Refresh status after dialog closes
        self._check_models_status()

    def _process_file(self, file_info: Dict[str, Any]):
        """Process a single file for transcription using WhisperX.

        Args:
            file_info: Dictionary containing file information.
        """
        file_path = file_info["path"]
        output_path = file_info["output_path"]

        logger.info(f"Processing file for transcription: {file_path}")

        # Update status to processing
        file_info["status"] = "processing"
        file_info["progress"] = 0.0
        file_info["error_log"] = ""
        file_info["parser"] = self._create_progress_parser()
        self.output_queue.put(("file_update", file_path))

        try:
            import whisperx

            # Get Hugging Face token
            token = ""
            if hasattr(self.app, 'full_config'):
                token = self.app.full_config.get("hugging_face_token", "")

            if not token:
                raise ValueError(
                    "Hugging Face token is required for diarization. "
                    "Please set it in the Manage Models dialog."
                )

            # Update progress: Loading model (10%)
            file_info["progress"] = 0.1
            self.output_queue.put(("file_update", file_path))
            logger.info("Loading WhisperX model...")

            # Load WhisperX model
            import torch

            # PyTorch 2.6+ requires explicit allowlisting of classes used in pickled models.
            # WhisperX models internally use torch.load() which needs these safe globals.
            # We use add_safe_globals (not context manager) because whisperx.load_model
            # makes internal torch.load calls that we can't wrap.
            safe_globals = self._get_whisperx_safe_globals()
            torch.serialization.add_safe_globals(safe_globals)

            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "float32"

            model = whisperx.load_model("base", device, compute_type=compute_type)

            # Update progress: Loading audio (20%)
            file_info["progress"] = 0.2
            self.output_queue.put(("file_update", file_path))
            logger.info("Loading audio file...")

            # Load audio
            audio = whisperx.load_audio(file_path)

            # Update progress: Transcribing (30%)
            file_info["progress"] = 0.3
            self.output_queue.put(("file_update", file_path))
            logger.info("Transcribing audio...")

            # Transcribe
            result = model.transcribe(audio, batch_size=16)

            # Preserve language for later use (it may be lost in subsequent processing steps)
            detected_language = result.get("language", "en")

            # Update progress: Aligning (50%)
            file_info["progress"] = 0.5
            self.output_queue.put(("file_update", file_path))
            logger.info("Aligning timestamps...")

            # Align timestamps
            model_a, metadata = whisperx.load_align_model(
                language_code=detected_language, device=device
            )
            result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)

            # Update progress: Diarizing (70%)
            file_info["progress"] = 0.7
            self.output_queue.put(("file_update", file_path))
            logger.info("Performing speaker diarization...")

            # Diarize
            from config_manager import get_models_path
            from whisperx.diarize import DiarizationPipeline

            models_path = get_models_path()

            diarize_model = DiarizationPipeline(
                use_auth_token=token,
                device=device,
            )
            diarize_segments = diarize_model(audio)

            # Update progress: Assigning speakers (85%)
            file_info["progress"] = 0.85
            self.output_queue.put(("file_update", file_path))
            logger.info("Assigning speakers to segments...")

            # Assign speakers to segments
            result = whisperx.assign_word_speakers(diarize_segments, result)

            # Ensure language key is present in result (it may have been lost during processing)
            if "language" not in result:
                result["language"] = detected_language

            # Update progress: Writing output (95%)
            file_info["progress"] = 0.95
            self.output_queue.put(("file_update", file_path))
            logger.info("Writing output file...")

            # Write output file
            output_dir = os.path.dirname(output_path)
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            logger.info(f"Writing output file to: {output_path}")

            writer = get_writer("all", output_dir=output_dir)
            writer(result, file=output_path, options={
                "max_line_width": 1000,
                "max_line_count": 1000,
                "highlight_words": True,
            })

            pretty_output_path = os.path.splitext(output_path)[0] + "_pretty.txt"
            self._write_transcription_output(result, pretty_output_path, file_path)

            # Update progress: Complete (100%)
            file_info["progress"] = 1.0
            file_info["status"] = "success"
            logger.info(f"Successfully processed: {file_path}")
            self.output_queue.put(("file_update", file_path))

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}", exc_info=True)
            file_info["status"] = "failed"
            file_info["progress"] = 0.0
            # Include full stack trace in error log
            error_trace = traceback.format_exc()
            file_info["error_log"] += f"\nException: {str(e)}\n\nFull traceback:\n{error_trace}"
            self.output_queue.put(("file_update", file_path))
            if file_path in self.currently_processing:
                self.currently_processing.remove(file_path)

    def _write_transcription_output(self, result: Dict, output_path: str, input_path: str):
        """Write transcription results to output file.

        Args:
            result: WhisperX transcription result dictionary.
            output_path: Path to write the output file.
            input_path: Path to the input file (for metadata).
        """
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Transcription for: {os.path.basename(input_path)}\n")
            f.write(f"Language: {result.get('language', 'en')}\n")
            f.write("=" * 60 + "\n\n")

            # Write segments with speaker labels
            for segment in result.get("segments", []):
                start = segment.get("start", 0)
                end = segment.get("end", 0)
                speaker = segment.get("speaker", "Unknown")
                text = segment.get("text", "").strip()

                if text:
                    f.write(f"{start:.2f}–{end:.2f}  {speaker}: {text}\n")

            # If no segments with speakers, write plain text
            if not result.get("segments"):
                f.write(result.get("text", "No transcription available."))

    @staticmethod
    def _get_whisperx_safe_globals():
        """Get the list of safe globals needed for WhisperX model loading.

        PyTorch 2.6+ requires explicit allowlisting of classes/functions used in
        pickled models. WhisperX models use OmegaConf and standard Python types
        that need to be explicitly allowed.

        Returns:
            List of classes/functions to allow for safe unpickling.
        """
        return [
            # Pyannote types
            pyannote.audio.core.model.Introspection,
            pyannote.audio.core.task.Specifications,
            pyannote.audio.core.task.Problem,
            pyannote.audio.core.task.Resolution,
            # PyTorch types
            torch.torch_version.TorchVersion,
            # OmegaConf types
            omegaconf.listconfig.ListConfig,
            omegaconf.dictconfig.DictConfig,
            omegaconf.base.ContainerMetadata,
            omegaconf.base.Metadata,
            omegaconf.nodes.AnyNode,
            # Python types
            typing.Any,
            list,
            dict,
            collections.defaultdict,
            set,
            tuple,
            str,
            int,
            float,
            bool,
            bytes,
            type(None)
        ]
