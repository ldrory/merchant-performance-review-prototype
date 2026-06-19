"""Pydantic contracts (NOT row wrappers).

The pipeline is tabular: KPI rows, profiles, evidence, and the monthly/quarterly
fact tables all live in pandas DataFrames / DuckDB. Pydantic is used only for
*contracts* — things with invariants or a small fixed shape: the input-validation
report, and (in ``registry.py``) the metric definitions. We deliberately do not wrap
every raw or fact row in a model.

The ``Literal`` aliases below are the single source of truth for the categorical
values the engine may emit; ``engine.py`` owns ``FACT_COLUMNS`` (the column set).
For production-grade DataFrame schema validation, Pandera/Great Expectations would
be the natural tool; custom pandas checks + tests are enough for this prototype.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["error", "warning"]
ValueSource = Literal["additive", "provided", "computed"]
ValidationStatus = Literal[
    "ok",
    "mismatch",
    "computed_only",
    "missing_components",
    "additive",
    # quarterly only: aggregate is within tolerance but a contributing month was flagged
    "contains_flagged_month",
]


class ValidationIssue(BaseModel):
    severity: Severity
    code: str
    message: str
    merchant_id: Optional[str] = None


class ValidationReport(BaseModel):
    """Result of **input validation** only (Layer 1). Issues, nothing else.

    Metric-quality warnings live elsewhere (``metrics/quality.py``); this report is purely
    the input gate. Per-merchant errors exclude that merchant; a global error aborts the run.
    """

    issues: list[ValidationIssue] = Field(default_factory=list)

    def add_issue(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def blocked_merchant_ids(self) -> set[str]:
        """Merchants with at least one error (excluded from ingestion)."""
        return {i.merchant_id for i in self.errors if i.merchant_id}
