"""
Controls Manager for SegaTools / Fate/Grand Order Arcade.
Handles reading, writing, and keycode translation for App/segatools.ini.
"""

import os
import re
from typing import Dict, Optional, Tuple

try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from .config import FGOA_ROOT


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
    # 0 - 9
    0x30: "0",
    0x31: "1",
    0x32: "2",
    0x33: "3",
    0x34: "4",
    0x35: "5",
    0x36: "6",
    0x37: "7",
    0x38: "8",
    0x39: "9",
    # A - Z
    0x41: "A",
    0x42: "B",
    0x43: "C",
    0x44: "D",
    0x45: "E",
    0x46: "F",
    0x47: "G",
    0x48: "H",
    0x49: "I",
    0x4A: "J",
    0x4B: "K",
    0x4C: "L",
    0x4D: "M",
    0x4E: "N",
    0x4F: "O",
    0x50: "P",
    0x51: "Q",
    0x52: "R",
    0x53: "S",
    0x54: "T",
    0x55: "U",
    0x56: "V",
    0x57: "W",
    0x58: "X",
    0x59: "Y",
    0x5A: "Z",
    # Numpad
    0x60: "Num 0",
    0x61: "Num 1",
    0x62: "Num 2",
    0x63: "Num 3",
    0x64: "Num 4",
    0x65: "Num 5",
    0x66: "Num 6",
    0x67: "Num 7",
    0x68: "Num 8",
    0x69: "Num 9",
    0x6A: "Num *",
    0x6B: "Num +",
    0x6D: "Num -",
    0x6E: "Num .",
    0x6F: "Num /",
    # Function Keys
    0x70: "F1",
    0x71: "F2",
    0x72: "F3",
    0x73: "F4",
    0x74: "F5",
    0x75: "F6",
    0x76: "F7",
    0x77: "F8",
    0x78: "F9",
    0x79: "F10",
    0x7A: "F11",
    0x7B: "F12",
    # Left/Right Modifiers
    0xA0: "Left Shift",
    0xA1: "Right Shift",
    0xA2: "Left Ctrl",
    0xA3: "Right Ctrl",
    0xA4: "Left Alt",
    0xA5: "Right Alt",
    # OEM punctuation
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

NAME_TO_VK: Dict[str, str] = {name.upper(): f"0x{vk:X}" for vk, name in VK_MAP.items()}


def parse_vk_code(val: str) -> int:
    """Parse integer or hex string (e.g. '0x57' or '87') into integer VK code."""
    val = str(val).strip()
    if val.lower().startswith("0x"):
        return int(val, 16)
    return int(val)


def vk_to_display_name(val: str | int) -> str:
    """Format a VK code as a human-friendly display name (e.g. 0x57 -> 'W')."""
    try:
        if isinstance(val, str):
            code = parse_vk_code(val)
        else:
            code = int(val)
        if code in VK_MAP:
            return VK_MAP[code]
        return f"0x{code:X}"
    except Exception:
        return str(val)


def qt_key_to_vk(key: int, mouse_button: Optional[int] = None) -> Optional[str]:
    """Convert a Qt Key or MouseButton to a Windows Virtual-Key hex string (e.g. '0x57')."""
    if mouse_button == 1:  # Qt.MouseButton.LeftButton
        return "0x1"
    if mouse_button == 2:  # Qt.MouseButton.RightButton
        return "0x2"
    if mouse_button == 4:  # Qt.MouseButton.MiddleButton
        return "0x4"

    # Qt.Key ascii mapping (0x20..0x5A match VK codes)
    if 0x20 <= key <= 0x5A:
        return f"0x{key:X}"

    # Function keys (Qt.Key_F1 = 0x01000030 -> VK_F1 = 0x70)
    if 0x01000030 <= key <= 0x0100003B:
        f_num = key - 0x01000030
        return f"0x{0x70 + f_num:X}"

    # Special Qt keys
    qt_specials = {
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
    return qt_specials.get(key)


DEFAULT_CONTROLS: Dict[str, str | int] = {
    # Mode
    "mode": "keyboard",  # "keyboard" or "xinput"
    # Movement (Keyboard)
    "up": "0x57",       # W
    "down": "0x53",     # S
    "left": "0x41",     # A
    "right": "0x44",    # D
    # Actions (Keyboard)
    "attack": "0x2",    # Right Mouse Button
    "dash": "0xA0",     # Left Shift
    "target": "0x46",   # F
    "np": "0x20",       # Spacebar
    "camera": "0x43",   # C
    # Cabinet & System
    "coin": "0x72",     # F3
    "service": "0x71",  # F2
    "test": "0x70",     # F1
    "scan": "0xD",      # Enter / Return
    # Gamepad (XInput)
    "controllerIndex": 0,
    "stickDeadzone": 7849,
    "rumble": 1,
    "rumbleStrength": 70,
}


def get_segatools_ini_path() -> str:
    """Return the path to App/segatools.ini."""
    return os.path.join(FGOA_ROOT, "App", "segatools.ini")


def get_runtime_ini_path() -> str:
    """Return the path to DEVICE/runtime/segatools.runtime.ini if it exists."""
    return os.path.join(FGOA_ROOT, "DEVICE", "runtime", "segatools.runtime.ini")


def _get_ini_key_value(text: str, section: str, key: str, default: str) -> str:
    """Extract a key value from a specific section in INI text."""
    sec_pattern = rf"(?ms)^\[{re.escape(section)}\]\s*$(.*?)(?=^\[|\Z)"
    sec_match = re.search(sec_pattern, text)
    if not sec_match:
        return default
    body = sec_match.group(1)
    key_match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*([^;\r\n]+)", body)
    if key_match:
        return key_match.group(1).strip()
    return default


def _set_ini_key_value(text: str, section: str, key: str, value: str) -> str:
    """Replace or append a key=value pair within a given section in INI text."""
    sec_pattern = rf"(?ms)^\[{re.escape(section)}\]\s*$(.*?)(?=^\[|\Z)"
    sec_match = re.search(sec_pattern, text)
    if not sec_match:
        text = text.rstrip() + f"\n\n[{section}]\n{key}={value}\n"
        return text

    body = sec_match.group(1)
    key_pattern = rf"(?m)^(\s*{re.escape(key)}\s*=).*$"
    if re.search(key_pattern, body):
        new_body = re.sub(key_pattern, rf"\g<1>{value}", body)
    else:
        new_body = f"{key}={value}\n" + body

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

        # [io4]
        res["mode"] = _get_ini_key_value(text, "io4", "mode", "keyboard").lower()
        res["coin"] = _get_ini_key_value(text, "io4", "coin", "0x72")
        res["service"] = _get_ini_key_value(text, "io4", "service", "0x71")
        res["test"] = _get_ini_key_value(text, "io4", "test", "0x70")

        # [aime]
        res["scan"] = _get_ini_key_value(text, "aime", "scan", "0xD")

        # [keyboard]
        res["up"] = _get_ini_key_value(text, "keyboard", "up", "0x57")
        res["down"] = _get_ini_key_value(text, "keyboard", "down", "0x53")
        res["left"] = _get_ini_key_value(text, "keyboard", "left", "0x41")
        res["right"] = _get_ini_key_value(text, "keyboard", "right", "0x44")
        res["attack"] = _get_ini_key_value(text, "keyboard", "attack", "0x2")
        res["dash"] = _get_ini_key_value(text, "keyboard", "dash", "0xA0")
        res["target"] = _get_ini_key_value(text, "keyboard", "target", "0x46")
        res["np"] = _get_ini_key_value(text, "keyboard", "np", "0x20")
        res["camera"] = _get_ini_key_value(text, "keyboard", "camera", "0x43")

        # [xinput]
        try:
            res["controllerIndex"] = int(_get_ini_key_value(text, "xinput", "controllerIndex", "0"))
            res["stickDeadzone"] = int(_get_ini_key_value(text, "xinput", "stickDeadzone", "7849"))
            res["rumble"] = int(_get_ini_key_value(text, "xinput", "rumble", "1"))
            res["rumbleStrength"] = int(_get_ini_key_value(text, "xinput", "rumbleStrength", "70"))
        except Exception:
            pass

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

            # [io4]
            if "mode" in controls:
                text = _set_ini_key_value(text, "io4", "mode", str(controls["mode"]))
            if "coin" in controls:
                text = _set_ini_key_value(text, "io4", "coin", str(controls["coin"]))
            if "service" in controls:
                text = _set_ini_key_value(text, "io4", "service", str(controls["service"]))
            if "test" in controls:
                text = _set_ini_key_value(text, "io4", "test", str(controls["test"]))

            # [aime]
            if "scan" in controls:
                text = _set_ini_key_value(text, "aime", "scan", str(controls["scan"]))

            # [keyboard]
            for key in ["up", "down", "left", "right", "attack", "dash", "target", "np", "camera"]:
                if key in controls:
                    text = _set_ini_key_value(text, "keyboard", key, str(controls[key]))

            # [xinput]
            for key in ["controllerIndex", "stickDeadzone", "rumble", "rumbleStrength"]:
                if key in controls:
                    text = _set_ini_key_value(text, "xinput", key, str(controls[key]))

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
