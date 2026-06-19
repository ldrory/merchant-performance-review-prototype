"""LangChain chat-model factory (provider-agnostic, configured via settings).

Defaults to Claude; swap provider/model with LLM_PROVIDER / LLM_MODEL env vars.
The import is done lazily so the rest of the app (and the offline tests) don't require
provider packages or an API key just to import this module.
"""
from __future__ import annotations

from src.config import settings


def get_chat_model(temperature: float = 0.2):
    """Build the configured chat model. Requires the provider's API key in the env."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(
        settings.LLM_MODEL,
        model_provider=settings.LLM_PROVIDER,
        temperature=temperature,
    )
