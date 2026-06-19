"""Quarterly rollups on synthetic monthly-fact fixtures.

Key property under test: ratio metrics are **volume-weighted**, never naively
averaged across months.
"""
import pandas as pd

from src.metrics.engine import FACT_COLUMNS
from src.metrics.quarterly import compute_quarterly_facts


def _monthly_row(**overrides):
    row = {c: None for c in FACT_COLUMNS}
    row.update(merchant_id="acme", quarter="2025-Q3")
    row.update(overrides)
    return row


def _df(rows):
    return pd.DataFrame(rows, columns=FACT_COLUMNS)


def _one(facts, metric_id, variant="cnt"):
    sub = facts[(facts.metric_id == metric_id) & (facts.variant == variant)]
    assert len(sub) == 1
    return sub.iloc[0]


def test_ratio_rollup_is_volume_weighted_not_naive_mean():
    # m1: rate 0.10 on 100 orders; m2: rate 0.20 on 900 orders.
    # naive mean = 0.15; volume-weighted = (0.10*100 + 0.20*900)/1000 = 0.19
    monthly = _df([
        _monthly_row(period="2025-07", metric_id="accepted_chargeback_rate", metric_name="Accepted Chargeback Rate",
                     variant="cnt", value=0.10, value_source="provided", provided_value=0.10,
                     computed_value=0.10, numerator=10, denominator=100, validation_status="ok"),
        _monthly_row(period="2025-08", metric_id="accepted_chargeback_rate", metric_name="Accepted Chargeback Rate",
                     variant="cnt", value=0.20, value_source="provided", provided_value=0.20,
                     computed_value=0.20, numerator=180, denominator=900, validation_status="ok"),
    ])
    q = compute_quarterly_facts(monthly)
    row = _one(q, "accepted_chargeback_rate")
    assert round(row.value, 6) == 0.19
    assert row.value_source == "provided"
    assert row.numerator == 190
    assert row.denominator == 1000


def test_computed_basis_equals_sum_num_over_sum_denom():
    monthly = _df([
        _monthly_row(period="2025-07", metric_id="effective_fraud_rate", metric_name="Effective Fraud Rate",
                     variant="cnt", value=0.10, value_source="computed",
                     computed_value=0.10, numerator=10, denominator=100, validation_status="computed_only"),
        _monthly_row(period="2025-08", metric_id="effective_fraud_rate", metric_name="Effective Fraud Rate",
                     variant="cnt", value=0.20, value_source="computed",
                     computed_value=0.20, numerator=180, denominator=900, validation_status="computed_only"),
    ])
    q = compute_quarterly_facts(monthly)
    row = _one(q, "effective_fraud_rate")
    assert round(row.value, 6) == 0.19  # 190 / 1000
    assert row.value_source == "computed"
    assert row.validation_status == "computed_only"


def test_additive_rollup_is_sum():
    monthly = _df([
        _monthly_row(period="2025-07", metric_id="submission_volume", metric_name="Submission Volume",
                     variant="cnt", value=100, value_source="additive", validation_status="additive"),
        _monthly_row(period="2025-08", metric_id="submission_volume", metric_name="Submission Volume",
                     variant="cnt", value=900, value_source="additive", validation_status="additive"),
    ])
    q = compute_quarterly_facts(monthly)
    row = _one(q, "submission_volume")
    assert row.value == 1000
    assert row.value_source == "additive"
    assert row.validation_status == "additive"


def test_quarter_within_tolerance_but_flagged_month_marks_contains_flagged_month():
    # Quarter aggregate matches computed (ok), but one month was a mismatch.
    monthly = _df([
        _monthly_row(period="2025-07", metric_id="accepted_chargeback_rate", metric_name="Accepted Chargeback Rate",
                     variant="cnt", value=0.10, value_source="provided", provided_value=0.10,
                     computed_value=0.10, numerator=10, denominator=100, validation_status="ok"),
        _monthly_row(period="2025-08", metric_id="accepted_chargeback_rate", metric_name="Accepted Chargeback Rate",
                     variant="cnt", value=0.20, value_source="provided", provided_value=0.20,
                     computed_value=0.20, numerator=180, denominator=900, validation_status="mismatch"),
    ])
    q = compute_quarterly_facts(monthly)
    row = _one(q, "accepted_chargeback_rate")
    assert row.validation_status == "contains_flagged_month"


def test_quarter_level_mismatch_takes_precedence():
    # Aggregate provided (vol-weighted) diverges from aggregate computed -> mismatch.
    monthly = _df([
        _monthly_row(period="2025-07", metric_id="accepted_chargeback_rate", metric_name="Accepted Chargeback Rate",
                     variant="cnt", value=0.50, value_source="provided", provided_value=0.50,
                     computed_value=0.10, numerator=10, denominator=100, validation_status="mismatch"),
        _monthly_row(period="2025-08", metric_id="accepted_chargeback_rate", metric_name="Accepted Chargeback Rate",
                     variant="cnt", value=0.50, value_source="provided", provided_value=0.50,
                     computed_value=0.20, numerator=180, denominator=900, validation_status="mismatch"),
    ])
    q = compute_quarterly_facts(monthly)
    row = _one(q, "accepted_chargeback_rate")
    assert row.validation_status == "mismatch"


def test_separate_quarters_produce_separate_rows():
    monthly = _df([
        _monthly_row(period="2025-07", quarter="2025-Q3", metric_id="submission_volume",
                     metric_name="Submission Volume", variant="cnt", value=100,
                     value_source="additive", validation_status="additive"),
        _monthly_row(period="2025-10", quarter="2025-Q4", metric_id="submission_volume",
                     metric_name="Submission Volume", variant="cnt", value=300,
                     value_source="additive", validation_status="additive"),
    ])
    q = compute_quarterly_facts(monthly)
    assert set(q["quarter"]) == {"2025-Q3", "2025-Q4"}
    assert list(q.columns) == FACT_COLUMNS
    # period column carries the quarter label for quarterly facts
    assert set(q["period"]) == {"2025-Q3", "2025-Q4"}
