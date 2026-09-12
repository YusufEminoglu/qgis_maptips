"""Core engines for qgis_maptips."""
from .chart_engine import (
    build_progress_bar_table,
    build_segmented_bar_table,
    build_svg_donut_data_uri,
    build_svg_sparkline,
)
from .template_engine import (
    Archetype,
    PALETTES,
    TemplateConfig,
    build_conditional_badge_html,
    build_relational_metric_row,
    compile_maptip_html,
    compile_raster_hud_html,
)
from .action_builder import (
    AVAILABLE_ACTIONS,
    apply_actions_to_layer,
    build_custom_url_action,
    build_open_file_action,
    build_select_intersecting_action,
    is_layer_alive,
)


def __getattr__(name: str):
    if name == "CanvasHoverHUD":
        from .raster_hud import CanvasHoverHUD

        return CanvasHoverHUD
    raise AttributeError(f"module {__name__} has no attribute {name}")


__all__ = [
    "Archetype",
    "PALETTES",
    "TemplateConfig",
    "compile_maptip_html",
    "compile_raster_hud_html",
    "build_progress_bar_table",
    "build_segmented_bar_table",
    "build_svg_donut_data_uri",
    "build_svg_sparkline",
    "build_conditional_badge_html",
    "build_relational_metric_row",
    "AVAILABLE_ACTIONS",
    "apply_actions_to_layer",
    "build_open_file_action",
    "build_select_intersecting_action",
    "build_custom_url_action",
    "is_layer_alive",
    "CanvasHoverHUD",
]
