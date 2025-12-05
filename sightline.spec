"""PyInstaller spec for Sightline GUI application.

This spec is responsible for bundling the GUI *and* a small, internal
`deface` CLI entry point so that end-users do not need to install
`deface` separately.
"""

import sys
import os
import importlib.util
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files


app_name = "Sightline"
bundle_id = "com.sightlineapp.sightline"
entry_script = "main.py"
cli_entry_script = "deface_cli_entry.py"
# Use .icns for macOS, .png for other platforms
icon_file = "icon.icns" if sys.platform == "darwin" else "icon.png"

block_cipher = None

# Ensure package metadata and data files are available at runtime.
# - imageio: needs distribution metadata for importlib.metadata.
# - deface: ships ONNX models (e.g. centerface.onnx) as package data.
extra_datas = copy_metadata("imageio")
deface_datas = collect_data_files("deface")

# Collect data for lightning and lightning_fabric to resolve missing version.info issues
# These are dependencies of whisperx/pyannote.audio
lightning_datas = collect_data_files("lightning")
lightning_metadata = copy_metadata("lightning")

lightning_fabric_datas = collect_data_files("lightning_fabric")
lightning_fabric_metadata = copy_metadata("lightning_fabric")

# Explicitly check for version.info which is often missed
# spec = importlib.util.find_spec("lightning_fabric")
# if spec and spec.origin:
#     pkg_path = Path(spec.origin).parent
#     version_file = pkg_path / "version.info"
#     if version_file.exists():
#         found = False
#         for src, dest in lightning_fabric_datas:
#             if os.path.abspath(src) == os.path.abspath(str(version_file)):
#                 found = True
#                 break

#         if not found:
#             print(f"Explicitly adding lightning_fabric/version.info: {version_file}")
#             # Target _internal/lightning_fabric since PyInstaller 6 puts packages there
#             lightning_fabric_datas.append((str(version_file), "_internal/lightning_fabric"))

# Collect Tcl/Tk library files for tkinter
tcl_tk_datas = []
if sys.platform == 'darwin':
    # Find Tcl/Tk libraries from Python prefix
    tcl_lib = Path(sys.prefix) / 'lib' / 'tcl8.6'
    tk_lib = Path(sys.prefix) / 'lib' / 'tk8.6'

    if tcl_lib.exists():
        tcl_tk_datas.append((str(tcl_lib), 'tcl'))
        print(f"✓ Found Tcl library at: {tcl_lib}")
    else:
        print(f"✗ Tcl library not found at: {tcl_lib}")

    if tk_lib.exists():
        tcl_tk_datas.append((str(tk_lib), 'tk'))
        print(f"✓ Found Tk library at: {tk_lib}")
    else:
        print(f"✗ Tk library not found at: {tk_lib}")

# Include both icon files for cross-platform support
icon_files = [("icon.icns", '.'), ("icon.png", '.')] if sys.platform == "darwin" else [("icon.png", '.'), ("icon.ico", '.')]

# Include theme file
theme_file = Path("sightline_theme.json")
theme_files = [(str(theme_file), '.')] if theme_file.exists() else []

# Include flaticons directory for button icons
flaticons_dir = Path("flaticons")
flaticons_files = []
if flaticons_dir.exists():
    # Include the entire flaticons directory structure
    for png_file in (flaticons_dir / "png").glob("*.png"):
        flaticons_files.append((str(png_file), "flaticons/png"))
    # Also include license if present
    license_file = flaticons_dir / "license" / "license.html"
    if license_file.exists():
        flaticons_files.append((str(license_file), "flaticons/license"))

a = Analysis(
    [entry_script, cli_entry_script],
    pathex=[],
    binaries=[],
    datas=extra_datas + deface_datas + lightning_datas + lightning_metadata + lightning_fabric_datas + lightning_fabric_metadata + icon_files + theme_files + flaticons_files + tcl_tk_datas,
    hiddenimports=[
        "deface",
        "skimage._shared.geometry",
        "views.dialogs",
        "config_manager",
        "progress_parser",
        "tkinter",
        "_tkinter",
        "lightning",
        "lightning_fabric",
        "whisperx",
        "whisperx.asr",
        "whisperx.diarize",
        "whisperx.utils",
        "whisperx.align",
        "whisperx.load",
        "pyannote.audio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_tkinter.py'],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

gui_exe = EXE(
    pyz,
    # IMPORTANT: only the GUI entry script should be used as the main
    # executable. Including `deface_cli_entry.py` here would cause the
    # CLI to become the primary entry point of the app bundle.
    [("main", entry_script, "PYSOURCE")],
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI mode
)

# Standalone CLI executable that runs the deface library from the bundled
# Python runtime. This will typically live next to the GUI binary, e.g.:
#   macOS: Sightline.app/Contents/MacOS/deface-cli
#   Win/Linux: dist/Sightline/deface-cli(.exe)
cli_exe = EXE(
    pyz,
    [("deface_cli_entry", cli_entry_script, "PYSOURCE")],
    [],
    exclude_binaries=True,
    # IMPORTANT: use a distinct name from the GUI executable, especially on
    # case-insensitive filesystems (Deface vs deface collide there).
    name="deface-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # CLI mode
)

# OPTIONAL → one-folder layout (for CLI + debug use)
coll = COLLECT(
    gui_exe,
    cli_exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    a.zipped_data,
    strip=False,
    upx=False,
    name=app_name,
)

# macOS .app bundle build
# Use the full collected bundle (so libpython and all deps are present),
# but note that the GUI EXE is the one named "Sightline", so it becomes the
# CFBundleExecutable for the .app.
app = BUNDLE(
    coll,
    name=f"{app_name}.app",
    icon=icon_file,
    bundle_identifier=bundle_id,
    info_plist={
        "CFBundleDisplayName": app_name,
        "CFBundleIdentifier": bundle_id,
        "CFBundleName": app_name,
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
    },
)
