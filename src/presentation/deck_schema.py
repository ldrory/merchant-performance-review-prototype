"""Deck content model + insight builders (pure, no LLM, no chart I/O).

Turns the merchant-scoped fact tables into a structured ``DeckModel`` — every number,
delta and trend the deck needs, computed in Python. The LLM later narrates this model
but never recomputes it. These are Pydantic *contracts* (one per-merchant aggregate),
not per-row wrappers.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from pydantic import BaseModel

from src.metrics.quality import summarize_metric_quality
from src.metrics.registry import METRIC_REGISTRY, MetricDefinition
from src.repositories.metrics_repository import MetricsRepository


def format_value(unit: str, value: Optional[float]) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    if unit == "rate":
        return f"{value * 100:.2f}%"
    return f"{value:,.0f}"


def format_amount(metric_id: str, unit: str, value: Optional[float]) -> str:
    """Like format_value, but prefixes '$' for submission_volume's amount (dollar) view."""
    s = format_value(unit, value)
    if metric_id == "submission_volume" and value is not None and not pd.isna(value):
        return f"${s}"
    return s


class VariantInsight(BaseModel):
    """One variant's (count or amount-weighted) series + headline summary. Non-recursive."""
    unit: str  # "rate" | "count"
    monthly_periods: list[str]
    monthly_values: list[float]
    quarterly_periods: list[str]
    quarterly_values: list[float]
    first_period: Optional[str] = None
    first_value: Optional[float] = None
    latest_period: Optional[str] = None
    latest_value: Optional[float] = None
    change_pct: Optional[float] = None


class KpiInsight(BaseModel):
    metric_id: str
    metric_name: str
    unit: str  # "rate" | "count"  (the count/primary view)
    higher_is_better: Optional[bool]

    monthly_periods: list[str]
    monthly_values: list[float]
    quarterly_periods: list[str]
    quarterly_values: list[float]

    first_period: Optional[str] = None
    first_value: Optional[float] = None
    latest_period: Optional[str] = None
    latest_value: Optional[float] = None
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    best_period: Optional[str] = None
    best_value: Optional[float] = None
    worst_period: Optional[str] = None
    worst_value: Optional[float] = None
    improving: Optional[bool] = None  # None = neutral metric

    # Amount-weighted (sum) view — present only for Strategic merchants.
    amount: Optional[VariantInsight] = None


class EvidenceItem(BaseModel):
    period: str
    event: str


class DeckModel(BaseModel):
    merchant_id: str
    merchant_name: str
    pre_or_post: str
    business_structure: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    kpis: list[KpiInsight]
    evidence: list[EvidenceItem]
    data_quality: list[str]


def _unit_for(metric_id: str) -> str:
    return "count" if metric_id == "submission_volume" else "rate"


def build_variant_insight(
    unit: str, monthly: pd.DataFrame, quarterly: pd.DataFrame
) -> VariantInsight:
    """Series + headline summary for one variant (count or amount-weighted)."""
    m = monthly.sort_values("period")
    q = quarterly.sort_values("quarter")
    periods = m["period"].tolist()
    values = [float(v) for v in m["value"].tolist()]

    vi = VariantInsight(
        unit=unit,
        monthly_periods=periods,
        monthly_values=values,
        quarterly_periods=q["quarter"].tolist(),
        quarterly_values=[float(v) for v in q["value"].tolist()],
    )
    if values:
        vi.first_period, vi.first_value = periods[0], values[0]
        vi.latest_period, vi.latest_value = periods[-1], values[-1]
        vi.change_pct = (values[-1] / values[0] - 1) * 100 if values[0] else None
    return vi


def build_kpi_insight(
    mdef: MetricDefinition, monthly: pd.DataFrame, quarterly: pd.DataFrame
) -> KpiInsight:
    """Compute one KPI's insight from its (cnt-variant) monthly + quarterly rows."""
    unit = _unit_for(mdef.id)
    v = build_variant_insight(unit, monthly, quarterly)

    insight = KpiInsight(
        metric_id=mdef.id,
        metric_name=mdef.name,
        unit=unit,
        higher_is_better=mdef.higher_is_better,
        monthly_periods=v.monthly_periods,
        monthly_values=v.monthly_values,
        quarterly_periods=v.quarterly_periods,
        quarterly_values=v.quarterly_values,
        first_period=v.first_period,
        first_value=v.first_value,
        latest_period=v.latest_period,
        latest_value=v.latest_value,
        change_pct=v.change_pct,
    )
    values, periods = v.monthly_values, v.monthly_periods
    if not values:
        return insight

    insight.change_abs = values[-1] - values[0]
    best_i = max(range(len(values)), key=lambda i: values[i])
    worst_i = min(range(len(values)), key=lambda i: values[i])
    insight.best_period, insight.best_value = periods[best_i], values[best_i]
    insight.worst_period, insight.worst_value = periods[worst_i], values[worst_i]

    if mdef.higher_is_better is not None:
        going_up = values[-1] >= values[0]
        insight.improving = going_up == mdef.higher_is_better
    return insight


def build_deck_model(repo: MetricsRepository, merchant_id: str) -> DeckModel:
    """Assemble the full per-merchant deck model from the scoped fact tables."""
    profile = repo.get_profile(merchant_id)
    if profile is None:
        raise ValueError(f"unknown merchant_id: {merchant_id!r}")

    monthly = repo.get_monthly_facts(merchant_id)
    quarterly = repo.get_quarterly_facts(merchant_id)
    evidence_df = repo.get_evidence(merchant_id)

    kpis: list[KpiInsight] = []
    for mdef in METRIC_REGISTRY:
        m = monthly[(monthly["metric_id"] == mdef.id) & (monthly["variant"] == "cnt")]
        q = quarterly[(quarterly["metric_id"] == mdef.id) & (quarterly["variant"] == "cnt")]
        insight = build_kpi_insight(mdef, m, q)

        # Amount-weighted (sum) view exists only for Strategic merchants.
        m_sum = monthly[(monthly["metric_id"] == mdef.id) & (monthly["variant"] == "sum")]
        if not m_sum.empty:
            q_sum = quarterly[(quarterly["metric_id"] == mdef.id) & (quarterly["variant"] == "sum")]
            insight.amount = build_variant_insight(_unit_for(mdef.id), m_sum, q_sum)
        kpis.append(insight)

    periods = sorted(monthly["period"].unique().tolist()) if not monthly.empty else []
    evidence = [
        EvidenceItem(period=r.period, event=r.event)
        for r in evidence_df.sort_values("period").itertuples(index=False)
    ]

    return DeckModel(
        merchant_id=merchant_id,
        merchant_name=profile["merchant_name"],
        pre_or_post=profile["pre_or_post"],
        business_structure=profile["business_structure"],
        period_start=periods[0] if periods else None,
        period_end=periods[-1] if periods else None,
        kpis=kpis,
        evidence=evidence,
        data_quality=summarize_metric_quality(monthly),
    )
