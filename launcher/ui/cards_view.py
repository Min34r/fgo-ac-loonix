"""
Cards View: Servant card catalog, sortie deck builder, and summon rates.
"""

import json
import math
import os
import shutil
import subprocess
from typing import List, Optional

from PyQt6.QtCore import QMimeData, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.core.card_catalog import CardCatalog, CardInfo, DeckItem
from launcher.ui.theme import Theme

try:
    from launcher.core.config import CARD_FILTERS_FILE, FGOA_ROOT, LOADOUTS_DIR
except ImportError:
    from ..core.config import CARD_FILTERS_FILE, FGOA_ROOT, LOADOUTS_DIR

CARD_DIR = os.path.join(FGOA_ROOT, "DEVICE", "print", "FGO11_AllServants")


class CardTileWidget(QFrame):
    clicked = pyqtSignal(object)
    double_clicked = pyqtSignal(object)

    def __init__(self, card: CardInfo, parent=None):
        super().__init__(parent)
        self.card = card
        self._drag_start_pos: Optional[QPoint] = None
        self.setFixedSize(148, 240)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 0px;
                padding: 4px;
            }}
            QFrame:hover {{
                border: 1px solid {Theme.ICE};
                background-color: #23272E;
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{card.name_en or card.name_jp}\n• Drag & drop onto deck shelf below to add\n• Double-click to change form / ascension / foil")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Image
        self.lbl_img = QLabel()
        self.lbl_img.setFixedSize(134, 160)
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setStyleSheet("background-color: #0E1013; border: 1px solid #2B3038;")

        if os.path.exists(card.image_path):
            pix = QPixmap(card.image_path).scaled(
                134, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_img.setPixmap(pix)
        else:
            self.lbl_img.setText("No Img")

        # Name
        self.lbl_name_en = QLabel(card.name_en or card.name_jp or "Unknown")
        self.lbl_name_en.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px; font-weight: 600;")
        self.lbl_name_en.setWordWrap(True)
        self.lbl_name_en.setMaximumHeight(32)

        # Details
        stars = "★" * card.rarity if card.rarity > 0 else ""
        class_str = card.class_name if card.class_name else "Craft"
        fatal_badge = " [FATAL]" if card.is_holo else ""
        self.lbl_sub = QLabel(f"{class_str}  {stars}{fatal_badge}")
        self.lbl_sub.setStyleSheet(
            f"color: {'#E5C07B' if card.is_holo else Theme.TEXT_SOFT}; "
            f"font-size: 11px; font-weight: {'600' if card.is_holo else 'normal'};"
        )

        layout.addWidget(self.lbl_img)
        layout.addWidget(self.lbl_name_en)
        layout.addWidget(self.lbl_sub)
        layout.addStretch()

    def update_card(self, new_card: CardInfo):
        self.card = new_card
        if os.path.exists(new_card.image_path):
            pix = QPixmap(new_card.image_path).scaled(
                134, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_img.setPixmap(pix)
        else:
            self.lbl_img.setText("No Img")

        self.lbl_name_en.setText(new_card.name_en or new_card.name_jp or "Unknown")
        stars = "★" * new_card.rarity if new_card.rarity > 0 else ""
        class_str = new_card.class_name if new_card.class_name else "Craft"
        fatal_badge = " [FATAL]" if new_card.is_holo else ""
        self.lbl_sub.setText(f"{class_str}  {stars}{fatal_badge}")
        self.lbl_sub.setStyleSheet(
            f"color: {'#E5C07B' if new_card.is_holo else Theme.TEXT_SOFT}; "
            f"font-size: 11px; font-weight: {'600' if new_card.is_holo else 'normal'};"
        )
        self.setToolTip(f"{new_card.name_en or new_card.name_jp}\n• Drag & drop onto deck shelf below to add\n• Double-click to change form / ascension / foil")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.clicked.emit(self.card)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._drag_start_pos:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(f"fgo_card:{self.card.tc_id}")
        drag.setMimeData(mime)

        if os.path.exists(self.card.image_path):
            pix = QPixmap(self.card.image_path).scaled(
                70, 98, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            drag.setPixmap(pix)
            drag.setHotSpot(QPoint(pix.width() // 2, pix.height() // 2))

        drag.exec(Qt.DropAction.CopyAction)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.card)
        super().mouseDoubleClickEvent(event)


class CardVariantsDialog(QDialog):
    """Dialog allowing user to choose ascension stage and foil type."""

    def __init__(self, base_card: CardInfo, catalog: CardCatalog, parent=None):
        super().__init__(parent)
        self.base_card = base_card
        self.catalog = catalog
        self.selected_variant: CardInfo = base_card

        self.setWindowTitle(f"Card Art & Form - {base_card.name_en or base_card.name_jp}")
        self.setFixedWidth(520)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.GROUND};
                color: {Theme.TEXT};
                font-family: 'Segoe UI', system-ui, sans-serif;
            }}
            QLabel {{
                color: {Theme.TEXT};
            }}
            QComboBox {{
                background-color: {Theme.PLATE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.LINE};
                border-radius: 3px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Theme.PLATE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.ICE};
                selection-background-color: {Theme.LINE};
                selection-color: {Theme.ICE};
                padding: 2px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 26px;
                padding: 4px 8px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {Theme.LINE_SOFT};
                color: {Theme.ICE};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header info
        lbl_title = QLabel(base_card.name_en or base_card.name_jp)
        lbl_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {Theme.TEXT};")
        lbl_jp = QLabel(base_card.name_jp)
        lbl_jp.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SOFT};")
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_jp)

        # Center preview image & details
        preview_row = QHBoxLayout()
        preview_row.setSpacing(16)

        self.lbl_preview = QLabel()
        self.lbl_preview.setFixedSize(110, 150)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid {Theme.LINE};")
        preview_row.addWidget(self.lbl_preview)

        v_info = QVBoxLayout()
        v_info.setSpacing(8)

        lbl_variant = QLabel("Select Ascension Stage & Foil:")
        lbl_variant.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.TEXT_SOFT};")
        self.cmb_variant = QComboBox()
        self.cmb_variant.setFixedHeight(34)

        # Find all matching variants for this card_id (e.g. SVT00011)
        self.variants = [c for c in catalog.cards if c.card_id == base_card.card_id]
        if not self.variants:
            self.variants = [base_card]

        init_idx = 0
        for i, v in enumerate(self.variants):
            foil = "Holo / Fatal" if v.is_holo else "Normal"
            asc = v.ascension if v.ascension else "Base"
            self.cmb_variant.addItem(f"{asc} ({foil}) - ID: {v.tc_id}", v)
            if v.tc_id == base_card.tc_id:
                init_idx = i

        self.cmb_variant.setCurrentIndex(init_idx)
        self.cmb_variant.currentIndexChanged.connect(self._on_variant_changed)

        v_info.addWidget(lbl_variant)
        v_info.addWidget(self.cmb_variant)

        self.lbl_details = QLabel()
        self.lbl_details.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px; line-height: 1.4;")
        v_info.addWidget(self.lbl_details)
        v_info.addStretch()

        preview_row.addLayout(v_info)
        layout.addLayout(preview_row)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_cancel.setFixedHeight(32)
        btn_cancel.clicked.connect(self.reject)

        btn_apply = QPushButton("Apply Art / Variant")
        btn_apply.setStyleSheet(Theme.PRIMARY_BUTTON)
        btn_apply.setFixedHeight(32)
        btn_apply.clicked.connect(self._confirm)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_apply)
        layout.addLayout(btn_row)

        self._on_variant_changed()

    def _on_variant_changed(self):
        v = self.cmb_variant.currentData() or self.base_card
        if os.path.exists(v.image_path):
            pix = QPixmap(v.image_path).scaled(
                110, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_preview.setPixmap(pix)
        else:
            self.lbl_preview.setText("No Art")

        foil_text = "Holographic / Fatal Edition" if v.is_holo else "Standard Normal Card"
        asc_text = v.ascension or "Base Form"
        stars = "★" * v.rarity if v.rarity > 0 else ""
        self.lbl_details.setText(f"Rarity: {stars} ({v.rarity} Star)\nClass: {v.class_name}\nForm: {asc_text}\nType: {foil_text}\nCard ID: {v.card_id} (#{v.tc_id})")

    def _confirm(self):
        self.selected_variant = self.cmb_variant.currentData() or self.base_card
        self.accept()


class DeckSlotWidget(QFrame):
    double_clicked = pyqtSignal(int)  # slot index
    remove_clicked = pyqtSignal(int)  # slot index

    def __init__(self, index: int, deck_item: DeckItem, card_info: Optional[CardInfo], parent=None):
        super().__init__(parent)
        self.index = index
        self.deck_item = deck_item
        self.card_info = card_info
        self.setFixedSize(68, 98)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
            }}
            QFrame:hover {{
                border: 1px solid {Theme.ICE};
            }}
        """)
        self.setToolTip(f"{card_info.name_en or card_info.name_jp if card_info else f'Card #{deck_item.tc_id}'}\n• Double-click to swap ascension / holo art\n• Click × to remove from deck")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        sl = QVBoxLayout(self)
        sl.setContentsMargins(2, 2, 2, 2)
        sl.setSpacing(2)

        lbl_thumb = QLabel()
        lbl_thumb.setFixedSize(62, 74)
        lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if card_info and os.path.exists(card_info.image_path):
            pix = QPixmap(card_info.image_path).scaled(
                62, 74, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            lbl_thumb.setPixmap(pix)
        else:
            lbl_thumb.setText(f"#{index + 1}")

        btn_rem = QPushButton("×")
        btn_rem.setFixedHeight(16)
        btn_rem.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.DANGER};
                border: none;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Theme.DANGER}22;
            }}
        """)
        btn_rem.clicked.connect(lambda: self.remove_clicked.emit(self.index))

        sl.addWidget(lbl_thumb)
        sl.addWidget(btn_rem)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.index)
        super().mouseDoubleClickEvent(event)


class DeckShelfScroll(QScrollArea):
    card_dropped = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("fgo_card:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("fgo_card:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        text = event.mimeData().text()
        if text.startswith("fgo_card:"):
            try:
                tc_id = int(text.split(":", 1)[1])
                self.card_dropped.emit(tc_id)
                event.acceptProposedAction()
            except ValueError:
                event.ignore()
        else:
            event.ignore()


class DeckShelfContainer(QWidget):
    card_dropped = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("fgo_card:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("fgo_card:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        text = event.mimeData().text()
        if text.startswith("fgo_card:"):
            try:
                tc_id = int(text.split(":", 1)[1])
                self.card_dropped.emit(tc_id)
                event.acceptProposedAction()
            except ValueError:
                event.ignore()
        else:
            event.ignore()


class CardsView(QWidget):
    """
    Cards & Deck management view with complete loadout support.
    """
    deck_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = CardCatalog()
        self.loaded_cards: List[CardInfo] = []
        self.deck_items: List[DeckItem] = []
        self.current_page: int = 1
        self.cards_per_page: int = 120
        self.total_pages: int = 1
        self._filtered_cards: List[CardInfo] = []
        self._is_loading_filters: bool = False
        os.makedirs(LOADOUTS_DIR, exist_ok=True)

        self._init_ui()
        self._load_filter_state()
        self.reload_cards()
        self._refresh_loadouts_list()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(10)

        # Top Subtabs: Deck | Draw Rates
        self.subtabs = QTabWidget()
        self.subtabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {Theme.TEXT_MUTED};
                font-size: 14px;
                font-weight: 500;
                padding: 6px 18px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {Theme.ICE};
                font-weight: 600;
                border-bottom: 2px solid {Theme.ICE};
            }}
            QTabBar::tab:hover:!selected {{
                color: {Theme.TEXT};
            }}
        """)

        # Tab 1: Deck
        tab_deck = QWidget()
        layout_deck = QVBoxLayout(tab_deck)
        layout_deck.setContentsMargins(0, 8, 0, 0)
        layout_deck.setSpacing(10)

        # -------------------------------------------------------------
        # Filter & Search Toolbar (2-Row Responsive Panel)
        # -------------------------------------------------------------
        filter_panel = QFrame()
        filter_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
            }}
        """)
        filter_vlayout = QVBoxLayout(filter_panel)
        filter_vlayout.setContentsMargins(10, 8, 10, 8)
        filter_vlayout.setSpacing(8)

        # Row 1: Search & Core Category Filters
        bar1 = QHBoxLayout()
        bar1.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search name, ID (SVT001), class, or CE effect...")
        self.txt_search.setFixedHeight(30)
        self.txt_search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.GROUND};
                border: 1px solid {Theme.LINE};
                color: {Theme.TEXT};
                padding: 4px 10px;
                font-size: 12px;
            }}
        """)
        self.txt_search.textChanged.connect(self._on_search_text_changed)
        bar1.addWidget(self.txt_search, stretch=3)

        # Card Type: All, Servants, Craft Essences
        self.cmb_type = QComboBox()
        self.cmb_type.addItem("All Types", "ALL")
        self.cmb_type.addItem("Servants (SVT)", "SVT")
        self.cmb_type.addItem("Craft Essences (CE)", "CE")
        self.cmb_type.setFixedHeight(30)
        self.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        bar1.addWidget(self.cmb_type)

        # Servant Class
        self.cmb_class = QComboBox()
        self.cmb_class.addItem("All Classes", "ALL")
        for cls_name in ["Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker", "Extra"]:
            self.cmb_class.addItem(cls_name, cls_name)
        self.cmb_class.setFixedHeight(30)
        self.cmb_class.currentIndexChanged.connect(self._on_filter_changed)
        bar1.addWidget(self.cmb_class)

        # Rarity
        self.cmb_rarity = QComboBox()
        self.cmb_rarity.addItem("All Rarities", 0)
        for r in range(5, 0, -1):
            self.cmb_rarity.addItem(f"{r} Star ({'★'*r})", r)
        self.cmb_rarity.setFixedHeight(30)
        self.cmb_rarity.currentIndexChanged.connect(self._on_filter_changed)
        bar1.addWidget(self.cmb_rarity)

        # Reset button
        self.btn_reset_filters = QPushButton("Reset Filters")
        self.btn_reset_filters.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_reset_filters.setFixedHeight(30)
        self.btn_reset_filters.clicked.connect(self._reset_filters)
        bar1.addWidget(self.btn_reset_filters)

        filter_vlayout.addLayout(bar1)

        # Row 2: Secondary Filters, Badges & Pagination
        bar2 = QHBoxLayout()
        bar2.setSpacing(10)

        lbl_foil = QLabel("Foil:")
        lbl_foil.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px;")
        bar2.addWidget(lbl_foil)

        self.cmb_foil = QComboBox()
        self.cmb_foil.addItem("All Foils", "ALL")
        self.cmb_foil.addItem("Normal Only", "NORMAL")
        self.cmb_foil.addItem("Fatal / Holo Only", "HOLO")
        self.cmb_foil.setFixedHeight(26)
        self.cmb_foil.currentIndexChanged.connect(self._on_filter_changed)
        bar2.addWidget(self.cmb_foil)

        self.chk_owned = QCheckBox("Owned cards only")
        self.chk_owned.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px;")
        self.chk_owned.toggled.connect(self._on_filter_changed)
        bar2.addWidget(self.chk_owned)

        self.chk_group = QCheckBox("Group variants (1 tile/card)")
        self.chk_group.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px;")
        self.chk_group.toggled.connect(self._on_filter_changed)
        bar2.addWidget(self.chk_group)

        bar2.addStretch()

        # Pagination Controls
        btn_nav_style = f"""
            QPushButton {{
                background-color: {Theme.PLATE};
                color: {Theme.TEXT};
                font-size: 13px;
                font-weight: 600;
                border: 1px solid {Theme.LINE};
                border-radius: 3px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #23272E;
                border-color: #3A414B;
            }}
            QPushButton:pressed {{
                background-color: {Theme.GROUND};
            }}
            QPushButton:disabled {{
                background-color: {Theme.GROUND};
                color: {Theme.TEXT_FAINT};
                border-color: {Theme.LINE_SOFT};
            }}
        """

        self.btn_first = QPushButton("⏮")
        self.btn_first.setToolTip("First Page")
        self.btn_first.setStyleSheet(btn_nav_style)
        self.btn_first.setFixedSize(28, 26)
        self.btn_first.clicked.connect(self._go_first_page)
        bar2.addWidget(self.btn_first)

        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.setToolTip("Previous Page")
        self.btn_prev.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_prev.setFixedHeight(26)
        self.btn_prev.clicked.connect(self._go_prev_page)
        bar2.addWidget(self.btn_prev)

        self.lbl_page_info = QLabel("Page 1 of 1")
        self.lbl_page_info.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; font-weight: 600; padding: 0 4px;")
        bar2.addWidget(self.lbl_page_info)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setToolTip("Next Page")
        self.btn_next.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_next.setFixedHeight(26)
        self.btn_next.clicked.connect(self._go_next_page)
        bar2.addWidget(self.btn_next)

        self.btn_last = QPushButton("⏭")
        self.btn_last.setToolTip("Last Page")
        self.btn_last.setStyleSheet(btn_nav_style)
        self.btn_last.setFixedSize(28, 26)
        self.btn_last.clicked.connect(self._go_last_page)
        bar2.addWidget(self.btn_last)

        self.cmb_per_page = QComboBox()
        self.cmb_per_page.addItem("60 / page", 60)
        self.cmb_per_page.addItem("120 / page", 120)
        self.cmb_per_page.addItem("240 / page", 240)
        self.cmb_per_page.setCurrentIndex(1)  # Default 120
        self.cmb_per_page.setFixedHeight(26)
        self.cmb_per_page.currentIndexChanged.connect(self._on_per_page_changed)
        bar2.addWidget(self.cmb_per_page)

        self.lbl_results = QLabel("Showing 0 cards")
        self.lbl_results.setStyleSheet(f"color: {Theme.ICE}; font-size: 12px; font-weight: 600; margin-left: 4px;")
        bar2.addWidget(self.lbl_results)

        self.btn_reload = QPushButton("Reload")
        self.btn_reload.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_reload.setFixedHeight(26)
        self.btn_reload.clicked.connect(self.reload_cards)
        bar2.addWidget(self.btn_reload)

        filter_vlayout.addLayout(bar2)
        layout_deck.addWidget(filter_panel)

        # -------------------------------------------------------------
        # Center Catalog Grid
        # -------------------------------------------------------------
        self.scroll_catalog = QScrollArea()
        self.scroll_catalog.setWidgetResizable(True)
        self.scroll_catalog.setStyleSheet(f"background-color: {Theme.GROUND}; border: 1px solid {Theme.LINE};")

        self.catalog_list = QListWidget()
        self.catalog_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.catalog_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.catalog_list.setSpacing(10)
        self.catalog_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {Theme.GROUND};
                border: none;
                outline: none;
            }}
        """)
        self.scroll_catalog.setWidget(self.catalog_list)
        layout_deck.addWidget(self.scroll_catalog, stretch=1)

        # -------------------------------------------------------------
        # Bottom Deck Shelf & Loadouts Control Panel
        # -------------------------------------------------------------
        shelf_box = QFrame()
        shelf_box.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
            }}
        """)
        shelf_vlayout = QVBoxLayout(shelf_box)
        shelf_vlayout.setContentsMargins(12, 10, 12, 10)
        shelf_vlayout.setSpacing(8)

        # Row 1: Status & Clear Deck
        row_status = QHBoxLayout()
        self.lbl_deck_count = QLabel("Deck (0 / 30)")
        self.lbl_deck_count.setStyleSheet(f"color: {Theme.ICE}; font-size: 13px; font-weight: 700;")
        row_status.addWidget(self.lbl_deck_count)
        row_status.addStretch()

        self.btn_clear = QPushButton("Clear Deck")
        self.btn_clear.setStyleSheet(Theme.DANGER_BUTTON)
        self.btn_clear.clicked.connect(self._clear_deck)
        row_status.addWidget(self.btn_clear)
        shelf_vlayout.addLayout(row_status)

        # Row 2: Loadouts Management Controls
        row_loadouts = QHBoxLayout()
        row_loadouts.setSpacing(8)

        lbl_loadouts = QLabel("Loadouts")
        lbl_loadouts.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; font-weight: 500;")
        row_loadouts.addWidget(lbl_loadouts)

        self.cmb_loadouts = QComboBox()
        self.cmb_loadouts.setMinimumWidth(200)
        self.cmb_loadouts.setFixedHeight(30)
        self.cmb_loadouts.setToolTip("Saved deck loadouts. Click Load to apply to the active sortie deck.")
        row_loadouts.addWidget(self.cmb_loadouts)

        self.btn_save_as = QPushButton("Save as")
        self.btn_load = QPushButton("Load")
        self.btn_delete = QPushButton("Delete")
        self.btn_export = QPushButton("Export")
        self.btn_import = QPushButton("Import")
        self.btn_open_folder = QPushButton("Open folder")

        self.btn_save_as.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_load.setStyleSheet(Theme.PRIMARY_BUTTON)
        self.btn_delete.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_export.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_import.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_open_folder.setStyleSheet(Theme.SECONDARY_BUTTON)

        self.btn_save_as.clicked.connect(self._save_loadout_as)
        self.btn_load.clicked.connect(self._load_selected_loadout)
        self.btn_delete.clicked.connect(self._delete_selected_loadout)
        self.btn_export.clicked.connect(self._export_selected_loadout)
        self.btn_import.clicked.connect(self._import_loadout)
        self.btn_open_folder.clicked.connect(self._open_loadouts_folder)

        row_loadouts.addWidget(self.btn_save_as)
        row_loadouts.addWidget(self.btn_load)
        row_loadouts.addWidget(self.btn_delete)
        row_loadouts.addWidget(self.btn_export)
        row_loadouts.addWidget(self.btn_import)
        row_loadouts.addWidget(self.btn_open_folder)
        row_loadouts.addStretch()

        shelf_vlayout.addLayout(row_loadouts)

        # Row 3: 30-Card Slot Shelf with Vertical Scrolling Grid
        self.shelf_scroll = DeckShelfScroll()
        self.shelf_scroll.setFixedHeight(170)
        self.shelf_scroll.setWidgetResizable(True)
        self.shelf_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.shelf_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.shelf_scroll.setStyleSheet(f"background-color: {Theme.GROUND}; border: 1px solid {Theme.LINE};")
        self.shelf_scroll.card_dropped.connect(self._on_card_dropped)

        self.shelf_widget = DeckShelfContainer()
        self.shelf_widget.card_dropped.connect(self._on_card_dropped)
        self.shelf_layout = QGridLayout(self.shelf_widget)
        self.shelf_layout.setContentsMargins(8, 8, 8, 8)
        self.shelf_layout.setSpacing(6)
        self.shelf_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.shelf_scroll.setWidget(self.shelf_widget)

        shelf_vlayout.addWidget(self.shelf_scroll)
        layout_deck.addWidget(shelf_box)

        # Tab 2: Draw Rates
        tab_rates = QWidget()
        rates_layout = QVBoxLayout(tab_rates)
        rates_layout.setContentsMargins(20, 20, 20, 20)
        lbl_rates = QLabel("Summon Lineup & Rates (Synchronized with Artemis server pool)")
        lbl_rates.setStyleSheet(f"color: {Theme.TEXT}; font-size: 14px; font-weight: 600;")
        lbl_rates_desc = QLabel(
            "Rates are configured in Server/artemis/titles/fgo/data/summon_candidates.json.\n"
            "Servant Rate: 1.00% (5★ Featured)\n"
            "Craft Essence Rate: 4.00% (5★ Featured)"
        )
        lbl_rates_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; line-height: 1.6; margin-top: 10px;")
        rates_layout.addWidget(lbl_rates)
        rates_layout.addWidget(lbl_rates_desc)
        rates_layout.addStretch()

        self.subtabs.addTab(tab_deck, "Deck")
        self.subtabs.addTab(tab_rates, "Draw Rates")
        main_layout.addWidget(self.subtabs)

        self._refresh_deck_ui()

    # -----------------------------------------------------------------
    # Filter State Persistence
    # -----------------------------------------------------------------
    def _load_filter_state(self):
        if not os.path.exists(CARD_FILTERS_FILE):
            return
        try:
            with open(CARD_FILTERS_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._is_loading_filters = True

            self.txt_search.blockSignals(True)
            self.cmb_type.blockSignals(True)
            self.cmb_class.blockSignals(True)
            self.cmb_rarity.blockSignals(True)
            self.cmb_foil.blockSignals(True)
            self.chk_owned.blockSignals(True)
            self.chk_group.blockSignals(True)
            self.cmb_per_page.blockSignals(True)

            if "query" in state and isinstance(state["query"], str):
                self.txt_search.setText(state["query"])

            if "card_type" in state:
                idx = self.cmb_type.findData(state["card_type"])
                if idx >= 0:
                    self.cmb_type.setCurrentIndex(idx)
                self.cmb_class.setEnabled(state["card_type"] != "CE")

            if "class_name" in state:
                idx = self.cmb_class.findData(state["class_name"])
                if idx >= 0:
                    self.cmb_class.setCurrentIndex(idx)

            if "rarity" in state:
                idx = self.cmb_rarity.findData(int(state["rarity"]))
                if idx >= 0:
                    self.cmb_rarity.setCurrentIndex(idx)

            if "foil" in state:
                idx = self.cmb_foil.findData(state["foil"])
                if idx >= 0:
                    self.cmb_foil.setCurrentIndex(idx)

            if "owned_only" in state:
                self.chk_owned.setChecked(bool(state["owned_only"]))

            if "group_variants" in state:
                self.chk_group.setChecked(bool(state["group_variants"]))

            if "per_page" in state:
                idx = self.cmb_per_page.findData(int(state["per_page"]))
                if idx >= 0:
                    self.cmb_per_page.setCurrentIndex(idx)
                    self.cards_per_page = int(state["per_page"])

            if "page" in state:
                self.current_page = max(1, int(state["page"]))

        except Exception as e:
            print(f"[CardsView] Error loading filter state: {e}")
        finally:
            self.txt_search.blockSignals(False)
            self.cmb_type.blockSignals(False)
            self.cmb_class.blockSignals(False)
            self.cmb_rarity.blockSignals(False)
            self.cmb_foil.blockSignals(False)
            self.chk_owned.blockSignals(False)
            self.chk_group.blockSignals(False)
            self.cmb_per_page.blockSignals(False)
            self._is_loading_filters = False

    def _save_filter_state(self):
        if self._is_loading_filters:
            return
        try:
            os.makedirs(os.path.dirname(CARD_FILTERS_FILE), exist_ok=True)
            state = {
                "query": self.txt_search.text(),
                "card_type": self.cmb_type.currentData() or "ALL",
                "class_name": self.cmb_class.currentData() or "ALL",
                "rarity": int(self.cmb_rarity.currentData() or 0),
                "foil": self.cmb_foil.currentData() or "ALL",
                "owned_only": self.chk_owned.isChecked(),
                "group_variants": self.chk_group.isChecked(),
                "per_page": int(self.cmb_per_page.currentData() or 120),
                "page": self.current_page,
            }
            with open(CARD_FILTERS_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[CardsView] Error saving filter state: {e}")

    # -----------------------------------------------------------------
    # Catalog Browsing & Card Addition
    # -----------------------------------------------------------------
    def reload_cards(self):
        self.catalog = CardCatalog()
        self.loaded_cards = self.catalog.get_all_cards()
        self._apply_filter(keep_page=True)

    def _on_search_text_changed(self):
        self.current_page = 1
        self._apply_filter(keep_page=False)

    def _on_type_changed(self):
        c_type = self.cmb_type.currentData() or "ALL"
        self.cmb_class.setEnabled(c_type != "CE")
        self.current_page = 1
        self._apply_filter(keep_page=False)

    def _on_filter_changed(self):
        self.current_page = 1
        self._apply_filter(keep_page=False)

    def _reset_filters(self):
        self._is_loading_filters = True
        self.txt_search.blockSignals(True)
        self.cmb_type.blockSignals(True)
        self.cmb_class.blockSignals(True)
        self.cmb_rarity.blockSignals(True)
        self.cmb_foil.blockSignals(True)
        self.chk_owned.blockSignals(True)
        self.chk_group.blockSignals(True)
        self.cmb_per_page.blockSignals(True)

        self.txt_search.clear()
        self.cmb_type.setCurrentIndex(0)
        self.cmb_class.setCurrentIndex(0)
        self.cmb_class.setEnabled(True)
        self.cmb_rarity.setCurrentIndex(0)
        self.cmb_foil.setCurrentIndex(0)
        self.chk_owned.setChecked(False)
        self.chk_group.setChecked(False)
        self.cmb_per_page.setCurrentIndex(1)  # 120
        self.cards_per_page = 120
        self.current_page = 1

        self.txt_search.blockSignals(False)
        self.cmb_type.blockSignals(False)
        self.cmb_class.blockSignals(False)
        self.cmb_rarity.blockSignals(False)
        self.cmb_foil.blockSignals(False)
        self.chk_owned.blockSignals(False)
        self.chk_group.blockSignals(False)
        self.cmb_per_page.blockSignals(False)
        self._is_loading_filters = False

        self._apply_filter(keep_page=False)

    def _apply_filter(self, keep_page: bool = False):
        query = self.txt_search.text().strip()
        c_type = self.cmb_type.currentData() or "ALL"
        c_class = self.cmb_class.currentData() or "ALL"
        target_rarity = int(self.cmb_rarity.currentData() or 0)
        foil_filter = self.cmb_foil.currentData() or "ALL"
        owned_only = self.chk_owned.isChecked()
        group_vars = self.chk_group.isChecked()

        self._filtered_cards = self.catalog.search(
            query=query,
            card_type=c_type,
            class_name=c_class,
            rarity=target_rarity,
            foil_filter=foil_filter,
            owned_only=owned_only,
            group_variants=group_vars,
        )

        total_matches = len(self._filtered_cards)
        self.total_pages = max(1, math.ceil(total_matches / self.cards_per_page))

        if not keep_page:
            self.current_page = 1
        else:
            self.current_page = max(1, min(self.current_page, self.total_pages))

        self._render_current_page()

    def _render_current_page(self):
        total_matches = len(self._filtered_cards)
        self.total_pages = max(1, math.ceil(total_matches / self.cards_per_page))
        self.current_page = max(1, min(self.current_page, self.total_pages))

        start_idx = (self.current_page - 1) * self.cards_per_page
        end_idx = min(start_idx + self.cards_per_page, total_matches)
        display_cards = self._filtered_cards[start_idx:end_idx]

        self.catalog_list.clear()
        for card in display_cards:
            tile = CardTileWidget(card)
            tile.double_clicked.connect(lambda c, t=tile: self._on_catalog_tile_double_clicked(c, t))

            item = QListWidgetItem(self.catalog_list)
            item.setSizeHint(QSize(152, 244))
            self.catalog_list.addItem(item)
            self.catalog_list.setItemWidget(item, tile)

        # Scroll catalog back to top on page render
        self.scroll_catalog.verticalScrollBar().setValue(0)
        self.catalog_list.verticalScrollBar().setValue(0)

        # Update pagination display
        self.lbl_page_info.setText(f"Page {self.current_page} of {self.total_pages}")
        if total_matches > 0:
            self.lbl_results.setText(f"Showing {start_idx + 1:,}–{end_idx:,} of {total_matches:,} cards")
        else:
            self.lbl_results.setText("No matching cards")

        self.btn_first.setEnabled(self.current_page > 1)
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < self.total_pages)
        self.btn_last.setEnabled(self.current_page < self.total_pages)

        self._save_filter_state()

    def _go_first_page(self):
        if self.current_page != 1:
            self.current_page = 1
            self._render_current_page()

    def _go_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_current_page()

    def _go_next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._render_current_page()

    def _go_last_page(self):
        if self.current_page != self.total_pages:
            self.current_page = self.total_pages
            self._render_current_page()

    def _on_per_page_changed(self):
        self.cards_per_page = int(self.cmb_per_page.currentData() or 120)
        self.current_page = 1
        self._render_current_page()

    def _on_catalog_tile_double_clicked(self, card: CardInfo, tile: CardTileWidget):
        dlg = CardVariantsDialog(card, self.catalog, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            tile.update_card(dlg.selected_variant)

    def _on_card_dropped(self, tc_id: int):
        card = self.catalog.get_card_by_id(tc_id)
        if card:
            self._add_card_copies(card, 1)

    def _on_deck_slot_double_clicked(self, index: int):
        if 0 <= index < len(self.deck_items):
            deck_item = self.deck_items[index]
            base_card = self.catalog.get_card_by_id(deck_item.tc_id)
            if not base_card:
                return
            dlg = CardVariantsDialog(base_card, self.catalog, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_v = dlg.selected_variant
                self.deck_items[index] = DeckItem(tc_id=new_v.tc_id, count=1, card_info=new_v, card=new_v)
                self.catalog.save_deck(self.deck_items)
                self._refresh_deck_ui()
                self.deck_changed.emit()

    def _add_card_copies(self, card: CardInfo, count: int):
        if len(self.deck_items) >= 30:
            QMessageBox.warning(self, "Deck Full", "The sortie deck cannot contain more than 30 cards.")
            return

        copies_in_deck = sum(1 for d in self.deck_items if d.tc_id == card.tc_id)
        space_left = 30 - len(self.deck_items)
        allowed = min(count, space_left, max(0, 5 - copies_in_deck))

        if allowed <= 0:
            QMessageBox.warning(self, "Limit Reached", "You cannot place more than 5 copies of the same card.")
            return

        for _ in range(allowed):
            self.deck_items.append(DeckItem(tc_id=card.tc_id, count=1, card_info=card, card=card))

        self.catalog.save_deck(self.deck_items)
        self._refresh_deck_ui()
        self.deck_changed.emit()

    def _refresh_deck_ui(self):
        self.deck_items = self.catalog.load_deck()
        self.lbl_deck_count.setText(f"Deck ({len(self.deck_items)} / 30)")

        # Clear shelf slots
        while self.shelf_layout.count() > 0:
            item = self.shelf_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = 10
        for idx, deck_item in enumerate(self.deck_items):
            row = idx // cols
            col = idx % cols

            card_info = self.catalog.get_card_by_id(deck_item.tc_id)
            slot = DeckSlotWidget(idx, deck_item, card_info)
            slot.remove_clicked.connect(self._remove_from_deck)
            slot.double_clicked.connect(self._on_deck_slot_double_clicked)
            self.shelf_layout.addWidget(slot, row, col)

    def _remove_from_deck(self, index: int):
        if 0 <= index < len(self.deck_items):
            self.deck_items.pop(index)
            self.catalog.save_deck(self.deck_items)
            self._refresh_deck_ui()
            self.deck_changed.emit()

    def _clear_deck(self):
        if not self.deck_items:
            return
        reply = QMessageBox.question(
            self,
            "Clear Deck",
            "Are you sure you want to clear all cards from the active sortie deck?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deck_items.clear()
            self.catalog.save_deck(self.deck_items)
            self._refresh_deck_ui()
            self.deck_changed.emit()

    # -----------------------------------------------------------------
    # Loadout Management Operations
    # -----------------------------------------------------------------
    def _refresh_loadouts_list(self, select_name: Optional[str] = None):
        os.makedirs(LOADOUTS_DIR, exist_ok=True)
        self.cmb_loadouts.blockSignals(True)
        self.cmb_loadouts.clear()

        files = sorted([f[:-5] for f in os.listdir(LOADOUTS_DIR) if f.endswith(".json")])
        for f in files:
            self.cmb_loadouts.addItem(f)

        if select_name and select_name in files:
            self.cmb_loadouts.setCurrentText(select_name)
        elif files:
            self.cmb_loadouts.setCurrentIndex(0)

        self.cmb_loadouts.blockSignals(False)

    def _save_loadout_as(self):
        if not self.deck_items:
            QMessageBox.warning(self, "Save Loadout", "The deck is empty - nothing to save.")
            return

        current_val = self.cmb_loadouts.currentText() or "My Deck"
        name, ok = QInputDialog.getText(self, "Save Loadout", "Name for this deck loadout:", text=current_val)
        if not ok or not name.strip():
            return
        name = name.strip()

        target = os.path.join(LOADOUTS_DIR, f"{name}.json")
        if os.path.exists(target):
            reply = QMessageBox.question(
                self,
                "Save Loadout",
                f"Replace the existing loadout '{name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        cards_data = []
        for item in self.deck_items:
            fn = item.card.filename if item.card else ""
            if not fn and item.card_info:
                fn = item.card_info.filename
            if not fn:
                c = self.catalog.get_card_by_id(item.tc_id)
                if c:
                    fn = c.filename
            if fn:
                cards_data.append({"file": fn, "copy": item.copies or item.count or 1})

        loadout_obj = {
            "format": "fgoac-loadout",
            "version": 1,
            "name": name,
            "cards": cards_data
        }

        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(loadout_obj, f, indent=2, ensure_ascii=False)
            self._refresh_loadouts_list(select_name=name)
            self.lbl_deck_count.setText(f"Deck ({len(self.deck_items)} / 30) - Saved: {name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save loadout: {e}")

    def _load_selected_loadout(self):
        name = self.cmb_loadouts.currentText()
        if not name:
            QMessageBox.warning(self, "Load Loadout", "Select a loadout to load first.")
            return

        target = os.path.join(LOADOUTS_DIR, f"{name}.json")
        if not os.path.exists(target):
            QMessageBox.warning(self, "Load Loadout", f"Loadout file '{name}.json' not found.")
            return

        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)

            new_items = []
            if "cards" in data and isinstance(data["cards"], list):
                for entry in data["cards"]:
                    fn = os.path.basename(entry.get("file", ""))
                    copy = entry.get("copy", 1)
                    card_info = self.catalog.filename_to_card.get(fn)
                    if card_info:
                        new_items.append(DeckItem(card=card_info, copies=copy, tc_id=card_info.tc_id, count=copy, card_info=card_info))
            elif "SelectedCards" in data and isinstance(data["SelectedCards"], list):
                copies = data.get("SelectedCardCopies", [])
                for idx, raw_path in enumerate(data["SelectedCards"]):
                    fn = os.path.basename(raw_path.replace("\\", "/"))
                    copy = copies[idx] if idx < len(copies) else 1
                    card_info = self.catalog.filename_to_card.get(fn)
                    if card_info:
                        new_items.append(DeckItem(card=card_info, copies=copy, tc_id=card_info.tc_id, count=copy, card_info=card_info))

            if not new_items:
                QMessageBox.warning(self, "Load Loadout", f"Loadout '{name}' contains no matching cards in the catalog.")
                return

            self.deck_items = new_items[:30]
            self.catalog.save_deck(self.deck_items)
            self._refresh_deck_ui()
            self.lbl_deck_count.setText(f"Deck ({len(self.deck_items)} / 30) - Loaded: {name}")
            self.deck_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load loadout: {e}")

    def _delete_selected_loadout(self):
        name = self.cmb_loadouts.currentText()
        if not name:
            return
        target = os.path.join(LOADOUTS_DIR, f"{name}.json")
        reply = QMessageBox.question(
            self,
            "Delete Loadout",
            f"Are you sure you want to delete the loadout '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(target):
                    os.remove(target)
                self._refresh_loadouts_list()
                self.lbl_deck_count.setText(f"Deck ({len(self.deck_items)} / 30) - Deleted: {name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete loadout: {e}")

    def _export_selected_loadout(self):
        name = self.cmb_loadouts.currentText()
        if not name:
            QMessageBox.warning(self, "Export Loadout", "Select a loadout to export first.")
            return

        src = os.path.join(LOADOUTS_DIR, f"{name}.json")
        if not os.path.exists(src):
            QMessageBox.warning(self, "Export Loadout", f"Loadout file '{name}.json' not found.")
            return

        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Export Loadout",
            os.path.expanduser(f"~/{name}.json"),
            "Loadout Files (*.json)"
        )
        if dest:
            try:
                shutil.copyfile(src, dest)
                QMessageBox.information(self, "Export Loadout", f"Exported '{name}.json' successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export loadout: {e}")

    def _import_loadout(self):
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Import Loadout",
            os.path.expanduser("~"),
            "Loadout Files (*.json)"
        )
        if not src:
            return

        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not (("format" in data and "cards" in data) or ("SelectedCards" in data)):
                QMessageBox.warning(self, "Import Loadout", "Selected file is not a recognized deck loadout JSON.")
                return

            name = data.get("name") or os.path.splitext(os.path.basename(src))[0]
            dest = os.path.join(LOADOUTS_DIR, f"{name}.json")
            shutil.copyfile(src, dest)
            self._refresh_loadouts_list(select_name=name)
            self._load_selected_loadout()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import loadout: {e}")

    def _open_loadouts_folder(self):
        os.makedirs(LOADOUTS_DIR, exist_ok=True)
        subprocess.run(["xdg-open", LOADOUTS_DIR], check=False)
