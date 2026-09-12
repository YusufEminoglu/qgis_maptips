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
    build_svg_media_placeholder,
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
    "amber": {
        "name": "Cadastral Amber",
        "header_bg": "#d97706",
        "header_text": "#ffffff",
        "sub_bg": "#b45309",
        "sub_text": "#fef3c7",
        "accent": "#f59e0b",
        "card_bg": "#ffffff",
        "row_alt": "#fffbeb",
        "text_primary": "#78350f",
        "text_secondary": "#92400e",
        "border": "#fde68a",
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
    format_numbers: bool = True
    decimal_places: int = 2
    null_text: str = "—"
    media_fallback: str = "placeholder"  # "placeholder" | "hide"
    show_action_buttons: bool = True
    card_action_keys: list[str] = field(
        default_factory=lambda: ["google_satellite", "google_streetview", "copy_clipboard", "export_card_report"]
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["archetype"] = self.archetype.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateConfig:
        clean = dict(data)
        if "archetype" in clean:
            clean["archetype"] = Archetype(clean["archetype"])
        clean.setdefault("format_numbers", True)
        clean.setdefault("decimal_places", 2)
        clean.setdefault("null_text", "—")
        clean.setdefault("media_fallback", "placeholder")
        clean.setdefault("show_action_buttons", True)
        clean.setdefault(
            "card_action_keys",
            ["google_satellite", "google_streetview", "copy_clipboard", "export_card_report"],
        )
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


def build_safe_attribute_expr(
    field_name: str,
    format_numbers: bool = True,
    decimal_places: int = 2,
    null_text: str = "—",
) -> str:
    """Return a robust QGIS expression handling NULLs, integers, floats, and strings."""
    if not field_name:
        return f"'{null_text}'"
    fld = field_name if (field_name.startswith('"') and field_name.endswith('"')) else f'"{field_name}"'
    if not format_numbers:
        return f"coalesce(nullif(to_string({fld}), ''), '{null_text}')"

    # Native QGIS expression:
    # 1. NULL or whitespace -> null_text
    # 2. Try parsing numeric value via try(to_real(x), NULL):
    #    - If integer (equal to round(x, 0)) -> format_number(x, 0)
    #    - Else float -> format_number(x, decimal_places)
    # 3. Non-numeric text -> to_string(x)
    return (
        f"CASE "
        f"WHEN {fld} IS NULL OR length(trim(to_string({fld}))) = 0 THEN '{null_text}' "
        f"WHEN try(to_real({fld}), NULL) IS NOT NULL THEN ("
        f"CASE WHEN to_real({fld}) = round(to_real({fld}), 0) THEN format_number(to_real({fld}), 0) "
        f"ELSE format_number(to_real({fld}), {decimal_places}) END) "
        f"ELSE to_string({fld}) END"
    )


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


def build_card_action_buttons_row(action_keys: list[str], pal: dict[str, str], card_width: int = 320) -> str:
    """Build a compact footer ribbon of 1-click action buttons inside the card.

    Buttons are arranged in neat wrapped rows of max 2-3 buttons to strictly prevent table blowout.
    """
    if not action_keys:
        return ""

    from .action_builder import AVAILABLE_ACTIONS

    actions_map = {act["key"]: act for act in AVAILABLE_ACTIONS}
    icons = {
        "google_satellite": "&#127758;",
        "google_streetview": "&#128205;",
        "openstreetmap": "&#128506;",
        "yandex_maps": "&#129517;",
        "tkgm_cadastre": "&#9889;",
        "tkgm_api_instant": "&#9889;",
        "copy_clipboard": "&#128203;",
        "export_card_report": "&#128196;",
    }

    # Normalize keys to deduplicate any legacy tkgm_api_instant and tkgm_cadastre
    norm_keys = []
    seen = set()
    for k in action_keys:
        real_key = "tkgm_cadastre" if k == "tkgm_api_instant" else k
        if real_key not in seen:
            seen.add(real_key)
            norm_keys.append(real_key)

    buttons = []
    for key in norm_keys:
        act = actions_map.get(key)
        if not act:
            continue
        icon = icons.get(key, "&#9881;")
        raw_title = act.get("short_title", act["name"])
        clean_title = raw_title.lstrip("⚡ ").strip()
        title = html.escape(clean_title)
        href = act["command"] if act.get("type") == "OpenUrl" else f"action:{key}"
        buttons.append(
            f'<td style="padding:2px 3px;">'
            f'<a href="{href}" style="display:inline-block; padding:3px 6px; '
            f'background-color:{pal["sub_bg"]}; color:{pal["sub_text"]}; '
            f'font-size:9px; font-weight:bold; text-decoration:none; border-radius:3px; '
            f'border:1px solid {pal["border"]}; white-space:nowrap;">'
            f'{icon} {title}</a></td>'
        )

    if not buttons:
        return ""

    # Group buttons into rows of max 3 (or 2 for compact cards <280px) so the table never expands beyond card_width
    max_per_row = 2 if card_width < 280 else 3
    table_rows = []
    for i in range(0, len(buttons), max_per_row):
        row_tds = "".join(buttons[i : i + max_per_row])
        table_rows.append(f"<tr>{row_tds}</tr>")

    return (
        f'<tr><td colspan="2" align="center" style="padding:5px 6px; '
        f'background-color:{pal["row_alt"]}; border-top:1px solid {pal["border"]}; '
        f'border-bottom:1px solid {pal["border"]};">'
        f'<div style="font-size:8.5px; font-weight:bold; color:{pal["text_secondary"]}; '
        f'text-transform:uppercase; margin-bottom:3px; letter-spacing:0.5px;">&#9889; Quick Actions</div>'
        f'<table cellspacing="0" cellpadding="0" style="margin:0 auto;">'
        f'{"".join(table_rows)}'
        f'</table></td></tr>'
    )


def compile_maptip_html(config: TemplateConfig) -> str:
    """Compile TemplateConfig into a strict Qt-compatible HTML MapTip template."""
    pal = PALETTES.get(config.palette_key, PALETTES["emerald"])
    w = max(180, min(800, config.card_width))

    lines = []
    lines.append(
        f'<table width="{w}" cellspacing="0" cellpadding="0" '
        f'style="width:{w}px; min-width:{w}px; max-width:{w}px; font-family:Segoe UI, sans-serif; '
        f'background-color:{pal["card_bg"]}; border:1px solid {pal["border"]}; border-collapse:collapse;">'
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
        val_expr = build_safe_attribute_expr(
            config.kpi_field,
            format_numbers=config.format_numbers,
            decimal_places=config.decimal_places,
            null_text=config.null_text,
        )
        lines.append(
            f'<tr><td colspan="2" style="padding:8px 8px 4px 8px; text-align:center; '
            f'background-color:{pal["row_alt"]}; border-bottom:1px solid {pal["border"]};">'
            f'<div style="font-size:10px; color:{pal["text_secondary"]}; text-transform:uppercase;">{kpi_lbl}</div>'
            f'<div style="font-size:18px; font-weight:bold; color:{pal["accent"]}; margin-top:2px;">'
            f'[% {val_expr} %]{unit}</div>'
            f'</td></tr>'
        )

    elif config.archetype == Archetype.PROGRESS_BAR and config.kpi_field:
        kpi_lbl = html.escape(config.kpi_label or config.kpi_field)
        unit = f" {html.escape(config.kpi_unit)}" if config.kpi_unit else ""
        val_expr = build_safe_attribute_expr(
            config.kpi_field,
            format_numbers=config.format_numbers,
            decimal_places=config.decimal_places,
            null_text=config.null_text,
        )
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
            f'[% {val_expr} %]{unit}</span>'
            f'{bar_html}'
            f'</td></tr>'
        )

    elif config.archetype == Archetype.DONUT_CHART:
        raw_slices = config.donut_fields
        if not raw_slices and config.attribute_fields:
            donut_palette = ["#10b981", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4"]
            raw_slices = [
                (fld, lbl or fld, donut_palette[i % len(donut_palette)])
                for i, (fld, lbl) in enumerate(config.attribute_fields[:5])
            ]
        if raw_slices:
            slices = [(f'"{f}"', lbl, clr) for f, lbl, clr in raw_slices]
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

    elif config.archetype == Archetype.SPARKLINE:
        raw_spark_fields = config.sparkline_fields
        if not raw_spark_fields and config.attribute_fields:
            raw_spark_fields = [fld for fld, _ in config.attribute_fields[:6]]
        if raw_spark_fields:
            spark_svg = build_svg_sparkline(
                raw_spark_fields, width=w - 24, height=28, bar_color=pal["accent"]
            )
            lines.append(
                f'<tr><td colspan="2" style="padding:6px 8px; background-color:{pal["row_alt"]}; '
                f'border-bottom:1px solid {pal["border"]}; text-align:center;">'
                f'<div style="font-size:9px; color:{pal["text_secondary"]}; margin-bottom:3px;">Trend Timeline</div>'
                f'{spark_svg}'
                f'</td></tr>'
            )

    elif config.archetype == Archetype.MEDIA_CARD and config.media_field:
        media_w = w - 24
        placeholder_uri = build_svg_media_placeholder(
            width=media_w,
            height=120,
            bg_color=pal["row_alt"],
            border_color=pal["border"],
            text_color=pal["text_secondary"],
        )
        if config.media_fallback == "hide":
            lines.append(
                f'[% CASE WHEN length(trim(coalesce(to_string("{config.media_field}"), \'\'))) > 0 THEN '
                f'\'<tr><td colspan="2" align="center" style="padding:6px; background-color:{pal["row_alt"]}; '
                f'border-bottom:1px solid {pal["border"]};">\' || '
                f'\'<img src="\' || "{config.media_field}" || \'" width="{media_w}" '
                f'style="border:1px solid {pal["border"]}; max-height:160px;" />\' || '
                f'\'</td></tr>\' ELSE \'\' END %]'
            )
        else:
            src_expr = (
                f'CASE WHEN length(trim(coalesce(to_string("{config.media_field}"), \'\'))) > 0 '
                f'THEN "{config.media_field}" ELSE \'{placeholder_uri}\' END'
            )
            lines.append(
                f'<tr><td colspan="2" align="center" style="padding:6px; background-color:{pal["row_alt"]}; '
                f'border-bottom:1px solid {pal["border"]};">'
                f'<img src="[% {src_expr} %]" width="{media_w}" '
                f'style="border:1px solid {pal["border"]}; max-height:160px;" />'
                f'</td></tr>'
            )

    # 3. Attribute Key-Value Rows
    row_count = 0
    if config.attribute_fields:
        for idx, (fld, lbl) in enumerate(config.attribute_fields):
            row_bg = pal["card_bg"] if idx % 2 == 0 else pal["row_alt"]
            safe_lbl = html.escape(lbl or fld)
            val_expr = build_safe_attribute_expr(
                fld,
                format_numbers=config.format_numbers,
                decimal_places=config.decimal_places,
                null_text=config.null_text,
            )
            lines.append(
                f'<tr bgcolor="{row_bg}">'
                f'<td width="45%" style="color:{pal["text_secondary"]}; font-size:10px; '
                f'padding:3px 8px; border-bottom:1px solid {pal["border"]}; word-break:break-word;">{safe_lbl}</td>'
                f'<td width="55%" align="right" style="color:{pal["text_primary"]}; font-size:10px; '
                f'font-weight:bold; padding:3px 8px; border-bottom:1px solid {pal["border"]}; word-break:break-word;">'
                f'[% {val_expr} %]</td>'
                f'</tr>'
            )
            row_count += 1

    # 4. Cross-Layer Relational Metrics
    if config.relational_metrics:
        for metric in config.relational_metrics:
            row_bg = pal["card_bg"] if row_count % 2 == 0 else pal["row_alt"]
            lines.append(build_relational_metric_row(metric, pal, row_bg))
            row_count += 1

    # 4.5 1-Click Action Buttons Ribbon
    if config.show_action_buttons and config.card_action_keys:
        action_bar_html = build_card_action_buttons_row(config.card_action_keys, pal, card_width=w)
        if action_bar_html:
            lines.append(action_bar_html)

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
