"""Persistence + the merchant-scoped repository (the isolation boundary)."""
import pandas as pd

from src.db.connection import get_connection
from src.db.schema import create_schema
from src.ingestion.lineage import LINEAGE_COLUMNS
from src.ingestion.normalization import MEASURE_COLUMNS
from src.metrics.engine import FACT_COLUMNS
from src.repositories.metrics_repository import MetricsRepository


def _fact_row(merchant_id, metric_id="submission_volume", **overrides):
    row = {c: None for c in FACT_COLUMNS}
    row.update(
        merchant_id=merchant_id, period="2025-07", quarter="2025-Q3",
        metric_id=metric_id, metric_name="Submission Volume", variant="cnt",
        value=100.0, value_source="additive", validation_status="additive",
    )
    row.update(overrides)
    return row


def _seed_repo():
    con = get_connection(":memory:")
    create_schema(con)
    repo = MetricsRepository(con)
    merchants = pd.DataFrame(
        [
            ("acme", "ACME", "Post", "Strategic"),
            ("cyberdyne-systems", "Cyberdyne Systems", "Pre", "Strategic"),
        ],
        columns=["merchant_id", "merchant_name", "pre_or_post", "business_structure"],
    )
    evidence = pd.DataFrame(
        [("acme", "2026-01", "High Fraud"), ("cyberdyne-systems", "2025-10", "High Fraud")],
        columns=["merchant_id", "period", "event"],
    )
    measures = pd.DataFrame(
        [
            ("acme", "ACME", "2025-07", "Submitted Cnt", 100.0),
            ("cyberdyne-systems", "Cyberdyne Systems", "2025-07", "Submitted Cnt", 50.0),
        ],
        columns=MEASURE_COLUMNS,
    )
    monthly = pd.DataFrame([_fact_row("acme"), _fact_row("cyberdyne-systems")], columns=FACT_COLUMNS)
    quarterly = monthly.copy()
    repo.write_merchants(merchants)
    repo.write_kpi_measures(measures)
    repo.write_evidence(evidence)
    repo.write_facts(monthly, quarterly)
    return repo


def test_get_monthly_is_scoped_to_one_merchant():
    repo = _seed_repo()
    df = repo.get_monthly_facts("acme")
    assert set(df["merchant_id"]) == {"acme"}


def test_get_quarterly_is_scoped_to_one_merchant():
    repo = _seed_repo()
    df = repo.get_quarterly_facts("cyberdyne-systems")
    assert set(df["merchant_id"]) == {"cyberdyne-systems"}


def test_evidence_and_profile_are_scoped():
    repo = _seed_repo()
    assert set(repo.get_evidence("acme")["merchant_id"]) == {"acme"}
    profile = repo.get_profile("acme")
    assert profile["merchant_name"] == "ACME"


def test_unknown_merchant_returns_empty_not_other_data():
    repo = _seed_repo()
    assert repo.get_monthly_facts("ghost").empty
    assert repo.get_profile("ghost") is None


def test_list_merchants():
    repo = _seed_repo()
    assert set(repo.list_merchant_ids()) == {"acme", "cyberdyne-systems"}


def test_full_reads_for_engine():
    repo = _seed_repo()
    assert len(repo.get_kpi_measures()) == 2
    assert set(repo.get_merchants()["merchant_id"]) == {"acme", "cyberdyne-systems"}


def test_schema_fact_columns_match_engine_contract():
    # Drift guard: schema.sql fact tables = FACT_COLUMNS (business) + LINEAGE_COLUMNS.
    con = get_connection(":memory:")
    create_schema(con)
    for table in ("kpi_facts_monthly", "kpi_facts_quarterly"):
        cols = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
        assert cols == FACT_COLUMNS + LINEAGE_COLUMNS


def test_schema_kpi_measures_columns():
    con = get_connection(":memory:")
    create_schema(con)
    cols = [r[0] for r in con.execute("DESCRIBE kpi_measures").fetchall()]
    assert cols == MEASURE_COLUMNS + LINEAGE_COLUMNS


def test_exactly_five_curated_tables_no_raw():
    con = get_connection(":memory:")
    create_schema(con)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert tables == {
        "merchants", "kpi_measures", "evidence", "kpi_facts_monthly", "kpi_facts_quarterly"
    }
