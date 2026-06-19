"""Apply the DuckDB schema from the dedicated ``schema.sql`` file."""
from __future__ import annotations

from pathlib import Path

import duckdb

SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Execute the schema script (idempotent — every statement uses CREATE OR REPLACE).

    DuckDB executes the full multi-statement script in a single ``execute`` call.
    """
    con.execute(SCHEMA_SQL.read_text())
