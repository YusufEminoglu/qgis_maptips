"""Zero-dependency micro-chart generator for QGIS MapTips.

Produces Qt-safe HTML nested tables and pure SVG data-URIs that render natively
inside QGIS QTextDocument without external JavaScript, WebKit, or network requests.
"""
from __future__ import annotations

import html


def build_progress_bar_table(
    val_expr: str,
    max_val_expr: str = "100",
    bar_color: str = "#10b981",
    bg_color: str = "#e2e8f0",
    height_px: int = 10,
    show_label: bool = True,
) -> str:
    """Return a 100% width Qt-safe HTML progress bar using nested table cells."""
    safe_val = val_expr.strip()
    safe_max = max_val_expr.strip()
    pct_expr = f"clamp(0.0, round(100.0 * (coalesce({safe_val}, 0)) / (nullif({safe_max}, 0)), 1), 100.0)"
    rem_expr = f"(100.0 - {pct_expr})"

    label_row = ""
    if show_label:
        label_row = (
            f'<tr><td colspan="2" style="font-size:9px; color:#64748b; padding-bottom:2px;">'
            f'[% {safe_val} %] / [% {safe_max} %] ([% {pct_expr} %]%)</td></tr>'
        )

    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:4px; margin-bottom:4px;">'
        f'{label_row}'
        f'<tr><td width="100%" style="background-color:{bg_color}; height:{height_px}px; border:1px solid {bg_color};">'
        f'<table width="100%" cellspacing="0" cellpadding="0" style="height:{height_px}px;"><tr>'
        f'<td width="[% {pct_expr} %]%" bgcolor="{bar_color}"></td>'
        f'<td width="[% {rem_expr} %]%" bgcolor="{bg_color}"></td>'
        f'</tr></table>'
        f'</td></tr></table>'
    )


def build_segmented_bar_table(
    segments: list[tuple[str, str, str]],
    height_px: int = 12,
) -> str:
    """Return a multi-segment horizontal bar table for 2-4 complementary values.

    segments: list of (field_or_expr, label, hex_color)
    """
    if not segments:
        return ""

    expr_parts = [f"coalesce({expr}, 0)" for expr, _, _ in segments]
    total_expr = " + ".join(expr_parts)

    cells = []
    legend_items = []
    for expr, label, color in segments:
        pct_expr = f"clamp(0.0, round(100.0 * (coalesce({expr}, 0)) / (nullif({total_expr}, 0)), 1), 100.0)"
        cells.append(f'<td width="[% {pct_expr} %]%" bgcolor="{color}" title="{html.escape(label)}"></td>')
        legend_items.append(
            f'<span style="color:{color}; font-weight:bold;">&#9632;</span> '
            f'<span style="color:#475569; font-size:9px;">{html.escape(label)}: [% {expr} %]</span>'
        )

    cells_html = "".join(cells)
    legend_html = " &nbsp;&nbsp; ".join(legend_items)

    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:4px; margin-bottom:4px;">'
        f'<tr><td style="font-size:9px; padding-bottom:3px;">{legend_html}</td></tr>'
        f'<tr><td>'
        f'<table width="100%" cellspacing="0" cellpadding="0" style="height:{height_px}px; border-collapse:collapse;">'
        f'<tr>{cells_html}</tr>'
        f'</table>'
        f'</td></tr></table>'
    )


def build_svg_donut_data_uri(
    slices: list[tuple[str, str, str]],
    size: int = 80,
    stroke_width: int = 16,
) -> str:
    """Return an SVG donut data-URI image evaluated via QGIS expression.

    Circumference is 100 with radius = 15.9155 so stroke-dasharray directly maps to percentage.
    """
    if not slices:
        return ""

    r = 15.9155
    cx, cy = 21, 21
    viewbox = "0 0 42 42"

    expr_parts = [f"coalesce({expr}, 0)" for expr, _, _ in slices]
    total_expr = " + ".join(expr_parts)

    circles = []
    # Base background ring
    circles.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e2e8f0" stroke-width="{stroke_width/4.0:.1f}"/>'
    )

    offset_expr = "25.0"  # start at 12 o'clock
    for expr, _, color in slices:
        pct = f"clamp(0.0, round(100.0 * (coalesce({expr}, 0)) / (nullif({total_expr}, 0)), 1), 100.0)"
        circles.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke_width/4.0:.1f}" '
            f'stroke-dasharray="[% {pct} %] [% 100.0 - ({pct}) %]" '
            f'stroke-dashoffset="[% {offset_expr} %]"/>'
        )
        offset_expr = f"({offset_expr} - ({pct}))"

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="{viewbox}">'
        f'{"".join(circles)}'
        f'</svg>'
    )
    return f'<img src="data:image/svg+xml;utf8,{svg}" width="{size}" height="{size}" />'
