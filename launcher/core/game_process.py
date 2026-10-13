"""
Game process manager using PyQt6 QProcess.
Provides non-blocking execution, real-time log capturing, and lifecycle management.
"""

import os
import subprocess
from PyQt6.QtCore import QObject, QProcess, pyqtSignal
from launcher.core.config import APP_DIR, FGOA_ROOT

def get_launch_script() -> str:
    for p in (
        os.path.join(APP_DIR, "launch_linux.sh"),
        os.path.join(FGOA_ROOT, "scripts", "launch_linux.sh"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts", "launch_linux.sh"),
        os.path.join(APP_DIR, "launch_nvidia.sh"),
        os.path.join(APP_DIR, "launch_amd.sh"),
    ):
        if os.path.isfile(p):
            return p
    return os.path.join(APP_DIR, "launch_linux.sh")


class GameProcessManager(QObject):
    started = pyqtSignal()
    finished = pyqtSignal(int)
    log_received = pyqtSignal(str)
    state_changed = pyqtSignal(str)  # "Stopped", "Running", "Error"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(lambda: self._emit_stream(self.process.readAllStandardOutput()))
        self.process.readyReadStandardError.connect(lambda: self._emit_stream(self.process.readAllStandardError()))
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

        self.state_changed.emit("Starting")
        self.log_received.emit(f"[LAUNCHER] Starting FGO Arcade ({'Fullscreen' if fullscreen else 'Windowed'})...\n")
        self.process.setWorkingDirectory(APP_DIR)
        script = get_launch_script()
        self.process.start("bash", [script, "--fullscreen" if fullscreen else "--windowed"])

    def terminate(self):
        if self.is_running:
            self.log_received.emit("[LAUNCHER] Stopping game process...\n")
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
        self._force_cleanup()

    def _force_cleanup(self):
        for pat in ("ago.exe", "inject.exe", "amdaemon"):
            subprocess.run(["pkill", "-f", pat], check=False)
        subprocess.run(["wineserver", "-k"], check=False)
        self.state_changed.emit("Stopped")

    def _on_started(self):
        self.state_changed.emit("Running")
        self.started.emit()

    def _on_finished(self, exit_code, _exit_status):
        self.state_changed.emit("Stopped")
        self.log_received.emit(f"[LAUNCHER] Game process exited with code {exit_code}\n")
        self.finished.emit(exit_code)

    def _on_error(self, error):
        self.state_changed.emit("Error")
        self.log_received.emit(f"[LAUNCHER ERROR] Process error: {error}\n")

    def _emit_stream(self, raw):
        if data := raw.data().decode("utf-8", errors="replace"):
            self.log_received.emit(data)
