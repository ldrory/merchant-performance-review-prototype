"""Generate the deck narrative via a single structured LLM call per merchant.

The chat model is injectable so tests pass a fake (no network); production builds the
real Claude model from ``client.get_chat_model``. The LLM only narrates the precomputed
``DeckModel`` — it never computes numbers.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.llm.prompts import SYSTEM_PROMPT, build_user_message
from src.presentation.deck_schema import DeckModel


class NarrativeBundle(BaseModel):
    """Structured LLM output for one merchant's deck."""
    executive_summary: list[str] = Field(description="3-5 one-line summary bullets")
    kpi_analysis: dict[str, str] = Field(
        description="metric_id -> 2-4 sentence analysis paragraph"
    )


def generate_narrative(deck: DeckModel, model: Optional[object] = None) -> NarrativeBundle:
    """Produce exec summary + per-KPI analysis. ``model`` is injectable for tests."""
    if model is None:
        from src.llm.client import get_chat_model
        model = get_chat_model()

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(build_user_message(deck))]
    structured = model.with_structured_output(NarrativeBundle)
    return structured.invoke(messages)
