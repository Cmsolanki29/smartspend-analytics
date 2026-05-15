"""
Shared LLM wiring for the AI Insights chatbot and document upload parser.

Preference order (everywhere):
  1. OPENAI_API_KEY → OpenAI (gpt-4o-mini default, override OPENAI_CHAT_MODEL)
  2. GROQ_API_KEY   → Groq OpenAI-compatible API (llama-3.3-70b-versatile) — fallback only

Both use the `openai` Python SDK with streaming support.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, dotenv_values
from openai import OpenAI

# Safety-net: load .env directly so keys are available even if main.py dotenv
# block ran before this module was imported.
_PROVIDER_ENV_PATH = Path(r"C:\Users\Chirag\Downloads\SMARTSPENDAPP\exiqo\.env")
if not _PROVIDER_ENV_PATH.is_file():
    _PROVIDER_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if _PROVIDER_ENV_PATH.is_file():
    load_dotenv(_PROVIDER_ENV_PATH, override=True)
    # Also read directly so we can use file values even if Windows env overrides
    _file_env = dotenv_values(_PROVIDER_ENV_PATH)
else:
    _file_env: dict = {}


def _env_val(key: str, default: str = "") -> str:
    """Read key from .env file first, then os.environ, stripping whitespace."""
    return (_file_env.get(key) or "").strip() or (os.getenv(key) or "").strip() or default

def _openai_key() -> str:
    return _env_val("OPENAI_API_KEY")


def _groq_key() -> str:
    return _env_val("GROQ_API_KEY")


def preferred_provider() -> str:
    """Returns 'openai', 'groq', or 'none' (OpenAI first)."""
    if _openai_key():
        return "openai"
    if _groq_key():
        return "groq"
    return "none"


def get_chat_client(timeout: float = 90.0) -> OpenAI:
    """Primary chat client — always creates fresh (never caches a client with empty key)."""
    prov = preferred_provider()
    if prov == "openai":
        return OpenAI(api_key=_openai_key(), timeout=timeout)
    if prov == "groq":
        return OpenAI(api_key=_groq_key(), base_url="https://api.groq.com/openai/v1", timeout=timeout)
    raise RuntimeError("No LLM API key configured")


def get_chat_model() -> str:
    """Model id for the active primary provider."""
    if preferred_provider() == "openai":
        return _env_val("OPENAI_CHAT_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    return _env_val("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile"


def get_fallback_chat_client_and_model(timeout: float = 90.0) -> tuple[OpenAI | None, str | None]:
    """If OpenAI is primary, return (Groq client, model); else (OpenAI client, model); else (None, None)."""
    if preferred_provider() == "openai" and _groq_key():
        m = _env_val("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile"
        return OpenAI(api_key=_groq_key(), base_url="https://api.groq.com/openai/v1", timeout=timeout), m
    if preferred_provider() == "groq" and _openai_key():
        m = _env_val("OPENAI_CHAT_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        return OpenAI(api_key=_openai_key(), timeout=timeout), m
    return None, None


def llm_session_meta() -> dict[str, str]:
    if preferred_provider() == "none":
        return {"status": "offline", "label": "Unavailable"}
    return {"status": "online", "label": "Online"}
