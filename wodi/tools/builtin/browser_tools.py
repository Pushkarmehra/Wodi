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
    """Search the web for a query."""
    try:
        import httpx
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.in_result = False
                self.in_snippet = False
                self.current_snippet = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "a" and "class" in attrs and "result-snippet" in attrs["class"]:
                    self.in_snippet = True

            def handle_endtag(self, tag):
                if tag == "a" and self.in_snippet:
                    self.in_snippet = False
                    self.results.append("".join(self.current_snippet).strip())
                    self.current_snippet = []

            def handle_data(self, data):
                if self.in_snippet:
                    self.current_snippet.append(data)

        # Use DDG HTML Lite API (no JS required, very fast)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        resp = httpx.get(f"https://html.duckduckgo.com/html/?q={query}", headers=headers, timeout=10.0)
        resp.raise_for_status()
        
        parser = DDGParser()
        parser.feed(resp.text)
        
        if not parser.results:
            return {"success": True, "results": ["No results found."]}
            
        return {"success": True, "results": parser.results[:5]}
    except Exception as e:
        return {"success": False, "error": str(e)}

def navigate_to(url: str) -> dict:
    """Navigate to a URL in the default system browser."""
    try:
        import webbrowser
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        return {"success": True, "message": f"Opened {url} in default browser."}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
