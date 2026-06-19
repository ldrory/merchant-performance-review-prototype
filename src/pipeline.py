"""Ingestion pipeline — table-first / ELT-shaped, expressed as a small DAG of steps.

    run_pipeline = validate_inputs → ingest_sources → compute_facts → persist_facts

Each step is a small, separately-readable function; ``run_pipeline`` wires them together and
handles the gates (a global input error or zero valid merchants aborts the run). The database
is the source of truth: facts are computed *on top of* the persisted ``kpi_measures`` table.

No modes. Metric-quality (provided-vs-computed) is a non-blocking warning surfaced from the
facts; genuinely uncomputable facts are prevented at input time (missing KPIs, zero
denominators) and guarded post-compute by a defensive safety net.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from src.config import settings
from src.db.schema import create_schema
from src.ingestion.lineage import file_sha256, now_utc, with_lineage
from src.ingestion.normalization import (
    build_evidence_df,
    build_kpi_measures_df,
    build_merchants_df,
)
from src.ingestion.validation import run_validation
from src.metrics.engine import compute_monthly_facts
from src.metrics.quality import find_broken_metric_merchants, summarize_metric_quality
from src.metrics.quarterly import compute_quarterly_facts
from src.models import ValidationReport
from src.presentation.versioning import new_version
from src.quality_summary import QualitySummary, ingest_summary
from src.repositories.metrics_repository import MetricsRepository


@dataclass
class SourceTables:
    """The normalized source-of-truth frames (one row-set per curated source table)."""
    merchants: pd.DataFrame
    kpi_measures: pd.DataFrame
    evidence: pd.DataFrame


@dataclass
class Facts:
    monthly: pd.DataFrame
    quarterly: pd.DataFrame


@dataclass
class PipelineResult:
    report: ValidationReport
    version: str = ""
    quality: QualitySummary | None = None  # ingest-owned quality (Layers 1-3, as far as they ran)
    aborted: bool = False                 # run could not proceed (exit non-zero)
    sources_persisted: bool = False
    facts_persisted: bool = False
    excluded_merchant_ids: list[str] = field(default_factory=list)  # input errors
    data_quality: list[str] = field(default_factory=list)           # metric-quality warnings
    merchant_count: int = 0
    measure_count: int = 0
    monthly_rows: int = 0
    quarterly_rows: int = 0


# --- DAG steps ---------------------------------------------------------------

def build_source_tables(
    kpis: pd.DataFrame,
    profiles: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    exclude: set[str],
) -> SourceTables:
    """Step: normalize raw frames → source tables (slugged), dropping excluded merchants. Pure."""
    merchants = build_merchants_df(profiles, exclude_ids=exclude)
    return SourceTables(
        merchants=merchants,
        kpi_measures=build_kpi_measures_df(kpis, merchants),
        evidence=build_evidence_df(evidence, merchants),
    )


def ingest_sources(
    repo: MetricsRepository,
    sources: SourceTables,
    *,
    loaded_at: datetime,
    kpis_path: str | Path,
    profiles_path: str | Path,
    evidence_path: str | Path,
) -> None:
    """Step (1) INGEST: write the source-of-truth tables into DuckDB (+ lineage)."""
    create_schema(repo.con)
    repo.write_merchants(with_lineage(sources.merchants, profiles_path, loaded_at, file_sha256(profiles_path)))
    repo.write_kpi_measures(with_lineage(sources.kpi_measures, kpis_path, loaded_at, file_sha256(kpis_path)))
    repo.write_evidence(with_lineage(sources.evidence, evidence_path, loaded_at, file_sha256(evidence_path)))


def compute_facts(repo: MetricsRepository, *, tolerance: float) -> Facts:
    """Step (2) COMPUTE: read sources back from DuckDB and compute monthly + quarterly facts."""
    monthly = compute_monthly_facts(repo.get_kpi_measures(), repo.get_merchants(), tolerance)
    quarterly = compute_quarterly_facts(monthly, tolerance)

    # Defense-in-depth: input validation should make this impossible. If a fact still couldn't
    # be produced, fail loudly rather than ship bad data.
    broken = find_broken_metric_merchants(monthly)
    if broken:
        raise RuntimeError(f"uncomputable facts after validation (unexpected): {broken}")
    return Facts(monthly=monthly, quarterly=quarterly)


def persist_facts(
    repo: MetricsRepository, facts: Facts, *, loaded_at: datetime, kpis_path: str | Path
) -> None:
    """Step (3) PERSIST: write the computed fact tables into DuckDB (+ lineage)."""
    kpis_hash = file_sha256(kpis_path)
    repo.write_facts(
        with_lineage(facts.monthly, kpis_path, loaded_at, kpis_hash),
        with_lineage(facts.quarterly, kpis_path, loaded_at, kpis_hash),
    )


# --- orchestrator ------------------------------------------------------------

def run_pipeline(
    con: duckdb.DuckDBPyConnection,
    kpis: pd.DataFrame,
    profiles: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    tolerance: float = settings.RATE_MISMATCH_TOLERANCE,
    kpis_path: str | Path = settings.KPIS_CSV,
    profiles_path: str | Path = settings.PROFILES_CSV,
    evidence_path: str | Path = settings.EVIDENCE_CSV,
    loaded_at: datetime | None = None,
) -> PipelineResult:
    """validate → ingest sources → compute facts → persist facts (table-first ELT)."""
    loaded_at = loaded_at or now_utc()
    version = new_version()

    # Step 0 — VALIDATE inputs (gate).
    report = run_validation(kpis, profiles, evidence)
    if any(i.code == "missing_columns" for i in report.errors):  # global error → cannot proceed
        quality = ingest_summary(version, report, None, validation_complete=False, facts_computed=False)
        return PipelineResult(report, version=version, quality=quality, aborted=True)

    excluded = sorted(report.blocked_merchant_ids())  # per-merchant errors → excluded
    sources = build_source_tables(kpis, profiles, evidence, exclude=set(excluded))
    if sources.merchants.empty:  # nothing valid to ingest
        quality = ingest_summary(version, report, None, validation_complete=True, facts_computed=False)
        return PipelineResult(report, version=version, quality=quality, aborted=True,
                              excluded_merchant_ids=excluded)

    # Steps 1-3 — INGEST sources → COMPUTE facts → PERSIST facts.
    repo = MetricsRepository(con)
    ingest_sources(repo, sources, loaded_at=loaded_at, kpis_path=kpis_path,
                   profiles_path=profiles_path, evidence_path=evidence_path)
    facts = compute_facts(repo, tolerance=tolerance)
    persist_facts(repo, facts, loaded_at=loaded_at, kpis_path=kpis_path)

    return PipelineResult(
        report=report,
        version=version,
        quality=ingest_summary(version, report, facts.monthly,
                               validation_complete=True, facts_computed=True),
        sources_persisted=True,
        facts_persisted=True,
        excluded_merchant_ids=excluded,
        data_quality=summarize_metric_quality(facts.monthly),
        merchant_count=len(sources.merchants),
        measure_count=len(sources.kpi_measures),
        monthly_rows=len(facts.monthly),
        quarterly_rows=len(facts.quarterly),
    )
