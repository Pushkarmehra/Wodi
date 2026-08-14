"""
Coding Agent — Sandboxed code execution. [Phase 3 Stub]
"""
from __future__ import annotations
from typing import Any
from wodi.agents.base_agent import AgentResult, BaseAgent
from wodi.utils.logging import get_logger

log = get_logger(__name__)


class CodingAgent(BaseAgent):
    AGENT_NAME = "coding_agent"
    ALLOWED_ACTIONS = {"write_code", "run_code", "explain_code", "debug_code", "refactor_code"}

    def __init__(self, sandbox: str = "job_object", confirm_callback: Any | None = None) -> None:
        super().__init__(max_retries=1, confirm_callback=confirm_callback)
        self._sandbox = sandbox

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        # TODO (Phase 3): Implement sandboxed code execution
        log.warning("coding_agent.not_implemented", action=action, phase="Phase 3")
        return AgentResult(success=False, output=None,
                           error="Coding Agent not yet implemented. Enable in Phase 3.")
