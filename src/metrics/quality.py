"""Metric Quality (Layer 2) — checks on the *computed facts*, not the raw input.

Two distinct things, by design:
  * ``summarize_metric_quality`` — provided-vs-computed rate divergence. This is a
    **warning, never a blocker** (the provided rate is the displayed source of truth).
    Aggregated to one neutral line per metric — no row-level spam, no scary wording.
  * ``find_broken_metric_merchants`` — facts that could not be produced (missing
    components / uncomputable / invalid denominator). These are **errors**. Input
    validation already blocks these merchants before persistence, so this is a
    post-compute safety net: if anything is still broken the pipeline fails loudly.

Both read the fact table the engine emits. Single definition, reused by the pipeline
(ingest summary) and the deck (`deck_schema`).
"""
from __future__ import annotations

import pandas as pd

# A merchant is "metric-broken" if any monthly fact couldn't produce a value.
_BROKEN_STATUSES = {"missing_components"}


def summarize_metric_quality(facts: pd.DataFrame) -> list[str]:
    """One aggregated warning per metric whose provided rate diverges from components.

    Counts ``validation_status == 'mismatch'`` rows among provided-rate facts. Returns
    one plain-English line per affected metric (no row detail). Empty when nothing diverges.
    """
    if facts.empty:
        return []
    provided = facts[facts["value_source"] == "provided"]
    if provided.empty:
        return []

    notes: list[str] = []
    for metric_name, g in provided.groupby("metric_name", sort=True):
        n_mismatch = int((g["validation_status"] == "mismatch").sum())
        if n_mismatch:
            notes.append(
                f"{metric_name}: shown as the provided rate; it differs from the "
                f"order-derived value in {n_mismatch} of {len(g)} data points "
                f"(provided rate used as the source of truth)."
            )
    return notes


def find_broken_metric_merchants(facts: pd.DataFrame) -> dict[str, str]:
    """Merchants with structurally-broken facts → {merchant_id: reason}.

    Broken = any fact row whose ``value`` is null/NaN, or whose ``validation_status`` is
    ``missing_components`` (a required component/denominator was unusable). These are
    treated as errors upstream (the merchant is excluded; the run aborts if none remain).
    """
    if facts.empty:
        return {}
    broken_mask = facts["value"].isna() | facts["validation_status"].isin(_BROKEN_STATUSES)
    broken = facts[broken_mask]
    out: dict[str, str] = {}
    for mid, g in broken.groupby("merchant_id", sort=True):
        metrics = sorted(g["metric_id"].unique())
        out[mid] = f"uncomputable metric(s): {', '.join(metrics)}"
    return out
