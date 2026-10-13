"""
Controls Manager for SegaTools / Fate/Grand Order Arcade.
Handles reading, writing, and keycode translation for App/segatools.ini.
"""

import os
import re
from typing import Dict, Optional, Tuple
from launcher.core.config import CONFIG_INI, DEVICE_DIR


# ==============================================================================
# Windows Virtual-Key (VK) Definitions and Bidirectional Mappings
# ==============================================================================

VK_MAP: Dict[int, str] = {
    0x01: "Left Click",
    0x02: "Right Click",
    0x04: "Middle Click",
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x13: "Pause",
    0x14: "Caps Lock",
    0x1B: "Esc",
    0x20: "Space",
    0x21: "Page Up",
    0x22: "Page Down",
    0x23: "End",
    0x24: "Home",
    0x25: "Left Arrow",
    0x26: "Up Arrow",
    0x27: "Right Arrow",
    0x28: "Down Arrow",
    0x2D: "Insert",
    0x2E: "Delete",
    **{0x30 + i: str(i) for i in range(10)},
    **{0x41 + i: chr(65 + i) for i in range(26)},
    **{0x60 + i: f"Num {i}" for i in range(10)},
    0x6A: "Num *",
    0x6B: "Num +",
    0x6D: "Num -",
    0x6E: "Num .",
    0x6F: "Num /",
    **{0x70 + i: f"F{i + 1}" for i in range(12)},
    0xA0: "Left Shift",
    0xA1: "Right Shift",
    0xA2: "Left Ctrl",
    0xA3: "Right Ctrl",
    0xA4: "Left Alt",
    0xA5: "Right Alt",
    0xBA: ";",
    0xBB: "=",
    0xBC: ",",
    0xBD: "-",
    0xBE: ".",
    0xBF: "/",
    0xC0: "`",
    0xDB: "[",
    0xDC: "\\",
    0xDD: "]",
    0xDE: "'",
}

QT_SPECIAL_KEYS = {
    0x01000000: "0x1B",  # Escape
    0x01000001: "0x9",   # Tab
    0x01000004: "0xD",   # Return
    0x01000005: "0xD",   # Enter
    0x01000003: "0x8",   # Backspace
    0x01000006: "0x2D",  # Insert
    0x01000007: "0x2E",  # Delete
    0x01000010: "0x24",  # Home
    0x01000011: "0x23",  # End
    0x01000012: "0x25",  # Left
    0x01000013: "0x26",  # Up
    0x01000014: "0x27",  # Right
    0x01000015: "0x28",  # Down
    0x01000016: "0x21",  # PageUp
    0x01000017: "0x22",  # PageDown
    0x01000020: "0xA0",  # Shift
    0x01000021: "0xA2",  # Control
    0x01000023: "0xA4",  # Alt
    0x01000024: "0x14",  # CapsLock
}


def parse_vk_code(val: str | int) -> int:
    """Parse integer or hex string (e.g. '0x57' or '87') into integer VK code."""
    return int(str(val).strip(), 0)


def vk_to_display_name(val: str | int) -> str:
    """Format a VK code as a human-friendly display name (e.g. 0x57 -> 'W')."""
    try:
        code = parse_vk_code(val)
        return VK_MAP.get(code, f"0x{code:X}")
    except Exception:
        return str(val)


def qt_key_to_vk(key: int, mouse_button: Optional[int] = None) -> Optional[str]:
    """Convert a Qt Key or MouseButton to a Windows Virtual-Key hex string (e.g. '0x57')."""
    if mouse_button in (1, 2, 4):
        return f"0x{mouse_button:X}"
    if 0x20 <= key <= 0x5A:
        return f"0x{key:X}"
    if 0x01000030 <= key <= 0x0100003B:
        return f"0x{0x70 + (key - 0x01000030):X}"
    return QT_SPECIAL_KEYS.get(key)


DEFAULT_CONTROLS: Dict[str, str | int] = {
    "mode": "keyboard",  # "keyboard" or "xinput"
    "up": "0x57",       # W
    "down": "0x53",     # S
    "left": "0x41",     # A
    "right": "0x44",    # D
    "attack": "0x2",    # Right Mouse Button
    "dash": "0xA0",     # Left Shift
    "target": "0x46",   # F
    "np": "0x20",       # Spacebar
    "camera": "0x43",   # C
    "coin": "0x72",     # F3
    "service": "0x71",  # F2
    "test": "0x70",     # F1
    "scan": "0xD",      # Enter / Return
    "controllerIndex": 0,
    "stickDeadzone": 7849,
    "rumble": 1,
    "rumbleStrength": 70,
}

INI_SECTIONS = {
    "io4": ("mode", "coin", "service", "test"),
    "aime": ("scan",),
    "keyboard": ("up", "down", "left", "right", "attack", "dash", "target", "np", "camera"),
    "xinput": ("controllerIndex", "stickDeadzone", "rumble", "rumbleStrength"),
}


def get_segatools_ini_path() -> str:
    """Return the path to App/segatools.ini."""
    return CONFIG_INI


def get_runtime_ini_path() -> str:
    """Return the path to DEVICE/runtime/segatools.runtime.ini if it exists."""
    return os.path.join(DEVICE_DIR, "runtime", "segatools.runtime.ini")


def _get_ini_key_value(text: str, section: str, key: str, default: str) -> str:
    """Extract a key value from a specific section in INI text."""
    sec_match = re.search(rf"(?ms)^\[{re.escape(section)}\]\s*$(.*?)(?=^\[|\Z)", text)
    if not sec_match:
        return default
    key_match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*([^;\r\n]+)", sec_match.group(1))
    return key_match.group(1).strip() if key_match else default


def _set_ini_key_value(text: str, section: str, key: str, value: str) -> str:
    """Replace or append a key=value pair within a given section in INI text."""
    sec_match = re.search(rf"(?ms)^\[{re.escape(section)}\]\s*$(.*?)(?=^\[|\Z)", text)
    if not sec_match:
        return text.rstrip() + f"\n\n[{section}]\n{key}={value}\n"

    body = sec_match.group(1)
    key_pattern = rf"(?m)^(\s*{re.escape(key)}\s*=).*$"
    new_body = re.sub(key_pattern, rf"\g<1>{value}", body) if re.search(key_pattern, body) else f"{key}={value}\n" + body
    return text[: sec_match.start(1)] + new_body + text[sec_match.end(1) :]


def load_controls_config(ini_path: Optional[str] = None) -> Dict[str, str | int]:
    """Read current control bindings from segatools.ini."""
    path = ini_path or get_segatools_ini_path()
    res = dict(DEFAULT_CONTROLS)
    if not os.path.isfile(path):
        return res

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        for section, keys in INI_SECTIONS.items():
            for key in keys:
                raw = _get_ini_key_value(text, section, key, str(DEFAULT_CONTROLS[key]))
                if section == "xinput":
                    try:
                        res[key] = int(raw)
                    except ValueError:
                        pass
                else:
                    res[key] = raw.lower() if key == "mode" else raw
    except Exception:
        pass
    return res


def save_controls_config(controls: Dict[str, str | int], ini_path: Optional[str] = None) -> Tuple[bool, str]:
    """Write updated control bindings to segatools.ini and runtime ini."""
    targets = [ini_path or get_segatools_ini_path()]
    runtime_path = get_runtime_ini_path()
    if os.path.isfile(runtime_path) and runtime_path not in targets:
        targets.append(runtime_path)

    saved_count = 0
    errors = []

    for path in targets:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for section, keys in INI_SECTIONS.items():
                for key in keys:
                    if key in controls:
                        text = _set_ini_key_value(text, section, key, str(controls[key]))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            saved_count += 1
        except Exception as e:
            errors.append(f"{os.path.basename(path)}: {e}")

    if errors:
        return False, "; ".join(errors)
    if saved_count == 0:
        return False, "segatools.ini was not found to save."
    return True, f"Controls successfully saved to {saved_count} file(s)."
