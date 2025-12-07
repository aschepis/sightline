"""Base view class for all application pages.

This module provides a base class that all view/page classes should inherit from,
ensuring consistent behavior and interface across the application.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter is required for views")

logger = logging.getLogger(__name__)


class BaseView(ctk.CTkFrame, ABC):
    """Base class for all application views/pages.

    All views should inherit from this class and implement the required methods.
    This ensures consistent behavior and makes it easy to add new pages.
    """

    def __init__(self, parent: ctk.CTk, app: Any):
        """Initialize the base view.

        Args:
            parent: The parent widget (typically the main application window).
            app: Reference to the main application instance for accessing shared state.
        """
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.parent = parent

    @abstractmethod
    def create_widgets(self) -> None:
        """Create and layout all widgets for this view.

        This method should be implemented by subclasses to set up their UI.
        """
        pass

    def show(self) -> None:
        """Show this view (pack it into the parent)."""
        self.pack(fill="both", expand=True)
        self.update_idletasks()
        self.lift()

    def hide(self) -> None:
        """Hide this view (remove it from the parent)."""
        self.pack_forget()

    def cleanup(self) -> None:
        """Clean up resources when the view is being removed.

        Override this method in subclasses to perform cleanup operations
        (e.g., cancel background tasks, close connections, etc.).
        """
        pass

