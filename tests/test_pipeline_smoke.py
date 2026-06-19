"""End-to-end smoke test on the REAL data files (table-first pipeline).

Asserts structural properties on the persisted DuckDB tables (not brittle exact floats):
the dummy data has systematic Accepted-Chargeback-Rate divergence, so we assert the pattern.
"""
from src.db.connection import get_connection
from src.ingestion.loaders import read_kpis, read_profiles, read_evidence
from src.pipeline import run_pipeline
from src.repositories.metrics_repository import MetricsRepository


def _ingest():
    con = get_connection(":memory:")
    result = run_pipeline(con, read_kpis(), read_profiles(), read_evidence())
    return con, result


def test_exactly_five_curated_tables_no_raw():
    con, _ = _ingest()
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert tables == {
        "merchants", "kpi_measures", "evidence", "kpi_facts_monthly", "kpi_facts_quarterly"
    }


def test_kpi_measures_is_full_source_of_truth():
    con, _ = _ingest()
    n = con.execute("SELECT COUNT(*) FROM kpi_measures").fetchone()[0]
    assert n == 576  # 3 merchants x 12 months x 16 KPI names


def test_three_merchants_with_expected_slugs():
    con, _ = _ingest()
    ids = {r[0] for r in con.execute("SELECT merchant_id FROM merchants").fetchall()}
    assert ids == {"acme", "cyberdyne-systems", "vandelay-industries"}


def test_fact_counts_and_rate_ranges():
    con, _ = _ingest()
    assert con.execute("SELECT COUNT(*) FROM kpi_facts_monthly").fetchone()[0] == 240
    assert con.execute("SELECT COUNT(*) FROM kpi_facts_quarterly").fetchone()[0] == 80
    bad = con.execute(
        "SELECT COUNT(*) FROM kpi_facts_monthly "
        "WHERE metric_id <> 'submission_volume' AND value IS NOT NULL "
        "AND (value < 0 OR value > 1)"
    ).fetchone()[0]
    assert bad == 0


def test_value_source_and_status_patterns():
    con, _ = _ingest()
    approval = con.execute(
        "SELECT DISTINCT validation_status FROM kpi_facts_monthly WHERE metric_id='approval_rate'"
    ).df()["validation_status"].tolist()
    assert approval == ["ok"]
    chbg_mismatch = con.execute(
        "SELECT AVG(CASE WHEN validation_status='mismatch' THEN 1.0 ELSE 0.0 END) "
        "FROM kpi_facts_monthly WHERE metric_id='accepted_chargeback_rate'"
    ).fetchone()[0]
    assert chbg_mismatch > 0.5
    eff = con.execute(
        "SELECT DISTINCT value_source FROM kpi_facts_monthly WHERE metric_id='effective_fraud_rate'"
    ).df()["value_source"].tolist()
    assert eff == ["computed"]


def test_enterprise_has_no_sum_variants():
    con, _ = _ingest()
    variants = {r[0] for r in con.execute(
        "SELECT DISTINCT variant FROM kpi_facts_monthly WHERE merchant_id='vandelay-industries'"
    ).fetchall()}
    assert variants == {"cnt"}


def test_lineage_on_every_curated_table():
    con, _ = _ingest()
    for table, expected_source in [
        ("merchants", "merchant_profiles.csv"),
        ("kpi_measures", "merchant_kpis.csv"),
        ("evidence", "merchant_evidence.csv"),
        ("kpi_facts_monthly", "merchant_kpis.csv"),
        ("kpi_facts_quarterly", "merchant_kpis.csv"),
    ]:
        row = con.execute(
            f"SELECT source_file, source_sha256, loaded_at FROM {table} LIMIT 1"
        ).fetchone()
        assert row[0] == expected_source
        assert row[1] and len(row[1]) == 64  # sha256
        assert row[2] is not None


def test_metric_quality_caveat_surfaced_not_blocking():
    con, result = _ingest()
    # provided-vs-computed divergence is a non-blocking caveat, surfaced in data_quality
    assert any("Accepted Chargeback Rate" in n for n in result.data_quality)
    assert result.aborted is False and result.facts_persisted is True


def test_facts_are_merchant_scoped_through_repository():
    con, _ = _ingest()
    repo = MetricsRepository(con)
    acme = repo.get_monthly_facts("acme")
    assert not acme.empty
    assert set(acme["merchant_id"]) == {"acme"}


def test_merchant_with_input_error_is_excluded_others_succeed():
    # Give Cyberdyne a zero denominator (input error) -> excluded; others still ingested.
    kpis = read_kpis()
    mask = (kpis["account_name"] == "Cyberdyne Systems") & (kpis["kpi_name"] == "Submitted Cnt")
    kpis.loc[mask, "value"] = 0
    con = get_connection(":memory:")
    result = run_pipeline(con, kpis, read_profiles(), read_evidence())
    assert result.aborted is False
    assert "cyberdyne-systems" in result.excluded_merchant_ids
    ids = {r[0] for r in con.execute("SELECT merchant_id FROM merchants").fetchall()}
    assert ids == {"acme", "vandelay-industries"}  # cyberdyne excluded before persistence


def test_ingest_emits_quality_with_layers_1_to_3_on_success():
    _, result = _ingest()
    assert result.quality.stage == "ingest"
    assert [l.layer for l in result.quality.layers] == [1, 2, 3]


def test_ingest_emits_quality_even_when_aborted():
    # Missing a required column -> ingest aborts, but still produces a Layer-1 quality artifact.
    kpis = read_kpis().drop(columns=["value"])
    con = get_connection(":memory:")
    result = run_pipeline(con, kpis, read_profiles(), read_evidence())
    assert result.aborted is True
    assert [l.layer for l in result.quality.layers] == [1]
    assert result.quality.overall_status == "FAIL"
