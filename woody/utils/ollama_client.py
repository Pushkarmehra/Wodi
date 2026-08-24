"""
Groq Client Adapter (Replaces legacy Ollama client).
All calls are routed exclusively to Groq Cloud API.
"""
from __future__ import annotations

from woody.utils.groq_client import (
    GroqClient,
    Message,
    ChatResponse,
    ROLE_SYSTEM,
    ROLE_USER,
    ROLE_ASSISTANT,
    ROLE_TOOL,
)

# Re-export GroqClient as OllamaClient to prevent any broken imports while guaranteeing zero Ollama usage
OllamaClient = GroqClient

__all__ = [
    "GroqClient",
    "OllamaClient",
    "Message",
    "ChatResponse",
    "ROLE_SYSTEM",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_TOOL",
]
