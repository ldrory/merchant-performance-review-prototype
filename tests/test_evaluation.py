"""Deterministic narrative guardrails (no network, no LLM-judge)."""
from src.db.connection import get_connection
from src.ingestion.loaders import read_kpis, read_profiles, read_evidence
from src.llm.evaluation import (
    check_faithfulness,
    check_language,
    check_structure,
    evaluate_narrative,
    extract_numbers,
)
from src.llm.narrative_generator import NarrativeBundle
from src.metrics.registry import METRIC_REGISTRY
from src.pipeline import run_pipeline
from src.presentation.deck_schema import build_deck_model
from src.repositories.metrics_repository import MetricsRepository


def _deck():
    con = get_connection(":memory:")
    run_pipeline(con, read_kpis(), read_profiles(), read_evidence())
    return build_deck_model(MetricsRepository(con), "acme")


def _full_analysis(text="Solid performance this period."):
    return {m.id: text for m in METRIC_REGISTRY}


# --- extract_numbers ---

def test_extract_numbers_handles_percent_commas_signs():
    nums = extract_numbers("Approval 98.15% on 4,584 orders, up +6.4% from 96.84%.")
    assert 98.15 in nums and 4584 in nums and 6.4 in nums and 96.84 in nums


# --- faithfulness (coarse) ---

def test_faithfulness_passes_when_material_numbers_come_from_deck():
    deck = _deck()
    sv = next(k for k in deck.kpis if k.metric_id == "submission_volume")
    narrative = NarrativeBundle(
        executive_summary=[f"Submission volume reached {sv.latest_value:,.0f} orders."],
        kpi_analysis=_full_analysis(),
    )
    result = check_faithfulness(deck, narrative)
    assert result.ok and result.unsupported == []


def test_faithfulness_flags_gross_invented_material_number():
    deck = _deck()
    narrative = NarrativeBundle(
        executive_summary=["Submission volume hit 999,999 orders this period."],
        kpi_analysis=_full_analysis(),
    )
    result = check_faithfulness(deck, narrative)
    assert not result.ok
    assert any("999,999" in u or "999999" in u for u in result.unsupported)


def test_faithfulness_tolerates_years_small_counts_and_rounding():
    deck = _deck()
    # 2025/2026 = years; 3 = small count; 98.2 ≈ a rate (small magnitude) — none should flag.
    narrative = NarrativeBundle(
        executive_summary=["Across 2025-2026, all 3 evidence events were reviewed; approval ~98.2%."],
        kpi_analysis=_full_analysis(),
    )
    result = check_faithfulness(deck, narrative)
    assert result.ok, result.unsupported


# --- structure ---

def test_structure_flags_missing_kpi_and_empty_summary():
    deck = _deck()
    partial = {m.id: "x" for m in METRIC_REGISTRY if m.id != "effective_fraud_rate"}
    narrative = NarrativeBundle(executive_summary=[], kpi_analysis=partial)
    issues = check_structure(deck, narrative)
    assert any("executive summary" in i.lower() for i in issues)
    assert any("effective_fraud_rate" in i for i in issues)


def test_structure_passes_when_complete():
    deck = _deck()
    narrative = NarrativeBundle(executive_summary=["A point."], kpi_analysis=_full_analysis())
    assert check_structure(deck, narrative) == []


# --- language gate (customer-safe) ---

def test_language_flags_internal_qa_terms():
    for term in ["mismatch", "provided vs computed", "validation status",
                 "order-derived value", "the rate differs from the computed value",
                 "data quality issue"]:
        nb = NarrativeBundle(executive_summary=[term], kpi_analysis=_full_analysis())
        assert check_language(nb), f"should flag: {term}"


def test_language_flags_data_points_count_phrasing():
    nb = NarrativeBundle(
        executive_summary=["The rate differs in 23 of 24 data points."],
        kpi_analysis=_full_analysis(),
    )
    assert check_language(nb)


def test_language_flags_over_strong_causal_claims():
    for term in ["directly attributable", "models appropriately tightened",
                 "fraud environment normalized", "demonstrates model robustness"]:
        nb = NarrativeBundle(executive_summary=[f"This {term}."], kpi_analysis=_full_analysis())
        assert check_language(nb), f"should flag: {term}"


def test_language_passes_for_hedged_customer_safe_text():
    nb = NarrativeBundle(
        executive_summary=["The improvement coincides with the new ruleset and may indicate"
                           " a healthier approval trend."],
        kpi_analysis=_full_analysis("This is consistent with seasonal demand; it suggests stability."),
    )
    assert check_language(nb) == []


def test_evaluate_narrative_gates_on_language():
    deck = _deck()
    bad = NarrativeBundle(
        executive_summary=["Improvement is directly attributable to the model."],
        kpi_analysis=_full_analysis(),
    )
    report = evaluate_narrative(deck, bad)
    assert not report.ok and report.language_issues


# --- integration ---

def test_evaluate_narrative_combines_checks():
    deck = _deck()
    good = NarrativeBundle(executive_summary=["Solid quarter."], kpi_analysis=_full_analysis())
    report = evaluate_narrative(deck, good)
    assert report.ok
    assert report.structural_issues == [] and report.faithfulness.ok and report.language_issues == []

    bad = NarrativeBundle(executive_summary=[], kpi_analysis={"approval_rate": "x"})
    bad_report = evaluate_narrative(deck, bad)
    assert not bad_report.ok and bad_report.structural_issues
