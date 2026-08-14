"""
Browser Agent — Playwright-based web automation. [Phase 3 Stub]

This agent is scaffolded with full interface definition.
Implementation fills in during Phase 3.
"""
from __future__ import annotations
from typing import Any
from wodi.agents.base_agent import AgentResult, BaseAgent
from wodi.utils.logging import get_logger

log = get_logger(__name__)


class BrowserAgent(BaseAgent):
    AGENT_NAME = "browser_agent"
    ALLOWED_ACTIONS = {
        "search_web", "navigate_to", "fill_form", "click_element",
        "get_page_text", "download_file", "take_page_screenshot",
        "scroll_page", "go_back", "go_forward",
    }

    def __init__(self, browser: str = "chromium", headless: bool = False,
                 confirm_callback: Any | None = None) -> None:
        super().__init__(max_retries=2, confirm_callback=confirm_callback)
        self._browser_type = browser
        self._headless = headless
        self._browser: Any = None
        self._page: Any = None

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        # TODO (Phase 3): Implement Playwright actions
        log.warning("browser_agent.not_implemented", action=action, phase="Phase 3")
        return AgentResult(
            success=False,
            output=None,
            error="Browser Agent not yet implemented. Enable in Phase 3.",
        )
