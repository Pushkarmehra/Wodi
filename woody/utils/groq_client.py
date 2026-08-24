"""
Async Groq Cloud client wrapper for Woody.

Provides:
  - Fast streaming chat completions via Groq LPU inference
  - OpenAI-compatible tool/function calling on LLaMA models
  - Health check & model validation for Groq API keys
  - Vision support via Groq vision models or OCR fallback
  - Drop-in compatibility for Planner, Synthesizer, Critic, and Agents
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from woody.utils.logging import get_logger

log = get_logger(__name__)

# Load .env from workspace root
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    load_dotenv(os.path.abspath(_env_path))
except ImportError:
    pass


def _clean_key(key: str | None) -> str:
    if not key:
        return ""
    return key.strip().strip("'\"")

# Default Groq Models
DEFAULT_MODEL = "llama-3.3-70b-versatile"
FAST_MODEL = "llama-3.1-8b-instant"
GROQ_API_BASE = "https://api.groq.com/openai/v1"

# Message Roles
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"


@dataclass
class Message:
    role: str
    content: str
    images: list[str] = field(default_factory=list)  # base64-encoded images or URLs
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.images:
            # Multi-modal format for vision models
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": self.content}]
            for img in self.images:
                if img.startswith("http://") or img.startswith("https://") or img.startswith("data:"):
                    content_parts.append({"type": "image_url", "image_url": {"url": img}})
                else:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img}"},
                    })
            d["content"] = content_parts
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


class GroqClient:
    """
    Async Groq API client with full streaming, tool-calling, and error handling.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = _clean_key(api_key or os.getenv("GROQ_API_KEY", ""))
        self.default_model = (
            default_model
            or os.getenv("GROQ_MODEL")
            or DEFAULT_MODEL
        )
        self.timeout = timeout
        self._http_client: httpx.AsyncClient | None = None
        self._groq_sdk_client: Any | None = None
        self._resolved_model_cache: dict[str, str] = {}

        # Initialize Groq SDK client if available
        if self.api_key:
            try:
                from groq import AsyncGroq
                self._groq_sdk_client = AsyncGroq(api_key=self.api_key, timeout=self.timeout)
            except Exception as e:
                log.debug("groq_client.sdk_init_fallback", error=str(e))

    def _get_headers(self) -> dict[str, str]:
        key = self.api_key or _clean_key(os.getenv("GROQ_API_KEY", ""))
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=GROQ_API_BASE,
                timeout=httpx.Timeout(self.timeout),
                headers=self._get_headers(),
                limits=httpx.Limits(max_connections=20),
            )
        return self._http_client

    async def __aenter__(self) -> "GroqClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        if self._groq_sdk_client and hasattr(self._groq_sdk_client, "close"):
            try:
                await self._groq_sdk_client.close()
            except Exception:
                pass

    # ── Health & Validation ───────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return True if Groq API key is present and reachable."""
        key = self.api_key or os.getenv("GROQ_API_KEY", "")
        if not key or key.strip() in ("", "your-groq-api-key-here", "your_groq_api_key_here"):
            return False

        try:
            client = self._get_http_client()
            resp = await client.get("/models", headers=self._get_headers(), timeout=5.0)
            return resp.status_code == 200
        except Exception as e:
            log.warning("groq.health_check_failed", error=str(e))
            return False

    async def list_models(self) -> list[str]:
        """Return list of available models from Groq."""
        try:
            client = self._get_http_client()
            resp = await client.get("/models", headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            log.warning("groq.list_models_error", error=str(e))
            return [DEFAULT_MODEL, FAST_MODEL]

    async def is_model_available(self, model: str) -> bool:
        models = await self.list_models()
        return any(model.lower() in m.lower() for m in models)

    # ── Chat Execution ────────────────────────────────────────────────────────

    async def chat(
        self,
        model: str | None = None,
        messages: list[Message] | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResponse:
        """
        Send a chat completion request to Groq.
        """
        target_model = self._resolve_model_name(model or self.default_model)
        msg_list = messages or []
        formatted_messages = [m.to_dict() for m in msg_list]

        key = self.api_key or _clean_key(os.getenv("GROQ_API_KEY", ""))
        if not key:
            raise ValueError(
                "GROQ_API_KEY is not set. Please add your Groq API key to .env\n"
                "Get your key at: https://console.groq.com/keys"
            )

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # Format tools for Groq/OpenAI function calling standard
        if tools:
            formatted_tools = []
            for t in tools:
                if "type" in t and "function" in t:
                    formatted_tools.append(t)
                elif "function" in t:
                    formatted_tools.append({"type": "function", "function": t["function"]})
                else:
                    formatted_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.get("name", ""),
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                        },
                    })
            payload["tools"] = formatted_tools
            payload["tool_choice"] = "auto"

        log.debug("groq.chat", model=target_model, n_messages=len(msg_list), has_tools=bool(tools))

        client = self._get_http_client()
        try:
            resp = await client.post(
                "/chat/completions",
                json=payload,
                headers=self._get_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                log.warning("groq.model_not_found_fallback", requested=target_model)
                available = await self.list_models()
                fallback = self._select_best_fallback(available)
                log.info("groq.fallback_model_selected", fallback=fallback)
                self._resolved_model_cache[target_model] = fallback
                if model:
                    self._resolved_model_cache[model] = fallback
                payload["model"] = fallback
                resp = await client.post("/chat/completions", json=payload, headers=self._get_headers())
                resp.raise_for_status()
                data = resp.json()
                target_model = fallback
            else:
                log.error("groq.chat.http_error", status=e.response.status_code, error=e.response.text)
                raise
        except Exception as e:
            log.error("groq.chat.error", error=str(e), model=target_model)
            raise

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls: list[dict] = []

        if "tool_calls" in msg and msg["tool_calls"]:
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                raw_args = func.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except Exception:
                        parsed_args = {"raw": raw_args}
                else:
                    parsed_args = raw_args

                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "arguments": parsed_args,
                })

        usage = data.get("usage", {})
        return ChatResponse(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            model=data.get("model", target_model),
            done=True,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    async def chat_stream(
        self,
        model: str | None = None,
        messages: list[Message] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from Groq in real-time.
        """
        target_model = self._resolve_model_name(model or self.default_model)
        msg_list = messages or []
        formatted_messages = [m.to_dict() for m in msg_list]

        key = self.api_key or _clean_key(os.getenv("GROQ_API_KEY", ""))
        if not key:
            raise ValueError("GROQ_API_KEY is not set. Add your key to .env")

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        client = self._get_http_client()
        try:
            async with client.stream(
                "POST",
                "/chat/completions",
                json=payload,
                headers=self._get_headers(),
            ) as resp:
                if resp.status_code == 404:
                    available = await self.list_models()
                    chat_models = [m for m in available if not m.startswith("whisper") and not m.startswith("meta-llama/llama-prompt")]
                    if chat_models:
                        payload["model"] = chat_models[0]
                        async with client.stream(
                            "POST",
                            "/chat/completions",
                            json=payload,
                            headers=self._get_headers(),
                        ) as fb_resp:
                            fb_resp.raise_for_status()
                            async for line in fb_resp.aiter_lines():
                                if not line:
                                    continue
                                if line.startswith("data: "):
                                    data_str = line[6:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        chunk = json.loads(data_str)
                                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                    except Exception:
                                        continue
                        return

                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            continue
        except Exception as e:
            log.error("groq.stream.error", error=str(e), model=target_model)
            raise

    async def vision_chat(
        self,
        model: str | None = None,
        prompt: str = "",
        images: list[bytes] | None = None,
        temperature: float = 0.1,
    ) -> ChatResponse:
        """
        Send a multimodal request to Groq Vision or fallback gracefully.
        """
        encoded_images = []
        if images:
            for img_bytes in images:
                encoded_images.append(base64.b64encode(img_bytes).decode("utf-8"))

        msg = Message(role=ROLE_USER, content=prompt, images=encoded_images)
        vision_model = model or "llama-3.2-11b-vision-preview"
        return await self.chat(model=vision_model, messages=[msg], temperature=temperature)

    def _select_best_fallback(self, available: list[str]) -> str:
        """Select best available chat model from list."""
        priority = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "groq/compound",
            "groq/compound-mini",
            "allam-2-7b",
        ]
        for p in priority:
            if p in available:
                return p
        chat_models = [
            m for m in available
            if not m.startswith("whisper")
            and not m.startswith("meta-llama/llama-prompt")
            and "orpheus" not in m
        ]
        return chat_models[0] if chat_models else "openai/gpt-oss-120b"

    def _resolve_model_name(self, model_name: str) -> str:
        """Map model names to exact IDs or pass through."""
        if not model_name:
            return self._resolved_model_cache.get(DEFAULT_MODEL, DEFAULT_MODEL)
        if model_name in self._resolved_model_cache:
            return self._resolved_model_cache[model_name]
        m = model_name.strip()
        m_lower = m.lower()
        if "instant" in m_lower or "8b" in m_lower:
            return self._resolved_model_cache.get(FAST_MODEL, FAST_MODEL)
        if "versatile" in m_lower or "70b" in m_lower or "3.3" in m_lower:
            return self._resolved_model_cache.get(DEFAULT_MODEL, DEFAULT_MODEL)
        if "qwen" in m_lower or "ollama" in m_lower:
            return self._resolved_model_cache.get(DEFAULT_MODEL, DEFAULT_MODEL)
        return m

