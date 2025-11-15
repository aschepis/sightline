"""PyInstaller spec for Deface GUI application.

This spec is responsible for bundling the GUI *and* a small, internal
`deface` CLI entry point so that end-users do not need to install
`deface` separately.
"""

from PyInstaller.utils.hooks import copy_metadata, collect_data_files


app_name = "Deface"
bundle_id = "com.defaceapp.deface"
entry_script = "main.py"
cli_entry_script = "deface_cli_entry.py"
icon_file = "icon.png"

block_cipher = None

# Ensure package metadata and data files are available at runtime.
# - imageio: needs distribution metadata for importlib.metadata.
# - deface: ships ONNX models (e.g. centerface.onnx) as package data.
extra_datas = copy_metadata("imageio")
deface_datas = collect_data_files("deface")


a = Analysis(
    [entry_script, cli_entry_script],
    pathex=[],
    binaries=[],
    datas=extra_datas + deface_datas,
    # Ensure the deface package and skimage internals used by it are collected.
    hiddenimports=[
        "deface",
        "skimage._shared.geometry",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
#   macOS: Deface.app/Contents/MacOS/deface-cli
#   Win/Linux: dist/Deface/deface-cli(.exe)
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
# but note that the GUI EXE is the one named "Deface", so it becomes the
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
