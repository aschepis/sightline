"""PyInstaller spec for Deface GUI application.

This spec is responsible for bundling the GUI *and* a small, internal
`deface` CLI entry point so that end-users do not need to install
`deface` separately.
"""

from PyInstaller.utils.hooks import copy_metadata


app_name = "Deface"
bundle_id = "com.defaceapp.deface"
entry_script = "main.py"
cli_entry_script = "deface_cli_entry.py"
icon_file = "icon.png"

block_cipher = None

# Ensure package metadata is available at runtime for importlib.metadata,
# particularly for imageio which queries its own distribution metadata.
extra_datas = copy_metadata("imageio")


a = Analysis(
    [entry_script, cli_entry_script],
    pathex=[],
    binaries=[],
    datas=extra_datas,
    hiddenimports=["deface"],  # ensure deface Python package is collected
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

gui_exe = EXE(
    pyz,
    a.scripts,
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
#   macOS: Deface.app/Contents/MacOS/deface
#   Win/Linux: dist/Deface/deface(.exe)
cli_exe = EXE(
    pyz,
    [("deface_cli_entry", cli_entry_script, "PYSOURCE")],
    [],
    exclude_binaries=True,
    name="deface",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # CLI mode
)

# REQUIRED → collects libs, binaries, datas into a folder
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
