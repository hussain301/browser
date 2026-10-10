"""
Gmail Manager — OAuth authorization + verification-email search.
Stores credentials securely via Windows Credential Manager (keyring).
"""
import os
import json
import re
import base64
import datetime
from typing import Optional, Dict, Any


# ---------------------------------------------------------------------------
# Optional secure credential storage
# ---------------------------------------------------------------------------
try:
    import keyring as _keyring
except ImportError:
    _keyring = None  # type: ignore

SERVICE_NAME = "DolaQAAutomation"


class GmailManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager
        self.is_monitoring = bool(self.state_manager.get_setting("gmail_is_monitoring", False))
        self.last_check_time = "Never"
        self.emails_matched = 0
        self.connected_email: Optional[str] = None
        self._creds_cache: Optional[Dict] = None
        self._load_saved_session()

    # ── Persistence ───────────────────────────────────────────────────────────
    def _load_saved_session(self):
        self.connected_email = self.state_manager.get_setting("gmail_connected_email", None)

    def save_credentials_securely(self, email: str, token_data: Dict):
        """Save OAuth token to Windows Credential Manager (keyring) with DB fallback."""
        self.connected_email = email
        self._creds_cache = token_data
        self.state_manager.set_setting("gmail_connected_email", email)

        token_json = json.dumps(token_data)
        saved = False
        if _keyring:
            try:
                _keyring.set_password(SERVICE_NAME, email, token_json)
                saved = True
            except Exception:
                pass
        if not saved:
            self.state_manager.set_setting("gmail_token_fallback", token_json)

        self.state_manager.log(None, "INFO", f"Gmail connected: {email}")

    def get_credentials(self) -> Optional[Dict]:
        if self._creds_cache:
            return self._creds_cache
        if not self.connected_email:
            return None
        token_str = None
        if _keyring:
            try:
                token_str = _keyring.get_password(SERVICE_NAME, self.connected_email)
            except Exception:
                pass
        if not token_str:
            token_str = self.state_manager.get_setting("gmail_token_fallback", None)
        if token_str:
            try:
                self._creds_cache = json.loads(token_str)
                return self._creds_cache
            except Exception:
                return None
        return None

    def disconnect(self):
        old = self.connected_email
        if old and _keyring:
            try:
                _keyring.delete_password(SERVICE_NAME, old)
            except Exception:
                pass
        self.state_manager.set_setting("gmail_connected_email", None)
        self.state_manager.set_setting("gmail_token_fallback", None)
        self.connected_email = None
        self._creds_cache = None
        self.is_monitoring = False
        self.state_manager.log(None, "INFO", f"Gmail disconnected: {old}")

    # ── Status ────────────────────────────────────────────────────────────────
    def get_status(self) -> Dict[str, Any]:
        return {
            "email": self.connected_email or "Not connected",
            "is_connected": bool(self.connected_email),
            "is_monitoring": self.is_monitoring,
            "last_check": self.last_check_time,
            "emails_matched": self.emails_matched,
        }

    # ── Code Extraction ───────────────────────────────────────────────────────
    def extract_code(self, text: str, regex_pattern: Optional[str] = None) -> Optional[str]:
        if not regex_pattern:
            regex_pattern = self.state_manager.get_setting("verification_code_regex", r"\b\d{6}\b")
        m = re.search(regex_pattern, text)
        return m.group(0) if m else None

    # ── Email Search ──────────────────────────────────────────────────────────
    def search_verification_email(self, target_account: str, after_timestamp: float = 0) -> Optional[Dict[str, str]]:
        """
        Find a verification email sent to *target_account*.
        If after_timestamp is > 0, strictly filters for emails received after that epoch time.
        Returns { matched, target_account, code, subject, received_at }
        or None if not found.
        """
        self.last_check_time = datetime.datetime.now().strftime("%H:%M:%S")

        # ── Mock mode ────────────────────────────────────────────────────────
        mock_mode = self.state_manager.get_setting("mock_mode", False)
        if mock_mode or not self.connected_email:
            import time, random
            time.sleep(random.uniform(1.5, 3.0))          # simulate network delay
            self.emails_matched += 1
            return {
                "matched": True,
                "target_account": target_account,
                "code": "".join([str(random.randint(0, 9)) for _ in range(6)]),
                "subject": "Your Google verification code",
                "received_at": self.last_check_time,
            }

        # ── Real Gmail API ────────────────────────────────────────────────────
        creds_data = self.get_credentials()
        if not creds_data:
            return None
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_info(creds_data)
            service = build("gmail", "v1", credentials=creds)

            sender_f = self.state_manager.get_setting("sender_filter", "google")
            subject_f = self.state_manager.get_setting("subject_filter", "verification")
            
            q = f"to:{target_account} from:{sender_f} subject:{subject_f}"
            if after_timestamp > 0:
                q += f" after:{int(after_timestamp)}"
                
            results = service.users().messages().list(userId="me", q=q, maxResults=5).execute()
            messages = results.get("messages", [])

            for msg_ref in messages:
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="full"
                ).execute()
                payload = msg.get("payload", {})
                headers = payload.get("headers", [])
                to_hdr = next((h["value"] for h in headers if h["name"].lower() == "to"), "")
                subj = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

                # Strict recipient matching
                if target_account.lower() not in to_hdr.lower():
                    continue

                body_text = msg.get("snippet", "")
                for part in payload.get("parts", []):
                    if part.get("mimeType") in ("text/plain", "text/html"):
                        data = part.get("body", {}).get("data")
                        if data:
                            body_text += " " + base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

                code = self.extract_code(body_text)
                if code:
                    self.emails_matched += 1
                    self.state_manager.log(None, "INFO", f"Gmail API: Found code {code} in email sent to {target_account}")
                    
                    # Delete (trash) the email so it doesn't get reused or clutter the inbox
                    try:
                        service.users().messages().trash(userId='me', id=msg_ref['id']).execute()
                        self.state_manager.log(None, "INFO", f"Gmail API: Deleted the processed verification email")
                    except Exception as e:
                        self.state_manager.log(None, "WARN", f"Gmail API: Failed to delete email: {e}")

                    return {
                        "matched": True,
                        "target_account": target_account,
                        "code": code,
                        "subject": subj,
                        "received_at": self.last_check_time,
                    }
        except Exception as e:
            self.state_manager.log(None, "ERROR", f"Gmail API error: {str(e)}")

        return None
