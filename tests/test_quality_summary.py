"""Per-process quality summaries (consistent schema, layers that actually ran)."""
import pandas as pd

from src.metrics.engine import FACT_COLUMNS
from src.models import ValidationIssue, ValidationReport
from src.quality_summary import (
    NarrativeResult,
    consolidated_summary,
    deck_summary,
    ingest_summary,
    overall_status,
)


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


def _by_layer(summary):
    return {l.layer: l for l in summary.layers}


# --- ingest_summary: only the layers that ran ---

def test_ingest_success_has_layers_1_2_3():
    s = ingest_summary("v1", ValidationReport(), _facts([_row()]),
                       validation_complete=True, facts_computed=True)
    assert s.stage == "ingest"
    assert [l.layer for l in s.layers] == [1, 2, 3]
    assert s.overall_status == "PASS"


def test_ingest_missing_columns_has_only_layer_1():
    report = ValidationReport(issues=[
        ValidationIssue(severity="error", code="missing_columns", message="kpis: missing [value]"),
    ])
    s = ingest_summary("v1", report, None, validation_complete=False, facts_computed=False)
    assert [l.layer for l in s.layers] == [1]  # later layers did not run — not faked
    assert s.overall_status == "FAIL"


def test_ingest_no_valid_merchants_has_layers_1_2_not_3():
    report = ValidationReport(issues=[
        ValidationIssue(severity="error", code="zero_denominator", merchant_id="acme",
                        message="denominator is 0"),
    ])
    s = ingest_summary("v1", report, None, validation_complete=True, facts_computed=False)
    by = _by_layer(s)
    assert set(by) == {1, 2}  # facts never computed -> no Layer 3
    assert by[2].status == "FAIL"
    assert s.overall_status == "FAIL"


def test_layer3_is_a_nonblocking_note():
    facts = _facts([_row(validation_status="mismatch"), _row(period="2025-08", validation_status="ok")])
    s = ingest_summary("v1", ValidationReport(), facts, validation_complete=True, facts_computed=True)
    by = _by_layer(s)
    assert by[3].type == "note" and by[3].blocking is False and by[3].status == "WARN"
    assert s.overall_status == "WARN"  # a note never escalates to FAIL


# --- deck_summary + consolidated ---

def test_deck_summary_is_layer_4():
    s = deck_summary("v1", [NarrativeResult(merchant_id="acme", ok=True)])
    assert s.stage == "decks"
    assert [l.layer for l in s.layers] == [4]
    assert s.overall_status == "PASS"


def test_consolidated_merges_ingest_and_deck_layers():
    ing = ingest_summary("v1", ValidationReport(), _facts([_row()]),
                         validation_complete=True, facts_computed=True)
    deck = deck_summary("v1", [NarrativeResult(merchant_id="acme", ok=True)])
    s = consolidated_summary("v1", ing, deck)
    assert s.stage == "consolidated"
    assert [l.layer for l in s.layers] == [1, 2, 3, 4]
    assert s.overall_status == "PASS"


def test_consolidated_without_ingest_keeps_only_layer_4():
    deck = deck_summary("v1", [NarrativeResult(merchant_id="acme", ok=False, reason="x")])
    s = consolidated_summary("v1", None, deck)
    assert [l.layer for l in s.layers] == [4]  # 1-3 omitted, not faked
    assert s.overall_status == "FAIL"


def test_consistent_schema_every_layer():
    ing = ingest_summary("v1", ValidationReport(), _facts([_row()]),
                         validation_complete=True, facts_computed=True)
    for l in ing.layers:
        assert l.type in {"gate", "note"}
        assert isinstance(l.blocking, bool)
        assert l.status in {"PASS", "WARN", "FAIL"}
        assert isinstance(l.summary, str) and isinstance(l.details, list)


def test_overall_status_precedence():
    ing = ingest_summary("v1", ValidationReport(), _facts([_row(validation_status="mismatch")]),
                         validation_complete=True, facts_computed=True)
    bad_deck = deck_summary("v1", [NarrativeResult(merchant_id="x", ok=False, reason="r")])
    # WARN (layer 3) + FAIL (blocking layer 4) -> overall FAIL
    assert consolidated_summary("v1", ing, bad_deck).overall_status == "FAIL"
