"""Unit tests for planner JSON parsing and task decomposition."""
from __future__ import annotations

import pytest

from woody.planner.planner import Planner


class TestPlannerJsonParsing:
    def test_parse_clean_json(self):
        raw = '{"agent": "system_agent", "direct_action": "get_time_date", "confidence": 0.95}'
        result = Planner._parse_json(raw, default={})
        assert result["agent"] == "system_agent"

    def test_parse_markdown_fenced_json(self):
        raw = "```json\n{\"agent\": \"desktop_agent\", \"confidence\": 0.9}\n```"
        result = Planner._parse_json(raw, default={})
        assert result["agent"] == "desktop_agent"

    def test_parse_invalid_returns_default(self):
        raw = "Sorry, I cannot do that."
        result = Planner._parse_json(raw, default={"agent": "fallback"})
        assert result["agent"] == "fallback"

    def test_extract_app_name_open(self):
        p = Planner.__new__(Planner)
        params = p._extract_simple_params("open notepad please", "open_app")
        assert params.get("app_name") == "notepad"

    def test_extract_app_name_with_hey_woody(self):
        p = Planner.__new__(Planner)
        params = p._extract_simple_params("Hey Woody, open notepad", "open_app")
        assert params.get("app_name") == "notepad"

    @pytest.mark.asyncio
    async def test_route_with_hey_woody_greeting(self):
        p = Planner.__new__(Planner)
        res = await p._route("Hey Woody")
        assert res["agent"] == "chat_agent"

    @pytest.mark.asyncio
    async def test_route_with_hey_woody_command(self):
        p = Planner.__new__(Planner)
        res = await p._route("Hey Woody, open chrome")
        assert res["agent"] == "desktop_agent"
        assert res["direct_action"] == "open_app"

    @pytest.mark.asyncio
    async def test_route_search_web(self):
        p = Planner.__new__(Planner)
        res = await p._route("search for artificial intelligence news")
        assert res["agent"] == "browser_agent"
        assert res["direct_action"] == "search_web"

    @pytest.mark.asyncio
    async def test_route_screen_perception(self):
        p = Planner.__new__(Planner)
        res = await p._route("what is on my screen right now")
        assert res["agent"] == "vision_agent"
        assert res["direct_action"] == "analyze_screen"

    @pytest.mark.asyncio
    async def test_route_screen_phonetic_variation(self):
        p = Planner.__new__(Planner)
        res = await p._route("what is one my screen")
        assert res["agent"] == "vision_agent"
        assert res["direct_action"] == "analyze_screen"

    @pytest.mark.asyncio
    async def test_route_mobility_maximize(self):
        p = Planner.__new__(Planner)
        res = await p._route("maximize window")
        assert res["agent"] == "desktop_agent"
        assert res["direct_action"] == "maximize_window"

    @pytest.mark.asyncio
    async def test_route_mobility_scroll(self):
        p = Planner.__new__(Planner)
        res = await p._route("scroll down")
        assert res["agent"] == "desktop_agent"
        assert res["direct_action"] == "scroll"

    @pytest.mark.asyncio
    async def test_route_stop_speaking(self):
        p = Planner.__new__(Planner)
        res = await p._route("stop speaking")
        assert res["agent"] == "system_agent"
        assert res["direct_action"] == "stop_speaking"

    @pytest.mark.asyncio
    async def test_route_be_quiet(self):
        p = Planner.__new__(Planner)
        res = await p._route("be quiet")
        assert res["agent"] == "system_agent"
        assert res["direct_action"] == "stop_speaking"
