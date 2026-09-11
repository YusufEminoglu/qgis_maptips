"""Universal MapTip HTML template engine.

Generates production-grade, Qt QTextDocument-compliant HTML tables with
responsive cell widths, color themes, inline micro-charts, conditional status
badges, and cross-layer relational aggregations.
"""
from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .chart_engine import (
    build_progress_bar_table,
    build_segmented_bar_table,
    build_svg_donut_data_uri,
    build_svg_sparkline,
)


class Archetype(str, Enum):
    KPI_CARD = "kpi_card"
    PROGRESS_BAR = "progress_bar"
    DONUT_CHART = "donut_chart"
    SPARKLINE = "sparkline"
    MEDIA_CARD = "media_card"
    CLEAN_TABLE = "clean_table"
    RASTER_HUD = "raster_hud"


PALETTES = {
    "emerald": {
        "name": "Emerald Studio",
        "header_bg": "#0f766e",
        "header_text": "#ffffff",
        "sub_bg": "#115e59",
        "sub_text": "#ccfbf1",
        "accent": "#10b981",
        "card_bg": "#ffffff",
        "row_alt": "#f8fafc",
        "text_primary": "#0f172a",
        "text_secondary": "#64748b",
        "border": "#e2e8f0",
    },
    "blue": {
        "name": "Classic Blue",
        "header_bg": "#1e40af",
        "header_text": "#ffffff",
        "sub_bg": "#1d4ed8",
        "sub_text": "#dbeafe",
        "accent": "#3b82f6",
        "card_bg": "#ffffff",
        "row_alt": "#f8fafc",
        "text_primary": "#0f172a",
        "text_secondary": "#64748b",
        "border": "#e2e8f0",
    },
    "slate": {
        "name": "Dark Slate",
        "header_bg": "#0f172a",
        "header_text": "#ffffff",
        "sub_bg": "#1e293b",
        "sub_text": "#94a3b8",
        "accent": "#38bdf8",
        "card_bg": "#ffffff",
        "row_alt": "#f8fafc",
        "text_primary": "#0f172a",
        "text_secondary": "#64748b",
        "border": "#cbd5e1",
    },
    "crimson": {
        "name": "Crimson Alert",
        "header_bg": "#991b1b",
        "header_text": "#ffffff",
        "sub_bg": "#b91c1c",
        "sub_text": "#fee2e2",
        "accent": "#ef4444",
        "card_bg": "#ffffff",
        "row_alt": "#f8fafc",
        "text_primary": "#0f172a",
        "text_secondary": "#64748b",
        "border": "#fecaca",
    },
    "purple": {
        "name": "Modern Purple",
        "header_bg": "#5b21b6",
        "header_text": "#ffffff",
        "sub_bg": "#6d28d9",
        "sub_text": "#ede9fe",
        "accent": "#8b5cf6",
        "card_bg": "#ffffff",
        "row_alt": "#f8fafc",
        "text_primary": "#0f172a",
        "text_secondary": "#64748b",
        "border": "#ddd6fe",
    },
}


@dataclass
class TemplateConfig:
    archetype: Archetype = Archetype.KPI_CARD
    palette_key: str = "emerald"
    card_width: int = 320
    title_field: str = ""
    subtitle_field: str = ""
    kpi_field: str = ""
    kpi_label: str = ""
    kpi_unit: str = ""
    progress_max_expr: str = "100"
    donut_fields: list[tuple[str, str, str]] = field(default_factory=list)  # (field, label, color)
    sparkline_fields: list[str] = field(default_factory=list)
    media_field: str = ""
    attribute_fields: list[tuple[str, str]] = field(default_factory=list)  # (field_name, display_label)
    # Conditional formatting rule: field name, threshold, condition (>, <, ==), badge_color, badge_label
    conditional_rules: list[dict[str, Any]] = field(default_factory=list)
    # Cross-layer relational metrics: target_layer, op, aggregate, field, label
    relational_metrics: list[dict[str, Any]] = field(default_factory=list)
    footer_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["archetype"] = self.archetype.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateConfig:
        clean = dict(data)
        if "archetype" in clean:
            clean["archetype"] = Archetype(clean["archetype"])
        return cls(**clean)

    def save_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, path: Path | str) -> TemplateConfig:
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


def build_conditional_badge_html(rule: dict[str, Any]) -> str:
    """Build a dynamic status badge using QGIS CASE WHEN expression."""
    fld = rule.get("field", "")
    op = rule.get("op", ">")
    val = rule.get("val", "0")
    color_true = rule.get("color_true", "#ef4444")
    color_false = rule.get("color_false", "#10b981")
    label_true = html.escape(rule.get("label_true", "Alert"))
    label_false = html.escape(rule.get("label_false", "Normal"))

    expr_bg = f"CASE WHEN (\"{fld}\" {op} {val}) THEN '{color_true}' ELSE '{color_false}' END"
    expr_lbl = f"CASE WHEN (\"{fld}\" {op} {val}) THEN '{label_true}' ELSE '{label_false}' END"

    return (
        f'<tr><td colspan="2" align="center" style="padding:4px 8px; border-bottom:1px solid #e2e8f0;">'
        f'<table cellspacing="0" cellpadding="0" style="margin:2px auto;"><tr>'
        f'<td bgcolor="[% {expr_bg} %]" style="color:#ffffff; font-size:9px; font-weight:bold; '
        f'padding:2px 8px; border-radius:3px; text-align:center;">'
        f'[% {expr_lbl} %]'
        f'</td></tr></table>'
        f'</td></tr>'
    )


def build_relational_metric_row(metric: dict[str, Any], pal: dict[str, str], row_bg: str) -> str:
    """Build a relational/spatial aggregate row linking to another project layer."""
    target_layer = metric.get("target_layer", "")
    op = metric.get("op", "intersects")
    agg = metric.get("aggregate", "count")
    fld = metric.get("field", "id")
    label = html.escape(metric.get("label", f"{agg.title()} in {target_layer}"))

    if op == "intersects" and agg == "count":
        expr = f"coalesce(overlay_intersects('{target_layer}', count:=\"{fld}\"), 0)"
    elif op == "intersects":
        expr = f"coalesce(overlay_intersects('{target_layer}', expression:=\"{fld}\", aggregate:='{agg}'), 0)"
    elif op == "contains" and agg == "count":
        expr = f"coalesce(overlay_contains('{target_layer}', count:=\"{fld}\"), 0)"
    elif op == "nearest":
        expr = f"coalesce(overlay_nearest('{target_layer}', \"{fld}\")[0], 'None')"
    else:
        expr = f"coalesce(overlay_intersects('{target_layer}', count:=\"{fld}\"), 0)"

    return (
        f'<tr bgcolor="{row_bg}">'
        f'<td width="50%" style="color:{pal["text_secondary"]}; font-size:10px; '
        f'padding:3px 8px; border-bottom:1px solid {pal["border"]};">&#128279; {label}</td>'
        f'<td width="50%" align="right" style="color:{pal["accent"]}; font-size:10px; '
        f'font-weight:bold; padding:3px 8px; border-bottom:1px solid {pal["border"]};">'
        f'[% {expr} %]</td>'
        f'</tr>'
    )


def compile_maptip_html(config: TemplateConfig) -> str:
    """Compile TemplateConfig into a strict Qt-compatible HTML MapTip template."""
    pal = PALETTES.get(config.palette_key, PALETTES["emerald"])
    w = max(240, min(600, config.card_width))

    lines = []
    lines.append(
        f'<table width="{w}" cellspacing="0" cellpadding="0" '
        f'style="font-family:Segoe UI, sans-serif; background-color:{pal["card_bg"]}; '
        f'border:1px solid {pal["border"]}; border-collapse:collapse;">'
    )

    # 1. Header Banner
    title_expr = f'[% "{config.title_field}" %]' if config.title_field else "Feature Information"
    lines.append(
        f'<tr><td colspan="2" bgcolor="{pal["header_bg"]}" '
        f'style="color:{pal["header_text"]}; font-size:12px; font-weight:bold; padding:6px 8px;">'
        f'{title_expr}</td></tr>'
    )

    # Subtitle Row
    if config.subtitle_field:
        lines.append(
            f'<tr><td colspan="2" bgcolor="{pal["sub_bg"]}" '
            f'style="color:{pal["sub_text"]}; font-size:10px; padding:3px 8px;">'
            f'[% "{config.subtitle_field}" %]</td></tr>'
        )

    # Conditional Status Badges
    for rule in config.conditional_rules:
        lines.append(build_conditional_badge_html(rule))

    # 2. Archetype-specific Body Section
    if config.archetype == Archetype.KPI_CARD and config.kpi_field:
        kpi_lbl = html.escape(config.kpi_label or config.kpi_field)
        unit = f" {html.escape(config.kpi_unit)}" if config.kpi_unit else ""
        lines.append(
            f'<tr><td colspan="2" style="padding:8px 8px 4px 8px; text-align:center; '
            f'background-color:{pal["row_alt"]}; border-bottom:1px solid {pal["border"]};">'
            f'<div style="font-size:10px; color:{pal["text_secondary"]}; text-transform:uppercase;">{kpi_lbl}</div>'
            f'<div style="font-size:18px; font-weight:bold; color:{pal["accent"]}; margin-top:2px;">'
            f'[% "{config.kpi_field}" %]{unit}</div>'
            f'</td></tr>'
        )

    elif config.archetype == Archetype.PROGRESS_BAR and config.kpi_field:
        kpi_lbl = html.escape(config.kpi_label or config.kpi_field)
        unit = f" {html.escape(config.kpi_unit)}" if config.kpi_unit else ""
        bar_html = build_progress_bar_table(
            val_expr=f'"{config.kpi_field}"',
            max_val_expr=config.progress_max_expr or "100",
            bar_color=pal["accent"],
            bg_color=pal["border"],
            height_px=10,
            show_label=True,
        )
        lines.append(
            f'<tr><td colspan="2" style="padding:6px 8px; background-color:{pal["row_alt"]}; '
            f'border-bottom:1px solid {pal["border"]};">'
            f'<span style="font-size:10px; font-weight:bold; color:{pal["text_primary"]};">{kpi_lbl}: </span>'
            f'<span style="font-size:12px; font-weight:bold; color:{pal["accent"]};">'
            f'[% "{config.kpi_field}" %]{unit}</span>'
            f'{bar_html}'
            f'</td></tr>'
        )

    elif config.archetype == Archetype.DONUT_CHART and config.donut_fields:
        slices = [(f'"{f}"', lbl, clr) for f, lbl, clr in config.donut_fields]
        donut_svg = build_svg_donut_data_uri(slices, size=76, stroke_width=16)
        seg_bar = build_segmented_bar_table(slices, height_px=8)
        lines.append(
            f'<tr><td colspan="2" style="padding:8px; background-color:{pal["row_alt"]}; '
            f'border-bottom:1px solid {pal["border"]};">'
            f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
            f'<td width="80" align="center" valign="middle">{donut_svg}</td>'
            f'<td style="padding-left:8px;" valign="middle">{seg_bar}</td>'
            f'</tr></table>'
            f'</td></tr>'
        )

    elif config.archetype == Archetype.SPARKLINE and config.sparkline_fields:
        spark_svg = build_svg_sparkline(
            config.sparkline_fields, width=w - 24, height=28, bar_color=pal["accent"]
        )
        lines.append(
            f'<tr><td colspan="2" style="padding:6px 8px; background-color:{pal["row_alt"]}; '
            f'border-bottom:1px solid {pal["border"]}; text-align:center;">'
            f'<div style="font-size:9px; color:{pal["text_secondary"]}; margin-bottom:3px;">Trend Timeline</div>'
            f'{spark_svg}'
            f'</td></tr>'
        )

    elif config.archetype == Archetype.MEDIA_CARD and config.media_field:
        lines.append(
            f'<tr><td colspan="2" align="center" style="padding:6px; background-color:{pal["row_alt"]}; '
            f'border-bottom:1px solid {pal["border"]};">'
            f'<img src="[% "{config.media_field}" %]" width="{w - 24}" '
            f'style="border:1px solid {pal["border"]}; max-height:160px;" />'
            f'</td></tr>'
        )

    # 3. Attribute Key-Value Rows
    row_count = 0
    if config.attribute_fields:
        for idx, (fld, lbl) in enumerate(config.attribute_fields):
            row_bg = pal["card_bg"] if idx % 2 == 0 else pal["row_alt"]
            safe_lbl = html.escape(lbl or fld)
            lines.append(
                f'<tr bgcolor="{row_bg}">'
                f'<td width="45%" style="color:{pal["text_secondary"]}; font-size:10px; '
                f'padding:3px 8px; border-bottom:1px solid {pal["border"]};">{safe_lbl}</td>'
                f'<td width="55%" align="right" style="color:{pal["text_primary"]}; font-size:10px; '
                f'font-weight:bold; padding:3px 8px; border-bottom:1px solid {pal["border"]};">'
                f'[% "{fld}" %]</td>'
                f'</tr>'
            )
            row_count += 1

    # 4. Cross-Layer Relational Metrics
    if config.relational_metrics:
        for metric in config.relational_metrics:
            row_bg = pal["card_bg"] if row_count % 2 == 0 else pal["row_alt"]
            lines.append(build_relational_metric_row(metric, pal, row_bg))
            row_count += 1

    # 5. Optional Footer
    if config.footer_text:
        safe_ft = html.escape(config.footer_text)
        lines.append(
            f'<tr><td colspan="2" style="color:{pal["text_secondary"]}; font-size:9px; '
            f'padding:4px 8px; background-color:{pal["row_alt"]}; text-align:center;">'
            f'{safe_ft}</td></tr>'
        )

    lines.append('</table>')
    return "\n".join(lines)


def compile_raster_hud_html(
    palette_key: str = "slate",
    card_width: int = 260,
    band_count: int = 1,
) -> str:
    """Return a compact HUD card template for live raster sampling."""
    pal = PALETTES.get(palette_key, PALETTES["slate"])
    w = max(200, min(360, card_width))

    rows = []
    for b in range(1, band_count + 1):
        rows.append(
            f'<tr><td width="50%" style="color:{pal["text_secondary"]}; font-size:10px; padding:2px 6px;">'
            f'Band {b}</td>'
            f'<td width="50%" align="right" style="color:{pal["accent"]}; font-size:11px; font-weight:bold; padding:2px 6px;">'
            f'{{band_{b}_val}}</td></tr>'
        )

    return (
        f'<table width="{w}" cellspacing="0" cellpadding="0" '
        f'style="font-family:Segoe UI, sans-serif; background-color:{pal["card_bg"]}; '
        f'border:1px solid {pal["border"]};">'
        f'<tr><td colspan="2" bgcolor="{pal["header_bg"]}" '
        f'style="color:{pal["header_text"]}; font-size:11px; font-weight:bold; padding:4px 6px;">'
        f'&#128065; Raster Cell Inspector</td></tr>'
        f'<tr><td colspan="2" style="font-size:9px; color:{pal["text_secondary"]}; padding:2px 6px; '
        f'background-color:{pal["row_alt"]}; border-bottom:1px solid {pal["border"]};">'
        f'X: {{coord_x}} &nbsp;|&nbsp; Y: {{coord_y}}</td></tr>'
        f'{"".join(rows)}'
        f'</table>'
    )
