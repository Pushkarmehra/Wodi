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

from woody.planner.prompts import (
    PLANNER_SYSTEM,
    PLANNER_USER_TEMPLATE,
    ROUTER_SYSTEM,
)
from woody.planner.working_memory import SubTask, WorkingMemoryState, make_initial_state
from woody.utils.logging import get_logger
from woody.utils.groq_client import Message, GroqClient

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

        if agent == "compound_open_type":
            p = routing.get("params", {})
            app_name = p.get("app_name", "notepad")
            text_to_type = p.get("text", "")
            state["is_simple"] = False
            state["intent"] = f"Open {app_name} and type '{text_to_type}'"
            state["subtasks"] = [
                SubTask(
                    id="t1",
                    agent="desktop_agent",
                    action="open_app",
                    params={"app_name": app_name},
                    depends_on=[],
                    description=f"Open {app_name}",
                    status="pending",
                    result=None,
                    error=None,
                    retries=0,
                ),
                SubTask(
                    id="t2",
                    agent="desktop_agent",
                    action="type_text",
                    params={"text": text_to_type},
                    depends_on=["t1"],
                    description=f"Type '{text_to_type}'",
                    status="pending",
                    result=None,
                    error=None,
                    retries=0,
                ),
            ]
            return state

        if agent == "chat_agent":
            # Direct conversational response
            state["is_simple"] = True
            state["intent"] = user_request
            state["subtasks"] = [
                SubTask(
                    id="t1",
                    agent="chat_agent",
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

    def _parse_compound_open_and_type(self, request: str) -> dict | None:
        """Check for compound open-and-type commands like 'open notebook and write that \"i love pari \"'."""
        import re
        req_clean = re.sub(r'^(hey|hi|hello|ok|okay)?\s*(woody|woodi|wodi|woodie)[,\s:]*\s*', '', request, flags=re.IGNORECASE).strip()

        # Match pattern: (open|launch|start) <app> (and|then|to) (write|type|say) (that|:) <text>
        m = re.match(
            r'^(?:open|launch|start)\s+(.+?)\s+(?:and|then|to)\s+(?:write|type|say)\s+(?:that\s+)?["\']?(.+?)["\']?$',
            req_clean,
            flags=re.IGNORECASE,
        )
        if m:
            app_raw = m.group(1).strip()
            text_raw = m.group(2).strip()
            # Clean app name
            app_raw = re.sub(r'^(the|a|my)\s+', '', app_raw, flags=re.IGNORECASE).strip()
            if app_raw.lower() in ("notebook", "notes"):
                app_raw = "notepad"
            elif app_raw.lower() in ("vs code", "vscode", "vs"):
                app_raw = "vs code"
            elif app_raw.lower() in ("calc",):
                app_raw = "calculator"
            return {"app_name": app_raw, "text": text_raw}
        return None

    async def _route(self, user_request: str) -> dict:
        """Fast intent classification via rules or small model."""
        import re
        req = user_request.lower().strip()

        # Strip leading wake words/greetings: "hey woody", "hi woody", "woody", "hello woody", etc.
        req_clean = re.sub(r'^(hey|hi|hello|ok|okay)?\s*(woody|woodi|wodi|woodie)[,\s:]*\s*', '', req, flags=re.IGNORECASE).strip()
        effective_req = req_clean if req_clean else req

        # Check for compound open + type (e.g. "open notebook and write that 'i love pari'")
        compound = self._parse_compound_open_and_type(user_request)
        if compound:
            return {"agent": "compound_open_type", "confidence": 1.0, "params": compound}

        # Fast-path heuristics (< 1ms)
        _open_re = re.compile(r'^(open|launch|start)\s+\S')
        _close_re = re.compile(r'^(close|quit|exit)\s+\S')

        # Only fast-path open_app if NOT containing secondary actions
        is_compound = any(w in effective_req for w in [" and ", " then ", " write ", " type ", " also ", " with "])

        if not is_compound and _open_re.match(effective_req):
            params = self._extract_simple_params(user_request, "open_app")
            if params.get("app_name"):
                return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "open_app"}

        if not is_compound and _close_re.match(effective_req):
            params = self._extract_simple_params(user_request, "close_app")
            if params.get("app_name"):
                return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "close_app"}

        # Stop speaking / silence fast-paths
        if any(effective_req == k or effective_req.startswith(k + " ") for k in [
            "stop speaking", "stop talking", "be quiet", "shut up", "silence", "hush",
            "stop speech", "stop audio", "stop voice", "mute audio", "pause speech", "stop reading",
            "mute"
        ]) or effective_req in ["stop speaking", "stop talking", "be quiet", "shut up", "silence", "hush", "stop"]:
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "stop_speaking"}

        if any(k in effective_req for k in ["what time", "what's the time", "current time", "what date", "what's the date", "today's date"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_time_date"}
        if any(k in effective_req for k in ["cpu usage", "ram usage", "system stats", "memory usage", "how much cpu", "how much ram"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_system_stats"}
        if any(k in effective_req for k in ["battery", "power level", "how much battery"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_battery"}
        if any(k in effective_req for k in ["clipboard", "show clipboard", "what's in my clipboard"]):
            return {"agent": "system_agent", "confidence": 1.0, "direct_action": "get_clipboard"}
        if any(k in effective_req for k in [
            "take screenshot", "take a screenshot", "screenshot", "take ss", "take a ss",
            "do ss", "take screen shot", "take a screen shot", "screen shot",
            "capture screen", "capture screenshot", "capture the screen", "save screenshot", "snap screen"
        ]) or effective_req == "ss":
            return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "take_screenshot"}

        # Mobility & Window Management fast-paths
        if any(effective_req == k or effective_req.startswith(k + " ") for k in ["maximize window", "maximize", "fullscreen", "full screen"]):
            return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "maximize_window"}
        if any(effective_req == k or effective_req.startswith(k + " ") for k in ["minimize window", "minimize", "hide window"]):
            return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "minimize_window"}
        if any(k in effective_req for k in ["show desktop", "go to desktop"]):
            return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "hotkey"}
        if "scroll down" in effective_req:
            return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "scroll"}
        if "scroll up" in effective_req:
            return {"agent": "desktop_agent", "confidence": 1.0, "direct_action": "scroll"}

        # Screen perception & Vision fast-path (including speech/phonetic variations like "one my screen")
        if any(k in effective_req for k in [
            "one my screen", "on my screen", "in my screen", "on screen", "one screen", "in screen",
            "on my display", "on display",
            "see my screen", "look at my screen", "read my screen", "scan my screen",
            "analyze screen", "analyze my screen", "describe my screen", "describe the screen",
            "explain what's on my screen", "explain this error", "what do you see",
            "check my screen", "view my screen", "what am i looking at", "what is open"
        ]):
            return {"agent": "vision_agent", "confidence": 1.0, "direct_action": "analyze_screen"}

        # Web search fast-path
        if any(effective_req.startswith(p) for p in [
            "search for ", "search the web for ", "search the web", "search online for ", "search online",
            "search ", "google ", "look up ", "find info on ", "find information on "
        ]) or any(k in effective_req for k in ["search the internet", "search the web", "search online"]):
            return {"agent": "browser_agent", "confidence": 1.0, "direct_action": "search_web"}

        # Fast-path: conversational messages go directly to chat_agent
        _CHAT_GREETINGS = {
            "hi", "hello", "hey", "yo", "sup", "howdy",
            "hi woody", "hello woody", "hey woody", "woody",
            "thanks", "thank you", "ok", "okay", "cool", "great",
            "bye", "goodbye", "stop", "quit",
        }
        if req in _CHAT_GREETINGS or not req_clean or (len(req.split()) <= 6 and not any(
            c in req for c in ["open", "close", "run", "search", "find", "make", "create", "delete", "download", "type", "write", "screen"]
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
        # Words to strip
        _ARTICLES = {"the", "a", "an", "my"}
        _TRAILING = {"please", "thanks", "now"}

        if action == "open_app":
            for kw in ["open ", "launch ", "start "]:
                if kw in request_lower:
                    idx = request_lower.find(kw) + len(kw)
                    words = request[idx:].strip().split()
                    while words and words[0].lower() in _ARTICLES:
                        words = words[1:]
                    while words and words[-1].lower() in _TRAILING:
                        words = words[:-1]
                    # Stop at conjunctions
                    stop_idx = len(words)
                    for i, w in enumerate(words):
                        if w.lower() in ("and", "then", "with", "write", "type", "to", "also", "saying"):
                            stop_idx = i
                            break
                    app_words = words[:stop_idx]
                    if app_words:
                        clean_app = " ".join(app_words).strip().strip("'\"").lower()
                        if clean_app in ("notebook", "notes"):
                            clean_app = "notepad"
                        elif clean_app in ("vs code", "vscode", "vs"):
                            clean_app = "vs code"
                        elif clean_app in ("calc",):
                            clean_app = "calculator"
                        params["app_name"] = clean_app
                    break

        elif action == "close_app":
            for kw in ["close ", "quit ", "exit "]:
                if kw in request_lower:
                    idx = request_lower.find(kw) + len(kw)
                    words = request[idx:].strip().split()
                    while words and words[0].lower() in _ARTICLES:
                        words = words[1:]
                    while words and words[-1].lower() in _TRAILING:
                        words = words[:-1]
                    stop_idx = len(words)
                    for i, w in enumerate(words):
                        if w.lower() in ("and", "then", "with", "also"):
                            stop_idx = i
                            break
                    app_words = words[:stop_idx]
                    if app_words:
                        clean_app = " ".join(app_words).strip().strip("'\"").lower()
                        if clean_app in ("notebook", "notes"):
                            clean_app = "notepad"
                        elif clean_app in ("vs code", "vscode", "vs"):
                            clean_app = "vs code"
                        elif clean_app in ("calc",):
                            clean_app = "calculator"
                        params["app_name"] = clean_app
                    break

        elif action == "search_web":
            for kw in [
                "search the web for ", "search the web ", "search online for ", "search online ",
                "search for ", "search ", "google for ", "google ", "look up ",
                "find information on ", "find info on ", "find out about ", "find "
            ]:
                if kw in request_lower:
                    idx = request_lower.find(kw) + len(kw)
                    # Preserve original capitalisation for the search query
                    params["query"] = request[idx:].strip()
                    break
            if not params.get("query"):
                params["query"] = request.strip()

        elif action == "analyze_screen":
            params["custom_prompt"] = request.strip()

        elif action == "scroll":
            params["direction"] = "up" if "up" in request_lower else "down"
            params["clicks"] = 5

        elif action == "hotkey":
            if "desktop" in request_lower:
                params["keys"] = ["win", "d"]

        elif action == "chat":
            params["message"] = request.strip()

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
