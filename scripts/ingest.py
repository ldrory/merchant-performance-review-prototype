"""CLI: load CSVs -> validate -> persist curated DuckDB tables.

Usage:
    python scripts/ingest.py
    python scripts/ingest.py --input-merchant-profiles path/to/profiles.csv \\
        --input-merchant-kpis path/to/kpis.csv --input-merchant-evidence path/to/evidence.csv

Table-first: source tables (merchants, kpi_measures, evidence) are persisted for the valid
merchants, then facts are computed from them. Input validation is a gate — a merchant with
errors is excluded; a global error (missing columns) or zero valid merchants aborts (exit 1).
Metric-quality (provided-vs-computed) is reported as a non-blocking warning.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make ``src`` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.db.connection import get_connection  # noqa: E402
from src.ingestion.loaders import read_evidence, read_kpis, read_profiles  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402
from src.presentation.versioning import ingest_quality_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest merchant CSVs into curated DuckDB tables.")
    parser.add_argument("--input-merchant-profiles", default=settings.PROFILES_CSV,
                        help=f"path to the merchant profiles CSV (default: {settings.PROFILES_CSV})")
    parser.add_argument("--input-merchant-kpis", default=settings.KPIS_CSV,
                        help=f"path to the merchant KPIs CSV (default: {settings.KPIS_CSV})")
    parser.add_argument("--input-merchant-evidence", default=settings.EVIDENCE_CSV,
                        help=f"path to the merchant evidence CSV (default: {settings.EVIDENCE_CSV})")
    args = parser.parse_args()

    kpis = read_kpis(args.input_merchant_kpis)
    profiles = read_profiles(args.input_merchant_profiles)
    evidence = read_evidence(args.input_merchant_evidence)

    con = get_connection()
    result = run_pipeline(
        con, kpis, profiles, evidence,
        kpis_path=args.input_merchant_kpis,
        profiles_path=args.input_merchant_profiles,
        evidence_path=args.input_merchant_evidence,
    )
    con.close()

    # Write the ingest-owned quality summary (Layers 1-3) — even when ingest fails.
    out = ingest_quality_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.quality.model_dump_json(indent=2))

    print(f"\nQuality (ingest) [overall: {result.quality.overall_status}] → {out.relative_to(settings.PROJECT_ROOT)}")
    for layer in result.quality.layers:
        print(f"  L{layer.layer} {layer.name}: {layer.status} — {layer.summary}")
        for d in layer.details:
            print(f"      {d}")

    if result.aborted:
        print("\nABORTED: cannot ingest (see Layer issues above). No facts written.")
        return 1

    print(f"\nIngested into {settings.DUCKDB_PATH.relative_to(settings.PROJECT_ROOT)}")
    print(f"  merchants:           {result.merchant_count}")
    print(f"  kpi_measures:        {result.measure_count} rows")
    print(f"  kpi_facts_monthly:   {result.monthly_rows} rows")
    print(f"  kpi_facts_quarterly: {result.quarterly_rows} rows")
    if result.excluded_merchant_ids:
        print(f"  excluded (input errors): {result.excluded_merchant_ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
