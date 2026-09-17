"""
Game process manager using PyQt6 QProcess.
Provides non-blocking execution, real-time log capturing, and lifecycle management.
"""

import os
import subprocess
from PyQt6.QtCore import QObject, QProcess, pyqtSignal
try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from .config import FGOA_ROOT

def get_launch_script() -> str:
    candidates = [
        os.path.join(FGOA_ROOT, "App", "launch_linux.sh"),
        os.path.join(FGOA_ROOT, "scripts", "launch_linux.sh"),
        os.path.join(FGOA_ROOT, "App", "launch_nvidia.sh"),
        os.path.join(FGOA_ROOT, "App", "launch_amd.sh"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return os.path.join(FGOA_ROOT, "App", "launch_linux.sh")

LAUNCH_SCRIPT = get_launch_script()


class GameProcessManager(QObject):
    started = pyqtSignal()
    finished = pyqtSignal(int)
    log_received = pyqtSignal(str)
    state_changed = pyqtSignal(str)  # "Stopped", "Running", "Error"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

    @property
    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def launch(self, fullscreen: bool = True):
        if self.is_running:
            return

        self.log_received.emit("[LAUNCHER] Cleaning up stale processes...\n")
        self._force_cleanup()

        args = []
        if fullscreen:
            args.append("--fullscreen")
        else:
            args.append("--windowed")

        self.state_changed.emit("Starting")
        self.log_received.emit(f"[LAUNCHER] Starting FGO Arcade ({'Fullscreen' if fullscreen else 'Windowed'})...\n")
        self.process.setWorkingDirectory(os.path.join(FGOA_ROOT, "App"))
        self.process.start("bash", [LAUNCH_SCRIPT] + args)

    def terminate(self):
        if not self.is_running:
            # Also clean up any lingering wine or ago processes
            self._force_cleanup()
            return

        self.log_received.emit("[LAUNCHER] Stopping game process...\n")
        self.process.terminate()
        if not self.process.waitForFinished(3000):
            self.process.kill()
        self._force_cleanup()

    def _force_cleanup(self):
        subprocess.run(["pkill", "-f", "ago.exe"], check=False)
        subprocess.run(["pkill", "-f", "inject.exe"], check=False)
        subprocess.run(["pkill", "-f", "amdaemon"], check=False)
        subprocess.run(["wineserver", "-k"], check=False)
        self.state_changed.emit("Stopped")

    def _on_started(self):
        self.state_changed.emit("Running")
        self.started.emit()

    def _on_finished(self, exit_code, exit_status):
        self.state_changed.emit("Stopped")
        self.log_received.emit(f"[LAUNCHER] Game process exited with code {exit_code}\n")
        self.finished.emit(exit_code)

    def _on_error(self, error):
        self.state_changed.emit("Error")
        self.log_received.emit(f"[LAUNCHER ERROR] Process error: {error}\n")

    def _on_stdout(self):
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        if data:
            self.log_received.emit(data)

    def _on_stderr(self):
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        if data:
            self.log_received.emit(data)
