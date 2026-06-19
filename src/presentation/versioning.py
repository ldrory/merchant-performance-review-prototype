"""Output versioning for generated artifacts (charts + decks).

Outputs are organized **per company, then version**, so each merchant has its own folder
with a history of versioned runs (never overwriting prior runs):

    data/output/decks/<merchant_id>/<merchant_id>_<version>.pptx
    data/output/charts/<merchant_id>/<version>/*.png
    data/output/{decks,charts}/<merchant_id>/LATEST   # names the newest version

Version = one UTC-timestamp shared by every merchant in a single ``generate_decks`` run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.config import settings


def new_version() -> str:
    """A unique, sortable run version, e.g. ``20260616T101500Z`` (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def merchant_paths(
    merchant_id: str, version: str, base: Path | str = settings.OUTPUT_DIR
) -> tuple[Path, Path]:
    """Return ``(deck_path, charts_dir)`` for one merchant+version under ``base``."""
    base = Path(base)
    deck_path = base / "decks" / merchant_id / f"{merchant_id}_{version}.pptx"
    charts_dir = base / "charts" / merchant_id / version
    return deck_path, charts_dir


def ingest_quality_path(base: Path | str = settings.OUTPUT_DIR) -> Path:
    """Stable path to the latest ingest quality summary (ingest is not versioned)."""
    return Path(base) / "quality" / "ingest_quality.json"


def deck_quality_path(version: str, base: Path | str = settings.OUTPUT_DIR) -> Path:
    """Path to the deck-run (Layer 4) quality summary."""
    return Path(base) / "quality" / version / "deck_quality.json"


def quality_path(version: str, base: Path | str = settings.OUTPUT_DIR) -> Path:
    """Path to the consolidated quality summary for a run."""
    return Path(base) / "quality" / version / "quality_summary.json"


def write_latest(merchant_kind_dir: Path | str, version: str) -> Path:
    """Write/refresh ``<dir>/LATEST`` with the version string."""
    d = Path(merchant_kind_dir)
    d.mkdir(parents=True, exist_ok=True)
    pointer = d / "LATEST"
    pointer.write_text(version + "\n")
    return pointer
