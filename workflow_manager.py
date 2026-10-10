import sqlite3
import json
from typing import List, Dict, Any

class WorkflowManager:
    def __init__(self, state_manager):
        self.state_manager = state_manager

    def get_all(self) -> List[Dict[str, Any]]:
        return self.state_manager.get_workflow_steps()

    def update_full(self, name: str, action: str, sel_type: str, selector: str, input_val: str, delay: int, timeout: int, fallback: str):
        self.state_manager.update_workflow_step(name, action, sel_type, selector, input_val, delay, timeout, fallback)

    def replace_all(self, steps: List[Dict[str, Any]]):
        self.state_manager.replace_all_workflow_steps(steps)

    def update_orders(self, names_in_order: List[str]):
        self.state_manager.update_workflow_orders(names_in_order)

    def to_playwright(self, sel_type: str, selector: str) -> str:
        """Convert selector type + value into a Playwright-compatible selector string."""
        if not selector: return ""
        stype = sel_type.lower()
        
        # If it looks like a playwright-native selector (css, xpath, text), use as is
        if selector.startswith("text=") or selector.startswith("css=") or selector.startswith("xpath=") or selector.startswith("//"):
            return selector

        if stype == "xpath":
            return selector if selector.startswith("//") else f"xpath={selector}"
        elif stype == "css":
            return selector
        elif stype == "id":
            return f"#{selector}"
        
        return selector
