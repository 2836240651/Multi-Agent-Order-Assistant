from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def create_chat_model(*, temperature: float = 0) -> ChatOpenAI:
    """Create a ChatOpenAI client from MiniMax or OpenAI-compatible env vars."""
    api_key = _first_non_empty(
        os.getenv("MINIMAX_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
    )
    base_url = _first_non_empty(
        os.getenv("MINIMAX_BASE_URL"),
        os.getenv("OPENAI_BASE_URL"),
    )
    model = _first_non_empty(
        os.getenv("MINIMAX_MODEL"),
        os.getenv("MODEL_NAME"),
        "gpt-4o",
    )

    kwargs: dict[str, object] = {
        "model": model,
        "temperature": temperature,
    }

    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs)
