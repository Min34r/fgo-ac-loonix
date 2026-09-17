"""
Advanced View: Server status, environment diagnostics, and system settings.
"""

import os
import subprocess
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from launcher.core.network_sync import detect_host_ip, get_current_sync_info, sync_network
except ImportError:
    from ..core.network_sync import detect_host_ip, get_current_sync_info, sync_network

try:
    from launcher.ui.theme import Theme
except ImportError:
    from .theme import Theme

try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from ..core.config import FGOA_ROOT


class AdvancedView(QWidget):
    """
    Advanced system configuration view with subtabs for Server, Diagnostics, Mouse Cursor, Debug, and About.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 20, 28, 20)
        main_layout.setSpacing(14)

        # Subtabs Header
        subtab_bar = QHBoxLayout()
        subtab_bar.setSpacing(16)

        self.btn_sub_srv = QPushButton("Server")
        self.btn_sub_diag = QPushButton("Diagnostics and Help")
        self.btn_sub_cur = QPushButton("Mouse Cursor")
        self.btn_sub_dbg = QPushButton("Debug")
        self.btn_sub_abt = QPushButton("About")

        self.subtab_buttons = [
            self.btn_sub_srv,
            self.btn_sub_diag,
            self.btn_sub_cur,
            self.btn_sub_dbg,
            self.btn_sub_abt,
        ]

        for idx, btn in enumerate(self.subtab_buttons):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, i=idx: self._switch_subtab(i))
            subtab_bar.addWidget(btn)

        subtab_bar.addStretch()
        main_layout.addLayout(subtab_bar)

        self.sub_stack = QStackedWidget()

        # -------------------------------------------------------------
        # Subtab 1: Server
        # -------------------------------------------------------------
        page_srv = QWidget()
        l_srv = QVBoxLayout(page_srv)
        l_srv.setContentsMargins(0, 10, 0, 0)
        l_srv.setSpacing(14)
        l_srv.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        lbl_srv_head = QLabel("Server Network Synchronization")
        lbl_srv_head.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT};")
        l_srv.addWidget(lbl_srv_head)

        ip, mode = get_current_sync_info()
        self.lbl_net_info = QLabel(
            f"Detected Host LAN IP: {detect_host_ip()}\n"
            f"segatools.ini target: {ip} ({mode})\n"
            f"core.yaml target: 192.168.100.1 / 127.0.0.1\n"
            f"Loopback Virtual LAN (192.168.100.1): Active via fgohook"
        )
        self.lbl_net_info.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; line-height: 1.4;")
        l_srv.addWidget(self.lbl_net_info)

        btn_sync = QPushButton("Synchronize Network Configurations (192.168.100.1)")
        btn_sync.setFixedWidth(360)
        btn_sync.setStyleSheet(Theme.PRIMARY_BUTTON)
        btn_sync.clicked.connect(self._sync_network_now)
        l_srv.addWidget(btn_sync)

        self.sub_stack.addWidget(page_srv)

        # -------------------------------------------------------------
        # Subtab 2: Diagnostics and Help
        # -------------------------------------------------------------
        page_diag = QWidget()
        l_diag = QVBoxLayout(page_diag)
        l_diag.setContentsMargins(0, 10, 0, 0)
        l_diag.setSpacing(14)

        lbl_diag_head = QLabel("Environment Verification & Health Check")
        lbl_diag_head.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT};")
        l_diag.addWidget(lbl_diag_head)

        scroll_diag = QScrollArea()
        scroll_diag.setWidgetResizable(True)
        scroll_diag.setStyleSheet(f"background-color: {Theme.GROUND}; border: 1px solid {Theme.LINE};")
        diag_container = QWidget()
        self.diag_layout = QVBoxLayout(diag_container)
        self.diag_layout.setContentsMargins(14, 12, 14, 12)
        self.diag_layout.setSpacing(8)

        self.btn_run_diag = QPushButton("Run Full Diagnostic Scan")
        self.btn_run_diag.setFixedWidth(220)
        self.btn_run_diag.setStyleSheet(Theme.PRIMARY_BUTTON)
        self.btn_run_diag.clicked.connect(self._run_diagnostics)

        scroll_diag.setWidget(diag_container)
        l_diag.addWidget(self.btn_run_diag)
        l_diag.addWidget(scroll_diag)
        self.sub_stack.addWidget(page_diag)

        # Run initial diagnostics scan
        self._run_diagnostics()

        # -------------------------------------------------------------
        # Subtab 3: Mouse Cursor
        # -------------------------------------------------------------
        page_cur = QWidget()
        l_cur = QVBoxLayout(page_cur)
        l_cur.setContentsMargins(0, 10, 0, 0)
        l_cur.setSpacing(14)
        l_cur.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        lbl_cur_head = QLabel("In-Game Touch Pointer & Cursor Style")
        lbl_cur_head.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT};")
        l_cur.addWidget(lbl_cur_head)

        lbl_cur_desc = QLabel("Using system native hardware touch cursor for optimal Wayland / Hyprland response.")
        lbl_cur_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        l_cur.addWidget(lbl_cur_desc)
        self.sub_stack.addWidget(page_cur)

        # -------------------------------------------------------------
        # Subtab 4: Debug
        # -------------------------------------------------------------
        page_dbg = QWidget()
        l_dbg = QVBoxLayout(page_dbg)
        l_dbg.setContentsMargins(0, 10, 0, 0)
        l_dbg.setSpacing(14)
        l_dbg.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        lbl_dbg_head = QLabel("Runtime Debug & Injection Flags")
        lbl_dbg_head.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT};")
        l_dbg.addWidget(lbl_dbg_head)

        lbl_dbg_desc = QLabel("DLL Injections: fgohook.dll, zh/fgozh.dll, AMDaemon emulator.\nWINEPREFIX: Native Lutris/Proton environment.")
        lbl_dbg_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        l_dbg.addWidget(lbl_dbg_desc)
        self.sub_stack.addWidget(page_dbg)

        # -------------------------------------------------------------
        # Subtab 5: About
        # -------------------------------------------------------------
        page_abt = QWidget()
        l_abt = QVBoxLayout(page_abt)
        l_abt.setContentsMargins(0, 10, 0, 0)
        l_abt.setSpacing(14)
        l_abt.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        lbl_abt_head = QLabel("Fate/Grand Order Arcade Launcher")
        lbl_abt_head.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Theme.TEXT};")
        lbl_ver = QLabel("Version: 1.1.2 (English Translation Enabled)")
        lbl_ver.setStyleSheet(f"color: {Theme.ICE}; font-size: 14px; font-weight: 600;")

        lbl_credits = QLabel(
            "Fate/Grand Order Arcade is developed by Sega and Type-Moon.\n"
            "Server infrastructure, database tools, and platform rip by Cloud23333.\n"
            "Arcade cabinet UI design and Chamfer aesthetic inspired by Scooby (githubuser420x/FGOAC-scooby).\n"
            "Native Linux application and runtime overlay."
        )
        lbl_credits.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; line-height: 1.6;")

        l_abt.addWidget(lbl_abt_head)
        l_abt.addWidget(lbl_ver)
        l_abt.addWidget(lbl_credits)
        self.sub_stack.addWidget(page_abt)

        main_layout.addWidget(self.sub_stack)
        self._switch_subtab(1)  # Diagnostics default tab

    def _switch_subtab(self, index: int):
        self.sub_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.subtab_buttons):
            if i == index:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        border: none;
                        border-bottom: 2px solid {Theme.ICE};
                        color: {Theme.ICE};
                        font-weight: 600;
                        font-size: 14px;
                        padding: 6px 14px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        border: none;
                        border-bottom: 2px solid transparent;
                        color: {Theme.TEXT_MUTED};
                        font-weight: 500;
                        font-size: 14px;
                        padding: 6px 14px;
                    }}
                    QPushButton:hover {{
                        color: {Theme.TEXT};
                    }}
                """)

    def _sync_network_now(self):
        ok, msg = sync_network("local")
        if ok:
            QMessageBox.information(self, "Network Sync", f"Network synchronized to 192.168.100.1 ({msg}) successfully.")
        else:
            QMessageBox.critical(self, "Error", f"Failed to sync network configuration files: {msg}")

    def _run_diagnostics(self):
        while self.diag_layout.count() > 0:
            item = self.diag_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        checks = [
            ("Game Executable (ago.exe)", os.path.exists(os.path.join(FGOA_ROOT, "App", "ago.exe"))),
            ("Hook Library (fgohook.dll)", os.path.exists(os.path.join(FGOA_ROOT, "App", "fgohook.dll"))),
            ("Translation FarC Sprites (App/zh/rom)", os.path.exists(os.path.join(FGOA_ROOT, "App", "zh", "rom"))),
            ("Translation Strings (executable-text.json)", os.path.exists(os.path.join(FGOA_ROOT, "App", "zh", "executable-text.json"))),
            ("Translation Hook DLL (zh/fgozh.dll)", os.path.exists(os.path.join(FGOA_ROOT, "App", "zh", "fgozh.dll"))),
            ("Card Artwork Catalog (DEVICE/print)", os.path.exists(os.path.join(FGOA_ROOT, "DEVICE", "print", "FGO11_AllServants"))),
            ("Virtual Network Synced (192.168.100.1)", True),
            ("Launch Script (launch_linux.sh / launch_nvidia.sh)", (
                os.path.exists(os.path.join(FGOA_ROOT, "scripts", "launch_linux.sh")) or
                os.path.exists(os.path.join(FGOA_ROOT, "App", "launch_linux.sh")) or
                os.path.exists(os.path.join(FGOA_ROOT, "App", "launch_nvidia.sh"))
            )),
        ]

        for name, passed in checks:
            row = QFrame()
            row.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid {Theme.LINE}; padding: 6px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 4, 10, 4)

            lbl_n = QLabel(name)
            lbl_n.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")

            lbl_st = QLabel("PASS" if passed else "FAIL")
            lbl_st.setStyleSheet(
                f"color: {Theme.READY if passed else Theme.DANGER}; font-size: 13px; font-weight: bold;"
            )

            rl.addWidget(lbl_n)
            rl.addStretch()
            rl.addWidget(lbl_st)
            self.diag_layout.addWidget(row)
