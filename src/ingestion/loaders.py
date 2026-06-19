"""CSV loaders that normalize the three raw inputs into tidy DataFrames.

All inputs are CSV (per the assignment). Loaders only normalize structure
(column names, whitespace, value dtype) — no business logic or validation here.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import settings


def _read_csv(path: str | Path, rename: dict[str, str]) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns={c: c.strip() for c in df.columns})
    missing = [c for c in rename if c not in df.columns]
    if missing:
        raise ValueError(f"{Path(path).name}: missing expected columns {missing}")
    df = df[list(rename)].rename(columns=rename)
    # Trim whitespace on all string cells.
    for col in df.columns:
        df[col] = df[col].str.strip()
    return df


def read_kpis(path: str | Path = settings.KPIS_CSV) -> pd.DataFrame:
    """Return columns: account_name, period, kpi_name, value (float)."""
    df = _read_csv(
        path,
        {
            "Account Name": "account_name",
            "Date": "period",
            "KPI": "kpi_name",
            "Value": "value",
        },
    )
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def read_profiles(path: str | Path = settings.PROFILES_CSV) -> pd.DataFrame:
    """Return columns: merchant_name, pre_or_post, business_structure."""
    return _read_csv(
        path,
        {
            "Merchant Name": "merchant_name",
            "Pre or Post": "pre_or_post",
            "Business structure": "business_structure",
        },
    )


def read_evidence(path: str | Path = settings.EVIDENCE_CSV) -> pd.DataFrame:
    """Return columns: merchant_name, period, event."""
    return _read_csv(
        path,
        {
            "Merchant Name": "merchant_name",
            "Month": "period",
            "Event": "event",
        },
    )
