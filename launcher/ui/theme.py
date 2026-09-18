"""
UI Theme: Authentic colors, styles, and typography from Scooby cabinet design.
"""


class Theme:
    # Palette
    GROUND = "#121417"
    PLATE = "#1A1D22"
    PLATE_LOW = "#16191D"
    LINE = "#282D35"
    LINE_SOFT = "#22262C"
    ICE = "#7CC4E4"
    READY = "#85E89D"
    TEXT = "#E8EAED"
    TEXT_SOFT = "#B0B7C3"
    TEXT_MUTED = "#8F96A3"
    TEXT_FAINT = "#6F7681"
    DANGER = "#F0899A"

    # Button Styles
    PRIMARY_BUTTON = f"""
        QPushButton {{
            background-color: {ICE};
            color: #121417;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid {ICE};
            border-radius: 3px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            background-color: #93D2EE;
            border-color: #93D2EE;
        }}
        QPushButton:pressed {{
            background-color: #6EB2D1;
        }}
        QPushButton:disabled {{
            background-color: #2B3038;
            color: #6F7681;
            border-color: #2B3038;
        }}
    """

    SECONDARY_BUTTON = f"""
        QPushButton {{
            background-color: {PLATE};
            color: {TEXT};
            font-size: 13px;
            font-weight: 500;
            border: 1px solid {LINE};
            border-radius: 3px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            background-color: #23272E;
            border-color: #3A414B;
        }}
        QPushButton:pressed {{
            background-color: {GROUND};
        }}
        QPushButton:disabled {{
            background-color: {GROUND};
            color: {TEXT_FAINT};
            border-color: {LINE_SOFT};
        }}
    """

    DANGER_BUTTON = f"""
        QPushButton {{
            background-color: #33191E;
            color: {DANGER};
            font-size: 13px;
            font-weight: 500;
            border: 1px solid #6E2F3A;
            border-radius: 3px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            background-color: #3F1C24;
            border-color: #8A3A48;
        }}
        QPushButton:pressed {{
            background-color: #281418;
        }}
    """

    COMBOBOX = f"""
        QComboBox {{
            background-color: {PLATE};
            color: {TEXT};
            border: 1px solid {LINE};
            border-radius: 3px;
            padding: 4px 10px;
            font-size: 12px;
            min-height: 22px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border-color: {ICE};
        }}
        QComboBox:disabled {{
            background-color: {GROUND};
            color: {TEXT_FAINT};
            border-color: {LINE_SOFT};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border-left: 1px solid {LINE};
            background-color: {PLATE_LOW};
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
        }}
        QComboBox::drop-down:hover {{
            background-color: {LINE_SOFT};
        }}
        QComboBox::down-arrow {{
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {TEXT_MUTED};
        }}
        QComboBox::down-arrow:hover {{
            border-top-color: {ICE};
        }}
        QComboBox QAbstractItemView {{
            background-color: {PLATE};
            color: {TEXT};
            border: 1px solid {ICE};
            selection-background-color: {LINE};
            selection-color: {ICE};
            padding: 2px;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 24px;
            padding: 4px 8px;
            border: none;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {LINE_SOFT};
            color: {ICE};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {LINE};
            color: {ICE};
        }}
    """

    GLOBAL_QSS = f"""
        * {{
            outline: none;
        }}
        *:focus {{
            outline: none;
        }}
        QWidget {{
            background-color: {GROUND};
            color: {TEXT};
            font-family: 'Segoe UI', 'Yu Gothic UI', 'Microsoft YaHei UI', system-ui, sans-serif;
            font-size: 13px;
            selection-background-color: #1C2E38;
            selection-color: {ICE};
            outline: none;
        }}
        QPushButton {{
            outline: none;
        }}
        QPushButton:focus {{
            outline: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {LINE};
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #4F8AA6;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {LINE};
            min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: #4F8AA6;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QComboBox {{
            background-color: {PLATE};
            color: {TEXT};
            border: 1px solid {LINE};
            border-radius: 3px;
            padding: 4px 10px;
            font-size: 12px;
            min-height: 22px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border-color: {ICE};
        }}
        QComboBox:disabled {{
            background-color: {GROUND};
            color: {TEXT_FAINT};
            border-color: {LINE_SOFT};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border-left: 1px solid {LINE};
            background-color: {PLATE_LOW};
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
        }}
        QComboBox::drop-down:hover {{
            background-color: {LINE_SOFT};
        }}
        QComboBox::down-arrow {{
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {TEXT_MUTED};
        }}
        QComboBox::down-arrow:hover {{
            border-top-color: {ICE};
        }}
        QComboBox QAbstractItemView {{
            background-color: {PLATE};
            color: {TEXT};
            border: 1px solid {ICE};
            selection-background-color: {LINE};
            selection-color: {ICE};
            padding: 2px;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 24px;
            padding: 4px 8px;
            border: none;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {LINE_SOFT};
            color: {ICE};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {LINE};
            color: {ICE};
        }}
    """
