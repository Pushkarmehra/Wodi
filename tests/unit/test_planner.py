"""Unit tests for planner JSON parsing and task decomposition."""
from __future__ import annotations

import pytest

from wodi.planner.planner import Planner


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

    def test_extract_app_name_launch(self):
        p = Planner.__new__(Planner)
        params = p._extract_simple_params("launch chrome", "open_app")
        assert params.get("app_name") == "chrome"
