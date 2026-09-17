#!/usr/bin/env python3
"""
Fate/Grand Order Arcade Launcher (PyQt6).
Main desktop application entry point.
"""

import os
import sys

# Ensure FGOA root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FGOA_ROOT = os.path.dirname(SCRIPT_DIR)
if FGOA_ROOT not in sys.path:
    sys.path.insert(0, FGOA_ROOT)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication

from launcher.core.translation_installer import ensure_fgozh_patched
from launcher.ui.main_window import MainWindow
from launcher.ui.theme import Theme

PLATFORM_ICO = os.path.join(SCRIPT_DIR, "assets", "platform.ico")


def main():
    # Ensure any existing translation hook DLLs are patched for Wine compatibility
    try:
        ensure_fgozh_patched()
    except Exception:
        pass
    if "--headless-test" in sys.argv:
        print("[TEST] Running headless initialization test for MainWindow...")
        app = QApplication(["fgo_launcher", "-platform", "offscreen"])
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

    platform_png = os.path.join(SCRIPT_DIR, "assets", "platform.png")
    if os.path.exists(platform_png):
        app.setWindowIcon(QIcon(platform_png))
    elif os.path.exists(PLATFORM_ICO):
        app.setWindowIcon(QIcon(PLATFORM_ICO))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
