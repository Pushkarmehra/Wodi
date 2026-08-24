"""
Browser Agent — Real-time Web Search and Browser Automation.

Capabilities:
  - search_web: Live DuckDuckGo / web search with instant answer synthesis
  - navigate_to: Open URLs in default browser / Playwright
  - get_page_text: Fetch and read article/page content
"""
from __future__ import annotations

import html
import os
import re
import urllib.parse
import webbrowser
from typing import Any

import httpx

from woody.agents.base_agent import AgentResult, BaseAgent
from woody.utils.logging import get_logger

log = get_logger(__name__)


class BrowserAgent(BaseAgent):
    AGENT_NAME = "browser_agent"
    ALLOWED_ACTIONS = {
        "search_web",
        "navigate_to",
        "get_page_text",
        "download_file",
        "take_page_screenshot",
    }

    def __init__(
        self,
        browser: str = "chromium",
        headless: bool = False,
        confirm_callback: Any | None = None,
    ) -> None:
        super().__init__(max_retries=2, confirm_callback=confirm_callback)
        self._browser_type = browser
        self._headless = headless

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        if action == "search_web":
            query = params.get("query") or params.get("q") or params.get("search_query", "")
            if not query:
                return AgentResult(success=False, output=None, error="No search query provided.")
            return await self._search_web(query, open_browser=params.get("open_browser", False))

        elif action == "navigate_to":
            url = params.get("url") or params.get("link", "")
            if not url:
                return AgentResult(success=False, output=None, error="No URL provided.")
            return await self._navigate_to(url)

        elif action == "get_page_text":
            url = params.get("url", "")
            if not url:
                return AgentResult(success=False, output=None, error="No URL provided.")
            return await self._get_page_text(url)

        return AgentResult(
            success=False,
            output=None,
            error=f"Action '{action}' is not supported by BrowserAgent.",
        )

    # ── Web Search ────────────────────────────────────────────────────────────

    async def _search_web(self, query: str, open_browser: bool = False) -> AgentResult:
        """Search the web in real-time and return structured results + summary."""
        log.info("browser.searching", query=query)
        try:
            # 1. Check if Tavily API key is available
            tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
            if tavily_key:
                results = await self._search_tavily(query, tavily_key)
            else:
                results = await self._search_duckduckgo(query)

            if not results:
                # If no search results found, fallback to opening the browser search
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
                return AgentResult(
                    success=True,
                    output={
                        "query": query,
                        "summary": f"Searched the web for '{query}' and opened the results in your browser.",
                        "results": [],
                    },
                )

            # Build a clear, readable summary for the user and LLM synthesizer
            summary_lines = [f"Web search results for '{query}':\n"]
            for i, r in enumerate(results[:4], 1):
                title = r.get("title", f"Result {i}")
                snippet = r.get("snippet", "")
                link = r.get("url", "")
                summary_lines.append(f"{i}. **{title}**\n   {snippet}\n   *Source: {link}*\n")

            summary_text = "\n".join(summary_lines).strip()

            if open_browser:
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")

            return AgentResult(
                success=True,
                output={
                    "query": query,
                    "summary": summary_text,
                    "results": results,
                },
            )
        except Exception as e:
            log.error("browser.search_failed", error=str(e))
            # Fallback to opening browser directly
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
            return AgentResult(
                success=True,
                output={
                    "query": query,
                    "summary": f"I opened the web search for '{query}' in your browser.",
                    "results": [],
                },
            )

    async def _search_duckduckgo(self, query: str, max_results: int = 4) -> list[dict]:
        """Fetch live web search results from DuckDuckGo HTML."""
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

        results = []
        blocks = re.findall(
            r'<div class="result results_links results_links_deep web-result.*?</div>\s*</div>\s*</div>',
            resp.text,
            re.DOTALL,
        )

        if not blocks:
            # Fallback regex
            snippets = re.findall(r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
            for i, s in enumerate(snippets[:max_results]):
                clean_s = html.unescape(re.sub(r'<[^>]+>', '', s)).strip()
                if clean_s:
                    results.append({"title": f"Result {i+1}", "snippet": clean_s, "url": ""})
            return results

        for block in blocks[:max_results]:
            title_m = re.search(r'<a class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL)
            snippet_m = re.search(r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
            url_m = re.search(r'<a class="result__url"[^>]*href="([^"]+)"', block)

            title = html.unescape(re.sub(r'<[^>]+>', '', title_m.group(1))).strip() if title_m else "Web Result"
            snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet_m.group(1))).strip() if snippet_m else ""
            raw_link = url_m.group(1) if url_m else ""
            # Decode DuckDuckGo redirect link if present
            if "uddg=" in raw_link:
                try:
                    raw_link = urllib.parse.unquote(raw_link.split("uddg=")[1].split("&")[0])
                except Exception:
                    pass

            if snippet:
                results.append({"title": title, "snippet": snippet, "url": raw_link})

        return results

    async def _search_tavily(self, query: str, api_key: str) -> list[dict]:
        """Search using Tavily AI Search API."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": 4},
            )
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("content", ""),
                    "url": r.get("url", ""),
                }
                for r in data.get("results", [])
            ]

    # ── Navigation & Page Text ────────────────────────────────────────────────

    async def _navigate_to(self, url: str) -> AgentResult:
        """Open a URL in the user's default browser."""
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        webbrowser.open(url)
        return AgentResult(
            success=True,
            output={"url": url, "message": f"Opened {url} in your browser."},
        )

    async def _get_page_text(self, url: str) -> AgentResult:
        """Fetch a web page and extract readable text."""
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
            clean_text = re.sub(r'<script.*?</script>', '', resp.text, flags=re.DOTALL)
            clean_text = re.sub(r'<style.*?</style>', '', clean_text, flags=re.DOTALL)
            clean_text = html.unescape(re.sub(r'<[^>]+>', ' ', clean_text))
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            return AgentResult(
                success=True,
                output={"url": url, "text": clean_text[:2000]},
            )
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

