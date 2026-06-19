"""DataFrame-level data-quality validation (pandas checks -> structured report)."""
import pandas as pd

from src.metrics.registry import required_raw_kpi_names
from src.ingestion.validation import run_validation


def _complete_kpis(account, period):
    rows = [
        (account, period, name, 0.5 if "Rate" in name else 100.0)
        for name in required_raw_kpi_names()
    ]
    return pd.DataFrame(rows, columns=["account_name", "period", "kpi_name", "value"])


def _profiles(rows):
    return pd.DataFrame(rows, columns=["merchant_name", "pre_or_post", "business_structure"])


def _evidence(rows):
    return pd.DataFrame(rows, columns=["merchant_name", "period", "event"])


def _codes(report):
    return {i.code for i in report.issues}


def _error_codes(report):
    return {i.code for i in report.errors}


# --- happy path ---

def test_clean_data_has_no_errors():
    kpis = _complete_kpis("ACME", "2025-07")
    profiles = _profiles([("ACME", "Post", "Strategic")])
    evidence = _evidence([("ACME", "2025-07", "High Fraud")])
    report = run_validation(kpis, profiles, evidence)
    assert report.issues == []


# --- required columns guard ---

def test_missing_required_column_is_error_and_skips_downstream():
    kpis = pd.DataFrame({"account_name": ["ACME"], "period": ["2025-07"], "kpi_name": ["Submitted Cnt"]})
    profiles = _profiles([("ACME", "Post", "Strategic")])
    report = run_validation(kpis, profiles, _evidence([]))  # no KeyError despite missing 'value'
    assert "missing_columns" in _error_codes(report)


# --- profile checks ---

def test_invalid_pre_or_post_is_error():
    report = run_validation(_complete_kpis("ACME", "2025-07"),
                            _profiles([("ACME", "Sideways", "Strategic")]),
                            _evidence([]))
    assert "invalid_enum" in _error_codes(report)
    assert "acme" in report.blocked_merchant_ids()


def test_invalid_business_structure_is_error():
    report = run_validation(_complete_kpis("ACME", "2025-07"),
                            _profiles([("ACME", "Post", "Galactic")]),
                            _evidence([]))
    assert "invalid_enum" in _error_codes(report)


def test_duplicate_profile_is_error():
    profiles = _profiles([("ACME", "Post", "Strategic"), ("ACME", "Pre", "Enterprise")])
    report = run_validation(_complete_kpis("ACME", "2025-07"), profiles, _evidence([]))
    assert "duplicate_profile" in _error_codes(report)


# --- referential ---

def test_kpi_account_without_profile_is_error():
    report = run_validation(_complete_kpis("Ghost", "2025-07"),
                            _profiles([("ACME", "Post", "Strategic")]),
                            _evidence([]))
    assert "kpi_without_profile" in _error_codes(report)
    assert "ghost" in report.blocked_merchant_ids()


def test_profile_without_kpi_is_warning():
    profiles = _profiles([("ACME", "Post", "Strategic"), ("Orphan", "Pre", "Enterprise")])
    report = run_validation(_complete_kpis("ACME", "2025-07"), profiles, _evidence([]))
    assert "profile_without_kpi" in _codes(report)
    assert "profile_without_kpi" not in _error_codes(report)  # warning only


# --- kpi structural ---

def test_kpi_bad_period_format_is_error():
    kpis = _complete_kpis("ACME", "2025/07")  # wrong separator
    report = run_validation(kpis, _profiles([("ACME", "Post", "Strategic")]), _evidence([]))
    assert "bad_period_format" in _error_codes(report)


def test_duplicate_kpi_row_is_error():
    kpis = _complete_kpis("ACME", "2025-07")
    dupe = kpis[kpis.kpi_name == "Submitted Cnt"]
    kpis = pd.concat([kpis, dupe], ignore_index=True)
    report = run_validation(kpis, _profiles([("ACME", "Post", "Strategic")]), _evidence([]))
    assert "duplicate_kpi" in _error_codes(report)


def test_missing_kpi_is_error():
    kpis = _complete_kpis("ACME", "2025-07")
    kpis = kpis[kpis.kpi_name != "Effective Fraud Cnt"]
    report = run_validation(kpis, _profiles([("ACME", "Post", "Strategic")]), _evidence([]))
    assert "missing_kpi" in _error_codes(report)


def test_rate_out_of_range_is_error():
    kpis = _complete_kpis("ACME", "2025-07")
    kpis.loc[kpis.kpi_name == "Accepted Chargebacks Rate Cnt", "value"] = 1.5
    report = run_validation(kpis, _profiles([("ACME", "Post", "Strategic")]), _evidence([]))
    assert "rate_out_of_range" in _error_codes(report)


def test_negative_count_is_error():
    kpis = _complete_kpis("ACME", "2025-07")
    kpis.loc[kpis.kpi_name == "Submitted Cnt", "value"] = -5
    report = run_validation(kpis, _profiles([("ACME", "Post", "Strategic")]), _evidence([]))
    assert "negative_value" in _error_codes(report)


# --- evidence ---

def test_unknown_evidence_event_is_warning():
    evidence = _evidence([("ACME", "2025-07", "Alien Invasion")])
    report = run_validation(_complete_kpis("ACME", "2025-07"),
                            _profiles([("ACME", "Post", "Strategic")]), evidence)
    assert "unknown_event" in _codes(report)


def test_evidence_period_out_of_range_is_warning():
    evidence = _evidence([("ACME", "2030-01", "High Fraud")])
    report = run_validation(_complete_kpis("ACME", "2025-07"),
                            _profiles([("ACME", "Post", "Strategic")]), evidence)
    assert "evidence_period_out_of_range" in _codes(report)


# --- rate-mismatch findings + blocking decision ---

def test_zero_denominator_is_error():
    kpis = _complete_kpis("ACME", "2025-07")
    kpis.loc[kpis.kpi_name == "Submitted Cnt", "value"] = 0
    report = run_validation(kpis, _profiles([("ACME", "Post", "Strategic")]), _evidence([]))
    assert "zero_denominator" in _error_codes(report)
