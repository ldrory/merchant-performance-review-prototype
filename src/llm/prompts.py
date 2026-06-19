"""Prompts for the deck narrative. Mirrored in docs/prompts.md (deliverable).

The model is given *precomputed* numbers and must not invent or recompute any figure —
this is the guardrail that keeps the LLM out of arithmetic.
"""
from __future__ import annotations

from src.presentation.deck_schema import DeckModel, format_amount, format_value

SYSTEM_PROMPT = """\
You are a Riskified Customer Success Manager writing a merchant performance review.
Write in clear, concise, professional business English for a merchant audience.

STRICT RULES:
- Use ONLY the numbers provided in the user message. NEVER invent, estimate, or
  recompute any figure. If a number isn't provided, don't state it.
- Explain what changed and why it matters. When an evidence event lines up in time with a
  movement, note that it COINCIDES with the change — do not assert it caused the change.
- Use measured, hedged language: prefer "coincides with", "is consistent with", "may
  indicate", "suggests". Do NOT use "directly attributable", "models appropriately tightened",
  "fraud environment normalized", or "demonstrates model robustness".
- Respect each KPI's direction: for Approval Rate higher is better; for Accepted
  Chargeback Rate and Effective Fraud Rate lower is better.
- This is a CUSTOMER-FACING document. Never mention internal data-quality, validation,
  mismatch, provided-vs-computed, reconciliation, or "data points" topics.
- Some merchants have a count-based (transaction volume) and an amount-weighted (submitted
  value) view. When both are provided for a KPI, discuss both perspectives.
- Keep each KPI analysis to 2-4 sentences; keep executive-summary bullets to one line.
"""


def _kpi_block(insight) -> str:
    direction = {True: "higher is better", False: "lower is better", None: "neutral"}[
        insight.higher_is_better
    ]
    fmt = lambda v: format_value(insight.unit, v)
    change = "n/a" if insight.change_pct is None else f"{insight.change_pct:+.1f}%"
    trend = {True: "improving", False: "worsening", None: "—"}[insight.improving]
    block = (
        f"- {insight.metric_name} (id={insight.metric_id}, {direction}):\n"
        f"    count-based: first {fmt(insight.first_value)} ({insight.first_period}) → "
        f"latest {fmt(insight.latest_value)} ({insight.latest_period}); "
        f"change {change}; trend {trend}\n"
        f"    best {fmt(insight.best_value)} ({insight.best_period}); "
        f"worst {fmt(insight.worst_value)} ({insight.worst_period})"
    )
    if insight.amount is not None:
        a = insight.amount
        afmt = lambda v: format_amount(insight.metric_id, a.unit, v)
        achange = "n/a" if a.change_pct is None else f"{a.change_pct:+.1f}%"
        block += (
            f"\n    amount-weighted: first {afmt(a.first_value)} ({a.first_period}) → "
            f"latest {afmt(a.latest_value)} ({a.latest_period}); change {achange}"
        )
    return block


def build_user_message(deck: DeckModel) -> str:
    """Render the precomputed deck model into the user prompt."""
    lines = [
        f"Merchant: {deck.merchant_name} "
        f"({deck.pre_or_post} authorization, {deck.business_structure})",
        f"Period: {deck.period_start} to {deck.period_end}",
        "",
        "KPIs (all figures precomputed — use exactly as given):",
    ]
    lines += [_kpi_block(k) for k in deck.kpis]

    if deck.evidence:
        lines += ["", "Evidence events:"]
        lines += [f"- {e.period}: {e.event}" for e in deck.evidence]

    lines += [
        "",
        "Write: (1) an executive_summary as 3-5 one-line bullets, and "
        "(2) kpi_analysis: a 2-4 sentence paragraph per KPI keyed by its id.",
    ]
    return "\n".join(lines)
