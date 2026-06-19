"""Merchant-scoped data access — the single read/write path for facts + dims.

This repository is the enforcement point for tenant isolation: every read takes an
explicit ``merchant_id`` and filters on it with a parameterized query. Later phases
(deck generator, agent tools) go through here, so an LLM or UI can never widen the
scope — the merchant_id comes from the session, never from model output.
"""
from __future__ import annotations

import duckdb
import pandas as pd


class MetricsRepository:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con

    # --- writes (pipeline only) ---------------------------------------------
    def _replace_table(self, table: str, df: pd.DataFrame) -> None:
        # INSERT BY NAME matches columns by name (order-independent) and leaves any
        # table columns absent from the frame (e.g. lineage in tests) as NULL.
        self.con.register("_df_tmp", df)
        self.con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM _df_tmp")
        self.con.unregister("_df_tmp")

    def write_merchants(self, merchants: pd.DataFrame) -> None:
        self._replace_table("merchants", merchants)

    def write_kpi_measures(self, measures: pd.DataFrame) -> None:
        self._replace_table("kpi_measures", measures)

    def write_evidence(self, evidence: pd.DataFrame) -> None:
        self._replace_table("evidence", evidence)

    # --- full reads (pipeline/engine; not merchant-scoped) ------------------
    def get_kpi_measures(self) -> pd.DataFrame:
        """All KPI measures — the engine's input (read back from the source table)."""
        return self.con.execute("SELECT * FROM kpi_measures").df()

    def get_merchants(self) -> pd.DataFrame:
        """All merchants — the engine's profile dimension."""
        return self.con.execute("SELECT * FROM merchants").df()

    def get_all_monthly_facts(self) -> pd.DataFrame:
        """All monthly facts (not merchant-scoped) — used to build the quality summary."""
        return self.con.execute("SELECT * FROM kpi_facts_monthly").df()

    def write_facts(self, monthly: pd.DataFrame, quarterly: pd.DataFrame) -> None:
        self._replace_table("kpi_facts_monthly", monthly)
        self._replace_table("kpi_facts_quarterly", quarterly)

    # --- scoped reads (always filtered by merchant_id) ----------------------
    def _scoped(self, table: str, merchant_id: str) -> pd.DataFrame:
        return self.con.execute(
            f"SELECT * FROM {table} WHERE merchant_id = ?", [merchant_id]
        ).df()

    def get_monthly_facts(self, merchant_id: str) -> pd.DataFrame:
        return self._scoped("kpi_facts_monthly", merchant_id)

    def get_quarterly_facts(self, merchant_id: str) -> pd.DataFrame:
        return self._scoped("kpi_facts_quarterly", merchant_id)

    def get_evidence(self, merchant_id: str) -> pd.DataFrame:
        return self._scoped("evidence", merchant_id)

    def get_measures(self, merchant_id: str) -> pd.DataFrame:
        """Scoped raw KPI measures for one merchant (calculation/audit details).

        Distinct from the no-arg ``get_kpi_measures()`` (the engine's all-merchant input):
        this is the merchant-scoped read the agent uses, so the raw grid is never exposed
        across tenants.
        """
        return self._scoped("kpi_measures", merchant_id)

    def get_profile(self, merchant_id: str) -> dict | None:
        rows = self.con.execute(
            "SELECT * FROM merchants WHERE merchant_id = ?", [merchant_id]
        ).df()
        return None if rows.empty else rows.iloc[0].to_dict()

    def list_merchant_ids(self) -> list[str]:
        return [r[0] for r in self.con.execute(
            "SELECT merchant_id FROM merchants ORDER BY merchant_id"
        ).fetchall()]
