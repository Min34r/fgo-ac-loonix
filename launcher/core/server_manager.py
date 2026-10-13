"""
Server manager module for FGO Arcade Linux launcher.
Monitors and manages MariaDB (3307) and Artemis server (8777, 8443, 22345).
"""

import os
import socket
import subprocess
from dataclasses import dataclass
from launcher.core.config import FGOA_ROOT, SERVER_DIR


def _server_script(name: str) -> str:
    candidates = (
        os.path.join(SERVER_DIR, name),
        os.path.join(FGOA_ROOT, "scripts", name),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts", name),
    )
    for p in candidates:
        if os.path.isfile(p):
            return p
    return os.path.join(SERVER_DIR, name)


@dataclass
class ServerStatus:
    mariadb: bool = False
    artemis_http: bool = False
    artemis_billing: bool = False
    artemis_aimedb: bool = False

    @property
    def up_count(self) -> int:
        return sum((self.mariadb, self.artemis_http, self.artemis_billing, self.artemis_aimedb))

    @property
    def is_all_online(self) -> bool:
        return self.up_count == 4


def check_port(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """Test if a TCP port is listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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
    script = _server_script("start_server_native.sh")
    env = os.environ.copy()
    env["FGOA_ROOT"] = FGOA_ROOT
    return subprocess.Popen(
        ["bash", script],
        cwd=SERVER_DIR if os.path.isdir(SERVER_DIR) else FGOA_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )


def stop_server_stack() -> None:
    """Stop MariaDB and Artemis native instances."""
    script = _server_script("stop_server_native.sh")
    if os.path.isfile(script):
        subprocess.run(["bash", script], check=False)
    subprocess.run(["pkill", "-f", "artemis.*index.py"], check=False)
    subprocess.run(["pkill", "-f", "mariadbd.*mariadb_native.cnf"], check=False)
