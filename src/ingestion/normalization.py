"""Normalization: turn tidy CSV frames into the curated dimension tables.

Flow: CSV -> normalized DataFrames (loaders) -> validation -> curated DuckDB tables.
This module builds the ``merchants`` and ``evidence`` dimensions, adding only the
deterministic ``merchant_id`` slug and dropping rows that can't be attributed to a
known merchant. No business logic here — KPI facts are computed in ``src.metrics``.
"""
from __future__ import annotations

import pandas as pd

from src.config import settings

_MERCHANT_COLUMNS = ["merchant_id", "merchant_name", "pre_or_post", "business_structure"]
MEASURE_COLUMNS = ["merchant_id", "account_name", "period", "kpi_name", "value"]


def build_merchants_df(profiles: pd.DataFrame, exclude_ids: set[str] | None = None) -> pd.DataFrame:
    """Profiles -> merchants dimension with a ``merchant_id`` slug column.

    Excludes ``exclude_ids`` (merchants blocked by validation errors) and dedups by slug.
    """
    exclude_ids = exclude_ids or set()
    df = profiles.copy()
    df["merchant_id"] = df["merchant_name"].map(settings.slugify)
    df = df[~df["merchant_id"].isin(exclude_ids)]
    df = df.drop_duplicates(subset=["merchant_id"], keep="first")
    return df[_MERCHANT_COLUMNS].reset_index(drop=True)


def build_evidence_df(evidence: pd.DataFrame, merchants: pd.DataFrame) -> pd.DataFrame:
    """Evidence -> clean dimension keyed by ``merchant_id``; drops unknown merchants."""
    df = evidence.copy()
    df["merchant_id"] = df["merchant_name"].map(settings.slugify)
    known = set(merchants["merchant_id"])
    df = df[df["merchant_id"].isin(known)]
    return df[["merchant_id", "period", "event"]].reset_index(drop=True)


def build_kpi_measures_df(kpis: pd.DataFrame, merchants: pd.DataFrame) -> pd.DataFrame:
    """KPI rows -> normalized long source-of-truth table keyed by ``merchant_id``.

    Adds the ``merchant_id`` slug (canonical key) while keeping ``account_name`` for
    reference, and drops rows whose merchant is not in the (already blocked-filtered)
    merchants dimension.
    """
    df = kpis.copy()
    df["merchant_id"] = df["account_name"].map(settings.slugify)
    known = set(merchants["merchant_id"])
    df = df[df["merchant_id"].isin(known)]
    return df[MEASURE_COLUMNS].reset_index(drop=True)
