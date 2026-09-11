"""Core engines for zero2maptips."""
from .chart_engine import (
    build_progress_bar_table,
    build_segmented_bar_table,
    build_svg_donut_data_uri,
)
from .template_engine import (
    Archetype,
    PALETTES,
    TemplateConfig,
    compile_maptip_html,
    compile_raster_hud_html,
)
from .action_builder import (
    AVAILABLE_ACTIONS,
    apply_actions_to_layer,
    build_open_file_action,
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
    "AVAILABLE_ACTIONS",
    "apply_actions_to_layer",
    "build_open_file_action",
    "CanvasHoverHUD",
]
