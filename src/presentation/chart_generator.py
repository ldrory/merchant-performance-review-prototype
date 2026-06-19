"""Render per-KPI charts (matplotlib) for a merchant's deck.

For each KPI: a monthly trend line (with evidence-event annotations) and a quarterly bar
chart, using the count (transaction-volume) view. For Strategic merchants, rate KPIs also
overlay the amount-weighted (submitted-value) series — both are percentages — with a clear
"Count-based" / "Amount-weighted" legend. Submission Volume is count-only (its amount view is
a dollar figure with a different unit, shown on the slide cards rather than a dual axis). All
styling comes from ``theme`` for a consistent look & feel.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter

from src.presentation import theme
from src.presentation.deck_schema import DeckModel, KpiInsight

_COUNT_LABEL = "Count-based"
_AMOUNT_LABEL = "Amount-weighted"


def _has_amount_overlay(insight: KpiInsight) -> bool:
    """Overlay both series only when units match (rate KPIs); never for volume ($ vs orders)."""
    return insight.amount is not None and insight.unit == "rate"


def _decimals_for(insight: KpiInsight) -> int:
    """Chargeback rates are tiny → show more precision so the axis is readable."""
    return 2 if insight.metric_id == "accepted_chargeback_rate" else 1


def _format_axis(ax, unit: str, decimals: int = 1) -> None:
    if unit == "rate":
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=decimals))
    else:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))


def _line_headroom(ax, values, *, top=0.30, bottom=0.08) -> None:
    """Pad the y-range so the top data point clears the title and leaves room for labels."""
    vals = [v for v in values if v is not None]
    if not vals:
        return
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or (abs(hi) or 1.0)
    ax.set_ylim(lo - bottom * rng, hi + top * rng)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _annotate_evidence(ax, x, y, evidence) -> None:
    """Mark evidence events as context: violet (never a series color), with alternating
    label heights and a thin connector so labels don't collide with the title or each other."""
    k = 0
    for i, period in enumerate(x):
        if period not in evidence:
            continue
        dy = 16 if k % 2 == 0 else 34  # stagger so adjacent labels don't overlap
        ax.annotate(
            evidence[period], xy=(i, y[i]), xytext=(0, dy), textcoords="offset points",
            ha="center", fontsize=7, color=theme.EVIDENCE, fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=theme.EVIDENCE, lw=0.8, alpha=0.6),
        )
        ax.scatter([i], [y[i]], color=theme.EVIDENCE, zorder=5, s=28)
        k += 1


def _monthly_chart(insight: KpiInsight, evidence: dict[str, str], path: Path) -> Path:
    fig, ax = plt.subplots(figsize=theme.CHART_FIGSIZE)
    x, y = insight.monthly_periods, insight.monthly_values
    series_vals = list(y)

    if _has_amount_overlay(insight):
        ax.plot(x, y, marker="o", color=theme.BLUE, linewidth=2, label=_COUNT_LABEL)
        a = insight.amount
        ax.plot(a.monthly_periods, a.monthly_values, marker="s", linestyle="--",
                color=theme.AMBER, linewidth=2, label=_AMOUNT_LABEL)
        series_vals += list(a.monthly_values)
        ax.legend(fontsize=8, loc="upper left", frameon=False)
    else:
        color = theme.good_bad_color(insight.higher_is_better, (y[-1] >= y[0]) if y else True)
        ax.plot(x, y, marker="o", color=color, linewidth=2)

    _line_headroom(ax, series_vals)
    _format_axis(ax, insight.unit, _decimals_for(insight))
    ax.set_title(f"{insight.metric_name} — Monthly", pad=14)
    ax.set_xticks(range(len(x)))
    ax.set_xticklabels(x, rotation=45, ha="right", fontsize=7)
    _annotate_evidence(ax, x, y, evidence)
    return _save(fig, path)


def _quarterly_chart(insight: KpiInsight, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=theme.CHART_FIGSIZE)
    q, v = insight.quarterly_periods, insight.quarterly_values
    vals = list(v)

    if _has_amount_overlay(insight):
        pos = list(range(len(q)))
        w = 0.4
        ax.bar([p - w / 2 for p in pos], v, width=w, color=theme.BLUE, label=_COUNT_LABEL)
        a = insight.amount
        ax.bar([p + w / 2 for p in pos], a.quarterly_values, width=w,
               color=theme.AMBER, label=_AMOUNT_LABEL)
        vals += list(a.quarterly_values)
        ax.set_xticks(pos)
        ax.set_xticklabels(q)
        ax.legend(fontsize=8, loc="upper left", frameon=False)
    else:
        ax.bar(q, v, color=theme.BLUE, width=0.6)

    nz = [x for x in vals if x is not None]
    if nz:  # bars start at 0; add top headroom so the legend/labels don't crowd the bars
        ax.set_ylim(0, max(nz) * 1.20)
    _format_axis(ax, insight.unit, _decimals_for(insight))
    ax.set_title(f"{insight.metric_name} — Quarterly", pad=14)
    ax.tick_params(axis="x", labelsize=8)
    return _save(fig, path)


def render_charts(deck: DeckModel, out_dir: Path | str) -> dict[str, dict[str, Path]]:
    """Render all charts for a merchant into ``out_dir``.

    Returns ``{metric_id: {"monthly": path, "quarterly": path}}``. ``out_dir`` is the final
    (already merchant/version-specific) folder — the caller owns the path layout.
    """
    theme.apply_matplotlib_theme()
    folder = Path(out_dir)
    evidence = {e.period: e.event for e in deck.evidence}

    charts: dict[str, dict[str, Path]] = {}
    for insight in deck.kpis:
        charts[insight.metric_id] = {
            "monthly": _monthly_chart(insight, evidence, folder / f"{insight.metric_id}_monthly.png"),
            "quarterly": _quarterly_chart(insight, folder / f"{insight.metric_id}_quarterly.png"),
        }
    return charts
