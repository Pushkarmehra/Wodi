"""
Working Memory — LangGraph state for the current task.

Holds the task graph, tool call trace, agent results, screen context,
and token budget. Handles recursive summarization when the context
window approaches its limit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, TypedDict


class SubTask(TypedDict):
    id: str
    agent: str
    action: str
    params: dict
    depends_on: list[str]
    description: str
    status: str        # pending | running | done | failed | skipped
    result: Any
    error: str | None
    retries: int


class WorkingMemoryState(TypedDict):
    """LangGraph state schema for the current request."""
    # Request
    user_request: str
    session_id: str
    request_id: str
    timestamp: float

    # Decomposition
    intent: str
    is_simple: bool
    subtasks: list[SubTask]
    current_subtask_id: str | None

    # Context
    screen_context: str          # OCR text from current screen
    clipboard_context: str
    task_history: str            # Summarized recent sessions

    # Results
    agent_results: dict[str, Any]     # task_id → result
    tool_call_trace: list[dict]       # Full tool call audit log
    final_response: str

    # Budget
    planner_tokens_used: int
    max_context_tokens: int
    summarization_triggered: bool


def make_initial_state(
    user_request: str,
    session_id: str,
    request_id: str,
    screen_context: str = "",
    clipboard_context: str = "",
    task_history: str = "",
    max_context_tokens: int = 8192,
) -> WorkingMemoryState:
    """Create a fresh working memory state for a new request."""
    return WorkingMemoryState(
        user_request=user_request,
        session_id=session_id,
        request_id=request_id,
        timestamp=time.time(),
        intent="",
        is_simple=False,
        subtasks=[],
        current_subtask_id=None,
        screen_context=screen_context,
        clipboard_context=clipboard_context,
        task_history=task_history,
        agent_results={},
        tool_call_trace=[],
        final_response="",
        planner_tokens_used=0,
        max_context_tokens=max_context_tokens,
        summarization_triggered=False,
    )


def get_pending_subtasks(state: WorkingMemoryState) -> list[SubTask]:
    """Return subtasks that are ready to run (pending + dependencies satisfied)."""
    done_ids = {t["id"] for t in state["subtasks"] if t["status"] == "done"}
    return [
        t for t in state["subtasks"]
        if t["status"] == "pending"
        and all(dep in done_ids for dep in t["depends_on"])
    ]


def mark_subtask_done(state: WorkingMemoryState, task_id: str, result: Any) -> None:
    for t in state["subtasks"]:
        if t["id"] == task_id:
            t["status"] = "done"
            t["result"] = result
            break
    state["agent_results"][task_id] = result


def mark_subtask_failed(state: WorkingMemoryState, task_id: str, error: str) -> None:
    for t in state["subtasks"]:
        if t["id"] == task_id:
            t["status"] = "failed"
            t["error"] = error
            break


def is_all_done(state: WorkingMemoryState) -> bool:
    return all(
        t["status"] in ("done", "failed", "skipped")
        for t in state["subtasks"]
    )


def log_tool_call(
    state: WorkingMemoryState,
    tool_name: str,
    inputs: dict,
    output: Any,
    permission_tier: str,
    confirmed: bool | None = None,
) -> None:
    state["tool_call_trace"].append({
        "tool": tool_name,
        "inputs": inputs,
        "output": output,
        "permission_tier": permission_tier,
        "confirmed": confirmed,
        "timestamp": time.time(),
    })
