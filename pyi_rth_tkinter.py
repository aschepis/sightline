"""PyInstaller runtime hook for tkinter/Tcl initialization.

This hook ensures that Tcl/Tk can find its initialization files when
the application is bundled with PyInstaller.
"""

import os
import sys

# Set TCL/TK library paths for bundled application
if hasattr(sys, '_MEIPASS'):
    # Running in PyInstaller bundle
    os.environ['TCL_LIBRARY'] = os.path.join(sys._MEIPASS, 'tcl')
    os.environ['TK_LIBRARY'] = os.path.join(sys._MEIPASS, 'tk')
