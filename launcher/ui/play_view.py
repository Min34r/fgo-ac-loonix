"""
Play View: Primary dashboard with hero leader card, play button, and server actions.
"""

import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.core.card_catalog import CardCatalog
from launcher.core.server_manager import (
    restart_server_stack,
    start_server_stack,
    stop_server_stack,
)
from launcher.ui.chamfer import ChamferButton
from launcher.ui.theme import Theme

try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from ..core.config import FGOA_ROOT

CARD_DIR = os.path.join(FGOA_ROOT, "DEVICE", "print", "FGO11_AllServants")
MASH_BMP = os.path.join(CARD_DIR, "00130_SVT00011_A00_NORMAL.bmp")


class PlayView(QWidget):
    launch_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    open_logs_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = CardCatalog()
        self._init_ui()
        self.refresh_leader_card()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(20)

        top_row = QHBoxLayout()
        top_row.setSpacing(24)

        # -------------------------------------------------------------
        # Left: Hero Card Art Frame (232 x 316)
        # -------------------------------------------------------------
        self.card_border = QFrame()
        self.card_border.setFixedSize(232, 316)
        self.card_border.setStyleSheet(
            f"background-color: {Theme.GROUND}; border: 1px solid {Theme.LINE}; padding: 4px;"
        )
        card_inner = QVBoxLayout(self.card_border)
        card_inner.setContentsMargins(0, 0, 0, 0)

        self.lbl_card_img = QLabel()
        self.lbl_card_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_card_img.setText("No Card")
        card_inner.addWidget(self.lbl_card_img)

        top_row.addWidget(self.card_border, alignment=Qt.AlignmentFlag.AlignTop)

        # -------------------------------------------------------------
        # Right: Chamfered Play Box + Status Lines + Action Buttons
        # -------------------------------------------------------------
        right_box = QVBoxLayout()
        right_box.setSpacing(16)

        # Chamfered Big Play Header Button
        self.btn_play_hero = ChamferButton(
            "Play",
            cut=12.0,
            stroke_color=Theme.ICE,
            hover_stroke="#B3E0F5",
            fill_color=Theme.PLATE,
            hover_fill="#23272E",
            text_color=Theme.TEXT,
            font_size=20,
        )
        self.btn_play_hero.setFixedHeight(68)
        self.btn_play_hero.clicked.connect(self.launch_requested.emit)
        right_box.addWidget(self.btn_play_hero)

        # Status lines
        status_frame = QFrame()
        status_frame.setStyleSheet(f"border-bottom: 1px solid {Theme.LINE_SOFT};")
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(0, 0, 0, 8)
        status_layout.setSpacing(8)

        # Line 1: Server
        row_server = QHBoxLayout()
        lbl_s = QLabel("Server")
        lbl_s.setFixedWidth(80)
        lbl_s.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        self.lbl_server_status = QLabel("Checking server...")
        self.lbl_server_status.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        row_server.addWidget(lbl_s)
        row_server.addWidget(self.lbl_server_status)
        row_server.addStretch()

        # Line 2: Master
        row_master = QHBoxLayout()
        lbl_m = QLabel("Master")
        lbl_m.setFixedWidth(80)
        lbl_m.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        self.lbl_master_info = QLabel("Chaldea Master (Aime: 23189425320398932138)")
        self.lbl_master_info.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        row_master.addWidget(lbl_m)
        row_master.addWidget(self.lbl_master_info)
        row_master.addStretch()

        # Line 3: Deck
        row_deck = QHBoxLayout()
        lbl_d = QLabel("Deck")
        lbl_d.setFixedWidth(80)
        lbl_d.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        self.lbl_deck_info = QLabel("Loading deck...")
        self.lbl_deck_info.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        row_deck.addWidget(lbl_d)
        row_deck.addWidget(self.lbl_deck_info)
        row_deck.addStretch()

        status_layout.addLayout(row_server)
        status_layout.addLayout(row_master)
        status_layout.addLayout(row_deck)
        right_box.addWidget(status_frame)

        # Action Buttons Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.btn_srv_start = QPushButton("Start server")
        self.btn_srv_stop = QPushButton("Stop server")
        self.btn_open_logs = QPushButton("Open logs")
        self.btn_stop_game = QPushButton("Stop game")

        self.btn_srv_start.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_srv_stop.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_open_logs.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_stop_game.setStyleSheet(Theme.DANGER_BUTTON)

        self.btn_srv_start.clicked.connect(self._start_server)
        self.btn_srv_stop.clicked.connect(self._stop_server)
        self.btn_open_logs.clicked.connect(self.open_logs_requested.emit)
        self.btn_stop_game.clicked.connect(self.stop_requested.emit)

        actions_row.addWidget(self.btn_srv_start)
        actions_row.addWidget(self.btn_srv_stop)
        actions_row.addWidget(self.btn_open_logs)
        actions_row.addWidget(self.btn_stop_game)
        actions_row.addStretch()

        right_box.addLayout(actions_row)
        top_row.addLayout(right_box, stretch=1)
        main_layout.addLayout(top_row)

        # -------------------------------------------------------------
        # Bottom Notice: First time here?
        # -------------------------------------------------------------
        bottom_box = QFrame()
        bottom_box.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid {Theme.LINE}; padding: 12px;")
        b_layout = QVBoxLayout(bottom_box)
        b_layout.setSpacing(6)

        lbl_first_time = QLabel("First time here?")
        lbl_first_time.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {Theme.TEXT};")
        lbl_desc = QLabel(
            "Start the server above, then click Play. Use the Cards and Deck tab to manage your party loadout. "
            "Native 1920x1080 resolution, English translation, and virtual LAN are automatically managed."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SOFT};")

        b_layout.addWidget(lbl_first_time)
        b_layout.addWidget(lbl_desc)
        main_layout.addWidget(bottom_box)
        main_layout.addStretch()

    def refresh_leader_card(self):
        deck = self.catalog.load_deck()
        leader_img = MASH_BMP
        leader_name = "Mash Kyrielight"

        if deck:
            first_item = deck[0]
            card_info = self.catalog.get_card_by_id(first_item.tc_id)
            if card_info and os.path.exists(card_info.image_path):
                leader_img = card_info.image_path
                leader_name = card_info.name_en or card_info.name_jp

        if os.path.exists(leader_img):
            pixmap = QPixmap(leader_img)
            scaled = pixmap.scaled(
                224, 308, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_card_img.setPixmap(scaled)
        else:
            self.lbl_card_img.setText("No Image")

        self.lbl_deck_info.setText(f"{len(deck)} / 30 cards - Leader: {leader_name}")

    def update_server_status(self, is_online: bool, text: str):
        if is_online:
            display_text = f"Online ({text})"
            color = Theme.READY
        else:
            display_text = "Offline (Auto-starts on Play)"
            color = Theme.TEXT_MUTED
        self.lbl_server_status.setText(display_text)
        self.lbl_server_status.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 500;")

    def _start_server(self):
        start_server_stack()

    def _stop_server(self):
        stop_server_stack()
