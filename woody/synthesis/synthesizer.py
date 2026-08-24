"""
Response Synthesizer — Final LLM condenser.

Takes all agent results and produces a clear, natural-language response
for the user. Streams tokens directly so the user sees progress.

Also handles clarification responses and error summaries.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from woody.planner.prompts import SYNTHESIZER_SYSTEM
from woody.planner.working_memory import WorkingMemoryState
from woody.utils.logging import get_logger
from woody.utils.groq_client import Message, GroqClient

log = get_logger(__name__)


class Synthesizer:
    """
    Produces the final response from all agent results.

    Usage:
        synth = Synthesizer(client=groq_client, model="llama-3.3-70b-versatile")
        # Streaming:
        async for chunk in synth.stream(state, tone="concise"):
            print(chunk, end="", flush=True)
        # Non-streaming:
        text = await synth.synthesize(state)
    """

    def __init__(
        self,
        client: GroqClient | Any,
        model: str = "llama-3.3-70b-versatile",
        tone: str = "concise",
    ) -> None:
        self._client = client
        self._model = model
        self._tone = tone

    async def synthesize(self, state: WorkingMemoryState, tone: str | None = None) -> str:
        """Generate the final response (non-streaming)."""
        prompt = self._build_prompt(state, tone or self._tone)
        messages = [
            Message(role="system", content=SYNTHESIZER_SYSTEM.format(tone=tone or self._tone)),
            Message(role="user", content=prompt),
        ]
        try:
            resp = await self._client.chat(
                model=self._model,
                messages=messages,
                temperature=0.55,
                max_tokens=512,
            )
            response = resp.content.strip()
            log.info("synthesizer.done", length=len(response), model=self._model)
            return response
        except Exception as e:
            log.error("synthesizer.error", error=str(e))
            return self._fallback_response(state)

    async def stream(
        self,
        state: WorkingMemoryState,
        tone: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Generate the final response as a streaming token generator."""
        prompt = self._build_prompt(state, tone or self._tone)
        messages = [
            Message(role="system", content=SYNTHESIZER_SYSTEM.format(tone=tone or self._tone)),
            Message(role="user", content=prompt),
        ]
        try:
            async for chunk in self._client.chat_stream(
                model=self._model,
                messages=messages,
                temperature=0.55,
                max_tokens=512,
            ):
                yield chunk
        except Exception as e:
            log.error("synthesizer.stream_error", error=str(e))
            yield self._fallback_response(state)

    def _build_prompt(self, state: WorkingMemoryState, tone: str) -> str:
        """Build the synthesis prompt from working memory state and conversation memory."""
        parts = []

        # 1. Include recent conversation history if available
        history = state.get("task_history") or state.get("dialogue_history")
        if history:
            parts.append(f"Recent Conversation History:\n{history}\n")

        parts.append(f"Current User Request: {state['user_request']}")

        # Summarize subtask results
        results_summary = []
        for task in state.get("subtasks", []):
            tid = task["id"]
            desc = task["description"]
            status = task["status"]
            result = task.get("result")
            error = task.get("error")

            if status == "done":
                output_str = ""
                if result is not None:
                    if isinstance(result, dict):
                        # Handle clarification responses
                        if result.get("clarification_needed"):
                            output_str = f"→ [NEEDS CLARIFICATION] {result.get('message', '')}"
                        elif result.get("analysis"):
                            output_str = f"→ {result.get('analysis')}"
                        else:
                            output_str = f"→ {json.dumps(result)[:300]}"
                    else:
                        output_str = f"→ {str(result)[:300]}"
                results_summary.append(f"✓ {desc} {output_str}")
            elif status == "failed":
                results_summary.append(f"✗ {desc} → Error: {error or 'Unknown'}")
            else:
                results_summary.append(f"? {desc} → {status}")

        if results_summary:
            parts.append("\nCompleted actions:\n" + "\n".join(results_summary))

        # Check for clarification needed
        for task in state.get("subtasks", []):
            if task.get("result") and isinstance(task["result"], dict):
                if task["result"].get("clarification_needed"):
                    parts.append(f"\nNeeds clarification: {task['result'].get('message', '')}")

        return "\n".join(parts)

    def _fallback_response(self, state: WorkingMemoryState) -> str:
        """Emergency fallback response if LLM call fails."""
        successful = [t for t in state.get("subtasks", []) if t.get("status") == "done"]
        failed = [t for t in state.get("subtasks", []) if t.get("status") == "failed"]

        if successful and not failed:
            return f"Done! I completed: {', '.join(t['description'] for t in successful)}."
        elif failed:
            errors = "; ".join(t.get("error", "unknown error") for t in failed)
            return f"I ran into an issue: {errors}. Please try again."
        return "I processed your request, but couldn't generate a proper response."
