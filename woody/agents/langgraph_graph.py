"""
Woody LangGraph Agent Graph — Cloud provider execution path.

Compiled once at module load. Used by the FastAPI SSE server when
Gemini or Groq API keys are present.

Graph flow:
    START → planner → (tools_condition) → tools → planner
                                        ↘ END
"""
from __future__ import annotations

import os
from typing import Annotated
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from woody.utils.llm_factory import get_llm
from woody.utils.logging import get_logger

log = get_logger(__name__)


# ── Shared state ──────────────────────────────────────────────────────────────

class WoodyGraphState(TypedDict):
    """
    Central state object flowing through all LangGraph nodes.

    Attributes:
        messages: Full conversation message history (auto-appended via reducer).
        current_agent: Display name of the active agent (shown in UI status).
        status: Short status string shown in the overlay (e.g. "Thinking…").
    """
    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str
    status: str


# ── System prompt ─────────────────────────────────────────────────────────────

# ── System prompt ─────────────────────────────────────────────────────────────

WOODY_SYSTEM_PROMPT = """\
You are Woody — an ultra-intelligent, highly capable AI operating system assistant running directly on Windows.

Core Capabilities:
1. Desktop Control & App Launching: You can launch and close applications (e.g. 'vs code', 'notepad', 'chrome', 'calculator'), type text into windows, press keyboard shortcuts, and manage open windows.
2. Email & Communication: You can draft, compose, and open emails using `compose_email(to, subject, body)`. You can also check saved user preferences/profile via `get_user_profile()` and save user info (like name) via `set_user_profile(name=...)`.
3. Screen Vision & Perception: You can analyze the screen using `analyze_screen` to see open applications, error messages, code, or visual layouts.
4. System Diagnostics & Command Execution: You can check CPU, RAM, battery, clipboard, processes, and run safe shell commands.
5. Web & Filesystem: You can search the web, read/write local files, and search directories.

Intelligence Directives:
- Email Writing & Drafting:
  * Check user name via `get_user_profile`. If user name is known (e.g. Pushkar), use it in the email sign-off. Never leave placeholder tokens like '[Your Name]' in the final email.
  * If the user introduces themselves or provides their name, call `set_user_profile(name=...)` to remember it permanently.
  * When the user asks to write/send/draft an email to an address (e.g. pushkaroops@gmail.com), construct the complete professional email (subject and body) and call `compose_email(to=..., subject=..., body=...)` so the compose window opens immediately on the user's desktop with all fields pre-filled, ready for the user to hit Send.
- App Names: Understand informal nicknames naturally ('vs code' -> VS Code, 'notebook' -> Notepad, 'calc' -> Calculator).
- Compound Actions: If the user says "open notepad and write hello", execute `open_app("notepad")` followed by `type_text("hello")`.
- Screen Queries: When asked about what is on screen or looking at an error, call `analyze_screen` or `take_screenshot`.
- Direct & Eloquent: Provide articulate, helpful responses.
"""


# ── Planner node ──────────────────────────────────────────────────────────────

def _build_tools():
    """Collect all available Woody tools for LangGraph binding."""
    from langchain_core.tools import StructuredTool

    tools = []

    def _wrap(fn, name: str | None = None, description: str | None = None):
        """Wrap a plain function as a LangChain StructuredTool."""
        return StructuredTool.from_function(
            func=fn,
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
        )

    # ── System tools ──
    try:
        from woody.tools.builtin.system_tools import (
            get_time_date, get_system_stats, get_battery, get_clipboard,
            set_clipboard, list_processes, run_command,
        )
        tools.extend([
            _wrap(get_time_date, description="Get the current local time, date, and timezone."),
            _wrap(get_system_stats, description="Get current CPU, RAM, and disk usage statistics."),
            _wrap(get_battery, description="Get current battery level and charging status."),
            _wrap(get_clipboard, description="Get the current clipboard text content."),
            _wrap(set_clipboard, description="Copy a string of text to the Windows clipboard."),
            _wrap(list_processes, description="List currently running processes."),
            _wrap(run_command, description="Execute a safe shell command on Windows and return its output."),
        ])
    except ImportError as e:
        log.warning("langgraph_graph.system_tools_error", error=str(e))

    # ── Desktop & Email tools ──
    try:
        from woody.tools.builtin.desktop_tools import (
            open_app, close_app, focus_window, type_text, press_key, hotkey,
            get_open_windows, take_screenshot, analyze_screen,
            compose_email, get_user_profile, set_user_profile,
        )
        tools.extend([
            _wrap(open_app, description="Open a desktop application by name (e.g. 'vs code', 'chrome', 'notepad')."),
            _wrap(close_app, description="Close a running desktop application by name."),
            _wrap(focus_window, description="Bring a window to the foreground by its title."),
            _wrap(type_text, description="Type text into the active window."),
            _wrap(press_key, description="Press a keyboard key like 'enter', 'escape', 'tab'."),
            _wrap(hotkey, description="Press a keyboard shortcut like 'ctrl+c', 'ctrl+v', 'win+d'."),
            _wrap(get_open_windows, description="Get titles of all currently visible open windows."),
            _wrap(take_screenshot, description="Capture a screenshot of the screen and save to disk."),
            _wrap(analyze_screen, description="Capture screen and analyze what applications, errors, or content are visible."),
            _wrap(compose_email, description="Open the user's email client or browser with recipient, subject, and body pre-filled so they can press Send."),
            _wrap(get_user_profile, description="Get stored user profile information such as user's name and email preferences."),
            _wrap(set_user_profile, description="Save user profile information such as name in persistent memory."),
        ])
    except ImportError as e:
        log.warning("langgraph_graph.desktop_tools_error", error=str(e))

    # ── Filesystem tools ──
    try:
        from woody.tools.builtin.filesystem_tools import (
            list_directory, read_file, write_file, search_files,
        )
        tools.extend([
            _wrap(list_directory, description="List files and folders in a directory."),
            _wrap(read_file, description="Read the text content of a file."),
            _wrap(write_file, description="Write text content to a file."),
            _wrap(search_files, description="Search for files matching a name pattern."),
        ])
    except ImportError as e:
        log.warning("langgraph_graph.filesystem_tools_error", error=str(e))

    # ── Browser tools (already @lc_tool decorated) ──
    try:
        from woody.tools.builtin.browser_tools import search_web
        tools.append(search_web)
    except ImportError as e:
        log.warning("langgraph_graph.browser_tools_error", error=str(e))

    # ── Tavily web search (if API key configured, already @lc_tool) ──
    try:
        if os.getenv("TAVILY_API_KEY"):
            from woody.tools.builtin.browser_tools import web_search_tavily
            tools.append(web_search_tavily)
    except ImportError:
        pass

    log.info("langgraph_graph.tools_loaded", count=len(tools))
    return tools


def _make_planner_node(tools: list):
    """Factory: returns a planner node function bound to the given tools."""
    from langchain_core.messages import SystemMessage

    def planner_node(state: WoodyGraphState) -> dict:
        messages = state["messages"]
        full_messages = [SystemMessage(content=WOODY_SYSTEM_PROMPT)] + list(messages)
        model = get_llm(temperature=0).bind_tools(tools)
        response = model.invoke(full_messages)
        return {
            "messages": [response],
            "current_agent": "Woody",
            "status": "Response ready.",
        }

    return planner_node


# ── Graph compilation ─────────────────────────────────────────────────────────

def build_graph():
    """
    Build and compile the Woody LangGraph state machine.

    Returns:
        Compiled LangGraph graph ready for .astream() / .ainvoke().
    """
    ALL_TOOLS = _build_tools()

    builder: StateGraph = StateGraph(WoodyGraphState)

    # Nodes
    builder.add_node("planner", _make_planner_node(ALL_TOOLS))
    builder.add_node("tools", ToolNode(ALL_TOOLS))

    # Edges
    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", tools_condition)
    builder.add_edge("tools", "planner")

    log.info("langgraph_graph.compiled", tools=len(ALL_TOOLS))
    return builder.compile()


# Compile once at module load — reused across all requests
try:
    graph = build_graph()
    log.info("langgraph_graph.ready")
except Exception as _e:
    log.warning(
        "langgraph_graph.build_failed",
        error=str(_e),
        hint="Install LangChain providers: pip install langchain langgraph",
    )
    graph = None  # type: ignore[assignment]
