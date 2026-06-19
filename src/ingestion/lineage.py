"""Lightweight ingestion lineage.

Every persisted curated table carries where its data came from and when it was
loaded. This is intentionally minimal — three columns, no load-history table:

    source_file    the originating CSV filename (basename, not the full path)
    source_sha256  sha256 of that CSV's bytes (content fingerprint)
    loaded_at      one UTC timestamp shared across all tables in a single run
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LINEAGE_COLUMNS = ["source_file", "source_sha256", "loaded_at"]


def now_utc() -> datetime:
    """Naive UTC timestamp (maps cleanly to a DuckDB TIMESTAMP column)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def with_lineage(
    df: pd.DataFrame,
    source_path: str | Path,
    loaded_at: datetime,
    source_hash: str | None = None,
) -> pd.DataFrame:
    """Return a copy of ``df`` with the lineage columns appended."""
    out = df.copy()
    out["source_file"] = Path(source_path).name
    out["source_sha256"] = source_hash if source_hash is not None else file_sha256(source_path)
    out["loaded_at"] = pd.Timestamp(loaded_at)
    return out
