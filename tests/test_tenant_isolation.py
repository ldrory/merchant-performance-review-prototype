"""Tenant isolation — proven structurally (the agent only ever holds one merchant's data)."""
from langchain_core.messages import AIMessage

from src.agent.chat_agent import MerchantAgent
from src.agent.prompts import build_system_prompt
from src.agent.tools import build_merchant_tools
from src.db.connection import get_connection
from src.ingestion.loaders import read_evidence, read_kpis, read_profiles
from src.pipeline import run_pipeline
from src.repositories.metrics_repository import MetricsRepository

_OTHERS = ("Cyberdyne", "Vandelay")


class FakeChatModel:
    """Minimal stand-in for a LangChain chat model: records messages, returns scripted replies."""
    def __init__(self, *replies: AIMessage):
        self._replies = list(replies) or [AIMessage(content="ok")]
        self.seen: list[list] = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.seen.append(list(messages))
        return self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]


def _repo():
    con = get_connection(":memory:")
    run_pipeline(con, read_kpis(), read_profiles(), read_evidence())
    return MetricsRepository(con)


def _tools_by_name(merchant_id="acme"):
    tools = build_merchant_tools(_repo(), merchant_id)
    return {t.name: t for t in tools}


# --- the tools expose no way to choose a tenant ---

def test_no_tool_accepts_merchant_id():
    for t in build_merchant_tools(_repo(), "acme"):
        assert "merchant_id" not in t.args, f"{t.name} must not expose merchant_id"


def test_expected_tool_set():
    # No get_data_quality_notes: internal QA/validation language is not merchant-facing.
    names = set(_tools_by_name())
    assert names == {
        "get_merchant_facts", "get_calculation_details", "get_evidence", "get_profile",
        "explain_reconciliation",
    }


# --- every tool returns only the selected merchant's data ---

def test_merchant_facts_is_scoped_to_acme():
    out = _tools_by_name()["get_merchant_facts"].invoke({})
    assert "Approval Rate" in out
    assert not any(name in out for name in _OTHERS)


def test_profile_is_acme_only():
    out = _tools_by_name()["get_profile"].invoke({})
    assert "ACME" in out and "Strategic" in out
    assert not any(name in out for name in _OTHERS)


def test_evidence_is_acme_only():
    out = _tools_by_name()["get_evidence"].invoke({})
    assert not any(name in out for name in _OTHERS)


# --- the full scoped dataset gives the LLM every month, so it can answer anything ---

def test_merchant_facts_includes_every_month_not_just_highlights():
    # The old summary only surfaced first/latest/best/worst, so "what about May?" failed.
    # The full dataset must contain the mid-period month (May 2026 approval = 98.35%).
    out = _tools_by_name("acme")["get_merchant_facts"].invoke({})
    assert "2026-05" in out
    assert "98.35%" in out  # ACME approval_rate count, May 2026 (0.983543)


def test_merchant_facts_shows_both_variants_for_strategic_merchant():
    # ACME is Strategic -> both the count and the amount-weighted (sum) views are returned.
    out = _tools_by_name("acme")["get_merchant_facts"].invoke({})
    assert "98.15%" in out  # approval count latest (0.981456)
    assert "97.33%" in out  # approval amount-weighted latest (0.973277)
    assert "count" in out.lower() and "amount" in out.lower()
    assert not any(name in out for name in _OTHERS)


def test_merchant_facts_shows_only_count_for_non_strategic_merchant():
    # Vandelay is Enterprise (not Strategic) -> only the count view exists, no sum.
    out = _tools_by_name("vandelay-industries")["get_merchant_facts"].invoke({})
    assert "98.82%" in out  # approval count latest (0.988181)
    assert "95.62%" not in out  # the sum value (0.956217) must not appear
    assert "amount" not in out.lower()  # no amount-weighted view at all


# --- get_calculation_details: scoped, profile-driven audit tool ---

def _calc(merchant_id, metric_id="approval_rate", period="2026-05"):
    return _tools_by_name(merchant_id)["get_calculation_details"].invoke(
        {"metric_id": metric_id, "period": period}
    )


def test_calc_details_post_merchant_uses_post_fields_only():
    out = _calc("acme")  # ACME is Post -> Post Auth components, never Pre
    assert "Post Auth" in out
    assert "Pre Auth" not in out  # no irrelevant Pre fields
    assert not any(name in out for name in _OTHERS)


def test_calc_details_pre_merchant_uses_pre_fields_only():
    out = _calc("cyberdyne-systems")  # Cyberdyne is Pre -> Pre Auth components, never Post
    assert "Pre Auth" in out
    assert "Post Auth" not in out  # no irrelevant Post fields


def test_calc_details_strategic_returns_cnt_and_sum():
    out = _calc("acme")  # Strategic
    assert "count" in out.lower() and "amount" in out.lower()


def test_calc_details_non_strategic_returns_cnt_only():
    out = _calc("vandelay-industries")  # Enterprise / not Strategic
    assert "count" in out.lower()
    assert "amount" not in out.lower()


def test_calc_details_exposes_supporting_components():
    # Calculation answers still expose the business supporting data: value + numerator +
    # denominator + the raw business field names.
    out = _calc("acme").lower()
    for field in ("numerator", "denominator", "submitted cnt"):
        assert field in out, f"missing supporting field: {field}"


def test_calc_details_reported_rate_uses_business_language():
    # Approval rate is reported in the dataset; explain it as reported + supporting components,
    # never as an internal "provided vs computed" comparison.
    out = _calc("acme", "approval_rate").lower()
    assert "reported" in out
    assert "submitted cnt" in out  # denominator named correctly


def test_calc_details_accepted_chargeback_denominator_is_submitted_not_approved():
    out = _calc("acme", "accepted_chargeback_rate")
    assert "Submitted Cnt" in out          # correct denominator
    assert "Accepted Chargeback Cnt" in out  # correct numerator
    assert "Approved" not in out            # NOT divided by approved orders


def test_calc_details_unknown_metric_is_handled():
    out = _calc("acme", "not_a_metric")
    assert "approval_rate" in out  # lists valid ids instead of erroring


# --- locked metric-explanation policy: provided-rate vs computed-only ---

def test_provided_rate_metrics_render_no_false_equation():
    # Approval / Accepted Chargeback are reported rates: never show "numerator / denominator ="
    # as if it equals the reported value. Show the reported rate + supporting components.
    for metric in ("approval_rate", "accepted_chargeback_rate"):
        out = _calc("acme", metric)
        assert "÷" not in out, f"{metric} must not render a component equation"
        assert "Reported count-based rate" in out
        assert "Supporting components" in out


def test_effective_fraud_renders_actual_equation():
    # Effective Fraud is computed-only -> the real equation IS the value.
    out = _calc("acme", "effective_fraud_rate")
    assert "÷" in out and "=" in out
    assert "Effective Fraud Cnt" in out and "Submitted Cnt" in out


def test_additive_metric_shows_raw_source_field():
    out = _calc("acme", "submission_volume")
    assert "Submitted Cnt" in out and "Submitted Sum" in out
    assert "÷" not in out  # additive has no ratio


def test_reconciliation_answer_is_transparent_and_customer_safe():
    out = _tools_by_name("acme")["explain_reconciliation"].invoke({})
    low = out.lower()
    assert "does not exactly reconcile" in low
    assert "official value" in low
    for term in _INTERNAL_TERMS:
        assert term not in low, f"internal term leaked: {term!r}"


# --- merchant-facing: no internal validation/QA terminology leaks to the merchant ---

# The forbidden internal/debug vocabulary (rule 4) — note "differences" is allowed English,
# so we ban the specific field names abs_diff / rel_diff_pct, not the bare substring "diff".
_INTERNAL_TERMS = (
    "mismatch", "validation_status", "provided_value", "computed_value",
    "abs_diff", "rel_diff_pct", "data quality issue", "investigating with your data team",
)


def test_merchant_facing_tools_hide_internal_terms():
    tools = _tools_by_name("acme")
    outputs = [
        tools["get_merchant_facts"].invoke({}),
        tools["get_calculation_details"].invoke({"metric_id": "accepted_chargeback_rate",
                                                  "period": "2026-05"}),
        tools["get_calculation_details"].invoke({"metric_id": "approval_rate",
                                                  "period": "2026-05"}),
        tools["get_calculation_details"].invoke({"metric_id": "effective_fraud_rate",
                                                  "period": "2026-05"}),
        tools["explain_reconciliation"].invoke({}),
    ]
    for out in outputs:
        low = out.lower()
        for term in _INTERNAL_TERMS:
            assert term not in low, f"internal term leaked to merchant: {term!r}"


def test_internal_quality_summary_still_flags_validation():
    # The customer-facing app hides it, but internal QA must still surface the divergence.
    from src.metrics.quality import summarize_metric_quality
    facts = _repo().get_all_monthly_facts()
    notes = " ".join(summarize_metric_quality(facts)).lower()
    assert "differs" in notes  # internal warning still produced for the team


# --- the prompt names only the selected merchant ---

def test_system_prompt_is_acme_only():
    prompt = build_system_prompt(_repo(), "acme")
    assert "ACME" in prompt
    assert not any(name in prompt for name in _OTHERS)


# --- the agent (fake model, no network) ---

def test_agent_returns_model_answer():
    fake = FakeChatModel(AIMessage(content="ACME approval rate is healthy."))
    agent = MerchantAgent(_repo(), "acme", model=fake)
    assert agent.ask("How is approval doing?") == "ACME approval rate is healthy."


def test_agent_feeds_only_acme_context_even_when_asked_about_another_merchant():
    fake = FakeChatModel(AIMessage(content="I can only help with the selected merchant."))
    agent = MerchantAgent(_repo(), "acme", model=fake)
    agent.ask("How is Cyberdyne Systems doing compared to Vandelay?")
    # The system message the model received must contain no other merchant's data,
    # regardless of what the user typed in the question.
    system_msg = fake.seen[0][0].content
    assert "ACME" in system_msg
    assert not any(name in system_msg for name in _OTHERS)


def test_agent_runs_tool_loop_with_scoped_tool_result():
    # 1st reply asks for a tool; 2nd reply is the final answer.
    call = AIMessage(content="", tool_calls=[{"name": "get_profile", "args": {}, "id": "t1"}])
    final = AIMessage(content="ACME is a Strategic, Post-auth merchant.")
    fake = FakeChatModel(call, final)
    agent = MerchantAgent(_repo(), "acme", model=fake)
    answer = agent.ask("What kind of account is this?")
    assert answer == "ACME is a Strategic, Post-auth merchant."
    # the tool result fed back on the 2nd call is ACME-scoped (and names no other merchant)
    tool_msgs = [m for m in fake.seen[1] if m.__class__.__name__ == "ToolMessage"]
    assert tool_msgs and "ACME" in tool_msgs[0].content
    assert not any(name in tool_msgs[0].content for name in _OTHERS)
