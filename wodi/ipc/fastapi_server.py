"""
Wodi FastAPI + SSE Backend Server.

Bridges the Wodi Kernel to web-based clients (WebEngine overlay, browser).

Endpoints:
  GET /                         — Serves the HTML renderer
  GET /api/execute?prompt=...   — SSE stream of agent events
  GET /api/clear_history        — Reset conversation context window
  GET /health                   — Provider + kernel status

Execution modes (auto-selected):
  • Cloud mode  — GEMINI_API_KEY or GROQ_API_KEY set → uses LangGraph graph
  • Local mode  — Ollama only → streams via WodiKernel.process_request()
"""
from __future__ import annotations

import json
import os
import asyncio
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from wodi.utils.llm_factory import get_backend_port, get_provider_name
from wodi.utils.logging import get_logger

log = get_logger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Wodi Agent Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static renderer ───────────────────────────────────────────────────────────

RENDERER_DIR = Path(__file__).parent.parent / "ui" / "renderer"

if RENDERER_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(RENDERER_DIR)), name="static")


@app.get("/")
def read_root():
    """Serve the Wodi Web UI."""
    index = RENDERER_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "app": "Wodi Backend", "health": "/health"}


@app.get("/styles.css")
def get_styles():
    return FileResponse(str(RENDERER_DIR / "styles.css"))


@app.get("/app.js")
def get_app_js():
    return FileResponse(str(RENDERER_DIR / "app.js"))


@app.get("/assets/{filename}")
def get_asset(filename: str):
    path = RENDERER_DIR / "assets" / filename
    if path.exists():
        return FileResponse(str(path))
    return {"error": "Asset not found"}


# ── Conversation history (sliding context window) ─────────────────────────────

conversation_history: list = []
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "8"))


@app.get("/api/clear_history")
def clear_history():
    """Reset active conversation context window."""
    global conversation_history
    conversation_history.clear()
    log.info("fastapi.history_cleared")
    return {"status": "ok", "message": "Conversation history cleared."}


# ── Main SSE execution endpoint ───────────────────────────────────────────────

@app.get("/api/execute")
async def execute_endpoint(prompt: str = Query(..., description="User prompt")):
    """
    Stream agent events for the given prompt as Server-Sent Events.

    Event schema:
        {"type": "status"|"response"|"log"|"error"|"complete",
         "agent": str, "message": str, "step": str}
    """
    return EventSourceResponse(_event_generator(prompt))


async def _event_generator(prompt: str) -> AsyncGenerator[dict, None]:
    """Generate SSE events for a user prompt."""
    global conversation_history

    # Initial acknowledgement
    yield {
        "data": json.dumps({
            "type": "status",
            "agent": "Planner",
            "step": "plan",
            "status": "Thinking...",
            "message": "Processing your request.",
        })
    }

    provider = get_provider_name()

    # ── Cloud path (Gemini/Groq) → LangGraph ─────────────────────────────────
    if provider in ("gemini", "groq"):
        async for event in _langgraph_stream(prompt):
            yield event
        return

    # ── Local path (Ollama) → WodiKernel ─────────────────────────────────────
    async for event in _kernel_stream(prompt):
        yield event


async def _langgraph_stream(prompt: str) -> AsyncGenerator[dict, None]:
    """Stream via LangGraph agent graph (cloud providers)."""
    global conversation_history

    try:
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        from wodi.agents.langgraph_graph import graph
    except ImportError as e:
        yield {
            "data": json.dumps({
                "type": "error",
                "agent": "System",
                "message": f"LangGraph not available: {e}. Install with: pip install langgraph langchain-core",
            })
        }
        return

    user_msg = HumanMessage(content=prompt)
    conversation_history.append(user_msg)

    # Apply sliding context window
    context = (
        conversation_history[-MAX_CONTEXT_MESSAGES:]
        if len(conversation_history) > MAX_CONTEXT_MESSAGES
        else list(conversation_history)
    )

    inputs = {"messages": context}
    full_response = ""

    try:
        async for event in graph.astream(
            inputs,
            config={"recursion_limit": 6},
            stream_mode="updates",
        ):
            node_name = list(event.keys())[0]
            node_data = event[node_name]

            agent = node_data.get("current_agent", "Planner")
            status = node_data.get("status", "")
            messages = node_data.get("messages", [])
            message_text = ""
            msg_type = "log"

            if messages:
                last = messages[-1]
                if isinstance(last, AIMessage):
                    if last.tool_calls:
                        tool_names = [tc["name"] for tc in last.tool_calls]
                        message_text = f"Calling: {', '.join(tool_names)}"
                    else:
                        message_text = last.content
                        full_response = message_text
                        msg_type = "response"
                elif isinstance(last, ToolMessage):
                    tool_name = getattr(last, "name", "tool")
                    content = str(last.content)
                    if "Error" in content or "Failed" in content:
                        msg_type = "error"
                        message_text = f"Tool {tool_name} error: {content[:120]}"
                    else:
                        msg_type = "log"
                        message_text = f"Executed {tool_name} successfully."

            yield {
                "data": json.dumps({
                    "type": "status",
                    "agent": agent,
                    "step": "execute",
                    "status": status or f"Running {node_name}...",
                })
            }

            if message_text:
                yield {
                    "data": json.dumps({
                        "type": msg_type,
                        "agent": agent,
                        "message": message_text,
                    })
                }

        if full_response:
            conversation_history.append(AIMessage(content=full_response))

    except Exception as e:
        log.error("fastapi.langgraph_error", error=str(e))
        yield {
            "data": json.dumps({
                "type": "error",
                "agent": "System",
                "status": "Failed",
                "message": f"Error: {e}",
            })
        }
        return

    yield {
        "data": json.dumps({
            "type": "complete",
            "agent": "System",
            "status": "Done",
            "step": "complete",
            "message": "Task complete.",
        })
    }


async def _kernel_stream(prompt: str) -> AsyncGenerator[dict, None]:
    """Stream via WodiKernel (local Ollama mode)."""
    try:
        from wodi.kernel.kernel import get_kernel
        kernel = get_kernel()
    except Exception:
        kernel = None

    if kernel is None:
        yield {
            "data": json.dumps({
                "type": "error",
                "agent": "System",
                "message": (
                    "Wodi Kernel not running. Start with 'wodi' or set "
                    "GEMINI_API_KEY / GROQ_API_KEY for cloud mode."
                ),
            })
        }
        yield {
            "data": json.dumps({
                "type": "complete", "agent": "System",
                "status": "Done", "step": "complete", "message": "",
            })
        }
        return

    chunks: list[str] = []
    complete = asyncio.Event()
    error_msg: list[str] = []

    def _on_chunk(chunk: str) -> None:
        chunks.append(chunk)

    async def _run() -> None:
        try:
            await kernel.process_request(prompt, on_response_chunk=_on_chunk)
        except Exception as e:
            error_msg.append(str(e))
        finally:
            complete.set()

    task = asyncio.create_task(_run())

    # Stream chunks as they arrive
    sent = 0
    while not complete.is_set() or sent < len(chunks):
        await asyncio.sleep(0.05)
        while sent < len(chunks):
            yield {
                "data": json.dumps({
                    "type": "response",
                    "agent": "Wodi",
                    "message": chunks[sent],
                })
            }
            sent += 1

    if error_msg:
        yield {
            "data": json.dumps({
                "type": "error",
                "agent": "System",
                "message": error_msg[0],
            })
        }

    yield {
        "data": json.dumps({
            "type": "complete",
            "agent": "System",
            "status": "Done",
            "step": "complete",
            "message": "Task complete.",
        })
    }


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check — returns provider and kernel status."""
    try:
        from wodi.kernel.kernel import get_kernel
        kernel_ok = get_kernel() is not None
    except Exception:
        kernel_ok = False

    return {
        "status": "ok",
        "provider": get_provider_name(),
        "kernel_running": kernel_ok,
        "port": get_backend_port(),
    }


# ── Standalone launch ─────────────────────────────────────────────────────────

def serve(port: int | None = None) -> None:
    """Start the Wodi FastAPI server (blocking)."""
    import uvicorn

    _port = port or get_backend_port()
    log.info("fastapi.starting", port=_port, provider=get_provider_name())
    uvicorn.run(app, host="127.0.0.1", port=_port, log_level="info")


if __name__ == "__main__":
    serve()
