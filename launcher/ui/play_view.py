"""
Play View: Primary dashboard with hero leader card, play button, and server actions.
"""

import os
from typing import Optional
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
from launcher.core.config import CARD_DIR
from launcher.core.server_manager import start_server_stack, stop_server_stack
from launcher.ui.chamfer import ChamferButton
from launcher.ui.theme import Theme

MASH_BMP = os.path.join(CARD_DIR, "00130_SVT00011_A00_NORMAL.bmp")


class PlayView(QWidget):
    launch_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    open_logs_requested = pyqtSignal()

    def __init__(self, parent=None, catalog: Optional[CardCatalog] = None):
        super().__init__(parent)
        self.catalog = catalog or CardCatalog()
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

        self.lbl_card_img = QLabel("No Card")
        self.lbl_card_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_inner.addWidget(self.lbl_card_img)
        top_row.addWidget(self.card_border, alignment=Qt.AlignmentFlag.AlignTop)

        # -------------------------------------------------------------
        # Right: Chamfered Play Box + Status Lines + Action Buttons
        # -------------------------------------------------------------
        right_box = QVBoxLayout()
        right_box.setSpacing(16)

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

        status_frame = QFrame()
        status_frame.setStyleSheet(f"border-bottom: 1px solid {Theme.LINE_SOFT};")
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(0, 0, 0, 8)
        status_layout.setSpacing(8)

        self.lbl_server_status = QLabel("Checking server...")
        self.lbl_master_info = QLabel("Chaldea Master (Aime: 23189425320398932138)")
        self.lbl_deck_info = QLabel("Loading deck...")

        for title, val_lbl in (
            ("Server", self.lbl_server_status),
            ("Master", self.lbl_master_info),
            ("Deck", self.lbl_deck_info),
        ):
            row = QHBoxLayout()
            lbl = QLabel(title)
            lbl.setFixedWidth(80)
            lbl.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
            val_lbl.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
            row.addWidget(lbl)
            row.addWidget(val_lbl)
            row.addStretch()
            status_layout.addLayout(row)

        right_box.addWidget(status_frame)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.btn_srv_start = QPushButton("Start server")
        self.btn_srv_stop = QPushButton("Stop server")
        self.btn_open_logs = QPushButton("Open logs")
        self.btn_stop_game = QPushButton("Stop game")

        for btn, style, slot in (
            (self.btn_srv_start, Theme.SECONDARY_BUTTON, start_server_stack),
            (self.btn_srv_stop, Theme.SECONDARY_BUTTON, stop_server_stack),
            (self.btn_open_logs, Theme.SECONDARY_BUTTON, self.open_logs_requested.emit),
            (self.btn_stop_game, Theme.DANGER_BUTTON, self.stop_requested.emit),
        ):
            btn.setStyleSheet(style)
            btn.clicked.connect(slot)
            actions_row.addWidget(btn)
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
            "Click Play above to start playing. The local server is automatically "
            "started and shut down on exit. Use the Cards and Deck tab to manage your party loadout. "
            "English translation, and virtual LAN are all automatically managed."
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

        if deck and (card_info := deck[0].card or self.catalog.get_card_by_id(deck[0].tc_id)):
            if os.path.exists(card_info.image_path):
                leader_img = card_info.image_path
                leader_name = card_info.name_en or card_info.name_jp

        if os.path.exists(leader_img):
            self.lbl_card_img.setPixmap(
                QPixmap(leader_img).scaled(
                    224, 308, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            self.lbl_card_img.setText("No Image")

        self.lbl_deck_info.setText(f"{len(deck)} / 30 cards - Leader: {leader_name}")

    def update_server_status(self, is_online: bool, text: str):
        display_text = f"Online ({text})" if is_online else "Offline (Auto-starts on Play)"
        color = Theme.READY if is_online else Theme.TEXT_MUTED
        self.lbl_server_status.setText(display_text)
        self.lbl_server_status.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 500;")
