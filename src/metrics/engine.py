"""Metric engine: turns raw KPI rows + merchant profiles into monthly KPI facts.

Tabular in, tabular out — the engine consumes DataFrames and returns the
``kpi_facts_monthly`` DataFrame. It builds a ``list[dict]`` while iterating the
small per-merchant/period groups (fine for this scale) and materializes one
DataFrame at the end; no per-row object wrapping.

Source-of-truth policy (decided against the real data):
  * additive metrics            -> value = the raw measure
  * ratio metrics WITH a provided rate (Approval, Accepted Chargeback)
                                -> value = provided rate; components computed for validation
  * ratio metrics WITHOUT one (Effective Fraud)
                                -> value = computed numerator/denominator

The LLM never does arithmetic — every displayed number originates here.
``value_source`` and ``validation_status`` values are constrained by the Literal
aliases in ``src.models`` (the single source of truth for those categories).
"""
from __future__ import annotations

import math

import pandas as pd

from src.config import settings
from src.metrics.registry import METRIC_REGISTRY, resolve

# Single source of truth for the fact-table column set (DuckDB schema + tests reference this).
FACT_COLUMNS = [
    "merchant_id", "period", "quarter", "metric_id", "metric_name", "variant",
    "value", "value_source", "provided_value", "computed_value",
    "numerator", "denominator", "abs_diff", "rel_diff_pct", "validation_status",
]


def quarter_of(period: str) -> str:
    """Calendar quarter label, e.g. '2025-07' -> '2025-Q3'."""
    year, month = period.split("-")
    q = (int(month) - 1) // 3 + 1
    return f"{year}-Q{q}"


def _clean(value) -> float | None:
    """Normalize missing/NaN measures to None before any arithmetic."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return float(value)


def _safe_ratio(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _rate_status(provided: float, computed: float | None, tolerance: float):
    """Return (abs_diff, rel_diff_pct, validation_status) for a provided rate."""
    if computed is None:
        return None, None, "missing_components"
    abs_diff = abs(provided - computed)
    if provided == 0:
        rel_pct = 0.0 if computed == 0 else math.inf
    else:
        rel_pct = abs_diff / abs(provided) * 100
    status = "mismatch" if rel_pct / 100 > tolerance else "ok"
    return abs_diff, rel_pct, status


def _variant_row(merchant, period, mdef, variant, wide, tolerance) -> dict:
    pre_post = merchant.pre_or_post
    row = {c: None for c in FACT_COLUMNS}
    row.update(
        merchant_id=merchant.merchant_id,
        period=period,
        quarter=quarter_of(period),
        metric_id=mdef.id,
        metric_name=mdef.name,
        variant=variant.suffix,
    )

    if variant.kind == "additive":
        row["value"] = _clean(wide.get(resolve(variant.source_kpi, pre_post)))
        row["value_source"] = "additive"
        row["validation_status"] = "additive"
        return row

    # ratio
    num = _clean(wide.get(resolve(variant.numerator_kpi, pre_post)))
    denom = _clean(wide.get(resolve(variant.denominator_kpi, pre_post)))
    computed = _safe_ratio(num, denom)
    row["numerator"] = num
    row["denominator"] = denom
    row["computed_value"] = computed

    if variant.provided_rate_kpi is None:
        # No provided rate (Effective Fraud) -> computed is the displayed value.
        row["value"] = computed
        row["value_source"] = "computed"
        row["validation_status"] = "computed_only" if computed is not None else "missing_components"
        return row

    provided = _clean(wide.get(resolve(variant.provided_rate_kpi, pre_post)))
    row["provided_value"] = provided
    if provided is not None:
        # Provided rate is the source of truth; components validate it.
        row["value"] = provided
        row["value_source"] = "provided"
        abs_diff, rel_pct, status = _rate_status(provided, computed, tolerance)
        row["abs_diff"], row["rel_diff_pct"], row["validation_status"] = abs_diff, rel_pct, status
    else:
        # Provided slot exists but value is missing -> best-effort display via computed.
        row["value"] = computed
        row["value_source"] = "computed"
        row["validation_status"] = "missing_components"
    return row


def compute_monthly_facts(
    measures: pd.DataFrame,
    merchants: pd.DataFrame,
    tolerance: float = settings.RATE_MISMATCH_TOLERANCE,
) -> pd.DataFrame:
    """Compute ``kpi_facts_monthly`` from the KPI measures + the merchants dimension.

    ``measures``: merchant_id, account_name, period, kpi_name, value
    ``merchants``: merchant_id, merchant_name, pre_or_post, business_structure
    ``merchant_id`` is the canonical key; measures whose merchant_id has no profile are skipped.
    """
    profile_by_id = {m.merchant_id: m for m in merchants.itertuples(index=False)}

    rows: list[dict] = []
    for (merchant_id, period), g in measures.groupby(["merchant_id", "period"], sort=True):
        merchant = profile_by_id.get(merchant_id)
        if merchant is None:
            continue
        wide = dict(zip(g["kpi_name"], g["value"]))
        is_strategic = merchant.business_structure == "Strategic"
        for mdef in METRIC_REGISTRY:
            for variant in mdef.variants:
                if variant.strategic_only and not is_strategic:
                    continue
                rows.append(_variant_row(merchant, period, mdef, variant, wide, tolerance))

    return pd.DataFrame(rows, columns=FACT_COLUMNS)
