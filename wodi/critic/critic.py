"""
Critic / Verifier Loop.

A small model checks each sub-task's result against the stated goal
before the pipeline continues. This prevents cascading failures
(e.g., don't submit a form if "fill form" produced validation errors).

Verdict types:
  - PASS         : Result clearly achieves the goal → proceed
  - RETRY        : Partial failure, correction possible → retry with hint
  - FAIL_GRACEFUL: Unrecoverable → report failure honestly

The Critic is intentionally small (qwen2.5:1.5b) for speed.
On Lite tier it uses heuristics instead of an LLM call.
"""
from __future__ import annotations

import json
from typing import Any

from wodi.agents.base_agent import AgentResult
from wodi.planner.prompts import CRITIC_SYSTEM
from wodi.utils.logging import get_logger
from wodi.utils.ollama_client import Message, OllamaClient

log = get_logger(__name__)


class Critic:
    """
    Verifies agent subtask results using a small LLM judge.

    Usage:
        critic = Critic(client=ollama_client, model="qwen2.5:1.5b")
        verdict = await critic.verify(
            goal="Open Notepad",
            result=agent_result,
        )
        if verdict["verdict"] == "PASS":
            ...
    """

    def __init__(
        self,
        client: OllamaClient | None = None,
        model: str = "qwen2.5:1.5b",
        use_heuristics: bool = False,  # Lite tier: skip LLM, use rule-based check
    ) -> None:
        self._client = client
        self._model = model
        self._use_heuristics = use_heuristics or (client is None)

    async def verify(
        self,
        goal: str,
        result: AgentResult,
        context: dict | None = None,
    ) -> dict:
        """
        Verify that an agent result satisfies the goal.
        Returns a dict with 'verdict', 'confidence', 'reason', 'retry_hint'.
        """
        if self._use_heuristics:
            return self._heuristic_verdict(goal, result)

        return await self._llm_verdict(goal, result)

    def _heuristic_verdict(self, goal: str, result: AgentResult) -> dict:
        """Simple rule-based verdict for Lite tier or when LLM unavailable."""
        if result.success:
            return {
                "verdict": "PASS",
                "confidence": 0.8,
                "reason": "Action completed without errors",
                "retry_hint": "",
            }
        elif result.retries < 2:
            return {
                "verdict": "RETRY",
                "confidence": 0.6,
                "reason": result.error or "Action failed",
                "retry_hint": "Retry the action with original parameters",
            }
        else:
            return {
                "verdict": "FAIL_GRACEFUL",
                "confidence": 0.9,
                "reason": result.error or "Repeated failures",
                "retry_hint": "",
            }

    async def _llm_verdict(self, goal: str, result: AgentResult) -> dict:
        """Use small LLM to intelligently judge the result."""
        user_msg = f"""Goal: {goal}

Result:
- Success: {result.success}
- Output: {str(result.output)[:500] if result.output else 'None'}
- Error: {result.error or 'None'}
- Retries: {result.retries}

Determine if this result achieves the goal."""

        try:
            messages = [
                Message(role="system", content=CRITIC_SYSTEM),
                Message(role="user", content=user_msg),
            ]
            resp = await self._client.chat(  # type: ignore[union-attr]
                model=self._model,
                messages=messages,
                temperature=0.0,
                max_tokens=256,
            )
            parsed = self._parse_verdict(resp.content)
            log.debug(
                "critic.verdict",
                verdict=parsed.get("verdict"),
                confidence=parsed.get("confidence"),
                goal=goal[:50],
            )
            return parsed
        except Exception as e:
            log.warning("critic.llm_error", error=str(e), fallback="heuristic")
            return self._heuristic_verdict(goal, result)

    @staticmethod
    def _parse_verdict(text: str) -> dict:
        """Parse JSON verdict from LLM output."""
        text = text.strip()
        if "```" in text:
            lines = text.splitlines()
            text = "\n".join(l for l in lines if not l.strip().startswith("```"))
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        # Fallback: parse verdict keyword
        if "PASS" in text.upper():
            return {"verdict": "PASS", "confidence": 0.7, "reason": text[:200], "retry_hint": ""}
        elif "RETRY" in text.upper():
            return {"verdict": "RETRY", "confidence": 0.6, "reason": text[:200], "retry_hint": ""}
        return {"verdict": "FAIL_GRACEFUL", "confidence": 0.5, "reason": text[:200], "retry_hint": ""}
