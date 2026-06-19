"""Single source of visual style — shared by matplotlib charts and python-pptx slides.

Keeping one theme here is how every merchant's deck gets a consistent look & feel.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # non-interactive backend (headless / tests)
import matplotlib.pyplot as plt  # noqa: E402

# --- Brand palette (hex) -----------------------------------------------------
NAVY = "#0B2545"      # primary / titles
BLUE = "#2E6FB7"      # primary series
TEAL = "#1B998B"      # positive / good
AMBER = "#E8A33D"     # caution
RED = "#D7263D"       # negative / bad
GREY = "#6B7280"      # axes / secondary text
LIGHT = "#EEF2F7"     # backgrounds / gridlines
EVIDENCE = "#7C3AED"  # evidence annotations (violet) — context, distinct from any data series

FONT_FAMILY = "DejaVu Sans"  # ships with matplotlib; avoids missing-font warnings

# Chart canvas
CHART_DPI = 150
CHART_FIGSIZE = (6.4, 3.4)


def apply_matplotlib_theme() -> None:
    """Apply the shared rcParams so all charts render identically."""
    plt.rcParams.update({
        "figure.dpi": CHART_DPI,
        "savefig.dpi": CHART_DPI,
        "font.family": FONT_FAMILY,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlecolor": NAVY,
        "axes.edgecolor": GREY,
        "axes.labelcolor": GREY,
        "axes.grid": True,
        "grid.color": LIGHT,
        "grid.linewidth": 1.0,
        "xtick.color": GREY,
        "ytick.color": GREY,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def good_bad_color(higher_is_better: bool | None, going_up: bool) -> str:
    """Color a trend by whether its direction is good for the metric."""
    if higher_is_better is None:
        return BLUE
    improving = (going_up and higher_is_better) or (not going_up and not higher_is_better)
    return TEAL if improving else RED


# --- python-pptx constants (RGB tuples) --------------------------------------
PPTX_NAVY = (0x0B, 0x25, 0x45)
PPTX_BLUE = (0x2E, 0x6F, 0xB7)
PPTX_GREY = (0x6B, 0x72, 0x80)
PPTX_RED = (0xD7, 0x26, 0x3D)
PPTX_TEAL = (0x1B, 0x99, 0x8B)
PPTX_AMBER = (0xE8, 0xA3, 0x3D)
PPTX_LIGHT = (0xEE, 0xF2, 0xF7)  # card / panel background
PPTX_WHITE = (0xFF, 0xFF, 0xFF)
PPTX_TITLE_FONT = "Calibri"
PPTX_BODY_FONT = "Calibri"
