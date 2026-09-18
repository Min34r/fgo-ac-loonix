"""
Settings View: Display, Controls (segatools.ini), and Audio configurations.
"""

import json
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.theme import Theme, OpaqueComboBox

try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from ..core.config import FGOA_ROOT

try:
    from launcher.core.translation_installer import TranslationInstallerWorker, is_translation_installed
except ImportError:
    from ..core.translation_installer import TranslationInstallerWorker, is_translation_installed

try:
    from launcher.core.controls_manager import (
        DEFAULT_CONTROLS,
        VK_MAP,
        get_segatools_ini_path,
        load_controls_config,
        qt_key_to_vk,
        save_controls_config,
        vk_to_display_name,
    )
except ImportError:
    from ..core.controls_manager import (
        DEFAULT_CONTROLS,
        VK_MAP,
        get_segatools_ini_path,
        load_controls_config,
        qt_key_to_vk,
        save_controls_config,
        vk_to_display_name,
    )

CONFIG_JSON = os.path.join(FGOA_ROOT, "App", "fgo-launcher.json")


# ==============================================================================
# Key Rebinding Dialog
# ==============================================================================

class KeyCaptureDialog(QDialog):
    """Modal dialog to capture a keypress or mouse click to rebind an action."""

    def __init__(self, action_name: str, current_vk: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rebind: {action_name}")
        self.setFixedSize(480, 310)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.GROUND};
                border: 1px solid {Theme.LINE};
            }}
        """)
        self.captured_vk = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        lbl_title = QLabel(f"Rebinding: <b>{action_name}</b>")
        lbl_title.setStyleSheet(f"font-size: 16px; color: {Theme.TEXT}; font-weight: 700;")
        layout.addWidget(lbl_title)

        curr_name = vk_to_display_name(current_vk)
        lbl_curr = QLabel(f"Current Binding: <font color='{Theme.ICE}'><b>{curr_name}</b> ({current_vk})</font>")
        lbl_curr.setStyleSheet(f"font-size: 13px; color: {Theme.TEXT_SOFT};")
        layout.addWidget(lbl_curr)

        # Big Interactive Key Listener Box
        self.box_listen = QFrame()
        self.box_listen.setObjectName("box_listen")
        self.box_listen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.box_listen.setStyleSheet(f"""
            QFrame#box_listen {{
                background-color: {Theme.PLATE};
                border: 2px dashed {Theme.ICE};
                border-radius: 6px;
            }}
            QFrame#box_listen:hover {{
                background-color: #23272E;
                border: 2px solid {Theme.ICE};
            }}
        """)
        l_box = QVBoxLayout(self.box_listen)
        l_box.setContentsMargins(16, 18, 16, 18)
        l_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l_box.setSpacing(4)

        self.lbl_prompt = QLabel("PRESS ANY KEY OR MOUSE BUTTON")
        self.lbl_prompt.setStyleSheet(f"color: {Theme.ICE}; font-size: 14px; font-weight: 700;")
        self.lbl_subprompt = QLabel("Press any keyboard key, Right Click, or Middle Click")
        self.lbl_subprompt.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px;")

        l_box.addWidget(self.lbl_prompt, alignment=Qt.AlignmentFlag.AlignCenter)
        l_box.addWidget(self.lbl_subprompt, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.box_listen)

        # Quick common presets row
        lbl_common = QLabel("Or click to bind directly:")
        lbl_common.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px;")
        layout.addWidget(lbl_common)

        row_quick = QHBoxLayout()
        row_quick.setSpacing(6)

        quick_keys = [
            ("Left Click", "0x1"),
            ("Right Click", "0x2"),
            ("Middle Click", "0x4"),
            ("Space", "0x20"),
            ("Enter", "0xD"),
            ("Shift", "0xA0"),
        ]
        for name, vk_code in quick_keys:
            btn = QPushButton(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.PLATE};
                    color: {Theme.TEXT};
                    border: 1px solid {Theme.LINE};
                    padding: 4px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    border: 1px solid {Theme.ICE};
                    color: {Theme.ICE};
                }}
            """)
            btn.clicked.connect(lambda _, code=vk_code: self._confirm_vk(code))
            row_quick.addWidget(btn)

        layout.addLayout(row_quick)
        layout.addStretch()

        # Bottom Cancel
        row_btn = QHBoxLayout()
        row_btn.addStretch()
        btn_cancel = QPushButton("Cancel (Esc)")
        btn_cancel.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_cancel.clicked.connect(self.reject)
        row_btn.addWidget(btn_cancel)
        layout.addLayout(row_btn)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
            return
        vk = qt_key_to_vk(key)
        if vk:
            self._confirm_vk(vk)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        btn = event.button()
        if btn == Qt.MouseButton.RightButton:
            self._confirm_vk("0x2")
        elif btn == Qt.MouseButton.MiddleButton:
            self._confirm_vk("0x4")
        else:
            super().mousePressEvent(event)

    def _confirm_vk(self, vk: str):
        self.captured_vk = vk
        self.accept()


# ==============================================================================
# Direct INI Editor Dialog
# ==============================================================================

class IniEditorDialog(QDialog):
    """Monospaced text editor dialog to directly inspect and edit segatools.ini."""

    def __init__(self, ini_path: str, parent=None):
        super().__init__(parent)
        self.ini_path = ini_path
        self.setWindowTitle(f"Direct INI Editor: {os.path.basename(ini_path)}")
        self.resize(760, 620)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.GROUND};
                border: 1px solid {Theme.LINE};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        lbl_header = QLabel(f"File: <font color='{Theme.ICE}'><b>{ini_path}</b></font>")
        lbl_header.setStyleSheet(f"font-size: 13px; color: {Theme.TEXT};")
        layout.addWidget(lbl_header)

        self.txt_editor = QPlainTextEdit()
        mono_font = QFont("Monospace", 10)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self.txt_editor.setFont(mono_font)
        self.txt_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                color: {Theme.TEXT};
                padding: 10px;
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.txt_editor, stretch=1)

        self._load_file()

        btn_layout = QHBoxLayout()
        btn_reload = QPushButton("Reload from Disk")
        btn_reload.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_reload.clicked.connect(self._load_file)
        btn_layout.addWidget(btn_reload)

        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save & Close")
        btn_save.setStyleSheet(Theme.PRIMARY_BUTTON)
        btn_save.clicked.connect(self._save_file)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _load_file(self):
        if os.path.isfile(self.ini_path):
            try:
                with open(self.ini_path, "r", encoding="utf-8", errors="ignore") as f:
                    self.txt_editor.setPlainText(f.read())
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")
        else:
            self.txt_editor.setPlainText(f"; File not found at: {self.ini_path}")

    def _save_file(self):
        try:
            with open(self.ini_path, "w", encoding="utf-8") as f:
                f.write(self.txt_editor.toPlainText())
            QMessageBox.information(self, "Saved", f"Successfully saved {os.path.basename(self.ini_path)}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")


# ==============================================================================
# Interactive Key Binding Row
# ==============================================================================

class KeyBindingRow(QFrame):
    def __init__(self, action_key: str, action_name: str, current_vk: str, on_changed=None, parent=None):
        super().__init__(parent)
        self.action_key = action_key
        self.action_name = action_name
        self.current_vk = str(current_vk)
        self.on_changed = on_changed

        self.setStyleSheet("background-color: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(16)

        self.lbl_action = QLabel(action_name)
        self.lbl_action.setFixedWidth(220)
        self.lbl_action.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px; font-weight: 500;")

        self.btn_key = QPushButton(self._format_binding(self.current_vk))
        self.btn_key.setFixedHeight(34)
        self.btn_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_key.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                color: {Theme.ICE};
                text-align: center;
                font-size: 13px;
                font-weight: 600;
                padding: 4px 16px;
            }}
            QPushButton:hover {{
                border-color: {Theme.ICE};
                background-color: {Theme.GROUND};
            }}
        """)
        self.btn_key.clicked.connect(self._open_rebind_dialog)

        layout.addWidget(self.lbl_action)
        layout.addWidget(self.btn_key, stretch=1)

    def _format_binding(self, vk: str) -> str:
        name = vk_to_display_name(vk)
        return f"{name}  [{vk}]"

    def set_vk(self, vk: str):
        self.current_vk = str(vk)
        self.btn_key.setText(self._format_binding(self.current_vk))

    def _open_rebind_dialog(self):
        dlg = KeyCaptureDialog(self.action_name, self.current_vk, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_vk:
            self.set_vk(dlg.captured_vk)
            if self.on_changed:
                self.on_changed(self.action_key, dlg.captured_vk)


# ==============================================================================
# Main Settings View
# ==============================================================================

class SettingsView(QWidget):
    """
    Settings configuration view with subtabs for Display, Controls (segatools.ini), and Audio.
    """
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trans_worker = None
        self._controls = load_controls_config()
        self._key_rows: Dict[str, KeyBindingRow] = {}

        self._init_ui()
        self._load_config()
        self._refresh_translation_status()
        self._refresh_controls_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 20, 28, 20)
        main_layout.setSpacing(14)

        # Top Subtabs
        subtab_bar = QHBoxLayout()
        subtab_bar.setSpacing(16)

        self.btn_sub_disp = QPushButton("Display")
        self.btn_sub_ctrl = QPushButton("Controls (segatools.ini)")
        self.btn_sub_aud = QPushButton("Audio")

        self.subtab_buttons = [self.btn_sub_disp, self.btn_sub_ctrl, self.btn_sub_aud]

        for idx, btn in enumerate(self.subtab_buttons):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, i=idx: self._switch_subtab(i))
            subtab_bar.addWidget(btn)

        subtab_bar.addStretch()
        main_layout.addLayout(subtab_bar)

        self.sub_stack = QStackedWidget()

        # =============================================================
        # Subtab 1: Display
        # =============================================================
        page_disp = QWidget()
        l_disp = QVBoxLayout(page_disp)
        l_disp.setContentsMargins(0, 10, 0, 0)
        l_disp.setSpacing(16)
        l_disp.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        lbl_mode = QLabel("Screen Presentation Mode")
        lbl_mode.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT};")
        l_disp.addWidget(lbl_mode)

        row_disp_mode = QHBoxLayout()
        row_disp_mode.setSpacing(24)

        self.rb_fullscreen = QRadioButton("Exclusive Fullscreen (Optimal for 1080p Arcade)")
        self.rb_fullscreen.setChecked(True)
        self.rb_fullscreen.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        row_disp_mode.addWidget(self.rb_fullscreen)

        self.rb_windowed = QRadioButton("Windowed Mode (Framed 1920x1080)")
        self.rb_windowed.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        row_disp_mode.addWidget(self.rb_windowed)
        row_disp_mode.addStretch()
        l_disp.addLayout(row_disp_mode)

        lbl_res = QLabel("Target Resolution")
        lbl_res.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT}; margin-top: 10px;")
        l_disp.addWidget(lbl_res)

        self.cmb_res = OpaqueComboBox()
        self.cmb_res.setFixedWidth(280)
        self.cmb_res.addItems([
            "1920 x 1080 (Native FGO Arcade)",
            "2560 x 1440 (16:9 2K Upscaled)",
            "3840 x 2160 (16:9 4K UHD)",
            "1280 x 720 (720p Windowed)",
        ])
        self.cmb_res.setFixedHeight(32)
        l_disp.addWidget(self.cmb_res)

        # Translation Group
        lbl_trans_title = QLabel("Language & Translation")
        lbl_trans_title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT}; margin-top: 14px;")
        l_disp.addWidget(lbl_trans_title)

        self.chk_translation = QCheckBox("Enable English Translation Hook (zh/fgozh.dll)")
        self.chk_translation.setChecked(True)
        self.chk_translation.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        l_disp.addWidget(self.chk_translation)

        row_trans = QHBoxLayout()
        row_trans.setSpacing(14)

        self.btn_get_translation = QPushButton("Download English Translation Files")
        self.btn_get_translation.setFixedHeight(34)
        self.btn_get_translation.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_get_translation.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_get_translation.clicked.connect(self._start_translation_download)
        row_trans.addWidget(self.btn_get_translation)

        self.lbl_trans_status = QLabel("Checking translation files...")
        self.lbl_trans_status.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        row_trans.addWidget(self.lbl_trans_status)
        row_trans.addStretch()

        l_disp.addLayout(row_trans)

        btn_save_disp = QPushButton("Apply Display Settings")
        btn_save_disp.setFixedWidth(200)
        btn_save_disp.setStyleSheet(Theme.PRIMARY_BUTTON)
        btn_save_disp.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_save_disp.clicked.connect(self._save_config)
        l_disp.addWidget(btn_save_disp)

        self.sub_stack.addWidget(page_disp)

        # =============================================================
        # Subtab 2: Controls (segatools.ini)
        # =============================================================
        page_ctrl = QWidget()
        l_ctrl = QVBoxLayout(page_ctrl)
        l_ctrl.setContentsMargins(0, 10, 0, 0)
        l_ctrl.setSpacing(12)

        # Header with INI path indicator
        ctrl_top = QHBoxLayout()
        lbl_ctrl_head = QLabel("Input Configuration (segatools.ini)")
        lbl_ctrl_head.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT};")
        ctrl_top.addWidget(lbl_ctrl_head)
        ctrl_top.addStretch()

        self.btn_direct_ini = QPushButton("Edit segatools.ini Directly...")
        self.btn_direct_ini.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_direct_ini.clicked.connect(self._open_ini_editor)
        ctrl_top.addWidget(self.btn_direct_ini)
        l_ctrl.addLayout(ctrl_top)

        # Mode Selection: Keyboard vs XInput
        mode_box = QFrame()
        mode_box.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid {Theme.LINE}; border-radius: 4px;")
        l_mode = QHBoxLayout(mode_box)
        l_mode.setContentsMargins(16, 10, 16, 10)
        l_mode.setSpacing(24)

        lbl_mode_title = QLabel("Input Mode:")
        lbl_mode_title.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px; font-weight: 600;")
        l_mode.addWidget(lbl_mode_title)

        self.rb_mode_kb = QRadioButton("Keyboard Mode (WASD, Mouse, Keybindings)")
        self.rb_mode_kb.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        self.rb_mode_kb.toggled.connect(self._on_mode_toggled)
        l_mode.addWidget(self.rb_mode_kb)

        self.rb_mode_xinput = QRadioButton("Controller / Gamepad Mode (XInput)")
        self.rb_mode_xinput.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px;")
        self.rb_mode_xinput.toggled.connect(self._on_mode_toggled)
        l_mode.addWidget(self.rb_mode_xinput)

        l_mode.addStretch()
        l_ctrl.addWidget(mode_box)

        # Scrollable area for Keybindings and Controller Settings
        scroll_ctrl = QScrollArea()
        scroll_ctrl.setWidgetResizable(True)
        scroll_ctrl.setStyleSheet(f"background-color: {Theme.GROUND}; border: 1px solid {Theme.LINE};")
        ctrl_container = QWidget()
        self.l_ctrl_body = QVBoxLayout(ctrl_container)
        self.l_ctrl_body.setContentsMargins(16, 14, 16, 14)
        self.l_ctrl_body.setSpacing(14)

        # 1. Keyboard Section
        self.grp_kb = QWidget()
        l_grp_kb = QVBoxLayout(self.grp_kb)
        l_grp_kb.setContentsMargins(0, 0, 0, 0)
        l_grp_kb.setSpacing(12)

        # Movement
        lbl_sec_move = QLabel("Arcade Joystick Movement")
        lbl_sec_move.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.ICE};")
        l_grp_kb.addWidget(lbl_sec_move)

        move_bindings = [
            ("up", "Movement: Up"),
            ("down", "Movement: Down"),
            ("left", "Movement: Left"),
            ("right", "Movement: Right"),
        ]
        for key, name in move_bindings:
            row = KeyBindingRow(key, name, self._controls.get(key, "0x0"), self._on_key_rebound)
            self._key_rows[key] = row
            l_grp_kb.addWidget(row)

        # Actions
        lbl_sec_act = QLabel("Arcade Action Buttons")
        lbl_sec_act.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.ICE}; margin-top: 8px;")
        l_grp_kb.addWidget(lbl_sec_act)

        action_bindings = [
            ("attack", "Attack (Button 1)"),
            ("target", "Target Lock-On (Button 2)"),
            ("dash", "Dash / Guard (Button 3)"),
            ("np", "Noble Phantasm (Button 4)"),
            ("camera", "Center Camera"),
        ]
        for key, name in action_bindings:
            row = KeyBindingRow(key, name, self._controls.get(key, "0x0"), self._on_key_rebound)
            self._key_rows[key] = row
            l_grp_kb.addWidget(row)

        # Cabinet
        lbl_sec_cab = QLabel("Cabinet Hardware & System")
        lbl_sec_cab.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.ICE}; margin-top: 8px;")
        l_grp_kb.addWidget(lbl_sec_cab)

        cab_bindings = [
            ("coin", "Insert Coin (100 Yen)"),
            ("service", "Service Credit Switch"),
            ("test", "Test Menu Switch"),
            ("scan", "Aime Card Login Touch"),
        ]
        for key, name in cab_bindings:
            row = KeyBindingRow(key, name, self._controls.get(key, "0x0"), self._on_key_rebound)
            self._key_rows[key] = row
            l_grp_kb.addWidget(row)

        self.l_ctrl_body.addWidget(self.grp_kb)

        # 2. XInput Controller Section
        self.grp_xinput = QWidget()
        l_grp_xi = QVBoxLayout(self.grp_xinput)
        l_grp_xi.setContentsMargins(0, 0, 0, 0)
        l_grp_xi.setSpacing(12)

        lbl_xi_head = QLabel("XInput Gamepad Parameters")
        lbl_xi_head.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.ICE};")
        l_grp_xi.addWidget(lbl_xi_head)

        grid_xi = QGridLayout()
        grid_xi.setSpacing(12)

        grid_xi.addWidget(QLabel("Controller Index:"), 0, 0)
        self.cmb_ctrl_idx = OpaqueComboBox()
        self.cmb_ctrl_idx.addItems(["0 (Player 1 / Default)", "1 (Player 2)", "2 (Player 3)", "3 (Player 4)"])
        self.cmb_ctrl_idx.setFixedHeight(28)
        grid_xi.addWidget(self.cmb_ctrl_idx, 0, 1)

        grid_xi.addWidget(QLabel("Stick Deadzone:"), 1, 0)
        self.spn_deadzone = QSpinBox()
        self.spn_deadzone.setRange(0, 32767)
        self.spn_deadzone.setValue(int(self._controls.get("stickDeadzone", 7849)))
        self.spn_deadzone.setStyleSheet(f"background-color: {Theme.PLATE}; color: {Theme.TEXT}; padding: 4px 8px;")
        grid_xi.addWidget(self.spn_deadzone, 1, 1)

        self.chk_rumble = QCheckBox("Enable Controller Rumble")
        self.chk_rumble.setChecked(bool(self._controls.get("rumble", 1)))
        grid_xi.addWidget(self.chk_rumble, 2, 0)

        row_rumble = QHBoxLayout()
        self.sld_rumble = QSlider(Qt.Orientation.Horizontal)
        self.sld_rumble.setRange(0, 100)
        self.sld_rumble.setValue(int(self._controls.get("rumbleStrength", 70)))
        self.lbl_rumble_pct = QLabel(f"{self.sld_rumble.value()}%")
        self.lbl_rumble_pct.setFixedWidth(40)
        self.sld_rumble.valueChanged.connect(lambda v: self.lbl_rumble_pct.setText(f"{v}%"))
        row_rumble.addWidget(self.sld_rumble)
        row_rumble.addWidget(self.lbl_rumble_pct)
        grid_xi.addLayout(row_rumble, 2, 1)

        l_grp_xi.addLayout(grid_xi)

        # Informative arcade layout reference
        lbl_ref = QLabel(
            "<b>Standard Controller Mapping:</b><br>"
            "• Left Stick: 8-Way Movement<br>"
            "• X / Square or A / Cross: Normal Attack<br>"
            "• Y / Triangle: Target Lock-On<br>"
            "• Left Trigger (LT): Dash / Evade<br>"
            "• Right Bumper (RB): Noble Phantasm (NP)<br>"
            "• Left Bumper (LB): Center Camera<br>"
            "• Select / Back: Coin Insert | Start: Test Menu"
        )
        lbl_ref.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px; margin-top: 8px; line-height: 1.4;")
        l_grp_xi.addWidget(lbl_ref)

        self.l_ctrl_body.addWidget(self.grp_xinput)

        scroll_ctrl.setWidget(ctrl_container)
        l_ctrl.addWidget(scroll_ctrl, stretch=1)

        # Bottom Control Buttons
        row_ctrl_btns = QHBoxLayout()
        row_ctrl_btns.setSpacing(14)

        btn_save_ctrl = QPushButton("Save Controls to segatools.ini")
        btn_save_ctrl.setStyleSheet(Theme.PRIMARY_BUTTON)
        btn_save_ctrl.setFixedHeight(36)
        btn_save_ctrl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_save_ctrl.clicked.connect(self._save_controls)
        row_ctrl_btns.addWidget(btn_save_ctrl)

        btn_reset_ctrl = QPushButton("Reset to Defaults")
        btn_reset_ctrl.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_reset_ctrl.setFixedHeight(36)
        btn_reset_ctrl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_reset_ctrl.clicked.connect(self._reset_controls_defaults)
        row_ctrl_btns.addWidget(btn_reset_ctrl)

        row_ctrl_btns.addStretch()
        l_ctrl.addLayout(row_ctrl_btns)

        self.sub_stack.addWidget(page_ctrl)

        # =============================================================
        # Subtab 3: Audio
        # =============================================================
        page_aud = QWidget()
        l_aud = QVBoxLayout(page_aud)
        l_aud.setContentsMargins(0, 10, 0, 0)
        l_aud.setSpacing(16)
        l_aud.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        lbl_aud_head = QLabel("Audio Output Device")
        lbl_aud_head.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Theme.TEXT};")
        l_aud.addWidget(lbl_aud_head)

        self.cmb_audio_dev = OpaqueComboBox()
        self.cmb_audio_dev.setFixedWidth(360)
        self.cmb_audio_dev.addItems([
            "Default System Output (PipeWire / PulseAudio)",
            "NVIDIA High Definition Audio (HDMI)",
            "Analog Stereo Output",
        ])
        self.cmb_audio_dev.setFixedHeight(32)
        l_aud.addWidget(self.cmb_audio_dev)

        self.sub_stack.addWidget(page_aud)

        main_layout.addWidget(self.sub_stack)
        self._switch_subtab(0)

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

    # -----------------------------------------------------------------
    # Controls Management
    # -----------------------------------------------------------------

    def _refresh_controls_ui(self):
        mode = str(self._controls.get("mode", "keyboard")).lower()
        if mode == "xinput":
            self.rb_mode_xinput.setChecked(True)
            self.grp_kb.setVisible(False)
            self.grp_xinput.setVisible(True)
        else:
            self.rb_mode_kb.setChecked(True)
            self.grp_kb.setVisible(True)
            self.grp_xinput.setVisible(False)

        for key, row in self._key_rows.items():
            if key in self._controls:
                row.set_vk(str(self._controls[key]))

        idx = int(self._controls.get("controllerIndex", 0))
        if 0 <= idx < self.cmb_ctrl_idx.count():
            self.cmb_ctrl_idx.setCurrentIndex(idx)
        self.spn_deadzone.setValue(int(self._controls.get("stickDeadzone", 7849)))
        self.chk_rumble.setChecked(bool(self._controls.get("rumble", 1)))
        self.sld_rumble.setValue(int(self._controls.get("rumbleStrength", 70)))

    def _on_mode_toggled(self):
        if self.rb_mode_xinput.isChecked():
            self._controls["mode"] = "xinput"
            self.grp_kb.setVisible(False)
            self.grp_xinput.setVisible(True)
        else:
            self._controls["mode"] = "keyboard"
            self.grp_kb.setVisible(True)
            self.grp_xinput.setVisible(False)

    def _on_key_rebound(self, action_key: str, new_vk: str):
        self._controls[action_key] = new_vk

    def _save_controls(self):
        # Update XInput values
        self._controls["controllerIndex"] = self.cmb_ctrl_idx.currentIndex()
        self._controls["stickDeadzone"] = self.spn_deadzone.value()
        self._controls["rumble"] = 1 if self.chk_rumble.isChecked() else 0
        self._controls["rumbleStrength"] = self.sld_rumble.value()

        success, msg = save_controls_config(self._controls)
        if success:
            QMessageBox.information(self, "Controls Saved", f"{msg}\nInput configuration is active for the next game launch.")
            self.log_message.emit(f"[CONTROLS] {msg}")
        else:
            QMessageBox.critical(self, "Error Saving Controls", msg)
            self.log_message.emit(f"[CONTROLS] Error: {msg}")

    def _reset_controls_defaults(self):
        reply = QMessageBox.question(
            self,
            "Reset Controls",
            "Reset all controls and keybindings to SegaTools defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._controls = dict(DEFAULT_CONTROLS)
            self._refresh_controls_ui()
            self._save_controls()

    def _open_ini_editor(self):
        path = get_segatools_ini_path()
        dlg = IniEditorDialog(path, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._controls = load_controls_config()
            self._refresh_controls_ui()

    # -----------------------------------------------------------------
    # Display & Translation
    # -----------------------------------------------------------------

    def _load_config(self):
        if os.path.exists(CONFIG_JSON):
            try:
                with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                fs = cfg.get("fullscreen", True)
                self.rb_fullscreen.setChecked(fs)
                self.rb_windowed.setChecked(not fs)
                self.chk_translation.setChecked(cfg.get("chineseEnabled", True))
            except Exception:
                pass

    def _save_config(self):
        cfg = {}
        if os.path.exists(CONFIG_JSON):
            try:
                with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}

        cfg["fullscreen"] = self.rb_fullscreen.isChecked()
        cfg["chineseEnabled"] = self.chk_translation.isChecked()

        try:
            with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Settings Saved", "Display settings successfully saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def _refresh_translation_status(self):
        installed = is_translation_installed()
        if installed:
            self.lbl_trans_status.setText("Status: Installed (App/zh/fgozh.dll detected)")
            self.lbl_trans_status.setStyleSheet(f"color: {Theme.READY}; font-size: 13px; font-weight: 500;")
            self.btn_get_translation.setText("Re-download / Update Translation")
        else:
            self.lbl_trans_status.setText("Status: Not installed")
            self.lbl_trans_status.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px;")
            self.btn_get_translation.setText("Download English Translation Files")

    def _start_translation_download(self):
        if self._trans_worker and self._trans_worker.isRunning():
            return

        self.btn_get_translation.setEnabled(False)
        self.btn_get_translation.setText("Downloading...")
        self.lbl_trans_status.setText("Connecting to GitHub...")
        self.lbl_trans_status.setStyleSheet(f"color: {Theme.ICE}; font-size: 13px;")

        self._trans_worker = TranslationInstallerWorker(self)
        self._trans_worker.progress.connect(self._on_translation_progress)
        self._trans_worker.finished.connect(self._on_translation_finished)
        self._trans_worker.start()

    def _on_translation_progress(self, msg: str):
        self.log_message.emit(msg)
        if "%" in msg:
            pct = msg.split("%")[0].split()[-1] + "%"
            self.lbl_trans_status.setText(f"Downloading {pct}...")

    def _on_translation_finished(self, success: bool, msg: str):
        self.btn_get_translation.setEnabled(True)
        self._refresh_translation_status()
        self.log_message.emit(f"[TRANSLATION] {msg}")
        if success:
            QMessageBox.information(self, "Translation Installed", msg)
        else:
            QMessageBox.critical(self, "Translation Error", f"Failed to download translation files:\n{msg}")
