"""
Planner — LangGraph-based task decomposition and routing.

The Planner runs a two-phase pipeline:
  Phase 1 (Router): Fast intent classification — is this simple or complex?
  Phase 2 (Decomposer): For complex tasks, decompose into ordered subtasks.

Simple commands ("open Notepad", "what time is it") skip the full planner
and route directly to the appropriate agent — keeping latency < 500ms.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from wodi.planner.prompts import (
    PLANNER_SYSTEM,
    PLANNER_USER_TEMPLATE,
    ROUTER_SYSTEM,
)
from wodi.planner.working_memory import SubTask, WorkingMemoryState, make_initial_state
from wodi.utils.logging import get_logger
from wodi.utils.groq_client import Message, GroqClient

log = get_logger(__name__)


class Planner:
    """
    Decomposes user requests into ordered subtask lists.

    Usage:
        planner = Planner(client=groq_client, router_model="llama-3.1-8b-instant",
                          planner_model="llama-3.3-70b-versatile")
        state = await planner.plan(
            user_request="Open Notepad and type Hello World",
            screen_context="Desktop visible",
        )
        for task in state["subtasks"]:
            print(task)
    """

    def __init__(
        self,
        client: GroqClient | Any,
        router_model: str = "llama-3.1-8b-instant",
        planner_model: str = "llama-3.3-70b-versatile",
        session_id: str | None = None,
    ) -> None:
        self._client = client
        self._router_model = router_model
        self._planner_model = planner_model
        self._session_id = session_id or str(uuid.uuid4())[:8]

    async def plan(
        self,
        user_request: str,
        screen_context: str = "",
        clipboard_context: str = "",
        task_history: str = "",
        max_context_tokens: int = 8192,
    ) -> WorkingMemoryState:
        """
        Route and decompose a user request into a WorkingMemoryState with subtasks.
        Returns immediately for simple commands; runs full planner for complex ones.
        """
        request_id = str(uuid.uuid4())[:8]
        state = make_initial_state(
            user_request=user_request,
            session_id=self._session_id,
            request_id=request_id,
            screen_context=screen_context,
            clipboard_context=clipboard_context,
            task_history=task_history,
            max_context_tokens=max_context_tokens,
        )

        log.info("planner.plan_start", request=user_request[:60], request_id=request_id)

        # Phase 1: Route
        routing = await self._route(user_request)
        agent = routing.get("agent", "planner")
        direct_action = routing.get("direct_action")
        confidence = routing.get("confidence", 0.5)

        log.info(
            "planner.routed",
            agent=agent,
            action=direct_action,
            confidence=confidence,
        )

        if agent == "chat_agent":
            # Direct conversational response — no tools, no decomposition
            # Use the small model directly for speed
            state["is_simple"] = True
            state["intent"] = user_request
            state["subtasks"] = [
                SubTask(
                    id="t1",
                    agent="system_agent",
                    action="chat",
                    params={"message": user_request},
                    depends_on=[],
                    description=user_request,
                    status="pending",
                    result=None,
                    error=None,
                    retries=0,
                )
            ]
            return state

        if agent == "react_agent":
            # ReAct agent handles complex tasks autonomously via tool calling
            state["is_simple"] = False
            state["intent"] = user_request
            state["subtasks"] = [
                SubTask(
                    id="t1",
                    agent="react_agent",
                    action="react_loop",
                    params={"goal": user_request},
                    depends_on=[],
                    description=user_request,
                    status="pending",
                    result=None,
                    error=None,
                    retries=0,
                )
            ]
            return state

        if agent != "planner" and direct_action and confidence >= 0.75:
            # Simple command — create a single subtask directly
            state["is_simple"] = True
            state["intent"] = user_request
            state["subtasks"] = [
                SubTask(
                    id="t1",
                    agent=agent,
                    action=direct_action,
                    params=self._extract_simple_params(user_request, direct_action),
                    depends_on=[],
                    description=user_request,
                    status="pending",
                    result=None,
                    error=None,
                    retries=0,
                )
            ]
            return state

        # Phase 2: Full decomposition
        return await self._decompose(state)

    async def _route(self, user_request: str) -> dict:
        """Fast intent classification via rules or small model."""
        import re
        req = user_request.lower().strip()

        # Fast-path heuristics (< 1ms)
        # Use word-boundary patterns so "close the deal" or "open sesame" don't
        # accidentally route to the desktop agent.
        _open_re = re.compile(r'^(open|launch|start)\s+\S')
        _close_re = re.compile(r'^(close|quit|exit)\s+\S')

        if _open_re.match(req):
            # Only fast-path if we can actually extract an app name
            params = self._extract_simple_params(user_request, "open_app")
            if params.get("app_name"):
                return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "open_app"}
        if _close_re.match(req):
            params = self._extract_simple_params(user_request, "close_app")
            if params.get("app_name"):
                return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "close_app"}
        if any(k in req for k in ["what time", "what's the time", "current time", "what date", "what's the date", "today's date"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_time_date"}
        if any(k in req for k in ["cpu usage", "ram usage", "system stats", "memory usage", "how much cpu", "how much ram"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_system_stats"}
        if any(k in req for k in ["battery", "power level", "how much battery"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_battery"}
        if any(k in req for k in ["clipboard", "show clipboard", "what's in my clipboard"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_clipboard"}
        if any(k in req for k in ["take screenshot", "take a screenshot", "screenshot"]):
            return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "take_screenshot"}
        if any(req.startswith(p) for p in ["search for ", "search ", "google ", "look up "]):
            return {"agent": "browser_agent", "confidence": 1.0, "direct_action": "search_web"}

        # Fast-path: short conversational messages go directly to chat_agent
        # (no tools needed — avoids expensive tool-calling loop on 1.5b model)
        _CHAT_GREETINGS = {
            "hi", "hello", "hey", "yo", "sup", "howdy",
            "hi wodi", "hello wodi", "hey wodi",
            "thanks", "thank you", "ok", "okay", "cool", "great",
            "bye", "goodbye", "stop", "quit",
        }
        if req in _CHAT_GREETINGS or (len(req.split()) <= 6 and not any(
            c in req for c in ["open", "close", "run", "search", "find", "make", "create", "delete", "download"]
        )):
            return {"agent": "chat_agent", "confidence": 1.0, "direct_action": "chat"}

        try:
            messages = [
                Message(role="system", content=ROUTER_SYSTEM),
                Message(role="user", content=user_request),
            ]
            resp = await self._client.chat(
                model=self._router_model,
                messages=messages,
                temperature=0.0,
                max_tokens=64,
            )
            return self._parse_json(resp.content, default={"agent": "react_agent"})
        except Exception as e:
            log.warning("planner.route_error", error=str(e), fallback="react_agent")
            return {"agent": "react_agent"}

    async def _decompose(self, state: WorkingMemoryState) -> WorkingMemoryState:
        """Full LLM-based task decomposition."""
        prompt = PLANNER_USER_TEMPLATE.format(
            user_request=state["user_request"],
            screen_context=state["screen_context"] or "Not available",
            clipboard_context=state["clipboard_context"] or "Empty",
            task_history=state["task_history"] or "No recent history",
        )
        messages = [
            Message(role="system", content=PLANNER_SYSTEM),
            Message(role="user", content=prompt),
        ]
        try:
            resp = await self._client.chat(
                model=self._planner_model,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )
            state["planner_tokens_used"] = resp.prompt_tokens + resp.completion_tokens
            plan = self._parse_json(resp.content, default={})

            state["intent"] = plan.get("intent", state["user_request"])
            state["is_simple"] = bool(plan.get("is_simple", False))
            raw_subtasks = plan.get("subtasks", [])

            state["subtasks"] = [
                SubTask(
                    id=t.get("id", f"t{i+1}"),
                    agent=t.get("agent", "system_agent"),
                    action=t.get("action", "unknown"),
                    params=t.get("params", {}),
                    depends_on=t.get("depends_on", []),
                    description=t.get("description", ""),
                    status="pending",
                    result=None,
                    error=None,
                    retries=0,
                )
                for i, t in enumerate(raw_subtasks)
            ]

            log.info(
                "planner.decomposed",
                intent=state["intent"][:60],
                n_subtasks=len(state["subtasks"]),
            )
        except Exception as e:
            log.error("planner.decompose_error", error=str(e))
            # Emergency fallback: ask user
            state["subtasks"] = [
                SubTask(
                    id="t1",
                    agent="system_agent",
                    action="clarify",
                    params={"message": f"I couldn't fully understand: '{state['user_request']}'. Could you rephrase?"},
                    depends_on=[],
                    description="Clarification needed",
                    status="pending",
                    result=None,
                    error=None,
                    retries=0,
                )
            ]
        return state

    def _extract_simple_params(self, request: str, action: str) -> dict:
        """Extract obvious parameters from simple requests.

        We operate on the *original* request (not lowercased) so that app
        names preserve their natural capitalisation (e.g. 'Notepad', 'Chrome').
        """
        request_lower = request.lower()
        params: dict[str, Any] = {}
        # Articles to strip when they appear immediately after the verb
        _ARTICLES = {"the", "a", "an", "my"}

        if action == "open_app":
            for kw in ["open ", "launch ", "start "]:
                if kw in request_lower:
                    # Find position in original string to preserve case
                    idx = request_lower.find(kw) + len(kw)
                    words = request[idx:].strip().split()
                    # Skip leading articles ("open the notepad" → "notepad")
                    while words and words[0].lower() in _ARTICLES:
                        words = words[1:]
                    if words:
                        params["app_name"] = " ".join(words).strip().lower()
                    break

        elif action == "close_app":
            for kw in ["close ", "quit ", "exit "]:
                if kw in request_lower:
                    idx = request_lower.find(kw) + len(kw)
                    words = request[idx:].strip().split()
                    while words and words[0].lower() in _ARTICLES:
                        words = words[1:]
                    if words:
                        params["app_name"] = " ".join(words).strip().lower()
                    break

        elif action == "search_web":
            for kw in ["search for ", "search ", "google ", "look up "]:
                if kw in request_lower:
                    idx = request_lower.find(kw) + len(kw)
                    # Preserve original capitalisation for the search query
                    params["query"] = request[idx:].strip()
                    break

        return params

    @staticmethod
    def _parse_json(text: str, default: dict) -> dict:
        """Parse JSON from LLM output, stripping markdown fences."""
        text = text.strip()
        # Strip ```json ... ``` fences
        if "```" in text:
            lines = text.splitlines()
            text = "\n".join(
                l for l in lines if not l.strip().startswith("```")
            )
        # Find first { ... }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return default
