from state_manager import StateManager

sm = StateManager()
conn = sm.get_connection()
conn.execute(
    "UPDATE workflow_steps SET selector_value = ?, fallback_selector = ? WHERE step_name = ?", 
    (
        "//input[@type='email' or @name='identifier' or @id='identifierId' or @name='login_hint']", 
        "input[type='email'], input[name='login_hint']", 
        "2. Type Email"
    )
)
conn.commit()
