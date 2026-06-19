"""Metric Quality layer: provided-vs-computed caveat + broken-fact detection."""
import pandas as pd

from src.metrics.engine import FACT_COLUMNS
from src.metrics.quality import find_broken_metric_merchants, summarize_metric_quality


def _facts(rows):
    return pd.DataFrame(rows, columns=FACT_COLUMNS)


def _row(**overrides):
    row = {c: None for c in FACT_COLUMNS}
    row.update(
        merchant_id="acme", period="2025-07", quarter="2025-Q3",
        metric_id="accepted_chargeback_rate", metric_name="Accepted Chargeback Rate",
        variant="cnt", value=0.01, value_source="provided", validation_status="ok",
    )
    row.update(overrides)
    return row


# --- summarize_metric_quality (caveat) ---

def test_summary_flags_mismatched_metric_with_counts():
    facts = _facts([
        _row(period="2025-07", validation_status="mismatch"),
        _row(period="2025-08", validation_status="mismatch"),
        _row(period="2025-09", validation_status="ok"),
    ])
    notes = summarize_metric_quality(facts)
    assert len(notes) == 1
    assert "Accepted Chargeback Rate" in notes[0]
    assert "2 of 3" in notes[0]


def test_summary_empty_when_all_ok():
    facts = _facts([_row(validation_status="ok"), _row(period="2025-08", validation_status="ok")])
    assert summarize_metric_quality(facts) == []


def test_summary_ignores_computed_only_metrics():
    # Effective Fraud is computed (no provided rate) -> never a provided-vs-computed caveat.
    facts = _facts([_row(metric_id="effective_fraud_rate", value_source="computed",
                         validation_status="computed_only")])
    assert summarize_metric_quality(facts) == []


# --- find_broken_metric_merchants (error) ---

def test_broken_detected_on_missing_components():
    facts = _facts([
        _row(merchant_id="acme", validation_status="ok"),
        _row(merchant_id="ghost", validation_status="missing_components"),
    ])
    broken = find_broken_metric_merchants(facts)
    assert set(broken) == {"ghost"}


def test_broken_detected_on_null_value():
    facts = _facts([_row(merchant_id="ghost", value=None, value_source="computed",
                         validation_status="computed_only")])
    assert "ghost" in find_broken_metric_merchants(facts)


def test_no_broken_when_clean():
    facts = _facts([_row(validation_status="ok")])
    assert find_broken_metric_merchants(facts) == {}
