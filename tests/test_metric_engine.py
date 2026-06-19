"""Engine logic on small synthetic fixtures (hand-computed), not the real dataset."""
from typing import get_args

import pandas as pd
import pytest

from src.config.settings import slugify
from src.metrics.engine import FACT_COLUMNS, compute_monthly_facts, quarter_of
from src.models import ValidationStatus, ValueSource


def _merchants(rows):
    return pd.DataFrame(rows, columns=["merchant_id", "merchant_name", "pre_or_post", "business_structure"])


def _kpis(account, period, mapping):
    # merchant_id (slug) is the canonical key the engine groups/joins on.
    return pd.DataFrame(
        [(slugify(account), account, period, k, v) for k, v in mapping.items()],
        columns=["merchant_id", "account_name", "period", "kpi_name", "value"],
    )


# A complete single-month KPI bundle for one merchant.
def _full_bundle(merchant="ACME", period="2025-07", **overrides):
    base = {
        "Submitted Cnt": 1000.0,
        "Submitted Sum": 500000.0,
        "CHBG Pre Auth Approved Cnt": 950.0,
        "CHBG Pre Auth Approved Sum": 470000.0,
        "CHBG Post Auth Approved Cnt": 900.0,
        "CHBG Post Auth Approved Sum": 460000.0,
        "Pre Auth Approval Rate Cnt": 0.95,
        "Pre Auth Approval Rate Sum": 0.94,
        "Post Auth Approval Rate Cnt": 0.90,
        "Post Auth Approval Rate Sum": 0.92,
        "Accepted Chargebacks Rate Cnt": 0.01,
        "Accepted Chargebacks Rate Sum": 0.02,
        "Accepted Chargeback Cnt": 10.0,
        "Accepted Chargeback Sum": 10000.0,
        "Effective Fraud Cnt": 50.0,
        "Effective Fraud Sum": 25000.0,
    }
    base.update(overrides)
    return _kpis(merchant, period, base)


def _facts_by_variant(facts):
    """Index facts by (metric_id, variant) -> row dict for one merchant/period."""
    return {(r.metric_id, r.variant): r for r in facts.itertuples()}


def test_quarter_of_calendar_quarters():
    assert quarter_of("2025-07") == "2025-Q3"
    assert quarter_of("2025-12") == "2025-Q4"
    assert quarter_of("2026-01") == "2026-Q1"
    assert quarter_of("2026-06") == "2026-Q2"


def test_submission_volume_is_additive():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(), merchants)
    by = _facts_by_variant(facts)
    cnt = by[("submission_volume", "cnt")]
    assert cnt.value == 1000.0
    assert cnt.value_source == "additive"
    assert cnt.validation_status == "additive"


def test_approval_rate_uses_provided_value_and_post_prefix():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(), merchants)
    by = _facts_by_variant(facts)
    appr = by[("approval_rate", "cnt")]
    # Post merchant -> provided Post Auth Approval Rate Cnt = 0.90
    assert appr.value == 0.90
    assert appr.value_source == "provided"
    # numerator is the Post component (900 / 1000 = 0.90) -> within tolerance -> ok
    assert appr.numerator == 900.0
    assert appr.validation_status == "ok"


def test_approval_rate_pre_merchant_uses_pre_components():
    merchants = _merchants([("cyberdyne", "Cyberdyne", "Pre", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(merchant="Cyberdyne"), merchants)
    by = _facts_by_variant(facts)
    appr = by[("approval_rate", "cnt")]
    assert appr.value == 0.95  # Pre Auth Approval Rate Cnt
    assert appr.numerator == 950.0  # CHBG Pre Auth Approved Cnt


def test_accepted_chargeback_mismatch_flagged_but_provided_is_value():
    # provided 0.01 vs computed 10/1000 = 0.01 -> matches; make it diverge:
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(
        _full_bundle(**{"Accepted Chargebacks Rate Cnt": 0.05}), merchants
    )
    by = _facts_by_variant(facts)
    chbg = by[("accepted_chargeback_rate", "cnt")]
    assert chbg.value == 0.05  # provided is source of truth
    assert chbg.computed_value == 0.01  # 10 / 1000
    assert chbg.value_source == "provided"
    assert chbg.validation_status == "mismatch"


def test_accepted_chargeback_within_tolerance_is_ok():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(), merchants)  # provided 0.01 == 10/1000
    by = _facts_by_variant(facts)
    assert by[("accepted_chargeback_rate", "cnt")].validation_status == "ok"


def test_effective_fraud_is_computed_only():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(), merchants)
    by = _facts_by_variant(facts)
    eff = by[("effective_fraud_rate", "cnt")]
    assert eff.value == 0.05  # 50 / 1000
    assert eff.value_source == "computed"
    assert eff.validation_status == "computed_only"


def test_strategic_gets_sum_variants():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(), merchants)
    variants = {(r.metric_id, r.variant) for r in facts.itertuples()}
    assert ("submission_volume", "sum") in variants
    assert ("approval_rate", "sum") in variants


def test_enterprise_has_no_sum_variants():
    merchants = _merchants([("vandelay", "Vandelay", "Post", "Enterprise")])
    facts = compute_monthly_facts(_full_bundle(merchant="Vandelay"), merchants)
    suffixes = {r.variant for r in facts.itertuples()}
    assert suffixes == {"cnt"}


def test_missing_components_flagged():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    bundle = _full_bundle()
    # drop the Post approved component
    bundle = bundle[bundle["kpi_name"] != "CHBG Post Auth Approved Cnt"]
    facts = compute_monthly_facts(bundle, merchants)
    by = _facts_by_variant(facts)
    appr = by[("approval_rate", "cnt")]
    assert appr.value == 0.90  # still shows provided rate
    assert appr.validation_status == "missing_components"


def test_quarter_column_present():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(period="2026-01"), merchants)
    assert (facts["quarter"] == "2026-Q1").all()


def test_merchant_without_profile_is_skipped():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    bundle = _full_bundle(merchant="UnknownCo")
    facts = compute_monthly_facts(bundle, merchants)
    assert facts.empty


def test_facts_only_emit_contract_columns_and_values():
    merchants = _merchants([("acme", "ACME", "Post", "Strategic")])
    facts = compute_monthly_facts(_full_bundle(), merchants)
    assert list(facts.columns) == FACT_COLUMNS
    assert set(facts["value_source"]) <= set(get_args(ValueSource))
    assert set(facts["validation_status"]) <= set(get_args(ValidationStatus))
