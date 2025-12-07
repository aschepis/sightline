"""PyInstaller runtime hook for tkinter/Tcl initialization.

This hook ensures that Tcl/Tk can find its initialization files when
the application is bundled with PyInstaller.

This runs BEFORE the main script, setting environment variables that
tkinter needs to find its initialization files.
"""

import os
import sys

# Debug mode - set to True to write debug info to a file
_DEBUG = os.environ.get('SIGHTLINE_TCL_DEBUG', '').lower() in ('1', 'true', 'yes')


def _debug_log(msg):
    """Write debug message to file if debug mode is enabled."""
    if _DEBUG:
        try:
            log_path = os.path.join(os.path.dirname(sys.executable), 'tcl_debug.log')
            with open(log_path, 'a') as f:
                f.write(msg + '\n')
        except Exception:
            pass


def _find_tcl_tk_paths():
    """Find Tcl/Tk library paths in the bundled application.
    
    PyInstaller versions may place these files in different locations:
    - PyInstaller 6.x: _internal/_tcl_data, _internal/_tk_data (Windows/Linux)
    - PyInstaller 5.x: _tcl_data, _tk_data directly in meipass
    - Older versions: tcl, tk
    - macOS: lib/tcl8.6, lib/tk8.6 or Resources/tcl, Resources/tk
    """
    if not hasattr(sys, '_MEIPASS'):
        _debug_log("Not running from PyInstaller bundle")
        return None, None
    
    meipass = sys._MEIPASS
    _debug_log(f"_MEIPASS = {meipass}")
    
    # Get the executable directory (where Sightline.exe lives)
    exe_dir = os.path.dirname(sys.executable)
    _debug_log(f"exe_dir = {exe_dir}")
    
    # Build list of candidate paths to search
    # Use os.path for more reliable Windows path handling
    candidates_tcl = []
    candidates_tk = []
    
    # PyInstaller 6.x typically has _MEIPASS pointing to _internal folder
    # The _tcl_data and _tk_data are inside _internal
    candidates_tcl.extend([
        os.path.join(meipass, '_tcl_data'),
        os.path.join(meipass, 'tcl'),
        os.path.join(meipass, 'tcl8.6'),
    ])
    candidates_tk.extend([
        os.path.join(meipass, '_tk_data'),
        os.path.join(meipass, 'tk'),
        os.path.join(meipass, 'tk8.6'),
    ])
    
    # Also check relative to exe directory (in case _MEIPASS is different)
    internal_dir = os.path.join(exe_dir, '_internal')
    candidates_tcl.extend([
        os.path.join(internal_dir, '_tcl_data'),
        os.path.join(internal_dir, 'tcl'),
        os.path.join(exe_dir, '_tcl_data'),
        os.path.join(exe_dir, 'tcl'),
    ])
    candidates_tk.extend([
        os.path.join(internal_dir, '_tk_data'),
        os.path.join(internal_dir, 'tk'),
        os.path.join(exe_dir, '_tk_data'),
        os.path.join(exe_dir, 'tk'),
    ])
    
    # macOS specific paths
    if sys.platform == 'darwin':
        if 'Contents/MacOS' in meipass:
            contents_dir = os.path.dirname(meipass)
            candidates_tcl.extend([
                os.path.join(contents_dir, 'lib', 'tcl8.6'),
                os.path.join(contents_dir, 'Resources', 'tcl'),
                os.path.join(contents_dir, 'Resources', '_tcl_data'),
            ])
            candidates_tk.extend([
                os.path.join(contents_dir, 'lib', 'tk8.6'),
                os.path.join(contents_dir, 'Resources', 'tk'),
                os.path.join(contents_dir, 'Resources', '_tk_data'),
            ])
    
    tcl_path = None
    tk_path = None
    
    # Find Tcl
    for candidate in candidates_tcl:
        init_tcl = os.path.join(candidate, 'init.tcl')
        _debug_log(f"Checking Tcl: {candidate} (init.tcl exists: {os.path.isfile(init_tcl)})")
        if os.path.isfile(init_tcl):
            tcl_path = candidate
            _debug_log(f"Found Tcl at: {tcl_path}")
            break
    
    # Find Tk
    for candidate in candidates_tk:
        tk_tcl = os.path.join(candidate, 'tk.tcl')
        _debug_log(f"Checking Tk: {candidate} (tk.tcl exists: {os.path.isfile(tk_tcl)})")
        if os.path.isfile(tk_tcl):
            tk_path = candidate
            _debug_log(f"Found Tk at: {tk_path}")
            break
    
    # Fallback: recursively search for init.tcl
    if tcl_path is None:
        _debug_log("Tcl not found in candidates, searching recursively...")
        for search_root in [meipass, exe_dir]:
            for root, dirs, files in os.walk(search_root):
                if 'init.tcl' in files:
                    tcl_path = root
                    _debug_log(f"Found Tcl via search at: {tcl_path}")
                    break
            if tcl_path:
                break
    
    if tk_path is None:
        _debug_log("Tk not found in candidates, searching recursively...")
        for search_root in [meipass, exe_dir]:
            for root, dirs, files in os.walk(search_root):
                if 'tk.tcl' in files:
                    tk_path = root
                    _debug_log(f"Found Tk via search at: {tk_path}")
                    break
            if tk_path:
                break
    
    return tcl_path, tk_path


# Set TCL/TK library paths IMMEDIATELY when this hook loads
# This must happen before any tkinter import

# Always write a marker file to verify the hook is running
try:
    marker_path = os.path.join(os.path.dirname(sys.executable), 'tcl_hook_ran.txt')
    with open(marker_path, 'w') as f:
        f.write(f"Runtime hook executed\n")
        f.write(f"sys.executable = {sys.executable}\n")
        f.write(f"_MEIPASS = {getattr(sys, '_MEIPASS', 'N/A')}\n")
except Exception as e:
    pass  # Ignore errors writing marker

_debug_log("="*50)
_debug_log("pyi_rth_tkinter.py runtime hook starting")
_debug_log(f"sys.executable = {sys.executable}")
_debug_log(f"sys.platform = {sys.platform}")

tcl_path, tk_path = _find_tcl_tk_paths()

if tcl_path:
    os.environ['TCL_LIBRARY'] = tcl_path
    _debug_log(f"Set TCL_LIBRARY = {tcl_path}")
else:
    _debug_log("WARNING: Could not find Tcl library!")

if tk_path:
    os.environ['TK_LIBRARY'] = tk_path
    _debug_log(f"Set TK_LIBRARY = {tk_path}")
else:
    _debug_log("WARNING: Could not find Tk library!")

_debug_log("Runtime hook complete")
_debug_log("="*50)
