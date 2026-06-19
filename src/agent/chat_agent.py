"""MerchantAgent — a per-merchant Q&A agent with isolation by construction.

The agent is bound to ONE ``merchant_id`` from the session. Its tools close over that id and
its system prompt is built only from that merchant, so it has no other tenant's data to leak.
The tool-calling loop is a small manual loop (no LangGraph). The chat model is injectable so
tests run with a fake (no network).
"""
from __future__ import annotations

from typing import Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.prompts import build_system_prompt
from src.agent.tools import build_merchant_tools
from src.repositories.metrics_repository import MetricsRepository

_MAX_TOOL_STEPS = 5


class MerchantAgent:
    def __init__(self, repo: MetricsRepository, merchant_id: str, *, model: Optional[object] = None):
        self.repo = repo
        self.merchant_id = merchant_id
        self._system = build_system_prompt(repo, merchant_id)
        self._tools = build_merchant_tools(repo, merchant_id)
        self._by_name = {t.name: t for t in self._tools}
        if model is None:
            from src.llm.client import get_chat_model
            model = get_chat_model()
        self._llm = model.bind_tools(self._tools)

    def ask(self, question: str, history: Sequence[BaseMessage] = ()) -> str:
        """Answer one question for the bound merchant, running the tool loop as needed."""
        messages: list[BaseMessage] = [SystemMessage(self._system), *history, HumanMessage(question)]
        ai = self._llm.invoke(messages)
        for _ in range(_MAX_TOOL_STEPS):
            tool_calls = getattr(ai, "tool_calls", None)
            if not tool_calls:
                break
            messages.append(ai)
            for call in tool_calls:
                tool = self._by_name.get(call["name"])
                result = tool.invoke(call["args"]) if tool else f"Unknown tool {call['name']}."
                messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
            ai = self._llm.invoke(messages)
        return ai.content if isinstance(ai, AIMessage) else str(ai)
