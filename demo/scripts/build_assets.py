"""Build the demo's static assets from the real product code (no LLM / no API key).

Renders the ACME deck's charts with the *same* code the product uses, so the demo video's
charts are pixel-identical to the generated deck, then copies the logo. Output lands in
``demo/public/`` where Remotion can serve it.

    python demo/scripts/build_assets.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.config import settings  # noqa: E402
from src.db.connection import get_connection  # noqa: E402
from src.ingestion.loaders import read_evidence, read_kpis, read_profiles  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402
from src.presentation.chart_generator import render_charts  # noqa: E402
from src.presentation.deck_schema import build_deck_model  # noqa: E402
from src.repositories.metrics_repository import MetricsRepository  # noqa: E402

MERCHANT = "acme"
PUBLIC = Path(__file__).resolve().parents[1] / "public"
CHARTS_OUT = PUBLIC / "charts"


def _repo():
    """Open the existing DuckDB if present; otherwise build it in-memory from the CSVs."""
    if settings.DUCKDB_PATH.exists():
        return MetricsRepository(get_connection(settings.DUCKDB_PATH, read_only=True))
    con = get_connection(":memory:")
    run_pipeline(con, read_kpis(), read_profiles(), read_evidence())
    return MetricsRepository(con)


def main() -> int:
    CHARTS_OUT.mkdir(parents=True, exist_ok=True)
    repo = _repo()
    deck = build_deck_model(repo, MERCHANT)
    charts = render_charts(deck, CHARTS_OUT)
    for metric_id, paths in charts.items():
        print(f"  {metric_id}: {paths['monthly'].name}, {paths['quarterly'].name}")

    logo_src = settings.PROJECT_ROOT / "assets" / "logo.png"
    if logo_src.exists():
        shutil.copy2(logo_src, PUBLIC / "logo.png")
        print(f"  logo -> {PUBLIC / 'logo.png'}")

    print(f"\nAssets written to {PUBLIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
