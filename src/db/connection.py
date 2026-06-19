"""DuckDB connection helper."""
from __future__ import annotations

from pathlib import Path

import duckdb

from src.config import settings


def get_connection(
    path: str | Path = settings.DUCKDB_PATH, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB database. Use ``":memory:"`` for tests.

    DuckDB is an embedded, single-writer store: a read-write connection takes an
    *exclusive* file lock, so only one writer can be open at a time. Serving paths
    (the agent / Streamlit) only read, so they pass ``read_only=True`` — multiple
    read-only readers (e.g. the app plus the DuckDB UI) can share the file
    concurrently. Only the ingest pipeline opens it read-write.
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)
