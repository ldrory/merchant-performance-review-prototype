"""Agent tools — the isolation boundary.

Each tool is a closure that captures ``(repo, merchant_id)`` from the session. The functions
the LLM sees take **no ``merchant_id``** — they can only read the one merchant bound at build
time, via the merchant-scoped repository methods. There is no lever for the model (or the user's
question) to reach another tenant.
"""
from __future__ import annotations

import pandas as pd
from langchain_core.tools import StructuredTool

from src.metrics.registry import METRIC_REGISTRY, MetricDefinition, MetricVariant, resolve
from src.presentation.deck_schema import format_value
from src.repositories.metrics_repository import MetricsRepository

_METRICS = {m.id: m for m in METRIC_REGISTRY}

# This agent is MERCHANT-FACING: outputs use business-friendly language only. Internal
# reconciliation fields (value_source, provided/computed values, validation_status, mismatch
# counts) live in the fact table and quality artifacts — never in these responses.

# Plain-English description of what each KPI measures.
_BUSINESS_DEFINITION = {
    "submission_volume": "the volume of orders submitted (count of orders and their total amount)",
    "approval_rate": "the share of submitted orders that were approved",
    "accepted_chargeback_rate": "the share of submitted orders that resulted in an accepted chargeback",
    "effective_fraud_rate": "the share of submitted orders identified as effective fraud",
}

# Locked policy: when an explicit rate KPI is reported in the source dataset, that reported value
# is the customer-facing source of truth; the component ratio is supporting context only. This is
# the customer-safe answer if a merchant asks why the components don't exactly reconcile.
RECONCILIATION_NOTE = (
    "The simple component ratio does not exactly reconcile to the reported KPI value. This "
    "prototype treats the reported KPI value from the source dataset as the official value. The "
    "provided data does not include enough detail to reconcile timing, attribution, or "
    "business-rule differences."
)


def _num(v) -> str:
    """Readable raw number: thousands for big counts/sums, full precision for rates."""
    if v is None or pd.isna(v):
        return "n/a"
    v = float(v)
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) < 1:
        return f"{v:.6f}"
    return f"{v:g}"


def _basis_note(mdef: MetricDefinition) -> str:
    """Short, business-friendly sourcing note for the overview header."""
    v = mdef.variants[0]
    if v.kind == "additive":
        return "reported from the dataset"
    if v.provided_rate_kpi:
        return "reported rate"
    return "calculated rate"


def _raw_used(variant: MetricVariant, pre_post: str) -> list[tuple[str, str]]:
    """Business field names (profile-resolved) that support this variant, with their role."""
    if variant.kind == "additive":
        return [(resolve(variant.source_kpi, pre_post), "source")]
    used: list[tuple[str, str]] = []
    if variant.provided_rate_kpi:
        used.append((resolve(variant.provided_rate_kpi, pre_post), "reported rate"))
    used.append((resolve(variant.numerator_kpi, pre_post), "numerator"))
    used.append((resolve(variant.denominator_kpi, pre_post), "denominator"))
    return used


def build_merchant_tools(repo: MetricsRepository, merchant_id: str) -> list[StructuredTool]:
    """Build the LLM tool set, scoped to one merchant. No tool exposes ``merchant_id``."""

    def get_profile() -> str:
        """Return the selected merchant's profile (name, authorization stage, structure)."""
        p = repo.get_profile(merchant_id)
        if p is None:
            return "Unknown merchant."
        return (f"{p['merchant_name']} — {p['pre_or_post']} authorization, "
                f"{p['business_structure']} account.")

    def get_merchant_facts() -> str:
        """Return ALL of the selected merchant's KPI facts: every monthly and quarterly value,
        for both the count and amount-weighted (sum) variants where they exist. Use this to
        answer ANY question about a specific month, quarter, trend, or comparison — the full
        time series is here, not just highlights. (Strategic merchants have both count and
        amount-weighted views; non-Strategic merchants have only count.)"""
        monthly = repo.get_monthly_facts(merchant_id)
        quarterly = repo.get_quarterly_facts(merchant_id)
        if monthly.empty:
            return "No facts available for this merchant."

        def series(df: pd.DataFrame, key: str) -> str:
            df = df.sort_values(key)
            return "; ".join(f"{r[key]}={format_value(unit, r['value'])}"
                             for _, r in df.iterrows())

        blocks: list[str] = []
        for mdef in METRIC_REGISTRY:
            unit = "count" if mdef.id == "submission_volume" else "rate"
            lines = [f"{mdef.name} (unit: {unit}; {_basis_note(mdef)}):"]
            for variant, label in (("cnt", "count"), ("sum", "amount-weighted")):
                m = monthly[(monthly["metric_id"] == mdef.id) & (monthly["variant"] == variant)]
                if m.empty:  # sum is absent for non-Strategic merchants
                    continue
                q = quarterly[(quarterly["metric_id"] == mdef.id) & (quarterly["variant"] == variant)]
                lines.append(f"  monthly [{label}]: {series(m, 'period')}")
                if not q.empty:
                    lines.append(f"  quarterly [{label}]: {series(q, 'quarter')}")
            blocks.append("\n".join(lines))
        return "\n".join(blocks)

    def get_calculation_details(metric_id: str, period: str) -> str:
        """Explain a KPI's methodology for ONE month (e.g. period '2026-05'), in
        business-friendly terms. Use this for "how is this calculated", "methodology",
        "supporting data", or "show the numerator/denominator". Returns the reported KPI value
        and its supporting business components (numerator, denominator, source field names) —
        selected by the merchant's profile (Pre vs Post fields; count, plus amount-weighted for
        Strategic). Explain the methodology and components; do not recompute the metric yourself.
        """
        mdef = _METRICS.get(metric_id)
        if mdef is None:
            return f"Unknown metric_id. Valid options: {', '.join(_METRICS)}."
        profile = repo.get_profile(merchant_id)
        if profile is None:
            return "Unknown merchant."
        pre_post = profile["pre_or_post"]

        monthly = repo.get_monthly_facts(merchant_id)
        rows = monthly[(monthly["metric_id"] == metric_id) & (monthly["period"] == period)]
        if rows.empty:
            avail = sorted(monthly["period"].unique().tolist())
            return f"No facts for {metric_id} in {period}. Available periods: {', '.join(avail)}."

        mp = repo.get_measures(merchant_id)
        wide = dict(zip(mp[mp["period"] == period]["kpi_name"], mp[mp["period"] == period]["value"]))
        unit = "count" if mdef.id == "submission_volume" else "rate"
        variant_by_suffix = {v.suffix: v for v in mdef.variants}

        out = [f"{mdef.name} — {period} — {profile['merchant_name']} "
               f"({pre_post} authorization, {profile['business_structure']} account)"]
        for label, suffix in (("count", "cnt"), ("amount-weighted", "sum")):
            r = rows[rows["variant"] == suffix]
            if r.empty:  # sum absent for non-Strategic merchants
                continue
            r = r.iloc[0]
            variant = variant_by_suffix[suffix]
            by_role = {role: (name, wide.get(name)) for name, role in _raw_used(variant, pre_post)}
            basis = "count-based" if suffix == "cnt" else "amount-weighted"
            reported = format_value(unit, r["value"])

            out.append(f"\n[{label}]")
            out.append(f"  Reported value: {reported}")
            out.append(f"  Business definition: {_BUSINESS_DEFINITION[mdef.id]}.")
            if variant.kind == "additive":
                name, val = by_role["source"]
                out.append(f"  Source field: {name} = {_num(val)} "
                           "(reported directly from the merchant performance dataset).")
            elif variant.provided_rate_kpi:
                # Reported rate is the source of truth; components are supporting context only —
                # do NOT present "numerator / denominator = reported value" (it won't reconcile).
                nname, nval = by_role["numerator"]
                dname, dval = by_role["denominator"]
                out.append(f"  Reported {basis} rate: {reported}.")
                out.append(f"  Supporting components: numerator {nname} ({_num(nval)}) "
                           f"and denominator {dname} ({_num(dval)}).")
            else:  # computed-only: the equation IS the value
                nname, nval = by_role["numerator"]
                dname, dval = by_role["denominator"]
                out.append(f"  Calculation: {nname} ({_num(nval)}) ÷ "
                           f"{dname} ({_num(dval)}) = {reported}.")
        out.append("\nNote: all figures above are for the requested period only.")
        return "\n".join(out)

    def explain_reconciliation() -> str:
        """Use ONLY when the merchant explicitly asks why the supporting numerator/denominator
        components do not exactly add up to / reconcile with the reported KPI value."""
        return RECONCILIATION_NOTE

    def get_evidence() -> str:
        """Return the selected merchant's evidence events (month + event)."""
        ev = repo.get_evidence(merchant_id).sort_values("period")
        if ev.empty:
            return "No evidence events recorded."
        return "\n".join(f"{r.period}: {r.event}" for r in ev.itertuples(index=False))

    return [
        StructuredTool.from_function(get_merchant_facts),
        StructuredTool.from_function(get_calculation_details),
        StructuredTool.from_function(explain_reconciliation),
        StructuredTool.from_function(get_evidence),
        StructuredTool.from_function(get_profile),
    ]
