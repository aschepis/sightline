"""Home view for the Sightline application.

The home view is the default view that is shown when the application is launched.
"""

import logging
import sys
import tkinter.messagebox as messagebox
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from typing import Any
from views.base_view import BaseView

logger = logging.getLogger(__name__)


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
        # Running in development mode - use parent directory of this file's parent
        # (views/ -> project root)
        base_path = Path(__file__).parent.parent.absolute()

    return str(Path(base_path) / relative_path)


class HomeView(BaseView):
    """Home view for the Sightline application."""

    def __init__(self, parent: ctk.CTk, app: Any):
        super().__init__(parent, app)
        self.create_widgets()

    def create_widgets(self):
        """Create and layout all GUI widgets."""
        # Main container with rounded border appearance
        main_frame = ctk.CTkFrame(self, corner_radius=15)
        main_frame.pack(fill="both", expand=True)

        # Title section
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(pady=(30, 10))

        # Title "Sightline"
        title_label = ctk.CTkLabel(
            title_frame,
            text="Sightline",
            font=ctk.CTkFont(size=36, weight="bold"),
        )
        title_label.pack()

        # Double underline effect (using two separator lines) - Sightline brand accent color
        underline1 = ctk.CTkFrame(
            title_frame, height=2, fg_color="#00a6ff"
        )
        underline1.pack(fill="x", padx=50, pady=(5, 0))
        underline2 = ctk.CTkFrame(
            title_frame, height=2, fg_color="#00a6ff"
        )
        underline2.pack(fill="x", padx=50, pady=(2, 0))

        # Container for heading and buttons (grouped together, doesn't expand)
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(pady=(40, 0))

        # "Choose a Task" heading
        task_heading = ctk.CTkLabel(
            content_frame,
            text="Choose a Task",
            font=ctk.CTkFont(size=24, weight="normal"),
        )
        task_heading.pack(pady=(0, 30))

        # Task buttons container (centered)
        buttons_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        buttons_frame.pack(pady=(0, 20), padx=40)

        # Inner container to center the buttons horizontally
        buttons_inner = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        buttons_inner.pack()

        # Three task buttons in a row - square and fixed size
        button_size = 150  # Square buttons (width = height)

        # Load icons from flaticon for buttons
        deface_icon = ctk.CTkImage(
            light_image=Image.open(get_resource_path("flaticons/png/002-blind.png")),
            dark_image=Image.open(get_resource_path("flaticons/png/002-blind.png")),
            size=(60, 60)
        )
        smudge_icon = ctk.CTkImage(
            light_image=Image.open(get_resource_path("flaticons/png/001-paint-brush.png")),
            dark_image=Image.open(get_resource_path("flaticons/png/001-paint-brush.png")),
        )
        transcribe_icon = ctk.CTkImage(
            light_image=Image.open(get_resource_path("flaticons/png/007-speech-to-text.png")),
            dark_image=Image.open(get_resource_path("flaticons/png/007-speech-to-text.png")),
            size=(60, 60)
        )

        # Configure grid columns for centering
        buttons_inner.grid_columnconfigure(0, weight=1)
        buttons_inner.grid_columnconfigure(1, weight=0)
        buttons_inner.grid_columnconfigure(2, weight=0)
        buttons_inner.grid_columnconfigure(3, weight=0)
        buttons_inner.grid_columnconfigure(4, weight=1)

        # Deface button - wrapped in fixed-size frame
        deface_frame = ctk.CTkFrame(buttons_inner, fg_color="transparent", width=button_size, height=button_size)
        deface_frame.grid(row=0, column=1, padx=15)
        deface_frame.grid_propagate(False)  # Prevent frame from resizing
        deface_button = ctk.CTkButton(
            deface_frame,
            text="Blur Faces",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=button_size,
            height=button_size,
            corner_radius=15,
            image=deface_icon,
            compound="top",
            command=self._on_deface_clicked,
        )
        deface_button.pack(fill="both", expand=True)

        # Smudge button - wrapped in fixed-size frame
        smudge_frame = ctk.CTkFrame(buttons_inner, fg_color="transparent", width=button_size, height=button_size)
        smudge_frame.grid(row=0, column=2, padx=15)
        smudge_frame.grid_propagate(False)  # Prevent frame from resizing
        smudge_button = ctk.CTkButton(
            smudge_frame,
            text="Manual Smudge",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=button_size,
            height=button_size,
            corner_radius=15,
            image=smudge_icon,
            compound="top",
            command=self._on_smudge_clicked,
        )
        smudge_button.pack(fill="both", expand=True)

        # Transcribe button - wrapped in fixed-size frame
        transcribe_frame = ctk.CTkFrame(buttons_inner, fg_color="transparent", width=button_size, height=button_size)
        transcribe_frame.grid(row=0, column=3, padx=15)
        transcribe_frame.grid_propagate(False)  # Prevent frame from resizing
        transcribe_button = ctk.CTkButton(
            transcribe_frame,
            text="Transcribe Audio",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=button_size,
            height=button_size,
            corner_radius=15,
            image=transcribe_icon,
            compound="top",
            command=self._on_transcribe_clicked,
        )
        transcribe_button.pack(fill="both", expand=True)

        # Settings gear icon button in upper right corner
        settings_button = ctk.CTkButton(
            main_frame,
            text="⚙︎",
            font=ctk.CTkFont(size=32),
            width=40,
            height=40,
            command=self._on_settings_clicked,
            fg_color="transparent",
            text_color="#8ea4c7",  # Mist Blue for secondary text
            hover_color="#00a6ff",  # Accent color on hover
            hover=True,
        )
        settings_button.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=20)

        # Info icon button in upper right corner
        info_button = ctk.CTkButton(
            main_frame,
            text="ℹ︎",
            font=ctk.CTkFont(size=32),
            width=40,
            height=40,
            command=self._on_info_clicked,
            fg_color="transparent",
            text_color="#8ea4c7",  # Mist Blue for secondary text
            hover_color="#00a6ff",  # Accent color on hover
            hover=True,
        )
        info_button.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)


    def _on_deface_clicked(self):
        """Handle Deface button click - navigate to batch processing view."""
        if hasattr(self.app, "show_view"):
            self.app.show_view("batch_processing")

    def _on_smudge_clicked(self):
        """Handle Smudge button click - open Face Smudge window."""
        if hasattr(self.app, "_open_face_smudge"):
            self.app._open_face_smudge()
        elif hasattr(self.app, "open_face_smudge"):
            self.app.open_face_smudge()

    def _on_transcribe_clicked(self):
        """Handle Transcribe button click."""
        # TODO: Implement transcribe functionality
        # For now, show a placeholder message
        messagebox.showinfo("Transcribe", "Transcribe feature coming soon!")

    def _on_settings_clicked(self):
        """Handle Settings button click - open settings dialog."""
        try:
            from dialogs import ConfigDialog
            dialog = ConfigDialog(self.app, self.app.config)
            self.app.wait_window(dialog)

            if dialog.result is not None:
                self.app.config = dialog.result
                if hasattr(self.app, "_save_config"):
                    self.app._save_config()
        except Exception as e:
            logger.error(f"Error opening settings dialog: {e}", exc_info=True)
            messagebox.showerror("Error", f"Could not open settings:\n{str(e)}\n\nType: {type(e).__name__}")

    def _on_info_clicked(self):
        """Handle Info button click - open info and attribution dialog."""
        try:
            from dialogs import InfoDialog
            dialog = InfoDialog(self.app)
            self.app.wait_window(dialog)
        except Exception as e:
            logger.error(f"Error opening info dialog: {e}", exc_info=True)
            messagebox.showerror("Error", f"Could not open info:\n{str(e)}\n\nType: {type(e).__name__}")
