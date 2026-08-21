"""
Browser Tools — Web search and browser interaction tools.

Provides two search backends:
  - search_web()        : DuckDuckGo (no API key, always available)
  - web_search_tavily() : Tavily API (requires TAVILY_API_KEY, higher quality)

Both are registered as LangChain @tool for LangGraph compatibility.
Plain function versions (search_web_duckduckgo) remain for the Ollama path.
"""
from __future__ import annotations

import os
import urllib.parse

from langchain_core.tools import tool as lc_tool

# Ordered list so tool schema registration is deterministic
TOOLS = [
    "search_web",
    "navigate_to",
    "fill_form",
    "click_web_element",
    "get_page_text",
    "download_file",
    "take_page_screenshot",
    "scroll_page",
]


# ── Tavily Web Search (from Nex prototype) ─────────────────────────────────────

@lc_tool
def web_search_tavily(query: str) -> str:
    """
    Search the web using Tavily API and return formatted results.
    Requires TAVILY_API_KEY environment variable.

    Args:
        query: The search query string.

    Returns:
        Formatted string of search results (title, URL, snippet).
    """
    try:
        from langchain_tavily import TavilySearch  # type: ignore
        tavily = TavilySearch(max_results=4)
        res = tavily.invoke(query)
        if isinstance(res, dict) and "results" in res:
            formatted = []
            for item in res["results"]:
                snippet = item.get("content", "")[:350]
                formatted.append(
                    f"**{item.get('title', '')}**\n"
                    f"URL: {item.get('url', '')}\n"
                    f"{snippet}"
                )
            return "\n\n".join(formatted) or "No results found."
        return str(res)[:1500]
    except ImportError:
        return "Tavily not installed. Run: pip install langchain-tavily"
    except Exception as e:
        return f"Tavily search error: {e}"


# ── DuckDuckGo Search (@tool for LangGraph) ────────────────────────────────────

@lc_tool
def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo (no API key required).
    Returns a formatted string of result snippets.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5).
    """
    result = search_web_duckduckgo(query=query, max_results=max_results)
    if result.get("success"):
        return "\n\n".join(result.get("results", ["No results found."]))
    return f"Search error: {result.get('error', 'Unknown error')}"


def search_web_duckduckgo(query: str, max_results: int = 5) -> dict:
    """Search the web using DuckDuckGo and return a list of result snippets.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5).
    """
    try:
        import httpx

        # URL-encode the query to handle spaces and special characters correctly
        encoded_query = urllib.parse.quote_plus(query)

        # Use the DDG JSON (Instant Answer) API — no JS, no HTML parsing fragility
        json_url = (
            f"https://api.duckduckgo.com/?q={encoded_query}"
            f"&format=json&no_html=1&skip_disambig=1"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

        resp = httpx.get(json_url, headers=headers, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()

        results: list[str] = []

        # 1. Abstract (best single answer)
        abstract = data.get("Abstract", "").strip()
        if abstract:
            source = data.get("AbstractSource", "")
            url = data.get("AbstractURL", "")
            results.append(f"{abstract} — {source} ({url})" if source else abstract)

        # 2. Related topics
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            if isinstance(topic, dict):
                text = topic.get("Text", "").strip()
                if text:
                    results.append(text)
            # Skip grouped sub-topics for brevity

        # 3. Fallback: HTML search if the JSON API returned nothing useful
        if not results:
            html_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            html_resp = httpx.get(
                html_url, headers=headers, timeout=10.0, follow_redirects=True
            )
            html_resp.raise_for_status()
            # Extract <a class="result__a"> snippets (current DDG HTML structure)
            import re
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</(?:a|span)>',
                html_resp.text,
                re.DOTALL,
            )
            clean = re.compile(r"<[^>]+>")
            for s in snippets[:max_results]:
                text = clean.sub("", s).strip()
                if text:
                    results.append(text)

        if not results:
            return {"success": True, "results": ["No results found for the given query."]}

        return {"success": True, "query": query, "results": results[:max_results]}

    except Exception as e:
        return {"success": False, "error": str(e)}


def navigate_to(url: str) -> dict:
    """Open a URL in the system's default web browser.

    Args:
        url: The URL to open. 'https://' is added automatically if missing.
    """
    try:
        import webbrowser

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return {"success": True, "message": f"Opened {url} in default browser."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fill_form(selector: str, value: str) -> dict:
    """Fill a web form field identified by a CSS selector. [Phase 3 — Playwright]

    Args:
        selector: CSS selector for the input element.
        value: Text to type into the field.
    """
    return {"success": False, "error": "fill_form requires Phase 3 Playwright integration."}


def click_web_element(selector: str) -> dict:
    """Click a web element identified by a CSS selector or visible text. [Phase 3 — Playwright]

    Args:
        selector: CSS selector or visible text of the element to click.
    """
    return {"success": False, "error": "click_web_element requires Phase 3 Playwright integration."}


def get_page_text() -> dict:
    """Get the visible text content of the currently active browser page. [Phase 3 — Playwright]"""
    return {"success": False, "error": "get_page_text requires Phase 3 Playwright integration."}


def download_file(url: str, destination: str = "") -> dict:
    """Download a file from a URL to a local path. [Phase 3 — Playwright]

    Args:
        url: The URL of the file to download.
        destination: Local path where the file should be saved.
    """
    return {"success": False, "error": "download_file requires Phase 3 Playwright integration."}


def take_page_screenshot() -> dict:
    """Capture a screenshot of the currently active browser page. [Phase 3 — Playwright]"""
    return {"success": False, "error": "take_page_screenshot requires Phase 3 Playwright integration."}


def scroll_page(direction: str = "down", amount: int = 3) -> dict:
    """Scroll the currently active browser page.

    Args:
        direction: Scroll direction — 'up' or 'down'.
        amount: Number of page-heights to scroll.

    [Phase 3 — Playwright]
    """
    return {"success": False, "error": "scroll_page requires Phase 3 Playwright integration."}
