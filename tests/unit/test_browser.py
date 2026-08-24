"""Unit tests for BrowserAgent web search and URL navigation."""
from __future__ import annotations

import pytest
from woody.agents.browser_agent import BrowserAgent


class TestBrowserAgent:
    @pytest.mark.asyncio
    async def test_search_web_empty_query_fails(self):
        agent = BrowserAgent()
        res = await agent.execute_action("search_web", {}, {})
        assert not res.success
        assert "No search query" in (res.error or "")

    @pytest.mark.asyncio
    async def test_search_web_duckduckgo_parsing(self):
        agent = BrowserAgent()
        results = await agent._search_duckduckgo("python programming language", max_results=2)
        assert isinstance(results, list)
        if results:
            assert "title" in results[0]
            assert "snippet" in results[0]

    @pytest.mark.asyncio
    async def test_unknown_action_fails(self):
        agent = BrowserAgent()
        res = await agent.execute_action("invalid_action", {}, {})
        assert not res.success
