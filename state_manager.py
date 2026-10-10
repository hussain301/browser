import sqlite3
import json
import os
import time
from typing import List, Dict, Any, Optional

DEFAULT_WORKFLOW_STEPS = [
    {
        "step_name": "1. Navigate to Google Signup",
        "action": "Navigate",
        "selector_type": "URL",
        "selector_value": "{{SIGNUP_URL}}",
        "input_value": "",
        "delay_seconds": 10,
        "timeout": 30000,
        "fallback_selector": ""
    },
    {
        "step_name": "2. Type Email",
        "action": "Type",
        "selector_type": "XPath",
        "selector_value": "//input[@type='email' or @name='identifier' or @id='identifierId' or @name='login_hint']",
        "input_value": "{{EMAIL}}",
        "delay_seconds": 5,
        "timeout": 15000,
        "fallback_selector": "input[type='email'], input[name='login_hint']"
    },
    {
        "step_name": "3. Click Next (Email)",
        "action": "Click",
        "selector_type": "XPath",
        "selector_value": "//button[.//span[contains(text(),'Next') or contains(text(),'Continue')]]",
        "input_value": "",
        "delay_seconds": 5,
        "timeout": 15000,
        "fallback_selector": "#identifierNext button"
    },
    {
        "step_name": "4. Wait for Verification Email",
        "action": "Wait for Gmail",
        "selector_type": "None",
        "selector_value": "",
        "input_value": "",
        "delay_seconds": 2,
        "timeout": 120000,
        "fallback_selector": ""
    },
    {
        "step_name": "5. Type Verification Code",
        "action": "Type",
        "selector_type": "XPath",
        "selector_value": "//input[@name='pinInput' or @name='code' or @id='code']",
        "input_value": "{{GMAIL_CODE}}",
        "delay_seconds": 5,
        "timeout": 20000,
        "fallback_selector": "input[name='pinInput']"
    },
    {
        "step_name": "6. Click Verify Submit",
        "action": "Click",
        "selector_type": "XPath",
        "selector_value": "//button[@aria-label='Verify' or @type='submit']",
        "input_value": "",
        "delay_seconds": 5,
        "timeout": 10000,
        "fallback_selector": "button[aria-label='Verify']"
    },
    {
        "step_name": "7. Navigate to Dola.ai",
        "action": "Navigate",
        "selector_type": "URL",
        "selector_value": "{{DOLA_URL}}",
        "input_value": "",
        "delay_seconds": 5,
        "timeout": 30000,
        "fallback_selector": ""
    },
    {
        "step_name": "8. Click Dola Login Button",
        "action": "Click",
        "selector_type": "XPath",
        "selector_value": "//button[contains(.,'Login') or contains(.,'Log In') or contains(.,'Sign In')]",
        "input_value": "",
        "delay_seconds": 3,
        "timeout": 15000,
        "fallback_selector": "text=Login"
    },
    {
        "step_name": "9. Click Continue with Google",
        "action": "Click",
        "selector_type": "XPath",
        "selector_value": "//button[contains(.,'Google') or contains(.,'Continue with Google') or contains(.,'Sign in with Google')]",
        "input_value": "",
        "delay_seconds": 5,
        "timeout": 15000,
        "fallback_selector": "text=Continue with Google"
    },
    {
        "step_name": "10. Verify Login Success",
        "action": "Wait for Element",
        "selector_type": "CSS",
        "selector_value": "[data-testid='user-profile'], .user-avatar, #flow-end-msg-send",
        "input_value": "",
        "delay_seconds": 2,
        "timeout": 20000,
        "fallback_selector": "//div[contains(@class,'avatar') or contains(@class,'profile')]"
    }
]

DEFAULT_SETTINGS = {
    "browser_mode": "headed",
    "browser_executable": "",
    "default_timeout": 15000,
    "navigation_timeout": 30000,
    "default_worker_count": 3,
    "max_concurrent_workers": 10,
    "retry_count": 2,
    "retry_delay": 5,
    "gmail_polling_interval": 5,
    "email_timeout": 120,
    "sender_filter": "google",
    "subject_filter": "verification",
    "verification_code_regex": r"\b[A-Z0-9]{6}\b",
    "dola_url": "https://dola.ai",
    "test_email_pattern": "@nariwal.shop",
    "signup_flow_url": "https://accounts.cloud.google.com/signup/email?continueUrl=https://console.cloud.google.com/freetrial&hl=en_US",
    "mock_mode": False,
    "screenshot_on_error": True,
    "workflow_locked": False
}

class StateManager:
    def __init__(self, db_path: str = "qa_testing.db"):
        self.db_path = db_path
        self._init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id INTEGER PRIMARY KEY,
                    account_email TEXT,
                    status TEXT,
                    step TEXT,
                    last_url TEXT,
                    session_state TEXT,
                    error_message TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    account_email TEXT PRIMARY KEY,
                    worker_id INTEGER,
                    status TEXT,
                    created_at TEXT,
                    dola_status TEXT,
                    last_activity TEXT
                );
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step_name TEXT UNIQUE,
                    action TEXT,
                    selector_type TEXT,
                    selector_value TEXT,
                    input_value TEXT,
                    delay_seconds INTEGER DEFAULT 2,
                    timeout INTEGER DEFAULT 10000,
                    fallback_selector TEXT,
                    order_idx INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS test_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    status TEXT,
                    worker_count INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    worker_id INTEGER,
                    level TEXT,
                    message TEXT
                );
                CREATE TABLE IF NOT EXISTS gmail_auth (
                    id INTEGER PRIMARY KEY,
                    email TEXT,
                    status TEXT,
                    connected_at TEXT,
                    encrypted_token TEXT
                );
            """)
            conn.commit()

            # Seed workflow steps
            for i, s in enumerate(DEFAULT_WORKFLOW_STEPS):
                cur.execute(
                    "INSERT OR IGNORE INTO workflow_steps "
                    "(step_name, action, selector_type, selector_value, input_value, delay_seconds, timeout, fallback_selector, order_idx) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        s["step_name"], s["action"], s["selector_type"], s["selector_value"],
                        s["input_value"], s["delay_seconds"], s["timeout"], s["fallback_selector"], i
                    ),
                )
            for k, v in DEFAULT_SETTINGS.items():
                cur.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)",
                    (k, json.dumps(v)),
                )
            conn.commit()

    # ── Settings ─────────────────────────────────────────────────────────────
    def get_setting(self, key: str, default=None):
        with self.get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
            return default

    def set_setting(self, key: str, value: Any):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                (key, json.dumps(value)),
            )
            conn.commit()

    def get_all_settings(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        result: Dict[str, Any] = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except Exception:
                result[r["key"]] = r["value"]
        return result

    # ── Workflow Steps ─────────────────────────────────────────────────────────────
    def get_workflow_steps(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM workflow_steps ORDER BY order_idx ASC, id ASC").fetchall()]

    def update_workflow_step(self, step_name: str, action: str, selector_type: str, selector_value: str, input_value: str, delay_seconds: int, timeout: int, fallback_selector: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE workflow_steps SET action=?, selector_type=?, selector_value=?, input_value=?, delay_seconds=?, timeout=?, fallback_selector=? WHERE step_name=?",
                (action, selector_type, selector_value, input_value, delay_seconds, timeout, fallback_selector, step_name),
            )
            conn.commit()

    def replace_all_workflow_steps(self, steps: List[Dict[str, Any]]):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM workflow_steps")
            for i, s in enumerate(steps):
                conn.execute(
                    "INSERT INTO workflow_steps "
                    "(step_name, action, selector_type, selector_value, input_value, delay_seconds, timeout, fallback_selector, order_idx) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        s.get("step_name", ""), s.get("action", ""), s.get("selector_type", ""), 
                        s.get("selector_value", ""), s.get("input_value", ""), 
                        s.get("delay_seconds", 2), s.get("timeout", 10000), 
                        s.get("fallback_selector", ""), i
                    ),
                )
            conn.commit()

    def update_workflow_orders(self, names_in_order: List[str]):
        with self.get_connection() as conn:
            for i, name in enumerate(names_in_order):
                conn.execute("UPDATE workflow_steps SET order_idx=? WHERE step_name=?", (i, name))
            conn.commit()

    # ── Workers ───────────────────────────────────────────────────────────────
    def save_worker_state(self, worker_id: int, account: str, status: str,
                          step: str, last_url: str = "", error_message: str = ""):
        with self.get_connection() as conn:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT OR REPLACE INTO workers (worker_id, account_email, status, step, last_url, error_message, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (worker_id, account, status, step, last_url, error_message, now),
            )
            if account:
                dola = "Verified ✓" if status == "Completed" else ("Failed ✗" if status == "Failed" else "—")
                row = conn.execute("SELECT created_at FROM accounts WHERE account_email=?", (account,)).fetchone()
                created_at = row["created_at"] if row else now
                
                conn.execute(
                    "INSERT INTO accounts (account_email, worker_id, status, created_at, dola_status, last_activity) "
                    "VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(account_email) DO UPDATE SET "
                    "worker_id=excluded.worker_id, status=excluded.status, "
                    "dola_status=excluded.dola_status, last_activity=excluded.last_activity",
                    (account, worker_id, status, created_at, dola, now),
                )
            conn.commit()

    def get_all_workers(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM workers").fetchall()]

    def get_all_accounts(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM accounts").fetchall()]

    def delete_accounts(self, emails: List[str]):
        if not emails: return
        with self.get_connection() as conn:
            placeholders = ",".join("?" for _ in emails)
            conn.execute(f"DELETE FROM accounts WHERE account_email IN ({placeholders})", emails)
            conn.commit()

    def replace_all_accounts(self, accounts: List[Dict[str, Any]]):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM accounts")
            for a in accounts:
                conn.execute(
                    "INSERT INTO accounts (account_email, worker_id, status, created_at, dola_status, last_activity) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        a.get("account_email", ""),
                        a.get("worker_id", 0),
                        a.get("status", ""),
                        a.get("created_at", ""),
                        a.get("dola_status", ""),
                        a.get("last_activity", "")
                    )
                )
            conn.commit()

    # ── Logs ──────────────────────────────────────────────────────────────────
    def log(self, worker_id: Optional[int], level: str, message: str):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO logs (timestamp, worker_id, level, message) VALUES (?,?,?,?)",
                (time.strftime("%H:%M:%S"), worker_id, level, message),
            )
            conn.commit()

    def get_recent_logs(self, limit=100) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM (SELECT * FROM logs ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,)
            ).fetchall()]

    def clear_logs(self):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM logs")
            conn.commit()
