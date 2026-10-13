"""
Configuration and dynamic path management for Fate/Grand Order Arcade Launcher.
Provides centralized path resolution that adapts dynamically to any installation directory.
"""

import os
from pathlib import Path
from typing import Optional

ROOT_PATH_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fgoa-launcher" / "root_path"


def find_game_root(base: Path) -> Optional[Path]:
    """Return the directory containing App/ago.exe inside base."""
    if not base or not base.is_dir():
        return None
    if (base / "App" / "ago.exe").is_file():
        return base.resolve()
    for child in sorted(base.iterdir()):
        if child.is_dir():
            if (child / "App" / "ago.exe").is_file():
                return child.resolve()
            for sub in sorted(child.iterdir()):
                if sub.is_dir() and (sub / "App" / "ago.exe").is_file():
                    return sub.resolve()
    try:
        for p in base.rglob("ago.exe"):
            if p.is_file() and p.parent.name.lower() == "app":
                return p.parent.parent.resolve()
    except Exception:
        pass
    return None


def get_fgoa_root() -> Path:
    """
    Resolve the root directory of the FGO Arcade installation.
    Precedence:
    1. FGOA_ROOT environment variable (if it contains App/ago.exe)
    2. Saved ~/.config/fgoa-launcher/root_path
    3. Current working directory or launcher parent directories
    """
    env_root = os.environ.get("FGOA_ROOT")
    if env_root:
        found = find_game_root(Path(env_root))
        if found:
            return found

    saved_root = Path(ROOT_PATH_CONFIG.read_text(encoding="utf-8").strip()) if ROOT_PATH_CONFIG.is_file() else None
    launcher_root = Path(__file__).resolve().parent.parent.parent
    cwd = Path.cwd().resolve()

    for c in (saved_root, cwd, launcher_root, launcher_root.parent,
              launcher_root.parent / "FGOA", launcher_root.parent / "fgoa", launcher_root.parent / "FGO_Arcade"):
        if c and (c / "App" / "ago.exe").is_file():
            return c.resolve()
    for c in (saved_root, cwd, launcher_root):
        if c and (c / "App").is_dir():
            return c.resolve()
    return launcher_root


def resolve_card_dir(root: Path) -> Path:
    p_1151 = root / "DEVICE" / "print" / "FGO11_51_AllServants"
    if p_1151.is_dir():
        return p_1151
    return root / "DEVICE" / "print" / "FGO11_AllServants"


def set_fgoa_root(root: Path) -> None:
    """Persist and update global FGOA root path variables."""
    global FGOA_ROOT_PATH, FGOA_ROOT, APP_DIR, SERVER_DIR, DEVICE_DIR, CARD_DIR
    global LOADOUTS_DIR, DECK_FILE, CARD_FILTERS_FILE, CONFIG_INI, SERVER_CONFIG_YAML
    FGOA_ROOT_PATH = root.resolve()
    FGOA_ROOT = str(FGOA_ROOT_PATH)
    os.environ["FGOA_ROOT"] = FGOA_ROOT
    ROOT_PATH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    ROOT_PATH_CONFIG.write_text(f"{FGOA_ROOT}\n", encoding="utf-8")

    APP_DIR = str(FGOA_ROOT_PATH / "App")
    SERVER_DIR = str(FGOA_ROOT_PATH / "Server")
    DEVICE_DIR = str(FGOA_ROOT_PATH / "DEVICE")
    CARD_DIR = str(resolve_card_dir(FGOA_ROOT_PATH))
    LOADOUTS_DIR = str(FGOA_ROOT_PATH / "App" / "deck-loadouts")
    DECK_FILE = str(FGOA_ROOT_PATH / "App" / "deck.json")
    CARD_FILTERS_FILE = str(FGOA_ROOT_PATH / "App" / "card_filters.json")
    CONFIG_INI = str(FGOA_ROOT_PATH / "App" / "segatools.ini")
    SERVER_CONFIG_YAML = str(FGOA_ROOT_PATH / "Server" / "artemis" / "config" / "core.yaml")


# Dynamic Root Path
FGOA_ROOT_PATH: Path = get_fgoa_root()
FGOA_ROOT: str = str(FGOA_ROOT_PATH)

# Common Subdirectories
APP_DIR = str(FGOA_ROOT_PATH / "App")
SERVER_DIR = str(FGOA_ROOT_PATH / "Server")
DEVICE_DIR = str(FGOA_ROOT_PATH / "DEVICE")
CARD_DIR = str(resolve_card_dir(FGOA_ROOT_PATH))
LAUNCHER_DIR = str(Path(__file__).resolve().parent.parent)
LOADOUTS_DIR = str(FGOA_ROOT_PATH / "App" / "deck-loadouts")
DECK_FILE = str(FGOA_ROOT_PATH / "App" / "deck.json")
CARD_FILTERS_FILE = str(FGOA_ROOT_PATH / "App" / "card_filters.json")
CONFIG_INI = str(FGOA_ROOT_PATH / "App" / "segatools.ini")
SERVER_CONFIG_YAML = str(FGOA_ROOT_PATH / "Server" / "artemis" / "config" / "core.yaml")
