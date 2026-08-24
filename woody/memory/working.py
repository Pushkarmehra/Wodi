"""
Working Memory — Kernel-level per-request scratch pad.

Extends the planner's WorkingMemoryState with kernel-level
context: TTS state, screen OCR cache, and mic audio buffer.
Kept separate from woody/planner/working_memory.py to maintain
the clean planner/kernel boundary.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestContext:
    """
    Kernel-level context for a single user request.
    Created fresh for each request, discarded after TTS playback.
    """
    request_id: str
    session_id: str
    user_text: str
    timestamp: float = field(default_factory=time.time)

    # Perception snapshot at request time
    screen_ocr_text: str = ""
    clipboard_text: str = ""
    active_window_title: str = ""

    # Planning & dispatch
    planner_state: Any | None = None   # WorkingMemoryState
    final_response: str = ""

    # TTS
    tts_started: bool = False
    tts_completed: bool = False

    # Latency tracking
    t_routed: float = 0.0
    t_dispatched: float = 0.0
    t_synthesized: float = 0.0
    t_tts_done: float = 0.0

    def elapsed_ms(self) -> float:
        return (time.time() - self.timestamp) * 1000

    def to_summary(self) -> dict:
        return {
            "request_id": self.request_id,
            "user_text": self.user_text[:80],
            "response": self.final_response[:200],
            "total_ms": round(self.elapsed_ms(), 1),
            "phases_ms": {
                "route": round((self.t_routed - self.timestamp) * 1000, 1) if self.t_routed else None,
                "dispatch": round((self.t_dispatched - self.t_routed) * 1000, 1) if self.t_dispatched and self.t_routed else None,
                "synthesize": round((self.t_synthesized - self.t_dispatched) * 1000, 1) if self.t_synthesized and self.t_dispatched else None,
                "tts": round((self.t_tts_done - self.t_synthesized) * 1000, 1) if self.t_tts_done and self.t_synthesized else None,
            },
        }


class KernelMemory:
    """
    Kernel-level working memory — holds the current request context,
    a multi-turn conversation dialogue history, and recent contexts.
    """

    def __init__(self, history_size: int = 20) -> None:
        self._current: RequestContext | None = None
        self._history: list[RequestContext] = []
        self._dialogue_history: list[dict[str, str]] = []
        self._history_size = history_size

    def start_request(self, request_id: str, session_id: str, user_text: str) -> RequestContext:
        ctx = RequestContext(
            request_id=request_id,
            session_id=session_id,
            user_text=user_text,
        )
        self._current = ctx
        return ctx

    def finish_request(self, ctx: RequestContext) -> None:
        self._history.append(ctx)
        if len(self._history) > self._history_size:
            self._history = self._history[-self._history_size:]
        if self._current is ctx:
            self._current = None

    def add_turn(self, role: str, content: str) -> None:
        """Add a user or assistant dialogue message to conversation history."""
        clean_content = content.strip()
        if clean_content:
            self._dialogue_history.append({"role": role, "content": clean_content})
            if len(self._dialogue_history) > self._history_size * 2:
                self._dialogue_history = self._dialogue_history[-self._history_size * 2:]

    def get_dialogue_history(self, n: int = 10) -> list[dict[str, str]]:
        """Return the n most recent dialogue turns."""
        return self._dialogue_history[-n:]

    def format_dialogue_for_prompt(self, n: int = 6) -> str:
        """Format recent dialogue history as a readable string for LLM prompts."""
        turns = self.get_dialogue_history(n=n)
        if not turns:
            return ""
        lines = []
        for t in turns:
            prefix = "User" if t["role"] == "user" else "Woody"
            lines.append(f"{prefix}: {t['content']}")
        return "\n".join(lines)

    def clear_dialogue(self) -> None:
        """Reset conversation dialogue history."""
        self._dialogue_history.clear()

    @property
    def current(self) -> RequestContext | None:
        return self._current

    def get_history(self, n: int = 5) -> list[RequestContext]:
        return self._history[-n:]
