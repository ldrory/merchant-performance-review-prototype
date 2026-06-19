"""Declarative KPI definitions — the single place that maps business KPIs to the
raw measure names in the data. Extending the product = adding entries here.

Templates may contain ``{prefix}`` which the engine resolves to the merchant's
"Pre" or "Post" authorization stage. ``Sum`` variants are ``strategic_only``.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class MetricVariant(BaseModel):
    model_config = ConfigDict(frozen=True)

    suffix: Literal["cnt", "sum"]
    kind: Literal["additive", "ratio"]
    source_kpi: Optional[str] = None  # additive
    numerator_kpi: Optional[str] = None  # ratio
    denominator_kpi: Optional[str] = None  # ratio
    provided_rate_kpi: Optional[str] = None  # ratio with a precomputed rate in the data
    strategic_only: bool = False

    @model_validator(mode="after")
    def _check_shape(self) -> "MetricVariant":
        if self.kind == "additive":
            if not self.source_kpi:
                raise ValueError("additive variant must define source_kpi")
            if self.numerator_kpi or self.denominator_kpi or self.provided_rate_kpi:
                raise ValueError("additive variant must not define ratio fields")
        else:  # ratio
            if not (self.numerator_kpi and self.denominator_kpi):
                raise ValueError("ratio variant must define numerator_kpi and denominator_kpi")
            if self.source_kpi:
                raise ValueError("ratio variant must not define source_kpi")
        return self


class MetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    variants: tuple[MetricVariant, ...]
    # Direction that is "good" for narrative phrasing/coloring: True = up is good,
    # False = down is good, None = neutral (e.g. volume).
    higher_is_better: bool | None = None


def resolve(template: str | None, pre_or_post: str) -> str | None:
    """Fill the ``{prefix}`` placeholder with the merchant's Pre/Post stage."""
    if template is None:
        return None
    return template.format(prefix=pre_or_post)


def _expand(template: str, into: set[str]) -> None:
    if "{prefix}" in template:
        into.add(template.format(prefix="Pre"))
        into.add(template.format(prefix="Post"))
    else:
        into.add(template)


def required_raw_kpi_names() -> set[str]:
    """Every raw KPI name the registry references, with ``{prefix}`` expanded to
    both Pre and Post. This is the expected-completeness contract for the raw grid.
    """
    names: set[str] = set()
    for mdef in METRIC_REGISTRY:
        for v in mdef.variants:
            for tmpl in (v.source_kpi, v.numerator_kpi, v.denominator_kpi, v.provided_rate_kpi):
                if tmpl is not None:
                    _expand(tmpl, names)
    return names


def denominator_kpi_names() -> set[str]:
    """Raw KPI names used as ratio denominators (must be > 0 to compute a rate)."""
    names: set[str] = set()
    for mdef in METRIC_REGISTRY:
        for v in mdef.variants:
            if v.denominator_kpi is not None:
                _expand(v.denominator_kpi, names)
    return names


METRIC_REGISTRY: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        id="submission_volume",
        name="Submission Volume",
        variants=(
            MetricVariant(suffix="cnt", kind="additive", source_kpi="Submitted Cnt"),
            MetricVariant(suffix="sum", kind="additive", source_kpi="Submitted Sum", strategic_only=True),
        ),
    ),
    MetricDefinition(
        id="approval_rate",
        name="Approval Rate",
        higher_is_better=True,
        variants=(
            MetricVariant(
                suffix="cnt", kind="ratio",
                provided_rate_kpi="{prefix} Auth Approval Rate Cnt",
                numerator_kpi="CHBG {prefix} Auth Approved Cnt",
                denominator_kpi="Submitted Cnt",
            ),
            MetricVariant(
                suffix="sum", kind="ratio", strategic_only=True,
                provided_rate_kpi="{prefix} Auth Approval Rate Sum",
                numerator_kpi="CHBG {prefix} Auth Approved Sum",
                denominator_kpi="Submitted Sum",
            ),
        ),
    ),
    MetricDefinition(
        id="accepted_chargeback_rate",
        name="Accepted Chargeback Rate",
        higher_is_better=False,
        variants=(
            MetricVariant(
                suffix="cnt", kind="ratio",
                provided_rate_kpi="Accepted Chargebacks Rate Cnt",
                numerator_kpi="Accepted Chargeback Cnt",
                denominator_kpi="Submitted Cnt",
            ),
            MetricVariant(
                suffix="sum", kind="ratio", strategic_only=True,
                provided_rate_kpi="Accepted Chargebacks Rate Sum",
                numerator_kpi="Accepted Chargeback Sum",
                denominator_kpi="Submitted Sum",
            ),
        ),
    ),
    MetricDefinition(
        id="effective_fraud_rate",
        name="Effective Fraud Rate",
        higher_is_better=False,
        variants=(
            MetricVariant(
                suffix="cnt", kind="ratio",
                numerator_kpi="Effective Fraud Cnt",
                denominator_kpi="Submitted Cnt",
            ),
            MetricVariant(
                suffix="sum", kind="ratio", strategic_only=True,
                numerator_kpi="Effective Fraud Sum",
                denominator_kpi="Submitted Sum",
            ),
        ),
    ),
)
