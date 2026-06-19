"""Central configuration: paths, pipeline tuning, and shared helpers.

Phase 1 only depends on the path constants, the validation-mode/tolerance settings,
and ``slugify``. LLM settings are read lazily by later phases.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# --- Paths -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load .env (e.g. ANTHROPIC_API_KEY) if present — keeps secrets out of the code/shell.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ModuleNotFoundError:  # python-dotenv only needed for LLM phases
    pass
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = DATA_DIR / "output"

KPIS_CSV = RAW_DIR / "merchant_kpis.csv"
PROFILES_CSV = RAW_DIR / "merchant_profiles.csv"
EVIDENCE_CSV = RAW_DIR / "merchant_evidence.csv"

DUCKDB_PATH = PROCESSED_DIR / "riskified.duckdb"

# --- Pipeline config (env-overridable) ---------------------------------------
# Relative tolerance for the provided-vs-computed rate cross-check (0.02 = 2%).
RATE_MISMATCH_TOLERANCE = float(os.getenv("RATE_MISMATCH_TOLERANCE", "0.02"))

# --- LLM config (Phase 2/3) --------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")


_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Deterministic merchant slug used as the isolation key everywhere.

    Lowercases, then collapses every run of non-alphanumeric characters into a
    single hyphen and trims leading/trailing hyphens.

    >>> slugify("Vandelay Industries")
    'vandelay-industries'
    """
    return _SLUG_NON_ALNUM.sub("-", name.strip().lower()).strip("-")
