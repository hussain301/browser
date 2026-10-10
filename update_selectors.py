import sqlite3

conn = sqlite3.connect('qa_testing.db')

# Verification code input
conn.execute("""
    UPDATE selectors 
    SET selector = "//input[@name='pinInput' or @name='code' or @id='code']",
        fallback_selector = "input[name='pinInput']"
    WHERE name = 'Google Verification Code Input'
""")

# Verify Submit button
conn.execute("""
    UPDATE selectors 
    SET selector = "//button[@aria-label='Verify' or @type='submit']",
        fallback_selector = "button[aria-label='Verify']"
    WHERE name = 'Google Verify Submit Button'
""")

conn.commit()
print("Updated selectors in DB")
