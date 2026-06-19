"""Quarterly rollup of monthly KPI facts — consistent with the monthly source of truth.

Ratio metrics are **volume-weighted** by the monthly denominator, never naively
averaged: ``value = Σ(monthly value · denom) / Σ(denom)``. For a computed basis this
equals ``Σ(numerator)/Σ(denominator)``, so one rule serves both provided and computed.
Additive metrics sum. Output schema matches ``kpi_facts_monthly`` (``FACT_COLUMNS``),
with ``period`` carrying the quarter label.
"""
from __future__ import annotations

import math

import pandas as pd

from src.config import settings
from src.metrics.engine import FACT_COLUMNS

_GROUP_KEYS = ["merchant_id", "quarter", "metric_id", "metric_name", "variant"]
_FLAGGED = {"mismatch", "missing_components"}


def _weighted(values: pd.Series, weights: pd.Series) -> float | None:
    mask = values.notna() & weights.notna()
    w = weights[mask].sum()
    if w == 0:
        return None
    return float((values[mask] * weights[mask]).sum()) / float(w)


def _rollup_group(g: pd.DataFrame, tolerance: float) -> dict:
    first = g.iloc[0]
    row = {c: None for c in FACT_COLUMNS}
    row.update(
        merchant_id=first.merchant_id,
        period=first.quarter,  # quarterly facts key off the quarter label
        quarter=first.quarter,
        metric_id=first.metric_id,
        metric_name=first.metric_name,
        variant=first.variant,
    )
    flagged_month = bool(g["validation_status"].isin(_FLAGGED).any())

    # Additive: just sum the monthly values.
    if (g["value_source"] == "additive").all():
        row["value"] = float(g["value"].sum())
        row["value_source"] = "additive"
        row["validation_status"] = "additive"
        return row

    sum_num = g["numerator"].sum(min_count=1)
    sum_denom = g["denominator"].sum(min_count=1)
    sum_num = None if pd.isna(sum_num) else float(sum_num)
    sum_denom = None if pd.isna(sum_denom) else float(sum_denom)
    rolled_computed = sum_num / sum_denom if sum_num is not None and sum_denom not in (None, 0) else None
    row["numerator"] = sum_num
    row["denominator"] = sum_denom
    row["computed_value"] = rolled_computed

    has_provided = g["provided_value"].notna().any()
    if not has_provided:
        # Computed-only basis (e.g. Effective Fraud).
        row["value"] = rolled_computed
        row["value_source"] = "computed"
        base = "computed_only" if rolled_computed is not None else "missing_components"
        row["validation_status"] = _finalize(base, flagged_month)
        return row

    # Provided-rate basis: volume-weighted provided is the source of truth.
    rolled_provided = _weighted(g["provided_value"], g["denominator"])
    row["value"] = rolled_provided
    row["value_source"] = "provided"
    row["provided_value"] = rolled_provided
    base = _rate_status(rolled_provided, rolled_computed, tolerance)
    row["validation_status"] = _finalize(base, flagged_month)
    if base != "missing_components" and rolled_computed is not None and rolled_provided is not None:
        abs_diff = abs(rolled_provided - rolled_computed)
        row["abs_diff"] = abs_diff
        row["rel_diff_pct"] = (abs_diff / abs(rolled_provided) * 100) if rolled_provided != 0 else math.inf
    return row


def _rate_status(provided: float | None, computed: float | None, tolerance: float) -> str:
    if provided is None or computed is None:
        return "missing_components"
    if provided == 0:
        return "ok" if computed == 0 else "mismatch"
    rel = abs(provided - computed) / abs(provided)
    return "mismatch" if rel > tolerance else "ok"


def _finalize(base: str, flagged_month: bool) -> str:
    """A clean quarter that hides a flagged month is surfaced as such."""
    if base in {"ok", "computed_only"} and flagged_month:
        return "contains_flagged_month"
    return base


def compute_quarterly_facts(
    monthly: pd.DataFrame,
    tolerance: float = settings.RATE_MISMATCH_TOLERANCE,
) -> pd.DataFrame:
    """Roll ``kpi_facts_monthly`` up to ``kpi_facts_quarterly`` (same columns)."""
    if monthly.empty:
        return pd.DataFrame(columns=FACT_COLUMNS)
    rows = [
        _rollup_group(g, tolerance)
        for _, g in monthly.groupby(_GROUP_KEYS, sort=True)
    ]
    return pd.DataFrame(rows, columns=FACT_COLUMNS)
