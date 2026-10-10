"""
Dola.ai QA & Account Testing Automation
Main application entry point — PySide6 desktop GUI.
"""
import os
import sys

# --- PORTABLE APP BROWSER CONFIG ---
if getattr(sys, 'frozen', False):
    # This ensures Playwright looks for browsers in the local 'pw-browsers' folder next to the .exe
    app_dir = os.path.dirname(sys.executable)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(app_dir, "pw-browsers")
# -----------------------------------

import threading
import time
import json
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QComboBox, QSpinBox, QCheckBox, QTextEdit,
    QGroupBox, QFormLayout, QMessageBox, QDialog, QDialogButtonBox,
    QScrollArea, QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QFont, QColor, QTextCursor

from state_manager import StateManager
from gmail_manager import GmailManager
from workflow_manager import WorkflowManager
from worker_manager import QAWorker, WorkerStatus

# ── Dark theme stylesheet ────────────────────────────────────────────────────
STYLESHEET = """
QMainWindow, QDialog {
    background-color: #1e1e24;
}
QWidget {
    background-color: #1e1e24;
    color: #e0e0e0;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 13px;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: #1e1e24;
}
QGroupBox {
    border: 1px solid #3d3d4d;
    border-radius: 8px;
    margin-top: 12px;
    font-weight: bold;
    padding: 10px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #64b5f6;
}
QPushButton {
    background-color: #2b2b36;
    border: 1px solid #4a4a5a;
    border-radius: 6px;
    padding: 6px 14px;
    color: #e0e0e0;
    font-weight: 500;
    min-height: 26px;
}
QPushButton:hover {
    background-color: #3b3b4a;
    border-color: #64b5f6;
}
QPushButton:pressed { background-color: #1a1a24; }
QPushButton#primaryBtn {
    background-color: #1565c0;
    color: white;
    border: none;
    font-weight: bold;
}
QPushButton#primaryBtn:hover { background-color: #1976d2; }
QPushButton#dangerBtn {
    background-color: #b71c1c;
    color: white;
    border: none;
}
QPushButton#dangerBtn:hover { background-color: #c62828; }
QPushButton#successBtn {
    background-color: #2e7d32;
    color: white;
    border: none;
}
QPushButton#successBtn:hover { background-color: #388e3c; }
QPushButton#warnBtn {
    background-color: #e65100;
    color: white;
    border: none;
}
QPushButton#warnBtn:hover { background-color: #ef6c00; }
QTableWidget {
    background-color: #25252f;
    color: #e0e0e0;
    gridline-color: #383848;
    border: 1px solid #383848;
    border-radius: 6px;
    alternate-background-color: #2a2a35;
}
QHeaderView { background-color: #1f1f28; }
QHeaderView::section {
    background-color: #1f1f28;
    color: #64b5f6;
    padding: 6px;
    border: 1px solid #383848;
    font-weight: bold;
}
QTableCornerButton::section {
    background-color: #1f1f28;
    border: 1px solid #383848;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: #25252f;
    border: 1px solid #444455;
    border-radius: 5px;
    padding: 5px 7px;
    color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border-color: #64b5f6;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #25252f;
    color: #ffffff;
    selection-background-color: #1976d2;
    selection-color: #ffffff;
    border: 1px solid #444455;
}
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    background-color: #25252f;
    border: 1px solid #555566;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #1976d2;
    border-color: #1976d2;
}
QScrollBar:vertical {
    background: #1e1e24;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #444455;
    border-radius: 5px;
    min-height: 20px;
}
QLabel#sectionTitle {
    color: #e0e0e0;
    font-size: 16px;
    font-weight: bold;
    padding-bottom: 6px;
}
"""


# ── Signal bridge (thread → Qt) ──────────────────────────────────────────────
class Bridge(QObject):
    worker_updated = Signal(int, str, str)   # worker_id, status, step


# ── Missing Selector Dialog ───────────────────────────────────────────────────
class WorkflowDialog(QDialog):
    def __init__(self, worker: QAWorker, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.setWindowTitle(f"Selector Required — Worker #{worker.worker_id}")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        info = worker.pending_selector or {}
        step_name = info.get("step", "?")
        data = info.get("data", {})
        
        layout.addWidget(QLabel(f"<b>Worker:</b> #{worker.worker_id}"))
        layout.addWidget(QLabel(f"<b>Step:</b> {step_name}"))
        layout.addWidget(QLabel(f"<b>Action:</b> {data.get('action', '?')}"))
        layout.addWidget(QLabel(f"<b>Current Value:</b> {data.get('selector_value', '?')}"))

        layout.addWidget(QLabel("<b>Enter new Selector or URL:</b>"))
        self.sel_edit = QLineEdit(data.get("selector_value", ""))
        layout.addWidget(self.sel_edit)

        self.sel_type = QComboBox()
        self.sel_type.addItems(["XPath", "CSS", "URL", "Text"])
        self.sel_type.setCurrentText(data.get("selector_type", "XPath"))
        layout.addWidget(self.sel_type)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_save(self):
        sel = self.sel_edit.text().strip()
        if not sel:
            return
        step = (self.worker.pending_selector or {}).get("step", "")
        if step:
            data = self.worker.pending_selector.get("data", {})
            self.worker.workflow_manager.update_full(
                step, 
                data.get("action", "Click"), 
                self.sel_type.currentText(), 
                sel, 
                data.get("input_value", ""), 
                data.get("delay_seconds", 2), 
                data.get("timeout", 15000), 
                data.get("fallback_selector", "")
            )
            self.worker.pending_selector["data"]["selector_value"] = sel
            self.worker.pending_selector["data"]["selector_type"] = self.sel_type.currentText()
            self.worker._selector_event.set()
        self.accept()

class EmailSelectionDialog(QDialog):
    def __init__(self, accounts: List[str], count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Email Strategy")
        self.setMinimumWidth(400)
        self.selected_emails = []
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>How do you want to start the automation?</b>"))
        
        self.btn_random = QPushButton(f"Create {count} New Random Email(s)")
        self.btn_random.setObjectName("primaryBtn")
        self.btn_random.clicked.connect(self._on_random)
        layout.addWidget(self.btn_random)
        
        layout.addWidget(QLabel("Or select an existing email:"))
        
        self.combo = QComboBox()
        self.combo.addItems(accounts)
        layout.addWidget(self.combo)
        
        self.btn_existing = QPushButton("Use Selected Existing Email")
        self.btn_existing.clicked.connect(self._on_existing)
        layout.addWidget(self.btn_existing)
        
    def _on_random(self):
        self.selected_emails = []
        self.accept()
        
    def _on_existing(self):
        self.selected_emails = [self.combo.currentText()]
        self.accept()


# ── Main Application Window ───────────────────────────────────────────────────
class DolaQAApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dola.ai QA & Account Testing Automation")
        self.resize(1280, 800)

        self.state_manager   = StateManager()
        self.gmail_manager   = GmailManager(self.state_manager)
        self.workflow_manager = WorkflowManager(self.state_manager)

        self.workers: Dict[int, QAWorker] = {}
        self.bridge = Bridge()
        self.bridge.worker_updated.connect(self._on_worker_updated)

        self._build_ui()
        self._setup_timers()
        self._load_settings_values()

    # ═══════════════════════════════ UI BUILD ════════════════════════════════
    def _build_ui(self):
        self.setStyleSheet(STYLESHEET)

        root = QWidget()
        self.setCentralWidget(root)
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background-color:#181820; border-right:1px solid #2d2d3a;")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(8, 18, 8, 18)
        sl.setSpacing(4)

        logo = QLabel("DOLA QA")
        logo.setFont(QFont("Segoe UI", 16, QFont.Bold))
        logo.setStyleSheet("color:#64b5f6; padding-left:8px; margin-bottom:14px;")
        sl.addWidget(logo)

        self._nav_btns = {}
        pages = [
            ("Dashboard",  self._pg_dashboard),
            ("Accounts",   self._pg_accounts),
            ("Gmail",      self._pg_gmail),
            ("Workers",    self._pg_workers),
            ("Automation", self._pg_automation),
            ("Workflow",  self._pg_selectors),
            ("Logs",       self._pg_logs),
            ("Settings",   self._pg_settings),
            ("About",      self._pg_about),
        ]
        for label, _ in pages:
            b = QPushButton(label)
            b.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 9px 14px;
                    border: none;
                    border-radius: 6px;
                    font-size: 13px;
                    background: transparent;
                    color: #c0c0c0;
                }
                QPushButton:hover { background:#252533; color:#64b5f6; }
                QPushButton[active="true"] { background:#252533; color:#64b5f6; font-weight:bold; }
            """)
            b.clicked.connect(lambda _, lbl=label: self._navigate(lbl))
            sl.addWidget(b)
            self._nav_btns[label] = b

        sl.addStretch()

        # ── Page stack ───────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self._page_index = {}
        for i, (label, builder) in enumerate(pages):
            page = builder()
            self.stack.addWidget(page)
            self._page_index[label] = i

        rl.addWidget(sidebar)
        rl.addWidget(self.stack, 1)

    # ── Navigation ────────────────────────────────────────────────────────────
    def _navigate(self, label: str):
        for lbl, btn in self._nav_btns.items():
            btn.setProperty("active", "true" if lbl == label else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.stack.setCurrentIndex(self._page_index[label])
        # Refresh data when switching to data pages
        refresh = {
            "Accounts": self._refresh_accounts,
            "Workers":  self._refresh_workers,
            "Workflow": self._refresh_selectors,
            "Logs": self._refresh_logs,
            "Gmail": self._refresh_gmail_ui,
        }
        if label in refresh:
            refresh[label]()

    # ══════════════════════ PAGE BUILDERS ════════════════════════════════════

    # ── 1. Dashboard ──────────────────────────────────────────────────────────
    def _pg_dashboard(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(14)

        v.addWidget(self._section_title("Automation Dashboard"))

        # Stat cards
        card_row = QHBoxLayout()
        self._stat_labels: Dict[str, QLabel] = {}
        for key in ["Total Workers", "Running", "Waiting for Gmail", "Verifying", "Paused", "Completed", "Failed"]:
            box = QGroupBox(key)
            bl = QVBoxLayout(box)
            lbl = QLabel("0")
            lbl.setFont(QFont("Segoe UI", 20, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#64b5f6;")
            bl.addWidget(lbl)
            card_row.addWidget(box)
            self._stat_labels[key] = lbl
        v.addLayout(card_row)

        # System status bar
        status_box = QGroupBox("System Status")
        sb = QHBoxLayout(status_box)
        self._lbl_gmail_status = QLabel("Gmail: ● Disconnected")
        self._lbl_auto_status  = QLabel("Automation: ● Idle")
        self._lbl_browser_mode = QLabel("Browser: Headed")
        self._lbl_worker_count = QLabel("Workers: 0")
        for lbl in [self._lbl_gmail_status, self._lbl_auto_status,
                    self._lbl_browser_mode, self._lbl_worker_count]:
            sb.addWidget(lbl)
        sb.addStretch()
        v.addWidget(status_box)

        # Global controls
        ctrl = QHBoxLayout()
        self._btn_start_all  = QPushButton("▶  Start All")
        self._btn_start_all.setObjectName("primaryBtn")
        self._btn_start_all.clicked.connect(self._start_all)
        self._btn_pause_all  = QPushButton("⏸  Pause All")
        self._btn_pause_all.setObjectName("warnBtn")
        self._btn_pause_all.clicked.connect(self._pause_all)
        self._btn_resume_all = QPushButton("▶▶ Resume All")
        self._btn_resume_all.setObjectName("successBtn")
        self._btn_resume_all.clicked.connect(self._resume_all)
        self._btn_stop_all   = QPushButton("■  Stop All")
        self._btn_stop_all.setObjectName("dangerBtn")
        self._btn_stop_all.clicked.connect(self._stop_all)
        for b in [self._btn_start_all, self._btn_pause_all, self._btn_resume_all, self._btn_stop_all]:
            ctrl.addWidget(b)
        ctrl.addStretch()
        v.addLayout(ctrl)

        # Live snapshot table
        self._dash_table = QTableWidget(0, 4)
        self._dash_table.setHorizontalHeaderLabels(["Worker", "Account", "Status", "Current Step"])
        self._dash_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._dash_table.setAlternatingRowColors(True)
        v.addWidget(self._dash_table)

        return page

    # ── 2. Accounts ───────────────────────────────────────────────────────────
    def _pg_accounts(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.addWidget(self._section_title("Test Accounts"))
        
        btn_row = QHBoxLayout()
        b_del = QPushButton("Delete Selected")
        b_del.clicked.connect(self._delete_selected_accounts)
        b_del_all = QPushButton("Delete All")
        b_del_all.clicked.connect(self._delete_all_accounts)
        b_export = QPushButton("Export JSON")
        b_export.clicked.connect(self._export_accounts)
        b_import = QPushButton("Import JSON")
        b_import.clicked.connect(self._import_accounts)
        
        btn_row.addWidget(b_del)
        btn_row.addWidget(b_del_all)
        btn_row.addSpacing(20)
        btn_row.addWidget(b_export)
        btn_row.addWidget(b_import)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self._accounts_table = QTableWidget(0, 6)
        self._accounts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._accounts_table.setHorizontalHeaderLabels(
            ["Account", "Worker", "Status", "Created", "Dola.ai Status", "Last Activity"]
        )
        self._accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._accounts_table.setAlternatingRowColors(True)
        v.addWidget(self._accounts_table)
        return page

    # ── 3. Gmail ──────────────────────────────────────────────────────────────
    def _pg_gmail(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(14)
        v.addWidget(self._section_title("Gmail Authorization & Monitoring"))

        box = QGroupBox("Google Account Connection")
        f = QFormLayout(box)
        self._gm_account  = QLabel("Not connected")
        self._gm_status   = QLabel("● Disconnected")
        self._gm_monitor  = QLabel("● Inactive")
        self._gm_last     = QLabel("Never")
        self._gm_matched  = QLabel("0")
        for lbl, wgt in [("Account:", self._gm_account), ("Status:", self._gm_status),
                          ("Monitoring:", self._gm_monitor), ("Last Check:", self._gm_last),
                          ("Emails Matched:", self._gm_matched)]:
            f.addRow(lbl, wgt)
        v.addWidget(box)

        btn_row = QHBoxLayout()
        b_connect = QPushButton("Connect Gmail (OAuth)")
        b_connect.setObjectName("primaryBtn")
        b_connect.clicked.connect(self._connect_gmail)
        b_check = QPushButton("Check Connection")
        b_check.clicked.connect(self._check_gmail_connection)
        b_toggle = QPushButton("Toggle Monitoring")
        b_toggle.clicked.connect(self._toggle_monitoring)
        b_disc = QPushButton("Disconnect")
        b_disc.setObjectName("dangerBtn")
        b_disc.clicked.connect(self._disconnect_gmail)
        for b in [b_connect, b_check, b_toggle, b_disc]:
            btn_row.addWidget(b)
        btn_row.addStretch()
        v.addLayout(btn_row)
        v.addStretch()
        return page

    # ── 4. Workers ────────────────────────────────────────────────────────────
    def _pg_workers(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.addWidget(self._section_title("Worker Management"))

        # Per-worker controls row
        ctrl = QHBoxLayout()
        for label, slot in [("Start All","_start_all"), ("Pause All","_pause_all"),
                             ("Resume All","_resume_all"), ("Stop All","_stop_all")]:
            b = QPushButton(label)
            b.clicked.connect(getattr(self, slot))
            ctrl.addWidget(b)
        ctrl.addStretch()
        v.addLayout(ctrl)

        self._workers_table = QTableWidget(0, 6)
        self._workers_table.setHorizontalHeaderLabels(
            ["#", "Account", "Status", "Step", "URL", "Actions"]
        )
        self._workers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._workers_table.setAlternatingRowColors(True)
        v.addWidget(self._workers_table)
        return page

    # ── 5. Automation ─────────────────────────────────────────────────────────
    def _pg_automation(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(14)
        v.addWidget(self._section_title("Automation Configuration & Launch"))

        box = QGroupBox("Workflow Configuration")
        f = QFormLayout(box)

        self._a_workers = QSpinBox()
        self._a_workers.setRange(1, 50)
        self._a_workers.setValue(int(self.state_manager.get_setting("default_worker_count", 3)))

        self._a_mode = QComboBox()
        self._a_mode.addItems(["Headed / Debug", "Headless"])
        saved_mode = self.state_manager.get_setting("browser_mode", "headed")
        self._a_mode.setCurrentText("Headless" if saved_mode == "headless" else "Headed / Debug")

        self._a_email = QLineEdit(self.state_manager.get_setting("test_email_pattern", "@nariwal.shop"))
        self._a_dola  = QLineEdit(self.state_manager.get_setting("dola_url", "https://dola.ai"))

        self._a_signup_url = QLineEdit(self.state_manager.get_setting("signup_flow_url", 
            "https://accounts.cloud.google.com/signup/email?continueUrl=https://console.cloud.google.com/freetrial&hl=en_US"))

        self._a_mock = QCheckBox("Simulate / Mock workflow (test without real Google signup)")
        self._a_mock.setChecked(bool(self.state_manager.get_setting("mock_mode", False)))

        self._a_screenshot = QCheckBox("Screenshot on error")
        self._a_screenshot.setChecked(bool(self.state_manager.get_setting("screenshot_on_error", True)))

        f.addRow("Number of Browsers:", self._a_workers)
        f.addRow("Browser Mode:", self._a_mode)
        f.addRow("Test Email Domain:", self._a_email)
        f.addRow("Dola.ai URL:", self._a_dola)
        f.addRow("Google Signup URL:", self._a_signup_url)
        f.addRow("", self._a_mock)
        f.addRow("", self._a_screenshot)
        v.addWidget(box)

        btn_row = QHBoxLayout()
        b_start = QPushButton("▶  Start Automation")
        b_start.setObjectName("primaryBtn")
        b_start.clicked.connect(self._start_automation)
        b_stop = QPushButton("■  Stop All")
        b_stop.setObjectName("dangerBtn")
        b_stop.clicked.connect(self._stop_all)
        btn_row.addWidget(b_start)
        btn_row.addWidget(b_stop)
        btn_row.addStretch()
        v.addLayout(btn_row)
        v.addStretch()
        return page

    # ── 6. Workflow ──────────────────────────────────────────────────────────
    def _pg_selectors(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(10)
        v.addWidget(self._section_title("Workflow Builder"))

        note = QLabel(
            "Double-click any cell to edit. Reorder steps with Up/Down buttons.\n"
            "Use variables {{EMAIL}}, {{GMAIL_CODE}}, {{SIGNUP_URL}}, {{DOLA_URL}} in 'Input Data' or 'Selector'."
        )
        note.setStyleSheet("color:#aaa; font-size:12px;")
        v.addWidget(note)

        self._wf_table = QTableWidget(0, 8)
        self._wf_table.setHorizontalHeaderLabels(
            ["Step Name", "Action", "Sel Type", "Selector / URL", "Input Data", "Delay(s)", "Timeout(ms)", "Fallback"]
        )
        self._wf_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._wf_table.horizontalHeader().setStretchLastSection(True)
        self._wf_table.setAlternatingRowColors(True)
        v.addWidget(self._wf_table)

        row1 = QHBoxLayout()
        b_up = QPushButton("▲ Move Up")
        b_up.clicked.connect(self._move_selector_up)
        b_down = QPushButton("▼ Move Down")
        b_down.clicked.connect(self._move_selector_down)
        b_add = QPushButton("Add New Step")
        b_add.clicked.connect(self._add_selector_row)
        b_del = QPushButton("Delete Step")
        b_del.clicked.connect(self._delete_selector_row)
        
        row1.addWidget(b_up)
        row1.addWidget(b_down)
        row1.addSpacing(20)
        row1.addWidget(b_add)
        row1.addWidget(b_del)
        row1.addStretch()
        
        row2 = QHBoxLayout()
        b_save = QPushButton("Save Workflow")
        b_save.setObjectName("primaryBtn")
        b_save.clicked.connect(self._save_all_workflows)
        
        b_export = QPushButton("Export to JSON")
        b_export.clicked.connect(self._export_workflow)
        b_import = QPushButton("Import JSON")
        b_import.clicked.connect(self._import_workflow)
        
        self._chk_lock = QCheckBox("🔒 Lock Workflow")
        self._chk_lock.stateChanged.connect(self._on_lock_changed)
        
        row2.addWidget(b_save)
        row2.addSpacing(20)
        row2.addWidget(b_export)
        row2.addWidget(b_import)
        row2.addSpacing(20)
        row2.addWidget(self._chk_lock)
        row2.addStretch()
        
        v.addLayout(row1)
        v.addLayout(row2)
        return page

    # ── 7. Logs ───────────────────────────────────────────────────────────────
    def _pg_logs(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.addWidget(self._section_title("Real-Time Automation Logs"))

        btn_row = QHBoxLayout()
        b_clear = QPushButton("Clear Logs")
        b_clear.setObjectName("dangerBtn")
        b_clear.setFixedWidth(120)
        b_clear.clicked.connect(self._clear_logs)
        btn_row.addWidget(b_clear)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setStyleSheet(
            "background:#0d0d14; font-family:Consolas,monospace; font-size:12px; color:#a0c080;"
            "border:1px solid #333344; border-radius:6px;"
        )
        v.addWidget(self._log_text)

        return page

    # ── 8. Settings ───────────────────────────────────────────────────────────
    def _pg_settings(self):
        page = QWidget()
        sv = QScrollArea()
        sv.setWidgetResizable(True)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(sv)

        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(14)
        sv.setWidget(inner)

        v.addWidget(self._section_title("Application Settings"))

        # Browser
        b_box = QGroupBox("Browser Settings")
        bf = QFormLayout(b_box)
        self._s_mode = QComboBox()
        self._s_mode.addItems(["headed", "headless"])
        self._s_timeout = QSpinBox()
        self._s_timeout.setRange(1000, 120000)
        self._s_timeout.setValue(15000)
        self._s_nav_timeout = QSpinBox()
        self._s_nav_timeout.setRange(5000, 120000)
        self._s_nav_timeout.setValue(30000)
        bf.addRow("Browser Mode:", self._s_mode)
        bf.addRow("Default Timeout (ms):", self._s_timeout)
        bf.addRow("Navigation Timeout (ms):", self._s_nav_timeout)
        v.addWidget(b_box)

        # Worker
        w_box = QGroupBox("Worker Settings")
        wf = QFormLayout(w_box)
        self._s_workers = QSpinBox()
        self._s_workers.setRange(1, 50)
        self._s_workers.setValue(3)
        self._s_retry = QSpinBox()
        self._s_retry.setRange(0, 10)
        self._s_retry.setValue(2)
        self._s_retry_delay = QSpinBox()
        self._s_retry_delay.setRange(1, 60)
        self._s_retry_delay.setValue(5)
        wf.addRow("Default Worker Count:", self._s_workers)
        wf.addRow("Retry Count:", self._s_retry)
        wf.addRow("Retry Delay (s):", self._s_retry_delay)
        v.addWidget(w_box)

        # Gmail
        g_box = QGroupBox("Gmail Settings")
        gf = QFormLayout(g_box)
        self._s_poll = QSpinBox()
        self._s_poll.setRange(1, 300)
        self._s_poll.setValue(5)
        self._s_email_timeout = QSpinBox()
        self._s_email_timeout.setRange(30, 600)
        self._s_email_timeout.setValue(120)
        self._s_regex = QLineEdit(r"\b[A-Z0-9]{6}\b")
        self._s_sender = QLineEdit("google")
        self._s_subject = QLineEdit("verification")
        gf.addRow("Polling Interval (s):", self._s_poll)
        gf.addRow("Email Timeout (s):", self._s_email_timeout)
        gf.addRow("Sender Filter:", self._s_sender)
        gf.addRow("Subject Filter:", self._s_subject)
        gf.addRow("Code Regex:", self._s_regex)
        v.addWidget(g_box)

        # Automation
        a_box = QGroupBox("Automation Settings")
        af = QFormLayout(a_box)
        self._s_screenshot = QCheckBox("Screenshot on error")
        self._s_screenshot.setChecked(True)
        self._s_auto_retry = QCheckBox("Auto-retry on failure")
        self._s_auto_retry.setChecked(True)
        self._s_pause_on_fail = QCheckBox("Pause worker on selector failure")
        self._s_pause_on_fail.setChecked(True)
        af.addRow("", self._s_screenshot)
        af.addRow("", self._s_auto_retry)
        af.addRow("", self._s_pause_on_fail)
        v.addWidget(a_box)

        b_save = QPushButton("Save All Settings")
        b_save.setObjectName("primaryBtn")
        b_save.clicked.connect(self._save_settings)
        v.addWidget(b_save)
        v.addStretch()
        return page

    # ── 9. About ──────────────────────────────────────────────────────────────
    def _pg_about(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(12)
        v.addWidget(self._section_title("About"))
        info = QLabel(
            "<b>Application Name:</b> Dola.ai QA &amp; Account Testing Automation<br>"
            "<b>Version:</b> 1.0.0<br>"
            "<b>Developer:</b> Internal QA Engineering Team<br>"
            "<b>Framework:</b> Python 3.13 · PySide6 (Qt6) · SQLite3<br>"
            "<b>Playwright Version:</b> 1.63+<br>"
            "<b>Chromium:</b> Playwright bundled Chromium<br><br>"
            "<i>Automated QA and Account Testing Tool for authorised test accounts<br>"
            "and Dola.ai login flow verification.</i>"
        )
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet("font-size:14px; line-height:1.8;")
        v.addWidget(info)
        v.addStretch()
        return page

    # ═══════════════════════════ HELPERS ════════════════════════════════════
    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        return lbl

    # ═══════════════════════ TIMERS & UPDATES ════════════════════════════════
    def _setup_timers(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._periodic_update)
        self._timer.start(1200)

    def _periodic_update(self):
        self._update_dashboard()
        self._refresh_logs()
        # Detect workers needing selector input
        for w in self.workers.values():
            if w.pending_selector and not self._dialog_open:
                self._open_selector_dialog(w)

    _dialog_open: bool = False

    def _open_selector_dialog(self, worker: QAWorker):
        self._dialog_open = True
        dlg = WorkflowDialog(worker, self)
        dlg.exec()
        self._dialog_open = False

    def _on_worker_updated(self, worker_id: int, status: str, step: str):
        self._update_dashboard()

    # ═══════════════════════ DASHBOARD ═══════════════════════════════════════
    def _update_dashboard(self):
        counts = {k: 0 for k in ["Total Workers", "Running", "Waiting for Gmail",
                                   "Verifying", "Paused", "Completed", "Failed"]}
        counts["Total Workers"] = len(self.workers)
        for w in self.workers.values():
            s = w.status
            if s == WorkerStatus.RUNNING:                      counts["Running"] += 1
            elif s == WorkerStatus.WAITING_FOR_GMAIL:          counts["Waiting for Gmail"] += 1
            elif s == WorkerStatus.ENTERING_VERIFICATION:
                                                               counts["Verifying"] += 1
            elif s == WorkerStatus.PAUSED:                     counts["Paused"] += 1
            elif s == WorkerStatus.COMPLETED:                  counts["Completed"] += 1
            elif s == WorkerStatus.FAILED:                     counts["Failed"] += 1

        for k, lbl in self._stat_labels.items():
            lbl.setText(str(counts.get(k, 0)))

        self._dash_table.setRowCount(len(self.workers))
        for row, (wid, w) in enumerate(sorted(self.workers.items())):
            self._dash_table.setItem(row, 0, QTableWidgetItem(f"#{wid}"))
            self._dash_table.setItem(row, 1, QTableWidgetItem(w.account_email))
            status_item = QTableWidgetItem(w.status)
            # Color-code status
            color = {
                WorkerStatus.COMPLETED: "#4caf50",
                WorkerStatus.FAILED:    "#f44336",
                WorkerStatus.PAUSED:    "#ff9800",
                WorkerStatus.RUNNING:   "#64b5f6",
                WorkerStatus.WAITING_FOR_GMAIL: "#ba68c8",
            }.get(w.status, "#e0e0e0")
            status_item.setForeground(QColor(color))
            self._dash_table.setItem(row, 2, status_item)
            self._dash_table.setItem(row, 3, QTableWidgetItem(w.step))

        gm = self.gmail_manager.get_status()
        if gm["is_connected"]:
            self._lbl_gmail_status.setText(f"Gmail: ● {gm['email']}")
            self._lbl_gmail_status.setStyleSheet("color:#4caf50;")
        else:
            self._lbl_gmail_status.setText("Gmail: ● Disconnected")
            self._lbl_gmail_status.setStyleSheet("color:#f44336;")
        self._lbl_worker_count.setText(f"Workers: {len(self.workers)}")

    # ═════════════════════════ GMAIL ═════════════════════════════════════════
    def _refresh_gmail_ui(self):
        gm = self.gmail_manager.get_status()
        self._gm_account.setText(gm["email"])
        if gm["is_connected"]:
            self._gm_status.setText("● Connected")
            self._gm_status.setStyleSheet("color:#4caf50; font-weight:bold;")
        else:
            self._gm_status.setText("● Disconnected")
            self._gm_status.setStyleSheet("color:#f44336;")
        self._gm_monitor.setText("● Active" if gm["is_monitoring"] else "● Inactive")
        self._gm_monitor.setStyleSheet("color:#4caf50;" if gm["is_monitoring"] else "color:#aaa;")
        self._gm_last.setText(gm["last_check"])
        self._gm_matched.setText(str(gm["emails_matched"]))

    def _connect_gmail(self):
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
            if not os.path.exists(creds_file):
                QMessageBox.warning(
                    self, "Missing credentials.json",
                    "Place your Google OAuth 2.0 client credentials file (credentials.json) "
                    "in the dola_qa_desktop folder.\n\n"
                    "Download it from:\n"
                    "Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs"
                )
                return

            QMessageBox.information(self, "Google OAuth",
                "Your browser will open for Google sign-in.\nSign in with your authorized Gmail account.")

            flow = InstalledAppFlow.from_client_secrets_file(
                creds_file, scopes=["https://www.googleapis.com/auth/gmail.modify"]
            )
            creds = flow.run_local_server(port=0)

            service = build("gmail", "v1", credentials=creds)
            profile = service.users().getProfile(userId="me").execute()
            email = profile.get("emailAddress", "unknown@gmail.com")

            self.gmail_manager.save_credentials_securely(email, {
                "token":          creds.token,
                "refresh_token":  creds.refresh_token,
                "token_uri":      creds.token_uri,
                "client_id":      creds.client_id,
                "client_secret":  creds.client_secret,
                "scopes":         list(creds.scopes or []),
            })
            self._refresh_gmail_ui()
            QMessageBox.information(self, "Connected", f"Gmail connected: {email}")

        except ImportError as ie:
            QMessageBox.warning(self, "Missing Dependency",
                f"Required library missing: {ie}\n\n"
                "Run in terminal:\n  python -m pip install google-auth-oauthlib google-api-python-client")
        except Exception as e:
            QMessageBox.warning(self, "OAuth Error", f"Authentication failed or was cancelled:\n{e}")

    def _check_gmail_connection(self):
        gm = self.gmail_manager.get_status()
        QMessageBox.information(self, "Gmail Status",
            f"Account: {gm['email']}\nConnected: {gm['is_connected']}\n"
            f"Monitoring: {gm['is_monitoring']}\nEmails matched: {gm['emails_matched']}")

    def _toggle_monitoring(self):
        self.gmail_manager.is_monitoring = not self.gmail_manager.is_monitoring
        self.state_manager.set_setting("gmail_is_monitoring", self.gmail_manager.is_monitoring)
        self._refresh_gmail_ui()

    def _disconnect_gmail(self):
        self.gmail_manager.disconnect()
        self._refresh_gmail_ui()

    # ═════════════════════════ AUTOMATION ═══════════════════════════════════
    def _start_automation(self):
        count   = self._a_workers.value()
        mode    = "headless" if "Headless" in self._a_mode.currentText() else "headed"
        mock    = self._a_mock.isChecked()

        self.state_manager.set_setting("browser_mode",     mode)
        self.state_manager.set_setting("default_worker_count", count)
        self.state_manager.set_setting("dola_url",         self._a_dola.text().strip())
        self.state_manager.set_setting("test_email_pattern", self._a_email.text().strip())
        self.state_manager.set_setting("signup_flow_url",  self._a_signup_url.text().strip())
        self.state_manager.set_setting("mock_mode",        mock)
        self.state_manager.set_setting("screenshot_on_error", self._a_screenshot.isChecked())

        accounts_db = self.state_manager.get_all_accounts()
        accounts_list = [a["account_email"] for a in accounts_db if a.get("account_email")]
        
        target_emails = []
        if accounts_list:
            dlg = EmailSelectionDialog(accounts_list, count, self)
            if dlg.exec() == QDialog.Accepted:
                target_emails = dlg.selected_emails
            else:
                return # user cancelled
        
        if not target_emails:
            # Random emails
            target_emails = [None] * count

        self._lbl_browser_mode.setText(f"Browser: {mode.capitalize()}")
        self._lbl_auto_status.setText("Automation: ● Running")
        self._lbl_auto_status.setStyleSheet("color:#4caf50;")

        for i, email in enumerate(target_emails, start=1):
            if i not in self.workers:
                w = QAWorker(
                    i, self.state_manager, self.gmail_manager, self.workflow_manager,
                    on_update_callback=lambda wid, s, st: self.bridge.worker_updated.emit(wid, s, st),
                )
                self.workers[i] = w
                w.start_workflow(mock_mode=mock, account_email=email)
                self.state_manager.log(None, "INFO", f"Worker #{i} spawned ({w.account_email})")
            else:
                w = self.workers[i]
                if w.status in (WorkerStatus.IDLE, WorkerStatus.STOPPED, WorkerStatus.FAILED):
                    w.start_workflow(mock_mode=mock, account_email=email)
                    self.state_manager.log(None, "INFO", f"Worker #{i} restarted ({w.account_email})")

        self._navigate("Dashboard")

    def _start_all(self):
        self._start_automation()

    def _pause_all(self):
        for w in self.workers.values():
            w.pause()

    def _resume_all(self):
        for w in self.workers.values():
            if w.status == WorkerStatus.PAUSED:
                w.resume()

    def _stop_all(self):
        for w in self.workers.values():
            threading.Thread(target=w.stop, daemon=True).start()
        self._lbl_auto_status.setText("Automation: ● Stopped")
        self._lbl_auto_status.setStyleSheet("color:#f44336;")

    # ═════════════════════════ WORKERS PAGE ═════════════════════════════════
    def _refresh_workers(self):
        self._workers_table.blockSignals(True)
        self._workers_table.setRowCount(len(self.workers))
        for row, (wid, w) in enumerate(sorted(self.workers.items())):
            self._workers_table.setItem(row, 0, QTableWidgetItem(str(wid)))
            self._workers_table.setItem(row, 1, QTableWidgetItem(w.account_email))
            si = QTableWidgetItem(w.status)
            si.setForeground(QColor({
                WorkerStatus.COMPLETED: "#4caf50", WorkerStatus.FAILED: "#f44336",
                WorkerStatus.PAUSED: "#ff9800", WorkerStatus.RUNNING: "#64b5f6",
                WorkerStatus.WAITING_FOR_GMAIL: "#ba68c8"
            }.get(w.status, "#e0e0e0")))
            self._workers_table.setItem(row, 2, si)
            self._workers_table.setItem(row, 3, QTableWidgetItem(w.step))
            self._workers_table.setItem(row, 4, QTableWidgetItem(w.last_url[:60] if w.last_url else "—"))

            aw = QWidget()
            al = QHBoxLayout(aw)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(4)
            for label, fn in [("Pause", w.pause), ("Resume", w.resume), ("Stop", w.stop), ("Restart", w.restart)]:
                b = QPushButton(label)
                b.setFixedHeight(24)
                b.clicked.connect(lambda _, f=fn: f())
                al.addWidget(b)
            self._workers_table.setCellWidget(row, 5, aw)
        self._workers_table.blockSignals(False)

    # ═════════════════════════ ACCOUNTS PAGE ════════════════════════════════
    def _refresh_accounts(self):
        accounts = self.state_manager.get_all_accounts()
        self._accounts_table.setRowCount(len(accounts))
        for row, a in enumerate(accounts):
            self._accounts_table.setItem(row, 0, QTableWidgetItem(a["account_email"]))
            self._accounts_table.setItem(row, 1, QTableWidgetItem(f"Worker #{a['worker_id']}"))
            self._accounts_table.setItem(row, 2, QTableWidgetItem(a["status"]))
            self._accounts_table.setItem(row, 3, QTableWidgetItem(str(a["created_at"] or "—")))
            self._accounts_table.setItem(row, 4, QTableWidgetItem(str(a["dola_status"] or "—")))
            self._accounts_table.setItem(row, 5, QTableWidgetItem(str(a["last_activity"] or "—")))

    def _delete_selected_accounts(self):
        selected_rows = set(item.row() for item in self._accounts_table.selectedItems())
        if not selected_rows: return
        emails = [self._accounts_table.item(row, 0).text() for row in selected_rows]
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete {len(emails)} account(s)?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.state_manager.delete_accounts(emails)
            self._refresh_accounts()

    def _delete_all_accounts(self):
        reply = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete ALL accounts?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            emails = [self._accounts_table.item(row, 0).text() for row in range(self._accounts_table.rowCount())]
            self.state_manager.delete_accounts(emails)
            self._refresh_accounts()

    def _export_accounts(self):
        os.makedirs("accounts", exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Export Accounts", "accounts/exported_accounts.json", "JSON Files (*.json)")
        if path:
            accounts = self.state_manager.get_all_accounts()
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(accounts, f, indent=4)
                QMessageBox.information(self, "Success", f"Accounts exported to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export accounts:\n{e}")

    def _import_accounts(self):
        os.makedirs("accounts", exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Import Accounts", "accounts", "JSON Files (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    accounts = json.load(f)
                self.state_manager.replace_all_accounts(accounts)
                self._refresh_accounts()
                QMessageBox.information(self, "Success", f"Imported {len(accounts)} accounts successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import accounts:\n{e}")

    # ═════════════════════════ SELECTORS PAGE ════════════════════════════════
    def _create_workflow_combo(self, items, current):
        cb = QComboBox()
        cb.addItems(items)
        if current and current not in items:
            cb.addItem(current)
        cb.setCurrentText(current)
        cb.setStyleSheet("background: transparent; border: none;")
        return cb

    def _refresh_selectors(self):
        self._wf_table.blockSignals(True)
        steps = self.workflow_manager.get_all()
        self._wf_table.setRowCount(len(steps))
        
        actions = ["Navigate", "Type", "Click", "Click If Exists", "Wait for Gmail", "Wait for Element", 
                   "Skip Next If Exists", "Skip Next If Missing", "Jump To If Exists", "Jump To If Missing", 
                   "Stop If URL Contains", "Jump To If URL Contains", "Save Cookies", "Stop Workflow"]
        sel_types = ["XPath", "CSS", "ID", "Text"]
        
        for row, s in enumerate(steps):
            for col, key in enumerate(["step_name", "action", "selector_type", "selector_value",
                                        "input_value", "delay_seconds", "timeout", "fallback_selector"]):
                val = str(s.get(key, ""))
                if col == 1:
                    self._wf_table.setCellWidget(row, col, self._create_workflow_combo(actions, val))
                elif col == 2:
                    self._wf_table.setCellWidget(row, col, self._create_workflow_combo(sel_types, val))
                else:
                    self._wf_table.setItem(row, col, QTableWidgetItem(val))
        self._wf_table.blockSignals(False)
        
        locked = bool(self.state_manager.get_setting("workflow_locked", False))
        self._update_workflow_lock(locked)

    def _add_selector_row(self):
        row = self._wf_table.rowCount()
        self._wf_table.insertRow(row)
        
        actions = ["Navigate", "Type", "Click", "Click If Exists", "Wait for Gmail", "Wait for Element", 
                   "Skip Next If Exists", "Skip Next If Missing", "Jump To If Exists", "Jump To If Missing", 
                   "Stop If URL Contains", "Jump To If URL Contains", "Save Cookies", "Stop Workflow"]
        sel_types = ["XPath", "CSS", "ID", "Text"]
        
        for col, val in enumerate(["New Step", "Click", "XPath", "", "", "2", "10000", ""]):
            if col == 1:
                self._wf_table.setCellWidget(row, col, self._create_workflow_combo(actions, val))
            elif col == 2:
                self._wf_table.setCellWidget(row, col, self._create_workflow_combo(sel_types, val))
            else:
                self._wf_table.setItem(row, col, QTableWidgetItem(val))

    def _delete_selector_row(self):
        row = self._wf_table.currentRow()
        if row >= 0:
            self._wf_table.removeRow(row)

    def _save_all_workflows(self, silent=False):
        steps = []
        for row in range(self._wf_table.rowCount()):
            def cell(c):
                w = self._wf_table.cellWidget(row, c)
                if hasattr(w, "currentText"):
                    return w.currentText().strip()
                return (self._wf_table.item(row, c) or QTableWidgetItem()).text().strip()
                
            name = cell(0)
            if not name: continue
            try: delay = int(cell(5))
            except: delay = 2
            try: timeout = int(cell(6))
            except: timeout = 10000
            
            steps.append({
                "step_name": name,
                "action": cell(1),
                "selector_type": cell(2),
                "selector_value": cell(3),
                "input_value": cell(4),
                "delay_seconds": delay,
                "timeout": timeout,
                "fallback_selector": cell(7)
            })
        
        self.workflow_manager.replace_all(steps)
        if not silent:
            QMessageBox.information(self, "Success", "Workflow saved successfully!")
            self._refresh_selectors()

    def _export_workflow(self):
        os.makedirs("workflows", exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Export Workflow", "workflows/my_workflow.json", "JSON Files (*.json)")
        if path:
            steps = self.workflow_manager.get_all()
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(steps, f, indent=4)
                QMessageBox.information(self, "Success", f"Workflow exported to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export workflow:\n{e}")

    def _import_workflow(self):
        os.makedirs("workflows", exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Import Workflow", "workflows", "JSON Files (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    steps = json.load(f)
                self.workflow_manager.replace_all(steps)
                self._refresh_selectors()
                QMessageBox.information(self, "Success", "Workflow imported successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import workflow:\n{e}")

    def _move_selector_up(self):
        row = self._wf_table.currentRow()
        if row > 0:
            self._swap_selector_rows(row, row - 1)

    def _move_selector_down(self):
        row = self._wf_table.currentRow()
        if row >= 0 and row < self._wf_table.rowCount() - 1:
            self._swap_selector_rows(row, row + 1)

    def _on_lock_changed(self, state):
        locked = state != 0
        self.state_manager.set_setting("workflow_locked", locked)
        self._update_workflow_lock(locked)

    def _update_workflow_lock(self, locked: bool):
        self._chk_lock.blockSignals(True)
        self._chk_lock.setChecked(locked)
        self._chk_lock.blockSignals(False)
        
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if not locked:
            flags |= Qt.ItemIsEditable
            
        for row in range(self._wf_table.rowCount()):
            for col in range(self._wf_table.columnCount()):
                item = self._wf_table.item(row, col)
                if item: item.setFlags(flags)
                w = self._wf_table.cellWidget(row, col)
                if w: w.setEnabled(not locked)

    def _swap_selector_rows(self, r1: int, r2: int):
        self._wf_table.blockSignals(True)
        # Swap all items in the UI table
        for col in range(self._wf_table.columnCount()):
            w1 = self._wf_table.cellWidget(r1, col)
            w2 = self._wf_table.cellWidget(r2, col)
            if w1 and w2 and hasattr(w1, 'currentText'):
                t1 = w1.currentText()
                t2 = w2.currentText()
                w1.setCurrentText(t2)
                w2.setCurrentText(t1)
            else:
                item1 = self._wf_table.takeItem(r1, col)
                item2 = self._wf_table.takeItem(r2, col)
                self._wf_table.setItem(r1, col, item2)
                self._wf_table.setItem(r2, col, item1)
        self._wf_table.selectRow(r2)
        self._wf_table.blockSignals(False)

        # Update order in DB
        self._save_all_workflows(silent=True)

    # ═════════════════════════ LOGS PAGE ════════════════════════════════════
    _last_log_hash = 0
    def _refresh_logs(self):
        logs = self.state_manager.get_recent_logs(150)
        current_hash = hash(str([l["id"] for l in logs]))
        if current_hash == self._last_log_hash:
            return
        self._last_log_hash = current_hash
        
        lines = []
        for entry in logs:
            wid = f"Worker #{entry['worker_id']} " if entry["worker_id"] else ""
            lvl_color = {"ERROR": "#f44336", "WARN": "#ff9800", "INFO": "#a0c080", "DEBUG": "#888"}.get(
                entry["level"], "#e0e0e0")
            lines.append(
                f'<span style="color:#666">{entry["timestamp"]}</span> '
                f'<span style="color:#64b5f6">{wid}</span>'
                f'<span style="color:{lvl_color}">[{entry["level"]}]</span> '
                f'{entry["message"]}'
            )
        
        # Save scrollbar position
        scrollbar = self._log_text.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5 if scrollbar else True
        
        self._log_text.setHtml("<br>".join(lines))
        
        if at_bottom:
            cursor = self._log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._log_text.setTextCursor(cursor)

    def _clear_logs(self):
        self.state_manager.clear_logs()
        self._log_text.clear()

    # ═════════════════════════ SETTINGS PAGE ════════════════════════════════
    def _load_settings_values(self):
        s = self.state_manager.get_all_settings()
        self._s_mode.setCurrentText(s.get("browser_mode", "headed"))
        self._s_timeout.setValue(int(s.get("default_timeout", 15000)))
        self._s_nav_timeout.setValue(int(s.get("navigation_timeout", 30000)))
        self._s_workers.setValue(int(s.get("default_worker_count", 3)))
        self._s_retry.setValue(int(s.get("retry_count", 2)))
        self._s_retry_delay.setValue(int(s.get("retry_delay", 5)))
        self._s_poll.setValue(int(s.get("gmail_polling_interval", 5)))
        self._s_email_timeout.setValue(int(s.get("email_timeout", 120)))
        self._s_regex.setText(s.get("verification_code_regex", r"\b\d{6}\b"))
        self._s_sender.setText(s.get("sender_filter", "google"))
        self._s_subject.setText(s.get("subject_filter", "verification"))
        self._s_screenshot.setChecked(bool(s.get("screenshot_on_error", True)))
        self._s_auto_retry.setChecked(bool(s.get("auto_retry", True)))
        self._s_pause_on_fail.setChecked(bool(s.get("pause_on_selector_failure", True)))

    def _save_settings(self):
        sm = self.state_manager
        sm.set_setting("browser_mode",              self._s_mode.currentText())
        sm.set_setting("default_timeout",           self._s_timeout.value())
        sm.set_setting("navigation_timeout",        self._s_nav_timeout.value())
        sm.set_setting("default_worker_count",      self._s_workers.value())
        sm.set_setting("retry_count",               self._s_retry.value())
        sm.set_setting("retry_delay",               self._s_retry_delay.value())
        sm.set_setting("gmail_polling_interval",    self._s_poll.value())
        sm.set_setting("email_timeout",             self._s_email_timeout.value())
        sm.set_setting("verification_code_regex",   self._s_regex.text())
        sm.set_setting("sender_filter",             self._s_sender.text())
        sm.set_setting("subject_filter",            self._s_subject.text())
        sm.set_setting("screenshot_on_error",       self._s_screenshot.isChecked())
        sm.set_setting("auto_retry",                self._s_auto_retry.isChecked())
        sm.set_setting("pause_on_selector_failure", self._s_pause_on_fail.isChecked())
        QMessageBox.information(self, "Saved", "All settings saved successfully.")


# ═══════════════════════════ ENTRY POINT ═════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    win = DolaQAApp()
    win._navigate("Dashboard")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
