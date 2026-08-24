"""
Nex Configuration Module
Handles environment loading and LLM provider factory.
"""
import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


def get_llm(temperature: float = 0, max_tokens: int = 1500):
    """
    Factory function that returns a LangChain chat model based on environment
    configuration. Checks for GEMINI_API_KEY first, then GROQ_API_KEY.
    """
    # ── Try Gemini first ──
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=gemini_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

    # ── Fall back to Groq ──
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        from langchain_groq import ChatGroq
        model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        return ChatGroq(
            model=model_name,
            groq_api_key=groq_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(
        "No LLM provider configured. "
        "Set either GEMINI_API_KEY or GROQ_API_KEY in your .env file."
    )


def get_provider_name() -> str:
    """Returns a human-readable name for the active LLM provider."""
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return "none"


def get_backend_port() -> int:
    """Returns the configured backend port (default 8000)."""
    return int(os.getenv("BACKEND_PORT", "8000"))
