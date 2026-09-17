"""
Account View: Master profile management and inventory controls.
Communicates directly with Server/tools/fgo_account.py.
"""

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.theme import Theme

try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from ..core.config import FGOA_ROOT

SERVER_TOOLS_DIR = os.path.join(FGOA_ROOT, "Server", "tools")
FGO_ACCOUNT_SCRIPT = os.path.join(SERVER_TOOLS_DIR, "fgo_account.py")
ARTEMIS_DIR = os.path.join(FGOA_ROOT, "Server", "artemis")


class AccountWorker(QThread):
    """Background worker to run fgo_account.py commands without locking the UI."""
    finished = pyqtSignal(bool, dict, str)

    def __init__(self, args: List[str]):
        super().__init__()
        self.args = args

    def run(self):
        venv_py = os.path.join(ARTEMIS_DIR, ".venv", "bin", "python")
        py_bin = venv_py if os.path.isfile(venv_py) else "python3"
        cmd = [py_bin, FGO_ACCOUNT_SCRIPT] + self.args
        try:
            res = subprocess.run(
                cmd,
                cwd=ARTEMIS_DIR,
                capture_output=True,
                text=True,
                check=False
            )
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            data = {}
            if stdout:
                try:
                    data = json.loads(stdout)
                except Exception:
                    data = {"raw_output": stdout}

            success = (res.returncode == 0) and (data.get("ok", True) is not False)
            err_msg = ""
            if not success:
                err_msg = data.get("message") or data.get("error") or stderr or stdout
            self.finished.emit(success, data, err_msg)
        except Exception as e:
            self.finished.emit(False, {}, str(e))


class NewAccountDialog(QDialog):
    """Dialog for registering a new Master account."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Local Account")
        self.setFixedWidth(480)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.GROUND};
                color: {Theme.TEXT};
                font-family: 'Segoe UI', system-ui, sans-serif;
            }}
            QLabel {{
                color: {Theme.TEXT};
                font-size: 13px;
            }}
            QLineEdit {{
                background-color: {Theme.PLATE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {Theme.ICE};
            }}
            QComboBox {{
                background-color: {Theme.PLATE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl_name = QLabel("Master name (shown in game)")
        lbl_name.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        self.edit_name = QLineEdit()
        self.edit_name.setMaxLength(32)
        self.edit_name.setPlaceholderText("Enter Master name...")

        lbl_mode = QLabel("Account mode")
        lbl_mode.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("normal - Standard account (starting resources)", "normal")

        lbl_help = QLabel(
            "A new account starts from the standard beginning state. "
            "Once it exists, use the card print and growth options on the account page "
            "whenever you need them."
        )
        lbl_help.setWordWrap(True)
        lbl_help.setStyleSheet(f"color: {Theme.TEXT_FAINT}; font-size: 12px; margin-top: 4px; margin-bottom: 8px;")

        layout.addWidget(lbl_name)
        layout.addWidget(self.edit_name)
        layout.addWidget(lbl_mode)
        layout.addWidget(self.cmb_mode)
        layout.addWidget(lbl_help)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setStyleSheet(Theme.SECONDARY_BUTTON)

        self.btn_create = QPushButton("Create")
        self.btn_create.setStyleSheet(Theme.PRIMARY_BUTTON)
        self.btn_create.clicked.connect(self._validate_and_accept)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_create)
        layout.addLayout(btn_row)

    def _validate_and_accept(self):
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, "New Account", "Please enter a Master name.")
            return
        self.accept()

    def get_data(self):
        return self.edit_name.text().strip(), self.cmb_mode.currentData()


class AccountView(QWidget):
    """
    Master account management view.
    Provides profile overview, account switching, creation, and growth tools.
    """
    account_changed = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accounts: List[Dict[str, Any]] = []
        self.current_access_code = ""
        self.selected_account: Optional[Dict[str, Any]] = None
        self._worker: Optional[AccountWorker] = None

        self._init_ui()
        self.refresh_accounts()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # -----------------------------------------------------------------
        # Row 1: Current In Use & Access Code Status
        # -----------------------------------------------------------------
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        lbl_in_use = QLabel("In use:")
        lbl_in_use.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        self.lbl_current_account = QLabel("Loading...")
        self.lbl_current_account.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px; font-weight: 600;")

        lbl_access = QLabel("Access code:")
        lbl_access.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; margin-left: 12px;")
        self.lbl_current_code = QLabel("—")
        self.lbl_current_code.setStyleSheet(f"color: {Theme.READY}; font-family: monospace; font-size: 13px; font-weight: bold;")

        self.lbl_summary = QLabel("Lv.1 - EXP 0 - 0 cards")
        self.lbl_summary.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; margin-left: 16px;")

        row1.addWidget(lbl_in_use)
        row1.addWidget(self.lbl_current_account)
        row1.addWidget(lbl_access)
        row1.addWidget(self.lbl_current_code)
        row1.addWidget(self.lbl_summary)
        row1.addStretch()
        layout.addLayout(row1)

        # -----------------------------------------------------------------
        # Row 2: Select Dropdown & Main Account Actions
        # -----------------------------------------------------------------
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        lbl_select = QLabel("Select:")
        lbl_select.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")

        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(260)
        self.account_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.PLATE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 13px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Theme.PLATE_LOW};
                color: {Theme.TEXT};
                selection-background-color: {Theme.LINE};
            }}
        """)
        self.account_combo.currentIndexChanged.connect(self._on_account_selected)

        self.btn_use = QPushButton("Use Selected Account")
        self.btn_use.setStyleSheet(Theme.PRIMARY_BUTTON)
        self.btn_use.clicked.connect(self._use_selected_account)

        self.btn_new = QPushButton("New Account")
        self.btn_new.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_new.clicked.connect(self._create_new_account)

        row2.addWidget(lbl_select)
        row2.addWidget(self.account_combo)
        row2.addWidget(self.btn_use)
        row2.addWidget(self.btn_new)
        row2.addStretch()
        layout.addLayout(row2)

        # -----------------------------------------------------------------
        # Row 3: Maintenance Actions (Reset, Delete, Repair, Grant, Refresh)
        # -----------------------------------------------------------------
        row3 = QHBoxLayout()
        row3.setSpacing(8)

        self.btn_reset = QPushButton("Reset Account")
        self.btn_reset.setStyleSheet(Theme.DANGER_BUTTON)
        self.btn_reset.clicked.connect(self._reset_account)

        self.btn_delete = QPushButton("Delete Account")
        self.btn_delete.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Theme.DANGER};
                color: {Theme.DANGER};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {Theme.DANGER}22;
            }}
        """)
        self.btn_delete.clicked.connect(self._delete_account)

        self.btn_repair = QPushButton("Repair Past Results")
        self.btn_repair.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_repair.setToolTip("Replays saved cabinet traffic to restore EXP, materials, Bond, and Quest progress")
        self.btn_repair.clicked.connect(self._repair_account)

        self.btn_grant = QPushButton("Grant Items")
        self.btn_grant.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_grant.setToolTip("Pick currency or materials and add chosen amounts")
        self.btn_grant.clicked.connect(self._grant_items_stub)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setStyleSheet(Theme.SECONDARY_BUTTON)
        self.btn_refresh.clicked.connect(self.refresh_accounts)

        row3.addWidget(self.btn_reset)
        row3.addWidget(self.btn_delete)
        row3.addWidget(self.btn_repair)
        row3.addWidget(self.btn_grant)
        row3.addWidget(self.btn_refresh)
        row3.addStretch()
        layout.addLayout(row3)

        # -----------------------------------------------------------------
        # Section 1: One-Click Inventory and Growth
        # -----------------------------------------------------------------
        lbl_growth_title = QLabel("One-Click Inventory and Growth")
        lbl_growth_title.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {Theme.TEXT}; margin-top: 10px;")
        layout.addWidget(lbl_growth_title)

        lbl_growth_desc = QLabel(
            "These act on the selected account. Quit the game and stop the server first. "
            "The growth options only affect Servants the account already owns."
        )
        lbl_growth_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; margin-bottom: 6px;")
        layout.addWidget(lbl_growth_desc)

        # 9 Upgrade Buttons Grid (3x3)
        self.upgrade_grid = QGridLayout()
        self.upgrade_grid.setSpacing(8)

        upgrades = [
            ("Grant All Servants", "servants", "Tops every Servant card up to 5 copies through normal print flow."),
            ("Grant All Craft Essences", "craft-essences", "Tops every Craft Essence card up to 5 copies."),
            ("Clear Present Box", "clear-gifts", "Deletes every unclaimed present without claiming it. Backed up first."),
            ("Clear All Quests", "quests", "Marks every Quest cleared and Master Mission complete."),
            ("Max All Bond", "bond", "Raises Bond to the cap for all owned Servants."),
            ("Unlock All Costumes", "costumes", "Unlocks all available Servant costumes."),
            ("Max All Materials", "materials", "Fills every enhancement material to its maximum capacity."),
            ("Max All Servants", "levels", "Raises level, Ascension, level cap, Skills, NP, and Bond to max."),
            ("Max Master Level", "master", "Sets Master EXP to the highest level table value."),
        ]

        self.upgrade_buttons = []
        for idx, (title, tag, tooltip) in enumerate(upgrades):
            btn = QPushButton(title)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(34)
            btn.setStyleSheet(Theme.SECONDARY_BUTTON)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _, t=tag, n=title: self._run_upgrade(t, n))
            row = idx // 3
            col = idx % 3
            self.upgrade_grid.addWidget(btn, row, col)
            self.upgrade_buttons.append(btn)

        layout.addLayout(self.upgrade_grid)

        # -----------------------------------------------------------------
        # Section 2: Account Details
        # -----------------------------------------------------------------
        lbl_details_title = QLabel("Account Details")
        lbl_details_title.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {Theme.TEXT}; margin-top: 14px;")
        layout.addWidget(lbl_details_title)

        self.details_container = QVBoxLayout()
        self.details_container.setSpacing(0)
        layout.addLayout(self.details_container)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    # ---------------------------------------------------------------------
    # Account Management Operations
    # ---------------------------------------------------------------------

    def refresh_accounts(self):
        """Runs fgo_account.py list --json"""
        self._run_tool(["list", "--json"], self._on_list_finished)

    def _on_list_finished(self, success: bool, data: dict, err: str):
        if not success or not data:
            self.lbl_current_account.setText("(error querying accounts)")
            if err:
                self.log_message.emit(f"Account query error: {err}")
            return

        self.current_access_code = data.get("current_access_code", "")
        self.lbl_current_code.setText(self.current_access_code if self.current_access_code else "—")

        self.accounts = data.get("accounts", [])
        self.account_combo.blockSignals(True)
        self.account_combo.clear()

        current_idx = -1
        for idx, acc in enumerate(self.accounts):
            aime_id = acc.get("aime_id")
            master_name = acc.get("master_name") or f"Aime-{aime_id}"
            mode = acc.get("account_mode", "normal")
            display = f"{master_name} (ID {aime_id} - {mode})"
            self.account_combo.addItem(display, acc)

            if acc.get("is_current") or str(acc.get("access_code")) == str(self.current_access_code):
                current_idx = idx
                self.lbl_current_account.setText(f"{master_name} (ID {aime_id})")

        if current_idx >= 0:
            self.account_combo.setCurrentIndex(current_idx)
        elif self.accounts:
            self.account_combo.setCurrentIndex(0)
        else:
            self.lbl_current_account.setText("(no accounts yet)")

        self.account_combo.blockSignals(False)
        self._on_account_selected(self.account_combo.currentIndex())

    def _on_account_selected(self, index: int):
        if 0 <= index < len(self.accounts):
            self.selected_account = self.accounts[index]
        else:
            self.selected_account = None

        self._refresh_details_table()

    def _refresh_details_table(self):
        while self.details_container.count() > 0:
            item = self.details_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        acc = self.selected_account
        if not acc:
            self.lbl_summary.setText("No account selected")
            return

        master_name = acc.get("master_name") or "Chaldea Master"
        aime_id = str(acc.get("aime_id", "-"))
        mode = acc.get("account_mode", "normal")
        level = acc.get("master_level", 1)
        exp = acc.get("master_exp", 0)
        cur_exp = acc.get("master_level_exp", 0)
        next_exp = acc.get("master_next_level_exp", 0)
        exp_to_next = acc.get("master_exp_to_next", 0)
        exp_str = f"{cur_exp:,} / {next_exp:,} ({exp_to_next:,} to go)" if next_exp > 0 else "Max level reached"

        qp = acc.get("qp_amnt", 0)
        fp = acc.get("fp_amnt", 0)
        mana = acc.get("mana_prism_amnt", 0)
        summon = acc.get("summon_point_amnt", 0)
        cleared_q = acc.get("cleared_quest_count", 0)
        tracked_q = acc.get("tracked_quest_count", 0)
        servants = acc.get("servant_count", 0)
        unique_cards = acc.get("owned_card_count", 0)
        copies = acc.get("owned_card_copy_count", 0)
        pending = acc.get("pending_print_count", 0)

        self.lbl_summary.setText(f"Lv.{level} - EXP {exp:,} - Quests {cleared_q} - Cards {unique_cards}")

        rows = [
            ("Master Name", master_name),
            ("Aime ID", aime_id),
            ("Access Code", str(acc.get("access_code", "-"))),
            ("Account Mode", mode),
            ("Master Level", f"Lv.{level}"),
            ("Total EXP", f"{exp:,}"),
            ("EXP This Level", exp_str),
            ("QP", f"{qp:,}"),
            ("Friend Points", f"{fp:,}"),
            ("Mana Prisms", f"{mana:,}"),
            ("Summon Points", f"{summon:,}"),
            ("Quests Cleared", f"{cleared_q} / {tracked_q} tracked"),
            ("Servants Owned", f"{servants:,}"),
            ("Printed Cards Owned", f"{unique_cards:,} unique / {copies:,} copies"),
            ("Prints Pending", f"{pending:,}"),
        ]

        for name, val in rows:
            row_frame = self._create_detail_row(name, val)
            self.details_container.addWidget(row_frame)

    def _create_detail_row(self, name: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE_SOFT};
                border-top: none;
            }}
        """)
        hlayout = QHBoxLayout(frame)
        hlayout.setContentsMargins(14, 6, 14, 6)

        lbl_name = QLabel(name)
        lbl_name.setFixedWidth(180)
        lbl_name.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")

        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"color: {Theme.TEXT}; font-size: 13px; font-weight: 500;")

        hlayout.addWidget(lbl_name)
        hlayout.addWidget(lbl_val)
        hlayout.addStretch()
        return frame

    def _use_selected_account(self):
        if not self.selected_account:
            QMessageBox.warning(self, "Use Account", "Please select an account first.")
            return

        aime_id = str(self.selected_account.get("aime_id"))
        name = self.selected_account.get("master_name", f"ID {aime_id}")

        def on_done(success: bool, data: dict, err: str):
            if success:
                self.log_message.emit(f"Switched active account to {name} (Aime ID: {aime_id})")
                QMessageBox.information(self, "Account Switched", f"Switched to account {name} (ID {aime_id}).")
                self.refresh_accounts()
                self.account_changed.emit(aime_id)
            else:
                QMessageBox.critical(self, "Error", f"Failed to switch account:\n{err}")

        self._run_tool(["use", "--aime-id", aime_id, "--json"], on_done)

    def _create_new_account(self):
        dlg = NewAccountDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name, mode = dlg.get_data()

        def on_done(success: bool, data: dict, err: str):
            if success:
                new_id = data.get("aime_id", "")
                code = data.get("access_code", "")
                self.log_message.emit(f"Created account {name} (ID {new_id}, mode {mode})")
                QMessageBox.information(
                    self,
                    "Account Created",
                    f"Account created successfully!\n\nMaster: {name}\nAime ID: {new_id}\nAccess Code: {code}"
                )
                self.refresh_accounts()
            else:
                QMessageBox.critical(self, "Error", f"Failed to create account:\n{err}")

        self._run_tool(["create", "--name", name, "--mode", mode, "--json"], on_done)

    def _reset_account(self):
        if not self.selected_account:
            return
        aime_id = str(self.selected_account.get("aime_id"))
        name = self.selected_account.get("master_name", f"ID {aime_id}")

        reply = QMessageBox.question(
            self,
            "Reset Account",
            f"Reset the account {name} (ID {aime_id}) to a brand new normal account?\n\n"
            "This clears owned Servants, points, items, print history, and all game progress.\n"
            "This operation cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(success: bool, data: dict, err: str):
            if success:
                self.log_message.emit(f"Reset account {name} (ID {aime_id}) to normal.")
                QMessageBox.information(self, "Account Reset", f"Account {name} has been reset.")
                self.refresh_accounts()
            else:
                QMessageBox.critical(self, "Error", f"Failed to reset account:\n{err}")

        self._run_tool(["reset", "--aime-id", aime_id, "--json"], on_done)

    def _delete_account(self):
        if not self.selected_account:
            return
        aime_id = str(self.selected_account.get("aime_id"))
        name = self.selected_account.get("master_name", f"ID {aime_id}")

        reply = QMessageBox.question(
            self,
            "Delete Account",
            f"Permanently delete the account {name} (Aime ID {aime_id})?\n\n"
            "The save data, Aime database identity, card mapping, and backups are deleted permanently.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(success: bool, data: dict, err: str):
            if success:
                self.log_message.emit(f"Deleted account {name} (ID {aime_id}).")
                QMessageBox.information(self, "Account Deleted", f"Account {name} has been deleted.")
                self.refresh_accounts()
            else:
                QMessageBox.critical(self, "Error", f"Failed to delete account:\n{err}")

        self._run_tool(["delete", "--aime-id", aime_id, "--yes", "--json"], on_done)

    def _repair_account(self):
        if not self.selected_account:
            return
        aime_id = str(self.selected_account.get("aime_id"))
        name = self.selected_account.get("master_name", f"ID {aime_id}")

        def on_done(success: bool, data: dict, err: str):
            if success:
                self.log_message.emit(f"Repair finished for {name} (ID {aime_id}).")
                QMessageBox.information(self, "Repair Finished", f"Repair completed for {name}.")
                self.refresh_accounts()
            else:
                QMessageBox.critical(self, "Error", f"Failed to repair account:\n{err}")

        self._run_tool(["repair", "--aime-id", aime_id, "--json"], on_done)

    def _grant_items_stub(self):
        QMessageBox.information(
            self,
            "Grant Items",
            "Item grant catalog dialog:\nYou can use the One-Click upgrades below to max materials, QP, and cards."
        )

    def _run_upgrade(self, tag: str, title: str):
        if not self.selected_account:
            QMessageBox.warning(self, "Account Upgrade", "Please select an account first.")
            return
        aime_id = str(self.selected_account.get("aime_id"))
        name = self.selected_account.get("master_name", f"ID {aime_id}")

        reply = QMessageBox.question(
            self,
            title,
            f"Run '{title}' on account {name} (ID {aime_id})?\n\n"
            "All other progress is kept, and the save is backed up before anything is written.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(success: bool, data: dict, err: str):
            if success:
                self.log_message.emit(f"{title} finished for {name} (ID {aime_id}).")
                QMessageBox.information(self, title, f"'{title}' completed successfully for {name}!")
                self.refresh_accounts()
            else:
                QMessageBox.critical(self, "Error", f"Failed to run {title}:\n{err}")

        self._run_tool(["upgrade", "--aime-id", aime_id, "--action", tag, "--json"], on_done)

    def _run_tool(self, args: List[str], callback):
        self._set_controls_enabled(False)
        self._worker = AccountWorker(args)

        def wrapped(success, data, err):
            self._set_controls_enabled(True)
            callback(success, data, err)

        self._worker.finished.connect(wrapped)
        self._worker.start()

    def _set_controls_enabled(self, enabled: bool):
        self.account_combo.setEnabled(enabled)
        self.btn_use.setEnabled(enabled)
        self.btn_new.setEnabled(enabled)
        self.btn_reset.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)
        self.btn_repair.setEnabled(enabled)
        self.btn_grant.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)
        for btn in self.upgrade_buttons:
            btn.setEnabled(enabled)
