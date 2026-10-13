#!/usr/bin/env python3
"""
Fate/Grand Order Arcade Launcher (PyQt6).
Main desktop application entry point.
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Ensure launcher package root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_INSTALL_DIR = os.path.dirname(SCRIPT_DIR)
if APP_INSTALL_DIR not in sys.path:
    sys.path.insert(0, APP_INSTALL_DIR)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication

from launcher.core.config import get_fgoa_root
from launcher.ui.theme import Theme

PLATFORM_ICO = os.path.join(SCRIPT_DIR, "assets", "platform.ico")


def _ensure_game_root(force_wizard: bool = False) -> Optional[Path]:
    if not force_wizard:
        current = get_fgoa_root()
        if (current / "App" / "ago.exe").is_file():
            return current

    from launcher.ui.setup_wizard import SetupWizardDialog

    wizard = SetupWizardDialog()
    if wizard.exec() == SetupWizardDialog.DialogCode.Accepted and wizard.configured_root:
        return wizard.configured_root
    return None


def main():
    if "--headless-test" in sys.argv:
        print("[TEST] Running headless initialization test for MainWindow...")
        app = QApplication(["fgo_launcher", "-platform", "offscreen"])
        from launcher.ui.main_window import MainWindow
        win = MainWindow()
        print(f"[TEST] Window initialized: {win.windowTitle()} (size: {win.size().width()}x{win.size().height()})")
        print(f"[TEST] Header status: {win.lbl_header_status.text()}")
        print(f"[TEST] Stack views: {win.stack.count()} views registered.")
        print("[TEST] MainWindow initialized successfully!")
        sys.exit(0)

    # Configure Wayland desktop file / app_id and high-DPI scaling before QApplication
    QGuiApplication.setDesktopFileName("fgo-arcade")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("fgo-arcade")
    app.setApplicationDisplayName("Fate/Grand Order Arcade")
    app.setOrganizationName("Type-Moon")
    app.setStyleSheet(Theme.GLOBAL_QSS)

    platform_png = os.path.join(SCRIPT_DIR, "assets", "platform.png")
    if os.path.exists(platform_png):
        app.setWindowIcon(QIcon(platform_png))
    elif os.path.exists(PLATFORM_ICO):
        app.setWindowIcon(QIcon(PLATFORM_ICO))

    force_wizard = "--setup" in sys.argv or "--wizard" in sys.argv
    if not _ensure_game_root(force_wizard=force_wizard):
        sys.exit(0)

    from launcher.core.translation_installer import ensure_fgozh_patched
    from launcher.ui.main_window import MainWindow

    try:
        ensure_fgozh_patched()
    except Exception:
        pass

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
