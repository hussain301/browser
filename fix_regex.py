import sqlite3
import json

conn = sqlite3.connect('qa_testing.db')
val = json.dumps(r'\b[A-Z0-9]{6}\b')
conn.execute("UPDATE settings SET value=? WHERE key='verification_code_regex'", (val,))
conn.commit()
print("UPDATED DB")
