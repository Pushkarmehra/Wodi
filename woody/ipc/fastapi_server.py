"""
Woody FastAPI + SSE Backend Server.

Bridges the Woody Kernel to web-based clients (WebEngine overlay, browser).

Endpoints:
  GET /                         — Serves the HTML renderer
  GET /api/execute?prompt=...   — SSE stream of agent events
  GET /api/clear_history        — Reset conversation context window
  GET /health                   — Provider + kernel status

Execution modes (auto-selected):
  • Cloud mode  — GEMINI_API_KEY or GROQ_API_KEY set → uses LangGraph graph
  • Local mode  — Ollama only → streams via WoodyKernel.process_request()
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

from woody.utils.llm_factory import get_backend_port, get_provider_name
from woody.utils.logging import get_logger

log = get_logger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Woody Agent Backend", version="2.0.0")

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
    """Serve the Woody Web UI."""
    index = RENDERER_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "app": "Woody Backend", "health": "/health"}


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


# ── Desktop AI Pet Lifecycle ──────────────────────────────────────────────────

_pet_process: Any | None = None


@app.get("/api/launch_pet")
def launch_pet():
    """Launch the animated Desktop AI Pet companion and switch voice to cat/pet voice."""
    global _pet_process
    import subprocess
    import sys

    # Switch active assistant mode to pet (using community-blcuaurhzmvi voice)
    set_mode("pet")

    if _pet_process is not None and _pet_process.poll() is None:
        return {"status": "ok", "message": "Desktop Pet is already running.", "running": True, "voice": "community-blcuaurhzmvi"}

    try:
        script_path = str(Path(__file__).parent.parent / "ui" / "desktop_pet.py")
        _pet_process = subprocess.Popen(
            [sys.executable, script_path],
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0,
        )
        log.info("fastapi.pet_launched", pid=_pet_process.pid, voice="community-blcuaurhzmvi")
        return {"status": "ok", "message": "Desktop Pet activated!", "pid": _pet_process.pid, "running": True, "voice": "community-blcuaurhzmvi"}
    except Exception as e:
        log.error("fastapi.pet_launch_failed", error=str(e))
        return {"status": "error", "error": str(e), "running": False}


@app.get("/api/toggle_pet")
def toggle_pet():
    """Toggle Desktop Pet on/off."""
    global _pet_process
    if _pet_process is not None and _pet_process.poll() is None:
        try:
            _pet_process.terminate()
            _pet_process = None
            set_mode("normal")
            return {"status": "ok", "message": "Desktop Pet closed. Normal voice restored.", "running": False, "voice": "Avery"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    else:
        return launch_pet()


@app.get("/api/pet_status")
def pet_status():
    """Check if the Desktop AI Pet companion is currently active."""
    global _pet_process
    is_running = _pet_process is not None and _pet_process.poll() is None
    tts = _get_tts_engine()
    active_voice = getattr(tts, "voice", "Avery") if tts else "Avery"
    return {"status": "ok", "running": is_running, "active_voice": active_voice}


@app.get("/api/set_mode")
def set_mode(mode: str = Query("normal", description="Mode: 'normal' or 'pet'")):
    """Switch mode and voice between normal mode ('Avery') and pet/cat mode ('community-blcuaurhzmvi')."""
    try:
        from woody.kernel.kernel import get_kernel
        k = get_kernel()
        if k:
            k.set_mode(mode)
    except Exception:
        pass

    tts = _get_tts_engine()
    if tts:
        tts.set_mode(mode)
        active_voice = tts.voice
    else:
        active_voice = "community-blcuaurhzmvi" if mode in ("pet", "cat") else "Avery"

    return {
        "status": "ok",
        "mode": mode,
        "active_voice": active_voice,
        "inworld_voice": active_voice,
    }


# ── TTS Engine helper ─────────────────────────────────────────────────────────

_tts_instance: Any | None = None


def _get_tts_engine() -> Any | None:
    global _tts_instance
    if _tts_instance is not None:
        return _tts_instance
    try:
        from woody.kernel.kernel import get_kernel
        k = get_kernel()
        if k and k.tts:
            _tts_instance = k.tts
            return _tts_instance
    except Exception:
        pass
    try:
        from woody.synthesis.tts import TTSEngine
        from woody.kernel.config import load_config
        cfg = load_config()
        _tts_instance = TTSEngine(
            engine=cfg.synthesis.tts_engine,
            voice=cfg.synthesis.tts_voice,
            pet_voice=getattr(cfg.synthesis, "pet_voice", "community-blcuaurhzmvi"),
            rate=cfg.synthesis.tts_rate,
            volume=cfg.synthesis.tts_volume,
            inworld_api_key=cfg.synthesis.inworld_api_key,
            inworld_model=cfg.synthesis.inworld_model,
            delivery_mode=cfg.synthesis.delivery_mode,
            language=cfg.synthesis.language,
        )
        _tts_instance.load()
    except Exception as e:
        log.warning("fastapi.tts_init_failed", error=str(e))
    return _tts_instance


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

    # Stop any current speech playback immediately
    tts = _get_tts_engine()
    if tts:
        tts.stop()

    # Check for direct stop / silence voice command
    p_clean = prompt.strip().lower()
    if p_clean in (
        "stop speaking", "stop talking", "be quiet", "shut up", "silence",
        "hush", "stop speech", "stop audio", "stop voice", "mute", "stop"
    ):
        yield {
            "data": json.dumps({
                "type": "response",
                "agent": "Woody",
                "message": "Speech stopped.",
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
        return

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

    # ── Local path (Ollama) → WoodyKernel ─────────────────────────────────────
    async for event in _kernel_stream(prompt):
        yield event


async def _langgraph_stream(prompt: str) -> AsyncGenerator[dict, None]:
    """Stream via LangGraph agent graph (cloud providers)."""
    global conversation_history

    try:
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        from woody.agents.langgraph_graph import graph
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
            tts = _get_tts_engine()
            if tts and getattr(tts, "engine", "") != "disabled":
                asyncio.create_task(tts.speak(full_response))

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
    """Stream via WoodyKernel (local Ollama mode)."""
    try:
        from woody.kernel.kernel import get_kernel
        kernel = get_kernel()
    except Exception:
        kernel = None

    if kernel is None:
        yield {
            "data": json.dumps({
                "type": "error",
                "agent": "System",
                "message": (
                    "Woody Kernel not running. Start with 'Woody' or set "
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
                    "agent": "Woody",
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
        from woody.kernel.kernel import get_kernel
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
    """Start the Woody FastAPI server (blocking)."""
    import uvicorn

    _port = port or get_backend_port()
    log.info("fastapi.starting", port=_port, provider=get_provider_name())
    uvicorn.run(app, host="127.0.0.1", port=_port, log_level="info")


if __name__ == "__main__":
    serve()
