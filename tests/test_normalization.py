import pandas as pd

from src.ingestion.normalization import (
    MEASURE_COLUMNS,
    build_evidence_df,
    build_kpi_measures_df,
    build_merchants_df,
)


def _profiles(rows):
    return pd.DataFrame(rows, columns=["merchant_name", "pre_or_post", "business_structure"])


def test_build_merchants_df_adds_slug_column():
    df = build_merchants_df(_profiles([("Vandelay Industries", "Post", "Enterprise")]))
    assert list(df.columns) == ["merchant_id", "merchant_name", "pre_or_post", "business_structure"]
    assert df.iloc[0]["merchant_id"] == "vandelay-industries"


def test_build_merchants_df_excludes_blocked_ids():
    df = build_merchants_df(
        _profiles([("ACME", "Post", "Strategic"), ("Ghost", "Pre", "Strategic")]),
        exclude_ids={"ghost"},
    )
    assert set(df["merchant_id"]) == {"acme"}


def test_build_merchants_df_dedups_by_slug():
    df = build_merchants_df(_profiles([("ACME", "Post", "Strategic"), ("ACME", "Pre", "Enterprise")]))
    assert len(df) == 1


def test_build_evidence_df_maps_to_merchant_id_and_drops_unknown():
    merchants = build_merchants_df(_profiles([("ACME", "Post", "Strategic")]))
    evidence = pd.DataFrame(
        [("ACME", "2026-01", "High Fraud"), ("Ghost", "2025-10", "High Fraud")],
        columns=["merchant_name", "period", "event"],
    )
    df = build_evidence_df(evidence, merchants)
    assert list(df.columns) == ["merchant_id", "period", "event"]
    assert set(df["merchant_id"]) == {"acme"}  # Ghost dropped (no merchant)


def test_build_kpi_measures_df_adds_merchant_id_and_drops_unknown():
    merchants = build_merchants_df(_profiles([("ACME", "Post", "Strategic")]))
    kpis = pd.DataFrame(
        [
            ("ACME", "2025-07", "Submitted Cnt", 100.0),
            ("Ghost", "2025-07", "Submitted Cnt", 5.0),
        ],
        columns=["account_name", "period", "kpi_name", "value"],
    )
    df = build_kpi_measures_df(kpis, merchants)
    assert list(df.columns) == MEASURE_COLUMNS
    assert set(df["merchant_id"]) == {"acme"}  # Ghost dropped (no merchant)
    assert df.iloc[0]["account_name"] == "ACME"  # original name retained
