"""
Network sync module for FGO Arcade.
Ensures App/segatools.ini and Server/artemis/config/core.yaml are synchronized.
Supports bulletproof Local Loopback (192.168.100.1) and dynamic LAN Mode.
"""

import os
import re
import subprocess
from typing import Tuple
try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from .config import FGOA_ROOT
SEGATOOLS_INI = os.path.join(FGOA_ROOT, "App", "segatools.ini")
CORE_YAML = os.path.join(FGOA_ROOT, "Server", "artemis", "config", "core.yaml")


def detect_host_ip() -> str:
    """Detect primary LAN IPv4 address."""
    try:
        res = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            match = re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", res.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass

    # Fallback to local loopback
    return "127.0.0.1"


def sync_network(mode: str = "local", custom_ip: str = "") -> Tuple[bool, str]:
    """
    Sync segatools.ini and core.yaml to either:
    - 'local' (192.168.100.1): Virtual LAN mapped to 127.0.0.1 by fgohook.
    - 'lan': Host's active LAN IP.
    """
    if mode == "local":
        target_ip = "192.168.100.1"
        subnet = "192.168.100.0"
        addr_suffix = "11"
        broadcast = "127.0.0.1"
    else:
        target_ip = custom_ip if custom_ip else detect_host_ip()
        parts = target_ip.split(".")
        if len(parts) == 4:
            subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0"
            addr_suffix = parts[3]
            broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
        else:
            return False, f"Invalid IP address: {target_ip}"

    # 1. Update Server/artemis/config/core.yaml
    if os.path.isfile(CORE_YAML):
        try:
            with open(CORE_YAML, "r", encoding="utf-8") as f:
                content = f.read()

            content = re.sub(
                r"(hostname:\s*)[^\n]+",
                rf"\g<1>{target_ip}",
                content,
            )

            with open(CORE_YAML, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return False, f"Failed updating core.yaml: {e}"

    # 2. Update App/segatools.ini
    if os.path.isfile(SEGATOOLS_INI):
        try:
            with open(SEGATOOLS_INI, "r", encoding="utf-8") as f:
                content = f.read()

            # [dns] default=...
            content = re.sub(
                r"(\[dns\][^\[]*?default=)[^\n]+",
                rf"\g<1>{target_ip}",
                content,
                flags=re.DOTALL,
            )

            # [netenv] addrSuffix=... broadcast=...
            content = re.sub(
                r"(\[netenv\][^\[]*?addrSuffix=)[^\n]+",
                rf"\g<1>{addr_suffix}",
                content,
                flags=re.DOTALL,
            )
            content = re.sub(
                r"(\[netenv\][^\[]*?broadcast=)[^\n]+",
                rf"\g<1>{broadcast}",
                content,
                flags=re.DOTALL,
            )

            # [keychip] subnet=...
            content = re.sub(
                r"(\[keychip\][^\[]*?subnet=)[^\n]+",
                rf"\g<1>{subnet}",
                content,
                flags=re.DOTALL,
            )

            with open(SEGATOOLS_INI, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return False, f"Failed updating segatools.ini: {e}"

    return True, target_ip


def get_current_sync_info() -> Tuple[str, str]:
    """Read current configured server IP from segatools.ini."""
    if os.path.isfile(SEGATOOLS_INI):
        try:
            with open(SEGATOOLS_INI, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(r"\[dns\][^\[]*?default=([^\n\r;]+)", content, re.DOTALL)
            if match:
                ip = match.group(1).strip()
                mode = "Local Loopback" if ip == "192.168.100.1" else "LAN Mode"
                return ip, mode
        except Exception:
            pass
    return "Unknown", "Unknown"
