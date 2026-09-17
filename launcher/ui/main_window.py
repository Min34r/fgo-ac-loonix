"""
Main Window: Desktop interface for Fate/Grand Order Arcade.
Provides header controls, sidebar navigation, view container, and system logs drawer.
"""

import os
import subprocess
from typing import Optional

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.core.game_process import GameProcessManager
from launcher.core.server_manager import (
    ServerManager,
    ServerStatus,
    get_server_status,
    restart_server_stack,
    start_server_stack,
    stop_server_stack,
)
from launcher.ui.advanced_view import AdvancedView
from launcher.ui.cards_view import CardsView
from launcher.ui.chamfer import ChamferButton
from launcher.ui.account_view import AccountView
from launcher.ui.play_view import PlayView
from launcher.ui.settings_view import SettingsView
from launcher.ui.theme import Theme
try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from ..core.config import FGOA_ROOT

ASSETS_DIR = os.path.join(FGOA_ROOT, "launcher", "assets")
PLATFORM_PNG = os.path.join(ASSETS_DIR, "platform.png")
PLATFORM_ICO = os.path.join(ASSETS_DIR, "platform.ico")


class ServerStartupWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            self.progress.emit("[SERVER] Starting MariaDB & Artemis server stack on-demand...")
            proc = start_server_stack()
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    line_str = line.strip()
                    if line_str:
                        self.progress.emit(f"[SERVER] {line_str}")
            proc.wait()

            if proc.returncode != 0:
                self.finished.emit(False, f"Server exited with code {proc.returncode}")
                return

            self.progress.emit("[SERVER] Script exited. Waiting for ports to come online...")
            import time
            for i in range(30):
                status = get_server_status()
                if status.is_all_online:
                    self.progress.emit("[SERVER] All services online (MariaDB, HTTP, Billing, AimeDB)")
                    self.finished.emit(True, "")
                    return
                missing = []
                if not status.mariadb: missing.append("MariaDB:3307")
                if not status.artemis_http: missing.append("HTTP:8777")
                if not status.artemis_billing: missing.append("Billing:8443")
                if not status.artemis_aimedb: missing.append("AimeDB:22345")
                self.progress.emit(f"[SERVER] Waiting for: {', '.join(missing)} ({i+1}/30)")
                time.sleep(1.0)

            self.finished.emit(False, "Timed out waiting for server ports")
        except Exception as e:
            self.finished.emit(False, str(e))


class SidebarButton(QPushButton):
    """Sidebar navigation tab button."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.update_style(False)

    def update_style(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.PLATE};
                    color: {Theme.ICE};
                    font-size: 15px;
                    font-weight: 600;
                    text-align: left;
                    padding-left: 20px;
                    border: none;
                    border-left: 3px solid {Theme.ICE};
                    outline: none;
                }}
                QPushButton:focus {{
                    outline: none;
                    border: none;
                    border-left: 3px solid {Theme.ICE};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Theme.TEXT_MUTED};
                    font-size: 15px;
                    font-weight: 500;
                    text-align: left;
                    padding-left: 23px;
                    border: none;
                    outline: none;
                }}
                QPushButton:hover {{
                    background-color: {Theme.PLATE_LOW};
                    color: {Theme.TEXT};
                    outline: none;
                }}
                QPushButton:focus {{
                    outline: none;
                    border: none;
                }}
            """)


class MainWindow(QMainWindow):
    """
    Main application window for Fate/Grand Order Arcade.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fate/Grand Order Arcade")
        self.setMinimumSize(1240, 780)
        self.resize(1366, 860)

        # Set Icon
        if os.path.exists(PLATFORM_PNG):
            self.setWindowIcon(QIcon(PLATFORM_PNG))
        elif os.path.exists(PLATFORM_ICO):
            self.setWindowIcon(QIcon(PLATFORM_ICO))

        self.game_process = GameProcessManager(self)
        self.server_manager = ServerManager()

        self._auto_manage_server = True
        self._server_worker: Optional[ServerStartupWorker] = None
        self._logs_visible = True
        self._init_ui()
        self._wire_signals()

        # Start Server Status Poll Timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_status)
        self.status_timer.start(3000)
        self._poll_status()

    def _init_ui(self):
        # Global Window Styling
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Theme.GROUND};
                color: {Theme.TEXT};
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            }}
            QSplitter::handle {{
                background-color: {Theme.LINE};
            }}
            QSplitter::handle:horizontal {{
                width: 4px;
            }}
            QSplitter::handle:vertical {{
                height: 4px;
            }}
        """)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # =============================================================
        # 1. Top Header Bar (Height: 60px)
        # =============================================================
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.GROUND};
                border-bottom: 1px solid {Theme.LINE};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 18, 0)
        h_layout.setSpacing(16)

        # Left: Icon + Brand Name
        brand_box = QHBoxLayout()
        brand_box.setSpacing(12)
        lbl_icon = QLabel()
        if os.path.exists(PLATFORM_ICO):
            pix = QPixmap(PLATFORM_ICO).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl_icon.setPixmap(pix)
        lbl_icon.setFixedSize(32, 32)

        lbl_brand = QLabel("Fate/Grand Order Arcade")
        lbl_brand.setStyleSheet(f"""
            font-size: 19px;
            font-weight: 700;
            color: {Theme.TEXT};
            letter-spacing: 0.3px;
        """)
        brand_box.addWidget(lbl_icon)
        brand_box.addWidget(lbl_brand)
        h_layout.addLayout(brand_box)

        # Middle: Runtime Status Label
        self.lbl_header_status = QLabel("Checking server ports...")
        self.lbl_header_status.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        h_layout.addWidget(self.lbl_header_status, stretch=1)

        # Right: Action Buttons
        actions_box = QHBoxLayout()
        actions_box.setSpacing(10)

        self.btn_check_updates = QPushButton("Check for updates")
        self.btn_check_updates.setFixedHeight(34)
        self.btn_check_updates.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_check_updates.clicked.connect(self._check_updates)

        self.btn_stop_game = QPushButton("Stop game")
        self.btn_stop_game.setFixedHeight(34)
        self.btn_stop_game.setMinimumWidth(104)
        self.btn_stop_game.setEnabled(False)
        self.btn_stop_game.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Theme.DANGER};
                color: {Theme.DANGER};
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Theme.DANGER}22;
            }}
            QPushButton:disabled {{
                border-color: {Theme.LINE};
                color: {Theme.TEXT_FAINT};
            }}
        """)
        self.btn_stop_game.clicked.connect(self._stop_game)

        # Chamfered Play Hero Button
        self.btn_play_top = ChamferButton(
            "Play",
            cut=8.0,
            stroke_color="#7CC4E4",
            hover_stroke="#A8DDF4",
            fill_color="#7CC4E4",
            hover_fill="#92D2EE",
            text_color="#121417",
            font_size=16,
        )
        self.btn_play_top.setFixedHeight(38)
        self.btn_play_top.setMinimumWidth(140)
        self.btn_play_top.clicked.connect(self._launch_game)

        actions_box.addWidget(self.btn_check_updates)
        actions_box.addWidget(self.btn_stop_game)
        actions_box.addWidget(self.btn_play_top)
        h_layout.addLayout(actions_box)

        root_layout.addWidget(header)

        # =============================================================
        # 2. Main Body Splitter (Workspace on left, LogPanel on right)
        # =============================================================
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        # -------------------------------------------------------------
        # 2A. Workspace: Left Sidebar + Central Stack
        # -------------------------------------------------------------
        workspace = QWidget()
        ws_layout = QHBoxLayout(workspace)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.GROUND};
                border-right: 1px solid {Theme.LINE};
            }}
        """)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 16, 0, 16)
        sb_layout.setSpacing(4)

        self.btn_tab_play = SidebarButton("Play")
        self.btn_tab_account = SidebarButton("Account")
        self.btn_tab_cards = SidebarButton("Cards and Deck")
        self.btn_tab_settings = SidebarButton("Settings")
        self.btn_tab_advanced = SidebarButton("Advanced")

        self.tab_buttons = [
            self.btn_tab_play,
            self.btn_tab_account,
            self.btn_tab_cards,
            self.btn_tab_settings,
            self.btn_tab_advanced,
        ]

        self.tab_group = QButtonGroup(self)
        for idx, btn in enumerate(self.tab_buttons):
            self.tab_group.addButton(btn, idx)
            sb_layout.addWidget(btn)
            btn.clicked.connect(lambda _, i=idx: self._switch_tab(i))

        sb_layout.addStretch()
        ws_layout.addWidget(sidebar)

        # Stacked Views
        self.stack = QStackedWidget()
        self.play_view = PlayView(self)
        self.account_view = AccountView(self)
        self.cards_view = CardsView(self)
        self.settings_view = SettingsView(self)
        self.advanced_view = AdvancedView(self)

        self.stack.addWidget(self.play_view)      # 0
        self.stack.addWidget(self.account_view)   # 1
        self.stack.addWidget(self.cards_view)     # 2
        self.stack.addWidget(self.settings_view)  # 3
        self.stack.addWidget(self.advanced_view)  # 4

        ws_layout.addWidget(self.stack, stretch=1)
        self.main_splitter.addWidget(workspace)

        # -------------------------------------------------------------
        # 2B. Log Panel (Right Column)
        # -------------------------------------------------------------
        self.log_panel = QFrame()
        self.log_panel.setMinimumWidth(320)
        self.log_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE_LOW};
                border-left: 1px solid {Theme.LINE};
            }}
        """)
        lp_layout = QVBoxLayout(self.log_panel)
        lp_layout.setContentsMargins(10, 10, 10, 10)
        lp_layout.setSpacing(8)

        log_splitter = QSplitter(Qt.Orientation.Vertical)
        log_splitter.setChildrenCollapsible(False)

        # Server Log Box
        box_server = QFrame()
        box_server.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
            }}
        """)
        bs_layout = QVBoxLayout(box_server)
        bs_layout.setContentsMargins(0, 0, 0, 0)
        bs_layout.setSpacing(0)

        header_srv = QFrame()
        header_srv.setFixedHeight(30)
        header_srv.setStyleSheet(f"background-color: {Theme.PLATE}; border-bottom: 1px solid {Theme.LINE};")
        hs_layout = QHBoxLayout(header_srv)
        hs_layout.setContentsMargins(12, 0, 12, 0)
        lbl_srv_title = QLabel("Server")
        lbl_srv_title.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px; font-weight: 600; border: none;")
        hs_layout.addWidget(lbl_srv_title)
        hs_layout.addStretch()

        self.txt_server_log = QPlainTextEdit()
        self.txt_server_log.setReadOnly(True)
        self.txt_server_log.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Theme.GROUND};
                color: {Theme.TEXT_MUTED};
                font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: none;
                padding: 6px;
            }}
        """)
        bs_layout.addWidget(header_srv)
        bs_layout.addWidget(self.txt_server_log)
        log_splitter.addWidget(box_server)

        # Game Log Box
        box_game = QFrame()
        box_game.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
            }}
        """)
        bg_layout = QVBoxLayout(box_game)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.setSpacing(0)

        header_game = QFrame()
        header_game.setFixedHeight(30)
        header_game.setStyleSheet(f"background-color: {Theme.PLATE}; border-bottom: 1px solid {Theme.LINE};")
        hg_layout = QHBoxLayout(header_game)
        hg_layout.setContentsMargins(12, 0, 12, 0)
        lbl_game_title = QLabel("Game")
        lbl_game_title.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px; font-weight: 600; border: none;")
        hg_layout.addWidget(lbl_game_title)
        hg_layout.addStretch()

        self.txt_game_log = QPlainTextEdit()
        self.txt_game_log.setReadOnly(True)
        self.txt_game_log.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Theme.GROUND};
                color: {Theme.ICE};
                font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: none;
                padding: 6px;
            }}
        """)
        bg_layout.addWidget(header_game)
        bg_layout.addWidget(self.txt_game_log)
        log_splitter.addWidget(box_game)

        log_splitter.setSizes([260, 360])
        lp_layout.addWidget(log_splitter)

        self.main_splitter.addWidget(self.log_panel)
        self.main_splitter.setSizes([920, 446])
        root_layout.addWidget(self.main_splitter, stretch=1)

        # =============================================================
        # 3. Bottom Status Bar (Height: 28px)
        # =============================================================
        statusbar = QFrame()
        statusbar.setFixedHeight(28)
        statusbar.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border-top: 1px solid {Theme.LINE};
            }}
        """)
        sb_bottom_layout = QHBoxLayout(statusbar)
        sb_bottom_layout.setContentsMargins(16, 0, 16, 0)

        self.lbl_bottom_status = QLabel("Server ports checking... | v1.1.2")
        self.lbl_bottom_status.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px;")
        sb_bottom_layout.addWidget(self.lbl_bottom_status, stretch=1)

        self.btn_toggle_logs = QPushButton("Hide logs")
        self.btn_toggle_logs.setFixedHeight(22)
        self.btn_toggle_logs.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.PLATE_LOW};
                color: {Theme.TEXT_SOFT};
                border: 1px solid {Theme.LINE};
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {Theme.TEXT};
                border-color: {Theme.ICE};
            }}
        """)
        self.btn_toggle_logs.clicked.connect(self._toggle_logs)
        sb_bottom_layout.addWidget(self.btn_toggle_logs)

        root_layout.addWidget(statusbar)

        # Activate first tab
        self._switch_tab(0)

    def _wire_signals(self):
        # Play view controls
        self.play_view.launch_requested.connect(self._launch_game)
        self.play_view.stop_requested.connect(self._stop_game)
        self.play_view.open_logs_requested.connect(self._show_logs)

        # Account view logs
        self.account_view.log_message.connect(self._append_server_log)

        # Settings view logs
        if hasattr(self.settings_view, "log_message"):
            self.settings_view.log_message.connect(self._append_server_log)

        # Cards view signals
        self.cards_view.deck_changed.connect(self._on_deck_changed)

        # Game process signals
        self.game_process.started.connect(self._on_game_started)
        self.game_process.finished.connect(self._on_game_finished)
        self.game_process.log_received.connect(self._append_game_log)

    def _on_deck_changed(self):
        self.play_view.refresh_leader_card()
        self._poll_status()

    # -----------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------
    def _switch_tab(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.tab_buttons):
            btn.setChecked(i == index)
            btn.update_style(i == index)

    # -----------------------------------------------------------------
    # Logs drawer management
    # -----------------------------------------------------------------
    def _toggle_logs(self):
        self._logs_visible = not self._logs_visible
        self.log_panel.setVisible(self._logs_visible)
        self.btn_toggle_logs.setText("Hide logs" if self._logs_visible else "Show logs")

    def _show_logs(self):
        if not self._logs_visible:
            self._toggle_logs()

    def _append_server_log(self, text: str):
        self.txt_server_log.appendPlainText(text.rstrip())

    def _append_game_log(self, text: str):
        self.txt_game_log.appendPlainText(text.rstrip())

    # -----------------------------------------------------------------
    # Process & Server Lifecycle
    # -----------------------------------------------------------------
    def _poll_status(self):
        statuses = self.server_manager.get_all_statuses()
        active_count = sum(1 for s in statuses.values() if s.is_running)
        total_count = len(statuses)

        status_str = f"Server ports {active_count}/{total_count} up"
        game_str = "Game running" if self.game_process.is_running else "Game not running"
        full_status = f"{status_str} - {game_str}"

        self.lbl_header_status.setText(full_status)
        self.lbl_bottom_status.setText(f"{full_status} | English v1.1.2")

        if hasattr(self.play_view, "update_server_status"):
            self.play_view.update_server_status(active_count == total_count, status_str)

    def _launch_game(self):
        if self.game_process.is_running:
            return

        self._show_logs()
        self.btn_play_top.setEnabled(False)
        self.btn_stop_game.setEnabled(True)
        if hasattr(self.play_view, "btn_play_hero"):
            self.play_view.btn_play_hero.setEnabled(False)

        # On-Demand Server: Check if server is running before launching
        if self._auto_manage_server:
            status = self.server_manager.get_status()
            if not status.is_all_online:
                self._append_server_log("[LAUNCHER] Server stack offline. Starting MariaDB and Artemis on-demand...")
                self._server_worker = ServerStartupWorker()
                self._server_worker.progress.connect(self._append_server_log)
                self._server_worker.finished.connect(self._on_server_ready_and_launch)
                self._server_worker.start()
                return

        self._start_game_process()

    def _on_server_ready_and_launch(self, success: bool, error_msg: str):
        self._poll_status()
        if not success:
            self.btn_play_top.setEnabled(True)
            self.btn_stop_game.setEnabled(False)
            if hasattr(self.play_view, "btn_play_hero"):
                self.play_view.btn_play_hero.setEnabled(True)
            self._append_server_log(f"[LAUNCHER] ERROR: Failed to start server stack: {error_msg}")
            QMessageBox.critical(self, "Server Error", f"Failed to start local server stack:\n{error_msg}")
            return

        self._append_server_log("[LAUNCHER] Server stack is fully online. Launching game...")
        self._start_game_process()

    def _start_game_process(self):
        self._append_game_log("[LAUNCHER] Starting Fate/Grand Order Arcade via launch_linux.sh...")
        self.game_process.launch(fullscreen=True)

    def _stop_game(self):
        self._append_game_log("[LAUNCHER] Stopping game process...")
        self.game_process.terminate()

    def _on_game_started(self):
        self.btn_play_top.setEnabled(False)
        self.btn_stop_game.setEnabled(True)
        if hasattr(self.play_view, "btn_play_hero"):
            self.play_view.btn_play_hero.setEnabled(False)
        self._poll_status()

    def _on_game_finished(self, code: int):
        self.btn_play_top.setEnabled(True)
        self.btn_stop_game.setEnabled(False)
        if hasattr(self.play_view, "btn_play_hero"):
            self.play_view.btn_play_hero.setEnabled(True)

        if self._auto_manage_server:
            self._append_server_log(f"[LAUNCHER] Game finished (exit code {code}). Stopping server stack on-demand...")
            stop_server_stack()

        self._poll_status()

    def closeEvent(self, event):
        if self._auto_manage_server:
            stop_server_stack()
        if self.game_process.is_running:
            self.game_process.terminate()
        event.accept()

    def _check_updates(self):
        QMessageBox.information(
            self,
            "Check for updates",
            "You are running Fate/Grand Order Arcade Launcher v1.1.2 with complete English Translation Package.\n\n"
            "Your installation is up to date."
        )
