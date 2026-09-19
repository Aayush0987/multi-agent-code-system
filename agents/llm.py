"""Pluggable LLM backend selection.

Supports Groq (free-tier API), Gemini (free-tier API), and Ollama (local,
fully free/offline). Backend and model are chosen via environment variables
so each agent role could, in principle, use a different provider/model.

Env vars:
    LLM_PROVIDER          groq | gemini | ollama   (default: groq)
    LLM_MODEL             provider-specific model name (optional, has defaults)
    GROQ_API_KEY          required if LLM_PROVIDER=groq
    GOOGLE_API_KEY        required if LLM_PROVIDER=gemini
    OLLAMA_MODEL          used if LLM_PROVIDER=ollama (default: qwen2.5-coder)
"""
from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

_DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-120b",
    "gemini": "gemini-flash-lite-latest",
    "ollama": "qwen2.5-coder",
}


def extract_text(response) -> str:
    """Normalize a chat model response's `.content` to plain text.

    Some providers (e.g. certain Gemini models) return `.content` as a list
    of structured content blocks (`{"type": "text", "text": "..."}`, plus
    non-text blocks like signatures) rather than a plain string. Every agent
    parses the model's raw text (regex/JSON), so this is the single place
    that normalizes both shapes.
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def get_llm(role: str | None = None, temperature: float = 0.2) -> BaseChatModel:
    """Return a chat model instance for the configured provider.

    `role` (e.g. "planner", "coder", "reviewer") allows per-agent overrides
    via `<ROLE>_LLM_PROVIDER` / `<ROLE>_LLM_MODEL` env vars, falling back to
    the global `LLM_PROVIDER` / `LLM_MODEL`.
    """
    prefix = f"{role.upper()}_" if role else ""
    provider = (os.getenv(f"{prefix}LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "groq").lower()
    model = (
        os.getenv(f"{prefix}LLM_MODEL")
        or os.getenv("LLM_MODEL")
        or _DEFAULT_MODELS.get(provider)
    )

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, temperature=temperature)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, temperature=temperature)

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, temperature=temperature)

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r} (expected groq | gemini | ollama)")


def invoke_text(llm: BaseChatModel, messages) -> str:
    """Invoke a chat model and return its response as plain text (see
    `extract_text`). Use this instead of `llm.invoke(...).content` directly
    in agent code, so text parsing is unaffected by provider-specific
    content shapes."""
    return extract_text(llm.invoke(messages))
