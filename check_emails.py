import os, json, sqlite3, base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

conn = sqlite3.connect('qa_testing.db')
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT value FROM settings WHERE key='gmail_token_fallback'").fetchone()

val = row['value']
if isinstance(val, str) and val.startswith('"'): val = json.loads(val)
creds = Credentials.from_authorized_user_info(json.loads(val))
service = build('gmail', 'v1', credentials=creds)

q = "to:chloeaxu13@nariwal.shop from:google subject:verification"
results = service.users().messages().list(userId='me', q=q).execute()
messages = results.get('messages', [])

if messages:
    msg = service.users().messages().get(userId='me', id=messages[0]['id'], format='full').execute()
    payload = msg.get("payload", {})
    
    body_text = msg.get("snippet", "")
    for part in payload.get("parts", []):
        if part.get("mimeType") in ("text/plain", "text/html"):
            data = part.get("body", {}).get("data")
            if data:
                body_text += " " + base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    
    print("BODY TEXT:\n", body_text)
