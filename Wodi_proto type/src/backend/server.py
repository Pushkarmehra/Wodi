"""
Nex FastAPI Backend Server
Exposes an SSE endpoint for the Electron frontend to stream agent responses.
"""
import json
import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from src.backend.config import get_provider_name, get_backend_port
from src.backend.agents.graph import graph

app = FastAPI(title="Nex Agent Backend")

# Allow CORS for local Electron development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve Static Web Frontend ──
RENDERER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../renderer"))

if os.path.exists(RENDERER_DIR):
    app.mount("/static", StaticFiles(directory=RENDERER_DIR), name="static")

@app.get("/")
def read_root():
    """Serves the Nex Agent Web Interface at root URL."""
    index_file = os.path.join(RENDERER_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "ok", "app": "Nex Agent Backend", "health": "/health"}

@app.get("/styles.css")
def get_styles():
    return FileResponse(os.path.join(RENDERER_DIR, "styles.css"))

@app.get("/app.js")
def get_app_js():
    return FileResponse(os.path.join(RENDERER_DIR, "app.js"))

@app.get("/assets/{filename}")
def get_asset(filename: str):
    asset_path = os.path.join(RENDERER_DIR, "assets", filename)
    if os.path.exists(asset_path):
        return FileResponse(asset_path)
    return {"error": "Asset not found"}




# ── In-Memory Conversation History & Context Window ──
conversation_history: list = []
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "8"))


@app.get("/api/clear_history")
def clear_history():
    """Clears active conversation context window history."""
    global conversation_history
    conversation_history.clear()
    return {"status": "ok", "message": "Conversation history cleared."}


@app.get("/api/execute")
async def execute_endpoint(prompt: str = Query(..., description="User prompt text")):
    """
    Main execution endpoint. Accepts a user prompt, appends to context window,
    and streams back status updates and agent responses via Server-Sent Events (SSE).
    """
    global conversation_history

    async def event_generator():
        global conversation_history

        # ── Initial status ──
        yield {
            "data": json.dumps({
                "type": "status",
                "agent": "Planner",
                "step": "plan",
                "status": "Thinking...",
                "message": "Processing your request.",
            })
        }

        # Append new user prompt to context history
        user_msg = HumanMessage(content=prompt)
        conversation_history.append(user_msg)

        # Apply Context Window sliding limit (keep last MAX_CONTEXT_MESSAGES)
        if len(conversation_history) > MAX_CONTEXT_MESSAGES:
            context_window = conversation_history[-MAX_CONTEXT_MESSAGES:]
        else:
            context_window = list(conversation_history)

        inputs = {"messages": context_window}

        try:
            full_response_text = ""
            # Stream the LangGraph execution with recursion limit to prevent tool loops
            async for event in graph.astream(inputs, config={"recursion_limit": 6}, stream_mode="updates"):
                node_name = list(event.keys())[0]
                node_data = event[node_name]

                agent = node_data.get("current_agent", "Planner")
                status = node_data.get("status", "")

                # Extract message content
                messages = node_data.get("messages", [])
                message_text = ""
                msg_type = "log"

                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, AIMessage):
                        if last_msg.tool_calls:
                            tool_names = [tc["name"] for tc in last_msg.tool_calls]
                            message_text = f"Calling: {', '.join(tool_names)}"
                        else:
                            message_text = last_msg.content
                            full_response_text = message_text
                            msg_type = "response"
                    elif isinstance(last_msg, ToolMessage):
                        tool_name = getattr(last_msg, "name", "tool")
                        message_text = str(last_msg.content)
                        if "Error" in message_text or "Failed" in message_text:
                            msg_type = "error"
                            message_text = f"Tool {tool_name} error: {message_text[:100]}"
                        else:
                            msg_type = "log"
                            message_text = f"Executed {tool_name} successfully."

                # Send status update
                yield {
                    "data": json.dumps({
                        "type": "status",
                        "agent": agent,
                        "step": "execute",
                        "status": status or f"Running {node_name}...",
                    })
                }

                # Send message content if present
                if message_text:
                    yield {
                        "data": json.dumps({
                            "type": msg_type,
                            "agent": agent,
                            "message": message_text,
                        })
                    }

            # Append completed AI response to conversation history for context continuity
            if full_response_text:
                conversation_history.append(AIMessage(content=full_response_text))

            # ── Completion ──
            yield {
                "data": json.dumps({
                    "type": "complete",
                    "agent": "System",
                    "status": "Done",
                    "step": "complete",
                    "message": "Task complete.",
                })
            }

        except Exception as e:
            yield {
                "data": json.dumps({
                    "type": "error",
                    "agent": "System",
                    "status": "Failed",
                    "message": f"Error: {str(e)}",
                })
            }

    return EventSourceResponse(event_generator())


@app.get("/health")
def health():
    """Health check endpoint. Returns server status and active LLM provider."""
    return {
        "status": "ok",
        "provider": get_provider_name(),
    }


if __name__ == "__main__":
    import uvicorn
    port = get_backend_port()
    uvicorn.run(app, host="127.0.0.1", port=port)
