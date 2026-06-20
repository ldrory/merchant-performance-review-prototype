"""Streamlit chat UI — the merchant picker is a *simulated login*.

Selecting a merchant sets the session's `merchant_id`; the agent is bound to it and can only
read that merchant's data. Switching merchants starts a fresh, isolated session. Run with
`python scripts/run_app.py` (or `streamlit run src/app/streamlit_app.py`).
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from src.agent.chat_agent import MerchantAgent  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.connection import get_connection  # noqa: E402
from src.llm.client import get_chat_model  # noqa: E402
from src.repositories.metrics_repository import MetricsRepository  # noqa: E402

LOGO = PROJECT_ROOT / "assets" / "riskified_logo.png"  # one logo asset, shared with the decks
_logo = str(LOGO) if LOGO.exists() else None

st.set_page_config(page_title="Riskified — Merchant Performance Agent", page_icon=_logo or "📊")
# Branded top-left logo (also shown in the sidebar), persistent across the app.
if _logo:
    st.logo(_logo, size="large", link="https://www.riskified.com")

# Cache the shared, NON-tenant-bound resources. The tenant-bound MerchantAgent is built per
# request below (never cached) so a cached object can't accidentally outlive its merchant scope.
@st.cache_resource
def _repo() -> MetricsRepository:
    # read-only: serving never writes, so it can share the DB with the DuckDB UI.
    return MetricsRepository(get_connection(str(settings.DUCKDB_PATH), read_only=True))


@st.cache_resource
def _model():
    return get_chat_model()


if not settings.DUCKDB_PATH.exists():
    st.error("No database found. Run `python scripts/ingest.py` first.")
    st.stop()

repo = _repo()
merchant_ids = repo.list_merchant_ids()

st.sidebar.header("Logged in as")  # the picker = simulated auth/session
merchant_id = st.sidebar.selectbox("Merchant", merchant_ids, key="merchant_id")
profile = repo.get_profile(merchant_id)
st.sidebar.caption(f"{profile['pre_or_post']} authorization · {profile['business_structure']}")

st.title(f"📊 {profile['merchant_name']} — performance assistant")
st.caption("Ask about this merchant's KPIs. The assistant can only access this merchant's data.")

# Per-merchant chat history (reset when the selected merchant changes).
if st.session_state.get("_active") != merchant_id:
    st.session_state["_active"] = merchant_id
    st.session_state["messages"] = []

for role, text in st.session_state["messages"]:
    st.chat_message(role).write(text)

if question := st.chat_input("Ask about this merchant…"):
    st.chat_message("user").write(question)
    # Recent history (reset on merchant change above, so it's always this merchant's turns).
    history = [
        HumanMessage(t) if role == "user" else AIMessage(t)
        for role, t in st.session_state["messages"]
    ]
    # Build the tenant-bound agent per request (not cached) from cached repo + model.
    agent = MerchantAgent(_repo(), merchant_id, model=_model())
    with st.spinner("Thinking…"):
        answer = agent.ask(question, history=history)
    st.chat_message("assistant").write(answer)
    st.session_state["messages"] += [("user", question), ("assistant", answer)]
