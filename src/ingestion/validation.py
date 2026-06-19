"""Input validation (Layer 1) — the pre-compute gate.

Structural/business-rule checks on the tidy input DataFrames, collected into a
``ValidationReport`` of issues. Per-merchant ``error``s exclude that merchant; a global
error (missing columns) aborts the run. There are no modes — one clear behavior.

Metric-quality (provided-vs-computed) lives in ``metrics/quality.py``, not here: it needs
the computed facts and is a warning, not an input gate.
"""
from __future__ import annotations

import re

import pandas as pd

from src.config import settings
from src.metrics.registry import denominator_kpi_names, required_raw_kpi_names
from src.models import ValidationIssue, ValidationReport

_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")
_VALID_PRE_POST = {"Pre", "Post"}
_VALID_STRUCTURE = {"Strategic", "Enterprise"}
KNOWN_EVENTS = {"High Fraud", "Low Volume", "Peak Season", "Chargeback Spike", "Strong Growth"}

_REQUIRED_COLUMNS = {
    "kpis": {"account_name", "period", "kpi_name", "value"},
    "profiles": {"merchant_name", "pre_or_post", "business_structure"},
    "evidence": {"merchant_name", "period", "event"},
}


def run_validation(
    kpis: pd.DataFrame,
    profiles: pd.DataFrame,
    evidence: pd.DataFrame,
) -> ValidationReport:
    report = ValidationReport()
    # Guard required columns first: missing columns -> stop before downstream KeyErrors.
    if not _check_required_columns(kpis, profiles, evidence, report):
        return report
    _check_profiles(profiles, report)
    _check_kpi_periods(kpis, report)
    _check_duplicate_kpis(kpis, report)
    _check_referential(kpis, profiles, evidence, report)
    _check_completeness(kpis, report)
    _check_value_ranges(kpis, report)
    _check_evidence(kpis, evidence, report)
    return report


def _check_required_columns(kpis, profiles, evidence, report) -> bool:
    ok = True
    for label, df in (("kpis", kpis), ("profiles", profiles), ("evidence", evidence)):
        missing = _REQUIRED_COLUMNS[label] - set(df.columns)
        if missing:
            ok = False
            report.add_issue(ValidationIssue(
                severity="error", code="missing_columns",
                message=f"{label}: missing required columns {sorted(missing)}",
            ))
    return ok


def _check_profiles(profiles, report) -> None:
    for r in profiles.itertuples(index=False):
        mid = settings.slugify(r.merchant_name)
        if r.pre_or_post not in _VALID_PRE_POST:
            report.add_issue(ValidationIssue(
                severity="error", code="invalid_enum", merchant_id=mid,
                message=f"{r.merchant_name}: invalid 'Pre or Post' value {r.pre_or_post!r}",
            ))
        if r.business_structure not in _VALID_STRUCTURE:
            report.add_issue(ValidationIssue(
                severity="error", code="invalid_enum", merchant_id=mid,
                message=f"{r.merchant_name}: invalid 'Business structure' value {r.business_structure!r}",
            ))
    dups = profiles["merchant_name"][profiles["merchant_name"].duplicated(keep=False)]
    for name in sorted(set(dups)):
        report.add_issue(ValidationIssue(
            severity="error", code="duplicate_profile", merchant_id=settings.slugify(name),
            message=f"{name}: appears more than once in profiles",
        ))


def _check_kpi_periods(kpis, report) -> None:
    bad = kpis[~kpis["period"].astype(str).str.match(_PERIOD_RE)]
    for (account, period), _ in bad.groupby(["account_name", "period"]):
        report.add_issue(ValidationIssue(
            severity="error", code="bad_period_format", merchant_id=settings.slugify(account),
            message=f"{account}: KPI period {period!r} is not YYYY-MM",
        ))


def _check_duplicate_kpis(kpis, report) -> None:
    keys = ["account_name", "period", "kpi_name"]
    dups = kpis[kpis.duplicated(subset=keys, keep=False)]
    for (account, period, kpi_name), _ in dups.groupby(keys):
        report.add_issue(ValidationIssue(
            severity="error", code="duplicate_kpi", merchant_id=settings.slugify(account),
            message=f"{account} {period}: duplicate KPI row for {kpi_name!r}",
        ))


def _check_referential(kpis, profiles, evidence, report) -> None:
    kpi_accounts = set(kpis["account_name"].unique())
    profile_names = set(profiles["merchant_name"].unique())
    evidence_names = set(evidence["merchant_name"].unique()) if not evidence.empty else set()

    for acct in sorted(kpi_accounts - profile_names):
        report.add_issue(ValidationIssue(
            severity="error", code="kpi_without_profile", merchant_id=settings.slugify(acct),
            message=f"{acct}: has KPI data but no merchant profile",
        ))
    for name in sorted(profile_names - kpi_accounts):
        report.add_issue(ValidationIssue(
            severity="warning", code="profile_without_kpi", merchant_id=settings.slugify(name),
            message=f"{name}: has a profile but no KPI data",
        ))
    for name in sorted(evidence_names - profile_names):
        report.add_issue(ValidationIssue(
            severity="warning", code="evidence_without_profile", merchant_id=settings.slugify(name),
            message=f"{name}: has evidence but no merchant profile",
        ))


def _check_completeness(kpis, report) -> None:
    expected = required_raw_kpi_names()
    present = kpis.groupby(["account_name", "period"])["kpi_name"].agg(set)
    for (account, period), names in present.items():
        missing = expected - names
        if missing:
            report.add_issue(ValidationIssue(
                severity="error", code="missing_kpi", merchant_id=settings.slugify(account),
                message=f"{account} {period}: missing {len(missing)} KPI(s): {sorted(missing)}",
            ))


def _check_value_ranges(kpis, report) -> None:
    is_rate = kpis["kpi_name"].str.contains("Rate", na=False)
    bad_rate = kpis[is_rate & ~kpis["value"].between(0, 1)]
    for r in bad_rate.itertuples(index=False):
        report.add_issue(ValidationIssue(
            severity="error", code="rate_out_of_range", merchant_id=settings.slugify(r.account_name),
            message=f"{r.account_name} {r.period}: {r.kpi_name}={r.value} outside [0,1]",
        ))
    negative = kpis[~is_rate & (kpis["value"] < 0)]
    for r in negative.itertuples(index=False):
        report.add_issue(ValidationIssue(
            severity="error", code="negative_value", merchant_id=settings.slugify(r.account_name),
            message=f"{r.account_name} {r.period}: {r.kpi_name}={r.value} is negative",
        ))
    # Zero denominators make every ratio uncomputable -> block the merchant at input time
    # (so we never persist a merchant whose facts can't be produced).
    zero_denom = kpis[kpis["kpi_name"].isin(denominator_kpi_names()) & (kpis["value"] == 0)]
    for r in zero_denom.itertuples(index=False):
        report.add_issue(ValidationIssue(
            severity="error", code="zero_denominator", merchant_id=settings.slugify(r.account_name),
            message=f"{r.account_name} {r.period}: denominator {r.kpi_name} is 0",
        ))


def _check_evidence(kpis, evidence, report) -> None:
    if evidence.empty:
        return
    valid_periods = kpis.loc[kpis["period"].astype(str).str.match(_PERIOD_RE), "period"]
    pmin, pmax = (valid_periods.min(), valid_periods.max()) if not valid_periods.empty else (None, None)
    for r in evidence.itertuples(index=False):
        mid = settings.slugify(r.merchant_name)
        if not _PERIOD_RE.match(str(r.period)):
            report.add_issue(ValidationIssue(
                severity="warning", code="bad_period_format", merchant_id=mid,
                message=f"{r.merchant_name}: evidence period {r.period!r} is not YYYY-MM",
            ))
        elif pmin is not None and not (pmin <= r.period <= pmax):
            report.add_issue(ValidationIssue(
                severity="warning", code="evidence_period_out_of_range", merchant_id=mid,
                message=f"{r.merchant_name}: evidence period {r.period} outside KPI range [{pmin}, {pmax}]",
            ))
        if r.event not in KNOWN_EVENTS:
            report.add_issue(ValidationIssue(
                severity="warning", code="unknown_event", merchant_id=mid,
                message=f"{r.merchant_name} {r.period}: unknown event {r.event!r}",
            ))
