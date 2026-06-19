"""Deck insight builders — pure delta/trend math on small synthetic fact frames."""
import pandas as pd

from src.db.connection import get_connection
from src.ingestion.loaders import read_kpis, read_profiles, read_evidence
from src.metrics.registry import METRIC_REGISTRY
from src.pipeline import run_pipeline
from src.presentation.deck_schema import build_deck_model, build_kpi_insight, format_value
from src.repositories.metrics_repository import MetricsRepository


def _mdef(metric_id):
    return {m.id: m for m in METRIC_REGISTRY}[metric_id]


def test_format_value():
    assert format_value("rate", 0.0345) == "3.45%"
    assert format_value("count", 4584.0) == "4,584"
    assert format_value("rate", None) == "n/a"


def test_insight_volume_deltas_neutral_direction():
    m = pd.DataFrame({"period": ["2025-07", "2025-08", "2025-09"], "value": [100.0, 150.0, 120.0]})
    q = pd.DataFrame({"quarter": ["2025-Q3"], "value": [370.0]})
    ins = build_kpi_insight(_mdef("submission_volume"), m, q)
    assert ins.unit == "count"
    assert ins.first_value == 100.0 and ins.latest_value == 120.0
    assert round(ins.change_pct, 1) == 20.0
    assert ins.best_period == "2025-08" and ins.best_value == 150.0
    assert ins.worst_period == "2025-07"
    assert ins.improving is None  # volume is neutral
    assert ins.monthly_periods == ["2025-07", "2025-08", "2025-09"]


def test_insight_rate_improving_when_up_and_higher_is_better():
    m = pd.DataFrame({"period": ["2025-07", "2025-08"], "value": [0.90, 0.95]})
    q = pd.DataFrame({"quarter": ["2025-Q3"], "value": [0.93]})
    ins = build_kpi_insight(_mdef("approval_rate"), m, q)
    assert ins.unit == "rate"
    assert ins.improving is True


def test_insight_fraud_rising_is_not_improving():
    m = pd.DataFrame({"period": ["2025-07", "2025-08"], "value": [0.01, 0.02]})
    q = pd.DataFrame({"quarter": ["2025-Q3"], "value": [0.015]})
    ins = build_kpi_insight(_mdef("effective_fraud_rate"), m, q)
    assert ins.improving is False  # up, but lower-is-better


# --- integration: build_deck_model from the real pipeline ---

def _repo_with_real_data():
    con = get_connection(":memory:")
    run_pipeline(con, read_kpis(), read_profiles(), read_evidence())
    return MetricsRepository(con)


def test_build_deck_model_has_profile_four_kpis_and_evidence():
    model = build_deck_model(_repo_with_real_data(), "acme")
    assert model.merchant_name == "ACME"
    assert model.business_structure == "Strategic"
    assert [k.metric_id for k in model.kpis] == [m.id for m in METRIC_REGISTRY]
    assert model.period_start == "2025-07" and model.period_end == "2026-06"
    assert len(model.evidence) == 3  # ACME has 3 evidence rows


def test_build_deck_model_flags_chargeback_data_quality():
    model = build_deck_model(_repo_with_real_data(), "acme")
    assert any("Accepted Chargeback Rate" in c for c in model.data_quality)


def test_build_deck_model_unknown_merchant_raises():
    import pytest
    with pytest.raises(ValueError):
        build_deck_model(_repo_with_real_data(), "ghost")


# --- amount-weighted view (Strategic) vs count-only (Enterprise) ---

def test_strategic_kpis_carry_amount_view_enterprise_does_not():
    acme = build_deck_model(_repo_with_real_data(), "acme")  # Strategic
    assert all(k.amount is not None for k in acme.kpis)
    a = next(k for k in acme.kpis if k.metric_id == "approval_rate").amount
    assert a.latest_value is not None and a.monthly_values  # populated series

    vandelay = build_deck_model(_repo_with_real_data(), "vandelay-industries")  # Enterprise
    assert all(k.amount is None for k in vandelay.kpis)


def test_deck_model_serializes_round_trip_with_amount():
    from src.presentation.deck_schema import DeckModel
    model = build_deck_model(_repo_with_real_data(), "acme")
    again = DeckModel(**model.model_dump())  # round-trips (nested VariantInsight included)
    assert again.merchant_id == "acme"
    assert again.kpis[0].amount is not None
    assert "amount" in model.model_dump_json()


def test_profile_drives_variants_per_merchant():
    """Profile → which views exist. (Pre/Post measure selection is verified at the value
    level in test_tenant_isolation; here we assert the deck-model shape per profile.)"""
    repo = _repo_with_real_data()
    acme = build_deck_model(repo, "acme")
    assert (acme.pre_or_post, acme.business_structure) == ("Post", "Strategic")
    assert all(k.amount is not None for k in acme.kpis)  # count + amount-weighted

    cyber = build_deck_model(repo, "cyberdyne-systems")
    assert (cyber.pre_or_post, cyber.business_structure) == ("Pre", "Strategic")
    assert all(k.amount is not None for k in cyber.kpis)  # count + amount-weighted

    vandelay = build_deck_model(repo, "vandelay-industries")
    assert (vandelay.pre_or_post, vandelay.business_structure) == ("Post", "Enterprise")
    assert all(k.amount is None for k in vandelay.kpis)  # count only
