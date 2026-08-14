"""
Browser Tools — MCP tool server stubs for Playwright web automation.
[Phase 3 — Stub with full interface]

These functions will be implemented in Phase 3 with Playwright.
"""
from __future__ import annotations

TOOLS = {
    "search_web",
    "navigate_to",
    "fill_form",
    "click_web_element",
    "get_page_text",
    "download_file",
    "take_page_screenshot",
    "scroll_page",
}


def search_web(query: str) -> dict:
    """Search the web for a query. [Phase 3]"""
    # TODO: Playwright + search engine automation
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}


def navigate_to(url: str) -> dict:
    """Navigate to a URL in the browser. [Phase 3]"""
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}


def fill_form(selector: str, value: str) -> dict:
    """Fill a web form field. [Phase 3]"""
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}


def click_web_element(selector: str) -> dict:
    """Click a web element by CSS selector or text. [Phase 3]"""
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}


def get_page_text() -> dict:
    """Get visible text content of the current page. [Phase 3]"""
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}


def download_file(url: str, destination: str = "") -> dict:
    """Download a file from a URL. [Phase 3]"""
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}


def take_page_screenshot() -> dict:
    """Capture a screenshot of the current browser page. [Phase 3]"""
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}


def scroll_page(direction: str = "down", amount: int = 3) -> dict:
    """Scroll the current page. [Phase 3]"""
    return {"success": False, "error": "Browser tools not yet implemented (Phase 3)"}
