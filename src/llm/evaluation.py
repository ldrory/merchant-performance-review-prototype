"""Deterministic narrative guardrails — don't trust the prompt alone.

Three cheap, dependency-free checks over the generated narrative:
  * structure    — exec summary present, every KPI covered
  * faithfulness — coarse guard against gross invented numbers
  * language     — customer-safe: no internal/QA terms, no over-strong causal claims

The numbers themselves are already correct by construction (the metric engine computes
them and is unit-tested; the LLM only narrates). These checks are a **gate**: if a
narrative fails, ``deck_generator`` refuses to write the deck (raises ``NarrativeEvalError``).
An LLM-as-judge + human-approval workflow is the production extension, out of scope here.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from src.llm.prompts import build_user_message
from src.presentation.deck_schema import DeckModel

# Coarse faithfulness tuning.
_MATERIAL_FLOOR = 100.0   # below this, numbers are rates/small counts → not checked
_REL_TOLERANCE = 0.01     # material numbers must be within 1% of a value we gave the model
_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")

# Customer-safe language: internal/QA vocabulary that must never reach the merchant.
_BANNED_INTERNAL = (
    "data-quality", "data quality", "mismatch", "provided vs computed",
    "provided-vs-computed", "order-derived", "differs", "validation status",
)
# Over-strong causal claims a CSM deck should avoid.
_BANNED_CAUSAL = (
    "directly attributable", "models appropriately tightened",
    "fraud environment normalized", "demonstrates model robustness",
)
# The "23 of 24 data points" internal-divergence phrasing.
_DATA_POINTS_RE = re.compile(r"\bof\s+\d+\s+data\s+points\b")


def extract_numbers(text: str) -> set[float]:
    """Pull numeric tokens from text, normalizing commas/%/sign to floats."""
    out: set[float] = set()
    for tok in _NUMBER_RE.findall(text):
        try:
            out.add(abs(float(tok.replace(",", ""))))
        except ValueError:
            continue
    return out


def _is_year(n: float) -> bool:
    return n.is_integer() and 1900 <= n <= 2100


class NarrativeEvalError(Exception):
    """Raised when a narrative fails evaluation — the deck must not be produced."""


class FaithfulnessResult(BaseModel):
    ok: bool
    unsupported: list[str] = []


class EvalReport(BaseModel):
    merchant_id: str
    structural_issues: list[str] = []
    faithfulness: FaithfulnessResult
    language_issues: list[str] = []
    ok: bool

    def reason(self) -> str:
        """One-line human reason for a failure (empty when ok)."""
        parts = list(self.structural_issues)
        if self.faithfulness.unsupported:
            parts.append(f"unsupported numbers: {', '.join(self.faithfulness.unsupported)}")
        parts += self.language_issues
        return "; ".join(parts)


def check_structure(deck: DeckModel, narrative) -> list[str]:
    """Exec summary non-empty and every KPI has a non-empty analysis."""
    issues: list[str] = []
    if not [b for b in narrative.executive_summary if b and b.strip()]:
        issues.append("Executive summary is empty.")
    for kpi in deck.kpis:
        text = narrative.kpi_analysis.get(kpi.metric_id, "")
        if not text or not text.strip():
            issues.append(f"Missing analysis for KPI '{kpi.metric_id}'.")
    return issues


def check_faithfulness(deck: DeckModel, narrative) -> FaithfulnessResult:
    """Coarse: flag only *material* numbers (counts/volumes) absent from the values we
    handed the model. Years, small magnitudes (rates/small counts) and rounding are tolerated."""
    allowed = extract_numbers(build_user_message(deck))
    text = " ".join(narrative.executive_summary) + " " + " ".join(narrative.kpi_analysis.values())

    unsupported: list[str] = []
    for n in extract_numbers(text):
        if _is_year(n) or n <= _MATERIAL_FLOOR:
            continue  # periods/dates, rates, small counts — rounding-prone, not checked
        supported = any(
            abs(n - a) <= _REL_TOLERANCE * max(abs(a), 1.0) for a in allowed
        )
        if not supported:
            unsupported.append(f"{n:,.0f}")
    return FaithfulnessResult(ok=not unsupported, unsupported=unsupported)


def check_language(narrative) -> list[str]:
    """Flag internal/QA vocabulary or over-strong causal claims (customer-facing gate)."""
    text = (" ".join(narrative.executive_summary) + " "
            + " ".join(narrative.kpi_analysis.values())).lower()
    issues: list[str] = []
    for term in _BANNED_INTERNAL + _BANNED_CAUSAL:
        if term in text:
            issues.append(f"banned phrase: '{term}'")
    if _DATA_POINTS_RE.search(text):
        issues.append("banned phrase: internal 'data points' count")
    return issues


def evaluate_narrative(deck: DeckModel, narrative) -> EvalReport:
    """Combine the deterministic checks into one report (the deck generator gates on it)."""
    structural = check_structure(deck, narrative)
    faithfulness = check_faithfulness(deck, narrative)
    language = check_language(narrative)
    return EvalReport(
        merchant_id=deck.merchant_id,
        structural_issues=structural,
        faithfulness=faithfulness,
        language_issues=language,
        ok=(not structural) and faithfulness.ok and (not language),
    )
