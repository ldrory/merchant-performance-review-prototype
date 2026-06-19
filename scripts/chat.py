"""CLI: chat with the per-merchant agent.

Usage:
    python scripts/chat.py --merchant acme

The ``--merchant`` flag IS the session — it's the only place the merchant is selected. The
agent is bound to that merchant; the LLM can never reach another tenant. Requires the DuckDB
(run scripts/ingest.py first) and an LLM API key (e.g. ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from src.agent.chat_agent import MerchantAgent  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.connection import get_connection  # noqa: E402
from src.llm.client import get_chat_model  # noqa: E402
from src.repositories.metrics_repository import MetricsRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat with a merchant's performance agent.")
    parser.add_argument("--merchant", required=True, help="merchant_id (slug), e.g. acme")
    args = parser.parse_args()

    if not settings.DUCKDB_PATH.exists():
        print(f"ERROR: {settings.DUCKDB_PATH} not found. Run: python scripts/ingest.py")
        return 1

    con = get_connection(settings.DUCKDB_PATH, read_only=True)  # serving never writes
    repo = MetricsRepository(con)
    if args.merchant not in repo.list_merchant_ids():
        print(f"Unknown merchant '{args.merchant}'. Available: {repo.list_merchant_ids()}")
        return 1

    try:
        model = get_chat_model()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR building LLM model (is the API key set?): {e}")
        return 1

    agent = MerchantAgent(repo, args.merchant, model=model)
    profile = repo.get_profile(args.merchant)
    print(f"Chatting as {profile['merchant_name']} ({args.merchant}). Type 'exit' to quit.\n")

    history: list = []
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break
        answer = agent.ask(question, history=history)
        print(f"\nagent> {answer}\n")
        history += [HumanMessage(question), AIMessage(answer)]

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
