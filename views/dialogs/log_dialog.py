"""Log dialog for displaying error logs."""

import logging
import sys
import tkinter as tk
from typing import Optional

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter is required for dialog windows")

logger = logging.getLogger(__name__)


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
        main_frame = ctk.CTkFrame(self, border_width=0, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(
            main_frame,
            text="Error Logs",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(pady=(0, 10))

        log_textbox = ctk.CTkTextbox(
            main_frame,
            font=("Courier", 11),
            wrap="word",
        )
        log_textbox.pack(fill="both", expand=True, pady=(0, 10))
        log_textbox.insert("1.0", log_text)
        log_textbox.configure(state="disabled")

        button_frame = ctk.CTkFrame(main_frame, border_width=0, fg_color="transparent")
        button_frame.pack(fill="x")

        close_btn = ctk.CTkButton(
            button_frame,
            text="Close",
            command=self.destroy,
            width=100,
        )
        close_btn.pack(side="right", padx=10)

        self.bind("<Escape>", lambda e: self.destroy())

