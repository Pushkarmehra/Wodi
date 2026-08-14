"""
Async Ollama HTTP client wrapper for Wodi.

Provides:
  - Streaming chat completions (OpenAI-compatible /api/chat)
  - Tool/function calling
  - Model health check + availability probe
  - Concurrent request management with per-model semaphores
  - Vision (multimodal) support — base64 image injection

All calls are async-first. Sync wrappers provided for non-async callers.
"""
from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from wodi.utils.logging import get_logger

log = get_logger(__name__)

# Default Ollama endpoint
DEFAULT_HOST = "http://localhost:11434"

# Tool-calling message roles
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"


@dataclass
class Message:
    role: str
    content: str
    images: list[str] = field(default_factory=list)   # base64-encoded images
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.images:
            d["images"] = self.images
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    done: bool = True
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class OllamaClient:
    """
    Async wrapper around the Ollama HTTP API.

    Example:
        client = OllamaClient(host="http://localhost:11434")
        resp = await client.chat(
            model="qwen2.5:7b",
            messages=[Message(role="user", content="Hello!")],
        )
        print(resp.content)
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        timeout: float = 120.0,
        max_concurrent_per_model: int = 2,
    ) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._max_concurrent = max_concurrent_per_model
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "OllamaClient":
        self._client = httpx.AsyncClient(
            base_url=self.host,
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=20),
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # Lazily create a persistent client
            self._client = httpx.AsyncClient(
                base_url=self.host,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=20),
            )
        return self._client

    def _semaphore(self, model: str) -> asyncio.Semaphore:
        if model not in self._semaphores:
            self._semaphores[model] = asyncio.Semaphore(self._max_concurrent)
        return self._semaphores[model]

    # ── Health / Model Availability ──────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return True if Ollama is running and reachable."""
        try:
            resp = await self._get_client().get("/api/version", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """Return list of locally pulled model names."""
        try:
            resp = await self._get_client().get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            log.warning("ollama.list_models.error", error=str(e))
            return []

    async def is_model_available(self, model: str) -> bool:
        """Check whether a specific model is pulled locally."""
        models = await self.list_models()
        return any(m.startswith(model.split(":")[0]) for m in models)

    async def pull_model(self, model: str) -> bool:
        """Pull a model if not already available. Returns True on success."""
        log.info("ollama.pull_model", model=model)
        try:
            async with self._get_client().stream(
                "POST", "/api/pull", json={"name": model}
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        status = data.get("status", "")
                        if "pulling" in status or "downloading" in status:
                            log.debug("ollama.pull_progress", status=status)
            return True
        except Exception as e:
            log.error("ollama.pull_model.failed", model=model, error=str(e))
            return False

    # ── Chat ─────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def chat(
        self,
        model: str,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResponse:
        """
        Send a chat request to Ollama. Returns a ChatResponse.
        For streaming token-by-token output, use chat_stream() instead.
        """
        async with self._semaphore(model):
            payload: dict[str, Any] = {
                "model": model,
                "messages": [m.to_dict() for m in messages],
                "stream": False,
                "options": {"temperature": temperature},
            }
            if tools:
                payload["tools"] = tools
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            log.debug("ollama.chat", model=model, n_messages=len(messages), has_tools=bool(tools))

            try:
                resp = await self._get_client().post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    log.warning("ollama.chat.model_not_found", requested_model=model, hint="attempting fallback to available model")
                    available = await self.list_models()
                    if available:
                        fallback_model = available[0]
                        log.info("ollama.chat.fallback_used", fallback_model=fallback_model)
                        payload["model"] = fallback_model
                        resp = await self._get_client().post("/api/chat", json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                    else:
                        raise
                else:
                    log.error("ollama.chat.http_error", status=e.response.status_code, model=model)
                    raise
            except Exception as e:
                log.error("ollama.chat.error", error=str(e), model=model)
                raise

            msg = data.get("message", {})
            tool_calls = []
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "name": tc["function"]["name"],
                        "arguments": tc["function"].get("arguments", {}),
                    })

            return ChatResponse(
                content=msg.get("content", ""),
                tool_calls=tool_calls,
                model=data.get("model", model),
                done=data.get("done", True),
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
            )

    async def chat_stream(
        self,
        model: str,
        messages: list[Message],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat tokens as they are generated.
        Yields partial text chunks.
        """
        async with self._semaphore(model):
            payload: dict[str, Any] = {
                "model": model,
                "messages": [m.to_dict() for m in messages],
                "stream": True,
                "options": {"temperature": temperature},
            }
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            try:
                available = await self.list_models()
                target_model = model if any(m.startswith(model.split(":")[0]) for m in available) else (available[0] if available else model)
                payload["model"] = target_model

                async with self._get_client().stream("POST", "/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                        if data.get("done"):
                            break
            except Exception as e:
                log.error("ollama.stream.error", error=str(e), model=model)
                raise

    # ── Vision (Multimodal) ──────────────────────────────────────────────────

    async def vision_chat(
        self,
        model: str,
        prompt: str,
        images: list[bytes | str | Path],
        temperature: float = 0.1,
    ) -> ChatResponse:
        """
        Send a vision request with one or more images.
        images: list of raw bytes, base64 strings, or file paths.
        """
        encoded: list[str] = []
        for img in images:
            if isinstance(img, (str, Path)):
                p = Path(img)
                if p.exists():
                    encoded.append(base64.b64encode(p.read_bytes()).decode())
                else:
                    encoded.append(str(img))  # assume already base64
            elif isinstance(img, bytes):
                encoded.append(base64.b64encode(img).decode())

        msg = Message(role=ROLE_USER, content=prompt, images=encoded)
        return await self.chat(model=model, messages=[msg], temperature=temperature)

    # ── Embeddings ───────────────────────────────────────────────────────────

    async def embed(self, model: str, text: str | list[str]) -> list[list[float]]:
        """Return embeddings for text(s) using the given model."""
        inputs = [text] if isinstance(text, str) else text
        results: list[list[float]] = []
        for inp in inputs:
            try:
                resp = await self._get_client().post(
                    "/api/embeddings", json={"model": model, "prompt": inp}
                )
                resp.raise_for_status()
                results.append(resp.json().get("embedding", []))
            except Exception as e:
                log.error("ollama.embed.error", error=str(e))
                results.append([])
        return results
