"""
Network sync module for FGO Arcade.
Ensures App/segatools.ini and Server/artemis/config/core.yaml are synchronized.
Supports bulletproof Local Loopback (192.168.100.1) and dynamic LAN Mode.
"""

import os
import re
import subprocess
from typing import Tuple
from launcher.core.config import CONFIG_INI as SEGATOOLS_INI, SERVER_CONFIG_YAML as CORE_YAML


def detect_host_ip() -> str:
    """Detect primary LAN IPv4 address."""
    try:
        res = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and (m := re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", res.stdout)):
            return m.group(1)
    except Exception:
        pass
    return "127.0.0.1"


def sync_network(mode: str = "local", custom_ip: str = "") -> Tuple[bool, str]:
    """
    Sync segatools.ini and core.yaml to either:
    - 'local' (192.168.100.1): Virtual LAN mapped to 127.0.0.1 by fgohook.
    - 'lan': Host's active LAN IP.
    """
    if mode == "local":
        target_ip, subnet, addr_suffix, broadcast = "192.168.100.1", "192.168.100.0", "11", "127.0.0.1"
    else:
        target_ip = custom_ip or detect_host_ip()
        parts = target_ip.split(".")
        if len(parts) != 4:
            return False, f"Invalid IP address: {target_ip}"
        prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
        subnet, addr_suffix, broadcast = f"{prefix}.0", parts[3], f"{prefix}.255"

    # 1. Update Server/artemis/config/core.yaml
    if os.path.isfile(CORE_YAML):
        try:
            with open(CORE_YAML, "r", encoding="utf-8") as f:
                content = re.sub(r"(hostname:\s*)[^\n]+", rf"\g<1>{target_ip}", f.read())
            with open(CORE_YAML, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return False, f"Failed updating core.yaml: {e}"

    # 2. Update App/segatools.ini
    if os.path.isfile(SEGATOOLS_INI):
        try:
            with open(SEGATOOLS_INI, "r", encoding="utf-8") as f:
                content = f.read()
            for pat, val in (
                (r"(\[dns\][^\[]*?default=)[^\n]+", target_ip),
                (r"(\[netenv\][^\[]*?addrSuffix=)[^\n]+", addr_suffix),
                (r"(\[netenv\][^\[]*?broadcast=)[^\n]+", broadcast),
                (r"(\[keychip\][^\[]*?subnet=)[^\n]+", subnet),
            ):
                content = re.sub(pat, rf"\g<1>{val}", content, flags=re.DOTALL)
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
                if match := re.search(r"\[dns\][^\[]*?default=([^\n\r;]+)", f.read(), re.DOTALL):
                    ip = match.group(1).strip()
                    return ip, ("Local Loopback" if ip == "192.168.100.1" else "LAN Mode")
        except Exception:
            pass
    return "Unknown", "Unknown"
