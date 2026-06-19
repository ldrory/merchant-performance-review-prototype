"""Quality summary — one consistent schema, produced per process.

Each process emits the layers it actually runs:
  * ingest  → Layer 1 (Input Validation), Layer 2 (Metric Computation Integrity, if it ran),
              Layer 3 (Metric Quality, if facts were computed).
  * decks   → Layer 4 (Narrative Evaluation), plus a consolidated merge of the latest ingest
              summary + the deck summary.

No DB table, no modes, no audit system — just `QualitySummary` objects serialized to JSON.
Layers that did not run are omitted (never faked); `overall_status` is computed only from the
layers present. The per-deck `<deck>.eval.json` is the Layer-4 per-merchant subset.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel

from src.metrics.quality import find_broken_metric_merchants, summarize_metric_quality
from src.models import ValidationReport

Status = Literal["PASS", "WARN", "FAIL"]
Stage = Literal["ingest", "decks", "consolidated"]

# Validation issue codes that are about *computing the metric* (Layer 2), not raw input sanity.
_COMPUTATION_CODES = {"missing_kpi", "zero_denominator"}


class NarrativeResult(BaseModel):
    """Per-merchant Layer-4 outcome from the deck run."""
    merchant_id: str
    ok: bool
    reason: str = ""


class LayerResult(BaseModel):
    layer: int
    name: str
    type: Literal["gate", "note"]  # "gate" blocks; "note" is informational (non-blocking)
    blocking: bool
    status: Status
    summary: str
    details: list[str] = []


class QualitySummary(BaseModel):
    stage: Stage
    version: str
    generated_at: str
    overall_status: Status
    layers: list[LayerResult]


def overall_status(layers: list[LayerResult]) -> Status:
    if any(l.blocking and l.status == "FAIL" for l in layers):
        return "FAIL"
    if any(l.status == "WARN" for l in layers):
        return "WARN"
    return "PASS"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summary(stage: Stage, version: str, layers: list[LayerResult]) -> QualitySummary:
    return QualitySummary(
        stage=stage, version=version, generated_at=_now(),
        overall_status=overall_status(layers), layers=layers,
    )


# --- per-layer builders ------------------------------------------------------

def input_validation_layer(report: ValidationReport) -> LayerResult:
    issues = [i for i in report.issues if i.code not in _COMPUTATION_CODES]
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    status: Status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return LayerResult(
        layer=1, name="Input Validation", type="gate", blocking=True, status=status,
        summary=f"{len(errors)} error(s), {len(warnings)} warning(s)",
        details=[f"[{i.severity}] {i.code}: {i.message}" for i in issues],
    )


def metric_computation_layer(report: ValidationReport, facts: pd.DataFrame) -> LayerResult:
    issues = [i for i in report.issues if i.code in _COMPUTATION_CODES]
    broken = find_broken_metric_merchants(facts) if facts is not None and not facts.empty else {}
    details = [f"[{i.severity}] {i.code}: {i.message}" for i in issues]
    details += [f"uncomputable: {mid} ({reason})" for mid, reason in sorted(broken.items())]
    status: Status = "FAIL" if (issues or broken) else "PASS"
    return LayerResult(
        layer=2, name="Metric Computation Integrity", type="gate", blocking=True, status=status,
        summary=f"{len(issues)} input issue(s), {len(broken)} uncomputable merchant(s)",
        details=details,
    )


def metric_quality_layer(facts: pd.DataFrame) -> LayerResult:
    notes = summarize_metric_quality(facts) if facts is not None else []
    status: Status = "WARN" if notes else "PASS"
    return LayerResult(
        layer=3, name="Metric Quality", type="note", blocking=False, status=status,
        summary=f"{len(notes)} metric(s) with provided-vs-computed differences",
        details=notes,
    )


def narrative_layer(results: list[NarrativeResult]) -> LayerResult:
    failed = [r for r in results if not r.ok]
    status: Status = "FAIL" if failed else "PASS"
    details = [f"{r.merchant_id}: {'PASS' if r.ok else 'FAIL — ' + r.reason}" for r in results]
    return LayerResult(
        layer=4, name="Narrative Evaluation", type="gate", blocking=True, status=status,
        summary=f"{len(results) - len(failed)}/{len(results)} deck(s) passed",
        details=details,
    )


# --- per-stage assemblers ----------------------------------------------------

def ingest_summary(
    version: str,
    report: ValidationReport,
    facts: Optional[pd.DataFrame],
    *,
    validation_complete: bool,
    facts_computed: bool,
) -> QualitySummary:
    """Ingest-owned layers. Only includes the layers that actually ran (no faking)."""
    layers = [input_validation_layer(report)]
    if validation_complete:
        layers.append(metric_computation_layer(report, facts if facts is not None else pd.DataFrame()))
        if facts_computed and facts is not None:
            layers.append(metric_quality_layer(facts))
    return _summary("ingest", version, layers)


def deck_summary(version: str, results: list[NarrativeResult]) -> QualitySummary:
    """Deck-owned layer (Layer 4)."""
    return _summary("decks", version, [narrative_layer(results)])


def consolidated_summary(
    version: str,
    ingest: Optional[QualitySummary],
    decks: QualitySummary,
) -> QualitySummary:
    """Merge the latest ingest layers (1-3) with the deck layers (4). Omits 1-3 if no ingest
    artifact is available — never fabricates them."""
    layers = (list(ingest.layers) if ingest else []) + list(decks.layers)
    return _summary("consolidated", version, layers)
