"""
Wodi LangGraph Agent Graph — Cloud provider execution path.

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

from wodi.utils.llm_factory import get_llm
from wodi.utils.logging import get_logger

log = get_logger(__name__)


# ── Shared state ──────────────────────────────────────────────────────────────

class WodiGraphState(TypedDict):
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

WODI_SYSTEM_PROMPT = """\
You are Wodi, an intelligent AI desktop assistant running on Windows.

Tool Efficiency Directives:
- Execute at most THREE tool calls per user query unless multi-step desktop interaction is strictly necessary.
- Once you receive tool execution results, immediately synthesize and deliver the final answer.
  Do NOT invoke additional tools unnecessarily.

Response Directives:
- Always answer directly, concisely, and helpfully.
- Use clean markdown formatting where appropriate (code blocks, bullet points).
- Do NOT add unnecessary preamble or filler phrases.
"""


# ── Planner node ──────────────────────────────────────────────────────────────

def _build_tools():
    """Collect all available Wodi tools for LangGraph binding.

    Wodi's builtin tools are plain functions returning dicts. LangGraph's
    ToolNode requires LangChain Tool objects, so we wrap them using
    StructuredTool.from_function().

    The @lc_tool-decorated tools from browser_tools (search_web,
    web_search_tavily) are already LangChain Tools and used directly.
    """
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
        from wodi.tools.builtin.system_tools import (
            get_time_date, get_system_stats, get_battery, get_clipboard,
        )
        tools.extend([
            _wrap(get_time_date, description="Get the current local time, date, and timezone."),
            _wrap(get_system_stats, description="Get current CPU, RAM, and disk usage statistics."),
            _wrap(get_battery, description="Get current battery level and charging status."),
            _wrap(get_clipboard, description="Get the current clipboard text content."),
        ])
    except ImportError as e:
        log.warning("langgraph_graph.system_tools_error", error=str(e))

    # ── Desktop tools ──
    try:
        from wodi.tools.builtin.desktop_tools import (
            open_app, close_app, take_screenshot,
        )
        tools.extend([
            _wrap(open_app, description="Open a desktop application by name (e.g. 'chrome', 'notepad')."),
            _wrap(close_app, description="Close a running desktop application by name."),
            _wrap(take_screenshot, description="Capture a screenshot of the active window."),
        ])
    except ImportError as e:
        log.warning("langgraph_graph.desktop_tools_error", error=str(e))

    # ── Filesystem tools ──
    try:
        from wodi.tools.builtin.filesystem_tools import (
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
        from wodi.tools.builtin.browser_tools import search_web
        tools.append(search_web)
    except ImportError as e:
        log.warning("langgraph_graph.browser_tools_error", error=str(e))

    # ── Tavily web search (if API key configured, already @lc_tool) ──
    try:
        if os.getenv("TAVILY_API_KEY"):
            from wodi.tools.builtin.browser_tools import web_search_tavily
            tools.append(web_search_tavily)
    except ImportError:
        pass

    log.info("langgraph_graph.tools_loaded", count=len(tools))
    return tools


def _make_planner_node(tools: list):
    """Factory: returns a planner node function bound to the given tools."""
    from langchain_core.messages import SystemMessage

    def planner_node(state: WodiGraphState) -> dict:
        messages = state["messages"]
        full_messages = [SystemMessage(content=WODI_SYSTEM_PROMPT)] + list(messages)
        model = get_llm(temperature=0).bind_tools(tools)
        response = model.invoke(full_messages)
        return {
            "messages": [response],
            "current_agent": "Wodi",
            "status": "Response ready.",
        }

    return planner_node


# ── Graph compilation ─────────────────────────────────────────────────────────

def build_graph():
    """
    Build and compile the Wodi LangGraph state machine.

    Returns:
        Compiled LangGraph graph ready for .astream() / .ainvoke().
    """
    ALL_TOOLS = _build_tools()

    builder: StateGraph = StateGraph(WodiGraphState)

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
