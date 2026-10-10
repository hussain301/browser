"""
Selector Manager — configurable DOM selectors with fallbacks.
"""
from typing import Dict, Any, List, Optional
from state_manager import StateManager


class SelectorManager:
    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager

    def get_all(self) -> List[Dict[str, Any]]:
        return self.state_manager.get_selectors()

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        for s in self.state_manager.get_selectors():
            if s["name"].lower() == name.lower():
                return s
        return None

    def update_full(self, name: str, website: str, page: str, selector_type: str, selector: str, fallback: str, timeout: int, description: str):
        self.state_manager.update_selector_full(name, website, page, selector_type, selector, fallback, timeout, description)

    def update_orders(self, names_in_order: List[str]):
        self.state_manager.update_selector_orders(names_in_order)

    def to_playwright(self, selector_info: Dict[str, Any]) -> str:
        """Convert selector type + value into a Playwright-compatible selector string."""
        stype = selector_info.get("selector_type", "XPath")
        val = selector_info.get("selector", "")
        if stype == "XPath":
            return val if val.startswith("//") or val.startswith("xpath=") else f"xpath={val}"
        elif stype == "CSS":
            return val
        elif stype == "Text":
            return f"text={val}"
        elif stype == "Test ID":
            return f"[data-testid='{val}']"
        elif stype == "Role":
            return f"role={val}"
        return val

    def get_playwright(self, name: str) -> Optional[str]:
        s = self.get(name)
        return self.to_playwright(s) if s else None
