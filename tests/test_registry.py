"""The registry uses Pydantic to enforce metric-shape invariants at definition time."""
import pytest
from pydantic import ValidationError

from src.metrics.registry import (
    METRIC_REGISTRY,
    MetricVariant,
    required_raw_kpi_names,
    resolve,
)


def test_additive_variant_requires_source_kpi():
    with pytest.raises(ValidationError):
        MetricVariant(suffix="cnt", kind="additive")


def test_ratio_variant_requires_numerator_and_denominator():
    with pytest.raises(ValidationError):
        MetricVariant(suffix="cnt", kind="ratio", numerator_kpi="A")


def test_additive_variant_rejects_ratio_fields():
    with pytest.raises(ValidationError):
        MetricVariant(suffix="cnt", kind="additive", source_kpi="X", numerator_kpi="A")


def test_resolve_fills_prefix():
    assert resolve("CHBG {prefix} Auth Approved Cnt", "Post") == "CHBG Post Auth Approved Cnt"
    assert resolve(None, "Post") is None


def test_registry_has_expected_metrics():
    ids = {m.id for m in METRIC_REGISTRY}
    assert ids == {
        "submission_volume",
        "approval_rate",
        "accepted_chargeback_rate",
        "effective_fraud_rate",
    }


def test_higher_is_better_direction_per_metric():
    by_id = {m.id: m for m in METRIC_REGISTRY}
    assert by_id["approval_rate"].higher_is_better is True
    assert by_id["accepted_chargeback_rate"].higher_is_better is False
    assert by_id["effective_fraud_rate"].higher_is_better is False
    assert by_id["submission_volume"].higher_is_better is None


def test_required_raw_kpi_names_expands_prefixes_to_16():
    names = required_raw_kpi_names()
    assert len(names) == 16
    assert "Pre Auth Approval Rate Cnt" in names
    assert "Post Auth Approval Rate Cnt" in names
    assert "Submitted Sum" in names
