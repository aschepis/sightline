"""PyInstaller spec for Sightline GUI application.

This spec is responsible for bundling the GUI *and* a small, internal
`deface` CLI entry point so that end-users do not need to install
`deface` separately.
"""

import sys
import os
import importlib.util
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files, collect_submodules, get_package_paths


def filter_large_files(datas, max_size_mb=10, allow_package_models=True):
    """Filter out large files that shouldn't be included in the distribution.

    This prevents including cached model files, large data files, etc.
    that can bloat the installer size. Models are downloaded at runtime,
    so we don't need to bundle cached model files.

    Args:
        datas: List of (source, dest) tuples from collect_data_files
        max_size_mb: Maximum file size in MB to include (default: 10MB)
        allow_package_models: If True, allow small model files from package data
                             (like deface's ONNX models). If False, exclude all model files.

    Returns:
        Filtered list of (source, dest) tuples
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    filtered = []
    excluded_count = 0
    excluded_size = 0

    # Patterns to exclude regardless of size (cache directories, etc.)
    exclude_patterns = [
        '__pycache__',
        '.pyc',
        '.pyo',
        '.pyd',
        '.cache',
        '.git',
        '__MACOSX',
        '.DS_Store',
        'model_cache',
        'hub_cache',
        'transformers_cache',
        'huggingface',  # Hugging Face cache directories
        '.huggingface',
    ]

    # File extensions that are typically large model files downloaded at runtime
    # Note: Small ONNX files from deface package data are allowed if allow_package_models=True
    large_model_extensions = ['.bin', '.safetensors', '.pt', '.pth', '.ckpt']

    # Always exclude large ONNX files (these are runtime-downloaded models)
    # Small ONNX files (< 10MB) from package data (like deface) are allowed
    onnx_max_size = 10 * 1024 * 1024  # 10MB for ONNX files

    for source, dest in datas:
        source_path = Path(source) if isinstance(source, str) else source

        # Skip if path contains excluded patterns
        if any(pattern in str(source_path) for pattern in exclude_patterns):
            excluded_count += 1
            continue

        # Handle model files specially
        file_ext = source_path.suffix.lower()

        # Always exclude large model file types (these are runtime-downloaded)
        if file_ext in large_model_extensions:
            try:
                if source_path.is_file():
                    size = source_path.stat().st_size
                    if size > max_size_bytes:
                        excluded_count += 1
                        excluded_size += size
                        continue
            except (OSError, AttributeError):
                pass

        # For ONNX files: exclude if large (runtime models) but allow small ones (package data)
        if file_ext == '.onnx':
            try:
                if source_path.is_file():
                    size = source_path.stat().st_size
                    # Exclude large ONNX files (these are runtime-downloaded models)
                    if size > onnx_max_size:
                        excluded_count += 1
                        excluded_size += size
                        continue
            except (OSError, AttributeError):
                pass

        # Skip any files larger than max_size_mb
        try:
            if source_path.is_file():
                size = source_path.stat().st_size
                if size > max_size_bytes:
                    excluded_count += 1
                    excluded_size += size
                    continue
        except (OSError, AttributeError):
            # If we can't check size, include it to be safe
            pass

        filtered.append((source, dest))

    if excluded_count > 0:
        excluded_mb = excluded_size / (1024 * 1024)
        print(f"✓ Filtered out {excluded_count} large files ({excluded_mb:.1f} MB)")

    return filtered


app_name = "Sightline"
bundle_id = "com.adamschepis.sightline"
entry_script = "main.py"
cli_entry_script = "deface_cli_entry.py"
# Use .icns for macOS, .ico for Windows, .png for Linux
icon_file = "icon.icns" if sys.platform == "darwin" else ("icon.ico" if sys.platform == "win32" else "icon.png")

block_cipher = None

# Ensure package metadata and data files are available at runtime.
# - imageio: needs distribution metadata for importlib.metadata.
# - deface: ships ONNX models (e.g. centerface.onnx) as package data.
#   These are small and needed, so we don't filter them.
extra_datas = copy_metadata("imageio")
deface_datas = collect_data_files("deface")  # Small ONNX models, keep all

# Collect data for lightning and lightning_fabric to resolve missing version.info issues
# These are dependencies of whisperx/pyannote.audio
lightning_datas = collect_data_files("lightning")
lightning_metadata = copy_metadata("lightning")

lightning_fabric_datas = collect_data_files("lightning_fabric")
lightning_fabric_metadata = copy_metadata("lightning_fabric")

# Collect data for transformers (dependency of whisperx)
# This helps ensure transformers is properly bundled
# Filter out large model cache files
transformers_datas_raw = collect_data_files("transformers")
transformers_datas = filter_large_files(transformers_datas_raw, max_size_mb=10)
transformers_metadata = copy_metadata("transformers")

# Collect submodules for pyannote and whisperx to ensure all parts are included
pyannote_hidden = collect_submodules("pyannote")
whisperx_hidden = collect_submodules("whisperx")

# Collect data for whisperx
# Filter out large model files (whisperx models should be downloaded at runtime)
whisperx_datas_raw = collect_data_files("whisperx")
whisperx_datas = filter_large_files(whisperx_datas_raw, max_size_mb=10)

# Collect ALL data for speechbrain (dependency of pyannote.audio)
# We manually collect source files and exclude it from PYZ to ensure
# dynamic discovery and inspect.getsource() work correctly.
speechbrain_datas = []
speechbrain_metadata = copy_metadata("speechbrain")

try:
    # get_package_paths returns (base_dir, package_dir)
    _, sb_pkg_dir = get_package_paths('speechbrain')

    # Walk the directory and collect ALL files (including .py)
    # But exclude large model files and cache directories
    for root, dirs, files in os.walk(sb_pkg_dir):
        # Skip cache directories
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.cache', 'cache', 'model_cache']]

        for f in files:
            full_path = os.path.join(root, f)
            # Calculate relative path to preserve structure in bundle
            # e.g. site-packages/speechbrain/utils/foo.py -> speechbrain/utils
            rel_dir = os.path.relpath(root, os.path.dirname(sb_pkg_dir))
            speechbrain_datas.append((full_path, rel_dir))

    # Filter out large files from speechbrain
    speechbrain_datas = filter_large_files(speechbrain_datas, max_size_mb=10)
    print(f"✓ Added speechbrain source files to datas ({len(speechbrain_datas)} files)")
except Exception as e:
    print(f"✗ Failed to collect speechbrain source files: {e}")

print(f"✓ Speechbrain datas: {len(speechbrain_datas)} files collected")
print(f"✓ Speechbrain metadata: {speechbrain_metadata}")

# Collect Tcl/Tk library files for tkinter
tcl_tk_datas = []
if sys.platform == 'darwin':
    # Find Tcl/Tk libraries from Python prefix (macOS)
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
elif sys.platform == 'win32':
    # Find Tcl/Tk libraries from Python prefix (Windows/Conda)
    # Conda on Windows puts Tcl/Tk in Library/lib or tcl subdirectories
    tcl_candidates = [
        Path(sys.prefix) / 'Library' / 'lib' / 'tcl8.6',
        Path(sys.prefix) / 'tcl' / 'tcl8.6',
        Path(sys.prefix) / 'lib' / 'tcl8.6',
        Path(sys.base_prefix) / 'Library' / 'lib' / 'tcl8.6',
        Path(sys.base_prefix) / 'tcl' / 'tcl8.6',
    ]
    tk_candidates = [
        Path(sys.prefix) / 'Library' / 'lib' / 'tk8.6',
        Path(sys.prefix) / 'tcl' / 'tk8.6',
        Path(sys.prefix) / 'lib' / 'tk8.6',
        Path(sys.base_prefix) / 'Library' / 'lib' / 'tk8.6',
        Path(sys.base_prefix) / 'tcl' / 'tk8.6',
    ]

    tcl_lib = None
    for candidate in tcl_candidates:
        if candidate.exists() and (candidate / 'init.tcl').exists():
            tcl_lib = candidate
            break

    tk_lib = None
    for candidate in tk_candidates:
        if candidate.exists() and (candidate / 'tk.tcl').exists():
            tk_lib = candidate
            break

    if tcl_lib:
        tcl_tk_datas.append((str(tcl_lib), '_tcl_data'))
        print(f"✓ Found Tcl library at: {tcl_lib}")
    else:
        print(f"✗ Tcl library not found in any candidate location")

    if tk_lib:
        tcl_tk_datas.append((str(tk_lib), '_tk_data'))
        print(f"✓ Found Tk library at: {tk_lib}")
    else:
        print(f"✗ Tk library not found in any candidate location")

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

# Collect customtkinter data files (themes, assets, etc.)
# This is needed for the default "blue" theme fallback
customtkinter_datas = collect_data_files("customtkinter")
print(f"✓ Collected {len(customtkinter_datas)} customtkinter data files")

a = Analysis(
    [entry_script, cli_entry_script],
    pathex=[],
    binaries=[],
    datas=extra_datas + deface_datas + lightning_datas + lightning_metadata + lightning_fabric_datas + lightning_fabric_metadata + transformers_datas + transformers_metadata + whisperx_datas + speechbrain_datas + speechbrain_metadata + icon_files + theme_files + flaticons_files + customtkinter_datas + tcl_tk_datas,
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
        "pyannote.audio.models",
        "transformers",
        "transformers.utils.auto_docstring",
    ] + pyannote_hidden + whisperx_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_tkinter.py', 'pyi_rth_transformers.py', 'pyi_rth_tqdm.py'],
    excludes=['speechbrain'],
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
    icon=icon_file if sys.platform in ("win32", "darwin") else None,  # Embed icon for Windows and macOS
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

# Create symlink for speechbrain in Frameworks directory (if needed)
# speechbrain's find_imports looks in Frameworks/, but PyInstaller puts it in Resources/
# Remove invalid symlinks that may be created by PyInstaller or other processes
if sys.platform == 'darwin':
    app_bundle_path = Path(f"dist/{app_name}.app")
    frameworks_path = app_bundle_path / "Contents" / "Frameworks"
    resources_path = app_bundle_path / "Contents" / "Resources"

    if frameworks_path.exists():
        # Remove invalid symlinks in Frameworks (tk and tcl - these shouldn't exist)
        # Remove ALL tk/tcl symlinks regardless of whether they're broken, as they shouldn't be in Frameworks
        for invalid_name in ["tk", "tcl"]:
            invalid_path = frameworks_path / invalid_name
            if invalid_path.exists():
                if invalid_path.is_symlink():
                    invalid_path.unlink()
                    print(f"✓ Removed symlink: {invalid_path}")
                elif invalid_path.is_dir():
                    # If it's a directory, it might be a leftover - but be careful not to remove actual needed dirs
                    # Only remove if it's empty or clearly not needed
                    try:
                        if not any(invalid_path.iterdir()):
                            invalid_path.rmdir()
                            print(f"✓ Removed empty directory: {invalid_path}")
                    except Exception:
                        pass

        # Only create speechbrain symlink if speechbrain exists in Resources
        if resources_path.exists():
            speechbrain_src = resources_path / "speechbrain"
            speechbrain_dst = frameworks_path / "speechbrain"
            if speechbrain_src.exists() and speechbrain_src.is_dir():
                # Remove existing symlink if present
                if speechbrain_dst.exists() and speechbrain_dst.is_symlink():
                    speechbrain_dst.unlink()
                # Create symlink only if destination doesn't already exist as a directory
                if not speechbrain_dst.exists():
                    # Use relative path from Frameworks to Resources/speechbrain
                    speechbrain_dst.symlink_to("../Resources/speechbrain")
                    print(f"✓ Created speechbrain symlink in Frameworks directory")

    # Remove invalid self-referential symlink in speechbrain (if created by PyInstaller)
    if resources_path.exists():
        speechbrain_self_link = resources_path / "speechbrain" / "speechbrain"
        if speechbrain_self_link.exists() and speechbrain_self_link.is_symlink():
            try:
                target = speechbrain_self_link.readlink()
                # Check if it's self-referential
                if str(target) == "." or str(target) == "speechbrain" or "speechbrain" in str(target):
                    speechbrain_self_link.unlink()
                    print(f"✓ Removed self-referential symlink: {speechbrain_self_link}")
            except Exception:
                speechbrain_self_link.unlink()
                print(f"✓ Removed broken symlink: {speechbrain_self_link}")
