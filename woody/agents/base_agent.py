"""
Base Agent — foundation class for all Woody specialist agents.

Provides:
  - Scoped tool access (only declared tools can be called)
  - Retry-with-repair loop (configurable max retries)
  - Per-subtask timeout budget enforcement
  - Standardized result schema
  - Integration with the Critic/Verifier loop
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from woody.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class AgentResult:
    success: bool
    output: Any
    error: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    elapsed_ms: float = 0.0
    retries: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": str(self.output)[:2000] if self.output else None,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "retries": self.retries,
        }


class PermissionDeniedError(Exception):
    """Raised when an agent attempts to call a tool outside its allowed scope."""
    pass


class BaseAgent(ABC):
    """
    Abstract base class for all Woody specialist agents.

    Subclasses must implement:
      - ALLOWED_ACTIONS: set of action names this agent can perform
      - execute_action(action, params, context): the actual action logic

    Usage:
        result = await agent.run(
            action="open_app",
            params={"app_name": "Notepad"},
            timeout_seconds=30,
            context={...},
        )
    """

    # Subclasses override these
    AGENT_NAME: str = "base"
    ALLOWED_ACTIONS: set[str] = set()

    def __init__(
        self,
        max_retries: int = 2,
        confirm_callback: Any | None = None,   # async fn(action, params) → bool
    ) -> None:
        self._max_retries = max_retries
        self._confirm_callback = confirm_callback

    async def run(
        self,
        action: str,
        params: dict,
        timeout_seconds: float = 30.0,
        context: dict | None = None,
        critic: Any | None = None,            # Critic instance for verify loop
        goal_description: str = "",
    ) -> AgentResult:
        """
        Execute an action with retry-with-repair logic and timeout budget.
        """
        # Scope check — agents cannot call actions outside their declared set
        if self.ALLOWED_ACTIONS and action not in self.ALLOWED_ACTIONS:
            msg = (
                f"Agent '{self.AGENT_NAME}' is not permitted to call action '{action}'. "
                f"Allowed: {sorted(self.ALLOWED_ACTIONS)}"
            )
            log.error("agent.permission_denied", agent=self.AGENT_NAME, action=action)
            raise PermissionDeniedError(msg)

        t0 = time.perf_counter()
        retries = 0
        last_error = ""
        retry_hint = ""

        while retries <= self._max_retries:
            try:
                # Inject retry_hint into params on retries
                if retry_hint:
                    params = {**params, "_retry_hint": retry_hint}

                log.info(
                    "agent.execute",
                    agent=self.AGENT_NAME,
                    action=action,
                    attempt=retries + 1,
                )

                result = await asyncio.wait_for(
                    self.execute_action(action, params, context or {}),
                    timeout=timeout_seconds,
                )

                elapsed = (time.perf_counter() - t0) * 1000
                result.elapsed_ms = elapsed
                result.retries = retries

                # Run critic verification if provided
                if critic and goal_description:
                    verdict = await critic.verify(
                        goal=goal_description,
                        result=result,
                    )
                    if verdict["verdict"] == "RETRY" and retries < self._max_retries:
                        retry_hint = verdict.get("retry_hint", "")
                        log.info(
                            "agent.critic_retry",
                            agent=self.AGENT_NAME,
                            hint=retry_hint,
                            attempt=retries + 1,
                        )
                        retries += 1
                        await asyncio.sleep(0.5 * retries)  # back-off
                        continue
                    elif verdict["verdict"] == "FAIL_GRACEFUL":
                        return AgentResult(
                            success=False,
                            output=None,
                            error=f"Critic: {verdict.get('reason', 'Unrecoverable failure')}",
                            elapsed_ms=(time.perf_counter() - t0) * 1000,
                            retries=retries,
                        )

                log.info(
                    "agent.done",
                    agent=self.AGENT_NAME,
                    action=action,
                    success=result.success,
                    elapsed_ms=f"{elapsed:.0f}",
                )
                return result

            except asyncio.TimeoutError:
                elapsed = (time.perf_counter() - t0) * 1000
                log.warning(
                    "agent.timeout",
                    agent=self.AGENT_NAME,
                    action=action,
                    timeout_seconds=timeout_seconds,
                )
                return AgentResult(
                    success=False,
                    output=None,
                    error=f"Timed out after {timeout_seconds}s",
                    elapsed_ms=elapsed,
                    retries=retries,
                )

            except PermissionDeniedError:
                raise

            except Exception as e:
                last_error = str(e)
                log.warning(
                    "agent.error",
                    agent=self.AGENT_NAME,
                    action=action,
                    error=last_error,
                    attempt=retries + 1,
                )
                retries += 1
                if retries <= self._max_retries:
                    await asyncio.sleep(0.5 * retries)

        elapsed = (time.perf_counter() - t0) * 1000
        return AgentResult(
            success=False,
            output=None,
            error=f"Failed after {self._max_retries} retries: {last_error}",
            elapsed_ms=elapsed,
            retries=self._max_retries,
        )

    @abstractmethod
    async def execute_action(
        self,
        action: str,
        params: dict,
        context: dict,
    ) -> AgentResult:
        """Subclasses implement this with actual action logic."""
        ...

    async def _request_confirmation(self, action: str, params: dict) -> bool:
        """Request user confirmation for privileged actions."""
        if self._confirm_callback is None:
            log.warning("agent.no_confirm_callback", action=action, defaulting="deny")
            return False
        try:
            return await self._confirm_callback(action, params)
        except Exception as e:
            log.error("agent.confirm_error", error=str(e))
            return False
