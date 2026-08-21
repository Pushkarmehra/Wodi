"""
Wodi LLM Factory — Multi-provider LangChain model factory.

Priority chain:
  1. Groq (GROQ_API_KEY) — Primary high-speed engine
  2. Gemini (GEMINI_API_KEY) — Cloud alternative

Usage:
    from wodi.utils.llm_factory import get_llm, get_provider_name

    llm = get_llm(temperature=0, max_tokens=1500)
    provider = get_provider_name()   # "groq" | "gemini"
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
    pass


def _clean_key(key: str | None) -> str:
    if not key:
        return ""
    return key.strip().strip("'\"")


def get_llm(temperature: float = 0, max_tokens: int = 1500) -> Any:
    """
    Factory that returns a LangChain chat model based on available API keys.
    Groq is the primary provider.
    """
    # ── 1. Groq (Primary) ─────────────────────────────────────────────────────
    raw_key = os.getenv("GROQ_API_KEY")
    groq_key = _clean_key(raw_key)
    if groq_key and groq_key not in ("your-groq-api-key-here", "your_groq_api_key_here"):
        try:
            from langchain_groq import ChatGroq  # type: ignore
            model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
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
                hint="pip install langchain-groq groq",
            )

    # ── 2. Google Gemini (Alternative) ────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key.strip() not in ("", "your-gemini-api-key-here"):
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

    # If groq_key was provided but import failed or key not yet pasted:
    raise ValueError(
        "Groq API key not configured. Please set GROQ_API_KEY in your .env file:\n"
        "  1. Get a free API key at: https://console.groq.com/keys\n"
        "  2. Open .env and set: GROQ_API_KEY=gsk_your_key_here\n"
        "  3. Set model: GROQ_MODEL=llama-3.3-70b-versatile or llama-3.1-8b-instant"
    )


def get_provider_name() -> str:
    """Returns a human-readable string for the active LLM provider."""
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and groq_key.strip() not in ("", "your-groq-api-key-here", "your_groq_api_key_here"):
        return "groq"
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key and gemini_key.strip() not in ("", "your-gemini-api-key-here"):
        return "gemini"
    return "groq"


def get_backend_port() -> int:
    """Returns the configured FastAPI backend port (default 8765)."""
    return int(os.getenv("BACKEND_PORT", "8765"))
