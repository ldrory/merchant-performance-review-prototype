"""CLI: generate per-merchant PowerPoint decks from the curated DuckDB.

Usage:
    python scripts/generate_decks.py                 # all merchants
    python scripts/generate_decks.py --merchant acme # one merchant

Requires the DuckDB to exist (run scripts/ingest.py first) and an LLM API key
(e.g. ANTHROPIC_API_KEY) since the narrative is LLM-generated.

Quality outputs (per-process ownership):
  - deck_quality.json       : Layer 4 (Narrative Evaluation), owned by this process
  - quality_summary.json    : consolidated = the latest ingest summary (Layers 1-3) + Layer 4
Both under data/output/quality/<version>/. Layers 1-3 are read from the ingest artifact —
this script does NOT re-run input validation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.db.connection import get_connection  # noqa: E402
from src.llm.client import get_chat_model  # noqa: E402
from src.llm.evaluation import NarrativeEvalError  # noqa: E402
from src.presentation.deck_generator import generate_deck_for_merchant  # noqa: E402
from src.presentation.versioning import (  # noqa: E402
    deck_quality_path,
    ingest_quality_path,
    new_version,
    quality_path,
)
from src.quality_summary import (  # noqa: E402
    NarrativeResult,
    QualitySummary,
    consolidated_summary,
    deck_summary,
)
from src.repositories.metrics_repository import MetricsRepository  # noqa: E402


def _load_ingest_quality() -> QualitySummary | None:
    p = ingest_quality_path()
    if not p.exists():
        return None
    return QualitySummary.model_validate_json(p.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate merchant performance-review decks.")
    parser.add_argument("--merchant", help="merchant_id (slug). Omit to generate all.")
    args = parser.parse_args()

    if not settings.DUCKDB_PATH.exists():
        print(f"ERROR: {settings.DUCKDB_PATH} not found. Run: python scripts/ingest.py")
        return 1

    con = get_connection(settings.DUCKDB_PATH, read_only=True)  # decks only read facts
    repo = MetricsRepository(con)
    merchant_ids = [args.merchant] if args.merchant else repo.list_merchant_ids()
    if not merchant_ids:
        print("No merchants found in the database.")
        return 1

    try:
        model = get_chat_model()  # built once, reused across merchants
    except Exception as e:  # noqa: BLE001
        print(f"ERROR building LLM model (is the API key set?): {e}")
        return 1

    version = new_version()
    print(f"Version: {version}\n")

    results: list[NarrativeResult] = []
    for mid in merchant_ids:
        try:
            path = generate_deck_for_merchant(repo, mid, model=model, version=version)
            results.append(NarrativeResult(merchant_id=mid, ok=True))
            print(f"  ✓ {mid} → {path}")
        except NarrativeEvalError as e:  # quality gate failed -> deck not written
            results.append(NarrativeResult(merchant_id=mid, ok=False, reason=str(e)))
            print(f"  ✗ {mid}: {e}")
        except Exception as e:  # noqa: BLE001
            results.append(NarrativeResult(merchant_id=mid, ok=False, reason=str(e)))
            print(f"  ✗ {mid}: {e}")
    con.close()

    # Deck-owned quality (Layer 4) + consolidated (merge of latest ingest + this deck run).
    deck = deck_summary(version, results)
    deck_out = deck_quality_path(version)
    deck_out.parent.mkdir(parents=True, exist_ok=True)
    deck_out.write_text(deck.model_dump_json(indent=2))

    consolidated = consolidated_summary(version, _load_ingest_quality(), deck)
    quality_path(version).write_text(consolidated.model_dump_json(indent=2))

    print(f"\nDecks: {settings.OUTPUT_DIR / 'decks'}/<merchant>/<merchant>_{version}.pptx")
    print(f"Quality: {quality_path(version)}  [overall: {consolidated.overall_status}]")
    return 1 if consolidated.overall_status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
