"""
Server manager module for FGO Arcade Linux launcher.
Monitors and manages MariaDB (3307) and Artemis server (8777, 8443, 22345).
"""

import os
import socket
import subprocess
from dataclasses import dataclass
from typing import Dict
try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from .config import FGOA_ROOT

SERVER_DIR = os.path.join(FGOA_ROOT, "Server")

def get_server_start_script() -> str:
    candidates = [
        os.path.join(SERVER_DIR, "start_server_native.sh"),
        os.path.join(FGOA_ROOT, "scripts", "start_server_native.sh"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return os.path.join(SERVER_DIR, "start_server_native.sh")

START_SCRIPT = get_server_start_script()

def get_server_stop_script() -> str:
    candidates = [
        os.path.join(SERVER_DIR, "stop_server_native.sh"),
        os.path.join(FGOA_ROOT, "scripts", "stop_server_native.sh"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return os.path.join(SERVER_DIR, "stop_server_native.sh")

STOP_SCRIPT = get_server_stop_script()


@dataclass
class ServiceStatus:
    name: str
    port: int
    is_running: bool


@dataclass
class ServerStatus:
    mariadb: bool = False
    artemis_http: bool = False
    artemis_billing: bool = False
    artemis_aimedb: bool = False

    @property
    def is_all_online(self) -> bool:
        return self.mariadb and self.artemis_http and self.artemis_billing and self.artemis_aimedb


def check_port(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """Test if a TCP port is listening."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        res = sock.connect_ex((host, port))
        return res == 0
    except Exception:
        return False
    finally:
        sock.close()


def get_server_status() -> ServerStatus:
    """Query current server stack ports."""
    return ServerStatus(
        mariadb=check_port(3307),
        artemis_http=check_port(8777),
        artemis_billing=check_port(8443),
        artemis_aimedb=check_port(22345),
    )


def start_server_stack() -> subprocess.Popen:
    """Launch native MariaDB and Artemis server stack."""
    cmd = ["bash", START_SCRIPT]
    return subprocess.Popen(
        cmd,
        cwd=SERVER_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_server_stack() -> None:
    """Stop MariaDB and Artemis native instances."""
    if os.path.isfile(STOP_SCRIPT):
        subprocess.run(["bash", STOP_SCRIPT], check=False)
    subprocess.run(["pkill", "-f", "artemis.*index.py"], check=False)
    subprocess.run(["pkill", "-f", "mariadbd.*mariadb_native.cnf"], check=False)


def restart_server_stack() -> subprocess.Popen:
    """Restart server stack."""
    stop_server_stack()
    return start_server_stack()


class ServerManager:
    """Object-oriented wrapper around server lifecycle and status monitoring."""

    def __init__(self):
        pass

    def get_status(self) -> ServerStatus:
        return get_server_status()

    def get_all_statuses(self) -> Dict[str, ServiceStatus]:
        status = get_server_status()
        return {
            "MariaDB": ServiceStatus("MariaDB (Port 3307)", 3307, status.mariadb),
            "HTTP": ServiceStatus("Artemis HTTP (Port 8777)", 8777, status.artemis_http),
            "Billing": ServiceStatus("Artemis Billing (Port 8443)", 8443, status.artemis_billing),
            "AimeDB": ServiceStatus("Artemis AimeDB (Port 22345)", 22345, status.artemis_aimedb),
        }

    def start_all(self):
        return start_server_stack()

    def stop_all(self):
        stop_server_stack()

    def restart_all(self):
        return restart_server_stack()
