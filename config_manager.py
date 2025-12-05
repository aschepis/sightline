"""Configuration persistence manager for Sightline.

This module handles loading and saving application configuration to disk.
Uses platform-appropriate storage when possible, falls back to a JSON file
in the user's home directory.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Configuration file name (hidden file in home directory)
CONFIG_FILENAME = ".sightline.json"


def get_config_path() -> Path:
    """Get the path to the configuration file.

    Uses platform-appropriate storage when possible:
    - macOS: ~/Library/Application Support/sightline/config.json
    - Windows: %APPDATA%/sightline/config.json
    - Linux: ~/.config/sightline/config.json

    Falls back to ~/.sightline.json if platform-specific paths aren't available.

    Returns:
        Path to the configuration file.
    """
    home = Path.home()

    # Try platform-specific paths first
    if sys.platform == "darwin":  # macOS
        config_dir = home / "Library" / "Application Support" / "sightline"
        config_file = config_dir / "config.json"
    elif sys.platform == "win32":  # Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            config_dir = Path(appdata) / "sightline"
            config_file = config_dir / "config.json"
        else:
            # Fallback to home directory
            config_file = home / CONFIG_FILENAME
    else:  # Linux and other Unix-like systems
        config_dir = home / ".config" / "sightline"
        config_file = config_dir / "config.json"

    # Test if we can write to the platform-specific path
    try:
        # Try to create the directory if it doesn't exist
        if config_file.parent != home:
            config_file.parent.mkdir(parents=True, exist_ok=True)
        # Test if we can write to the directory
        test_file = config_file.parent / ".test_write"
        test_file.touch()
        test_file.unlink()
    except (OSError, PermissionError):
        # Fallback to home directory if platform-specific path isn't writable
        logger.debug(f"Could not use platform-specific config path, using fallback")
        config_file = home / CONFIG_FILENAME

    return config_file


def get_legacy_config_path() -> Path:
    """Get the path to the legacy configuration file (deface-app).

    Returns:
        Path to the legacy configuration file.
    """
    home = Path.home()

    # Try platform-specific paths first
    if sys.platform == "darwin":  # macOS
        config_dir = home / "Library" / "Application Support" / "deface-app"
        config_file = config_dir / "config.json"
    elif sys.platform == "win32":  # Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            config_dir = Path(appdata) / "deface-app"
            config_file = config_dir / "config.json"
        else:
            # Fallback to home directory
            config_file = home / ".deface-app.json"
    else:  # Linux and other Unix-like systems
        config_dir = home / ".config" / "deface-app"
        config_file = config_dir / "config.json"

    return config_file


def load_config() -> Dict[str, Any]:
    """Load configuration from disk.

    Returns:
        Dictionary containing configuration. Returns default configuration
        if file doesn't exist or cannot be read.
    """
    config_path = get_config_path()

    if not config_path.exists():
        # Check for legacy config
        legacy_path = get_legacy_config_path()
        if legacy_path.exists():
            logger.info(f"Found legacy configuration at: {legacy_path}")
            config_path = legacy_path
        else:
            logger.debug(f"Config file does not exist: {config_path}")
            return get_default_config()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config: Dict[str, Any] = json.load(f)
        logger.info(f"Loaded configuration from: {config_path}")
        return config
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning(f"Error loading config from {config_path}: {e}")
        logger.info("Using default configuration")
        return get_default_config()


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to disk.

    Args:
        config: Dictionary containing configuration to save.

    Returns:
        True if configuration was saved successfully, False otherwise.
    """
    config_path = get_config_path()

    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Write configuration to file
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved configuration to: {config_path}")
        return True
    except (IOError, OSError) as e:
        logger.error(f"Error saving config to {config_path}: {e}")
        return False


def get_models_path() -> Path:
    """Get the path where transcription models should be stored.

    Uses platform-appropriate storage:
    - macOS: ~/Library/Application Support/sightline/models
    - Windows: %APPDATA%/sightline/models
    - Linux: ~/.config/sightline/models

    Returns:
        Path to the models directory.
    """
    home = Path.home()

    # Use platform-specific paths
    if sys.platform == "darwin":  # macOS
        models_dir = home / "Library" / "Application Support" / "sightline" / "models"
    elif sys.platform == "win32":  # Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            models_dir = Path(appdata) / "sightline" / "models"
        else:
            models_dir = home / ".sightline" / "models"
    else:  # Linux and other Unix-like systems
        models_dir = home / ".config" / "sightline" / "models"

    # Create directory if it doesn't exist
    try:
        models_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        logger.warning(f"Could not create models directory {models_dir}: {e}")
        # Fallback to home directory
        models_dir = home / ".sightline" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

    return models_dir


def get_default_config() -> Dict[str, Any]:
    """Get default configuration values.

    Returns:
        Dictionary containing default configuration.
    """
    return {
        "deface_config": {
            "thresh": 0.2,
            "scale": None,
            "boxes": False,
            "mask_scale": 1.3,
            "replacewith": "blur",
            "keep_audio": True,
            "keep_metadata": True,
            "batch_size": 1,
        },
        "hugging_face_token": "",
        "output_directory": None,  # Will default to Desktop on first run
        "face_smudge_config": {
            "blur_radius": 50,
            "blur_sigma": 25,
            "cache_size": 100,
            "playback_speed": 1.0,
        },
    }

