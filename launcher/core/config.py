"""
Configuration and dynamic path management for Fate/Grand Order Arcade Launcher.
Provides centralized path resolution that adapts dynamically to any installation directory.
"""

import os
from pathlib import Path

def get_fgoa_root() -> Path:
    """
    Resolve the root directory of the FGO Arcade installation.
    Precedence:
    1. FGOA_ROOT environment variable (if set and exists)
    2. Parent directory of the launcher package (two levels up from this file)
    3. Current working directory fallback
    """
    env_root = os.environ.get("FGOA_ROOT")
    if env_root and os.path.isdir(env_root):
        return Path(env_root).resolve()

    # launcher/core/config.py -> launcher/core -> launcher -> root
    launcher_root = Path(__file__).resolve().parent.parent.parent
    if (launcher_root / "App" / "ago.exe").is_file():
        return launcher_root

    # If running from a standalone overlay repo, check adjacent game directories
    for candidate in [
        launcher_root.parent / "FGOA",
        launcher_root.parent / "fgoa",
        launcher_root.parent / "FGO_Arcade",
    ]:
        if (candidate / "App" / "ago.exe").is_file():
            return candidate.resolve()

    if (launcher_root / "App").is_dir() or (launcher_root / "launcher").is_dir():
        return launcher_root

    cwd = Path.cwd().resolve()
    if (cwd / "App" / "ago.exe").is_file():
        return cwd
    if (cwd / "App").is_dir() or (cwd / "launcher").is_dir():
        return cwd

    return launcher_root

# Dynamic Root Path
FGOA_ROOT_PATH: Path = get_fgoa_root()
FGOA_ROOT: str = str(FGOA_ROOT_PATH)

# Common Subdirectories
APP_DIR = str(FGOA_ROOT_PATH / "App")
SERVER_DIR = str(FGOA_ROOT_PATH / "Server")
DEVICE_DIR = str(FGOA_ROOT_PATH / "DEVICE")
LAUNCHER_DIR = str(FGOA_ROOT_PATH / "launcher")
LOADOUTS_DIR = str(FGOA_ROOT_PATH / "App" / "deck-loadouts")
DECK_FILE = str(FGOA_ROOT_PATH / "App" / "deck.json")
CARD_FILTERS_FILE = str(FGOA_ROOT_PATH / "App" / "card_filters.json")
CONFIG_INI = str(FGOA_ROOT_PATH / "App" / "segatools.ini")
SERVER_CONFIG_YAML = str(FGOA_ROOT_PATH / "Server" / "artemis" / "config" / "core.yaml")
