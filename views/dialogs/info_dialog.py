"""Info dialog for Sightline."""

import importlib
import logging
import sys
import webbrowser

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


class InfoDialog(ctk.CTkToplevel):
    """Info dialog for Sightline."""

    # Uicons by <a href="https://www.flaticon.com/uicons">Flaticon</a>

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Info")
        self.geometry("600x600")
        self.resizable(False, False)

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

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
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # App title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Sightline",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(pady=(0, 5))

        # Version
        version_label = ctk.CTkLabel(
            main_frame,
            text=f"Version {_get_version()}",
            font=ctk.CTkFont(size=14),
            text_color="#8ea4c7",  # Mist Blue
        )
        version_label.pack(pady=(0, 20))

        # Creator section
        creator_frame = ctk.CTkFrame(main_frame)
        creator_frame.pack(fill="x", pady=(0, 10))

        creator_label = ctk.CTkLabel(
            creator_frame,
            text="Created by Adam Schepis",
            font=ctk.CTkFont(size=12),
        )
        creator_label.pack(anchor="w", padx=10, pady=(10, 5))

        website_button = ctk.CTkButton(
            creator_frame,
            text="https://linktr.ee/aschepis",
            command=lambda: webbrowser.open("https://linktr.ee/aschepis"),
            fg_color="transparent",
            text_color=("blue", "light blue"),
            hover_color=("light gray", "dark gray"),
            anchor="w",
            width=200,
        )
        website_button.pack(anchor="w", padx=10, pady=(0, 10))

        # Attributions section
        attributions_label = ctk.CTkLabel(
            main_frame,
            text="Attributions",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        attributions_label.pack(anchor="w", pady=(10, 5))

        # Scrollable text area for attributions
        attributions_textbox = ctk.CTkTextbox(
            main_frame,
            font=ctk.CTkFont(size=11),
            wrap="word",
        )
        attributions_textbox.pack(fill="both", expand=True, pady=(0, 10))

        # Build attributions text
        attributions_text = """Icons
Uicons by Flaticon
https://www.flaticon.com/uicons

Libraries
• deface - Face detection and blurring library
  https://github.com/ORB-HD/deface

• CustomTkinter - Modern GUI framework
  https://github.com/TomSchimansky/CustomTkinter

• tkinterdnd2 - Drag and drop support
  https://github.com/pmgagne/tkinterdnd2

• OpenCV - Computer vision library
  https://opencv.org/

• NumPy - Numerical computing
  https://numpy.org/

• Pillow - Image processing
  https://python-pillow.org/"""

        attributions_textbox.insert("1.0", attributions_text)
        attributions_textbox.configure(state="disabled")

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

        # Bind keyboard shortcuts
        self.bind("<Escape>", lambda e: self.destroy())

