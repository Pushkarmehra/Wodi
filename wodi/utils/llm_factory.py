"""
Wodi LLM Factory — Multi-provider LangChain model factory.

Priority chain (highest → lowest):
  1. Gemini (GEMINI_API_KEY)
  2. Groq  (GROQ_API_KEY)
  3. Ollama (local, default)

Usage:
    from wodi.utils.llm_factory import get_llm, get_provider_name

    llm = get_llm(temperature=0, max_tokens=1500)
    provider = get_provider_name()   # "gemini" | "groq" | "ollama"
"""
from __future__ import annotations

import os
from typing import Any

from wodi.utils.logging import get_logger

log = get_logger(__name__)

# Load .env from the workspace root (one level above the wodi package)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    load_dotenv(os.path.abspath(_env_path))
except ImportError:
    pass  # python-dotenv is optional


def get_llm(temperature: float = 0, max_tokens: int = 1500) -> Any:
    """
    Factory that returns a LangChain chat model based on available API keys.

    Fallback order: Gemini → Groq → Ollama (langchain-community wrapper).
    Raises ValueError only if no provider is configured at all.
    """
    # ── 1. Google Gemini ──────────────────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
            model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            log.info("llm_factory.using_gemini", model=model_name)
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=gemini_key,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        except ImportError:
            log.warning(
                "llm_factory.gemini_import_error",
                hint="pip install langchain-google-genai",
            )

    # ── 2. Groq ───────────────────────────────────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from langchain_groq import ChatGroq  # type: ignore
            model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
            log.info("llm_factory.using_groq", model=model_name)
            return ChatGroq(
                model=model_name,
                groq_api_key=groq_key,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except ImportError:
            log.warning(
                "llm_factory.groq_import_error",
                hint="pip install langchain-groq",
            )

    # ── 3. Ollama (local) ─────────────────────────────────────────────────────
    try:
        from langchain_ollama import ChatOllama  # type: ignore
        ollama_host = os.getenv("WODI_OLLAMA_HOST", "http://localhost:11434")
        model_name = os.getenv("WODI_PLANNER_MODEL", "qwen2.5:7b")
        log.info("llm_factory.using_ollama", model=model_name, host=ollama_host)
        return ChatOllama(
            model=model_name,
            base_url=ollama_host,
            temperature=temperature,
            num_predict=max_tokens,
        )
    except ImportError:
        pass

    raise ValueError(
        "No LLM provider configured. Set one of:\n"
        "  - GEMINI_API_KEY  (pip install langchain-google-genai)\n"
        "  - GROQ_API_KEY    (pip install langchain-groq)\n"
        "  - Ollama running  (pip install langchain-ollama)\n"
        "in your .env file."
    )


def get_provider_name() -> str:
    """Returns a human-readable string for the active LLM provider."""
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return "ollama"


def get_backend_port() -> int:
    """Returns the configured FastAPI backend port (default 8765)."""
    return int(os.getenv("BACKEND_PORT", "8765"))
