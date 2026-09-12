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

    expr_parts = [f"coalesce(try(to_real({expr}), 0.0), 0.0)" for expr, _, _ in slices]
    total_expr = " + ".join(expr_parts)

    circles = []
    # Base background ring
    circles.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="%23e2e8f0" stroke-width="{stroke_width/4.0:.1f}"/>'
    )

    offset_expr = "25.0"  # start at 12 o'clock
    for expr, _, color in slices:
        safe_clr = color.replace("#", "%23")
        safe_val = f"coalesce(try(to_real({expr}), 0.0), 0.0)"
        pct = f"clamp(0.0, round(100.0 * ({safe_val}) / (nullif({total_expr}, 0.0)), 1), 100.0)"
        circles.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{safe_clr}" '
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
    # Use single quotes for outer HTML src to prevent collision with inner SVG double quotes
    return f"<img src='data:image/svg+xml;utf8,{svg}' width='{size}' height='{size}' />"


def build_svg_sparkline(
    fields: list[str],
    width: int = 140,
    height: int = 28,
    bar_color: str = "#10b981",
    bg_color: str = "#f1f5f9",
) -> str:
    """Return an SVG mini bar sparkline for sequential/temporal fields."""
    if not fields:
        return ""

    n = len(fields)
    step = width / n
    bar_w = max(4.0, step - 3.0)

    # Use QGIS max() expression (NOT greatest) with numeric coercion and safe minimum floor
    field_coalesced = [f'coalesce(try(to_real("{f}"), 0.0), 0.0)' for f in fields]
    max_expr = f"max(0.001, {', '.join(field_coalesced)})"

    safe_bar_clr = bar_color.replace("#", "%23")
    safe_bg_clr = bg_color.replace("#", "%23")

    bars = []
    for idx, f in enumerate(fields):
        x = idx * step + 1.5
        val_expr = f'coalesce(try(to_real("{f}"), 0.0), 0.0)'
        h_expr = f"clamp(2.0, round({height - 4} * ({val_expr}) / (nullif({max_expr}, 0.0)), 1), {height - 4})"
        y_expr = f"({height - 2} - {h_expr})"

        bars.append(
            f'<rect x="{x:.1f}" y="[% {y_expr} %]" width="{bar_w:.1f}" height="[% {h_expr} %]" '
            f'rx="2" fill="{safe_bar_clr}" opacity="0.9"/>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="{safe_bg_clr}" rx="3"/>'
        f'{"".join(bars)}'
        f'</svg>'
    )
    # Use single quotes for outer HTML src to prevent collision with inner SVG double quotes
    return f"<img src='data:image/svg+xml;utf8,{svg}' width='{width}' height='{height}' />"


def build_svg_media_placeholder(
    width: int = 280,
    height: int = 120,
    bg_color: str = "#f8fafc",
    border_color: str = "#e2e8f0",
    text_color: str = "#64748b",
) -> str:
    """Return an inline SVG data-URI placeholder for missing images with a modern camera glyph and label."""
    cx = width / 2.0
    cy = height / 2.0 - 10.0
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="{bg_color}" stroke="{border_color}" stroke-width="1" rx="6"/>'
        f'<g fill="none" stroke="{text_color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M {cx - 15:.1f} {cy - 6:.1f} a 3 3 0 0 1 3 -3 h 4 l 2 -3 h 12 l 2 3 h 4 a 3 3 0 0 1 3 3 v 16 a 3 3 0 0 1 -3 3 h -24 a 3 3 0 0 1 -3 -3 z"/>'
        f'<circle cx="{cx:.1f}" cy="{cy + 2:.1f}" r="5"/>'
        f'</g>'
        f'<text x="{cx:.1f}" y="{cy + 26:.1f}" font-family="Segoe UI, sans-serif" font-size="10" font-weight="600" fill="{text_color}" text-anchor="middle">No Photo Available</text>'
        f'</svg>'
    )
    return f'data:image/svg+xml;utf8,{svg}'
