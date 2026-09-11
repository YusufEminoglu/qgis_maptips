"""Live Canvas Hover HUD for raster and composite multi-layer inspection.

Installs a passive event filter on the QGIS map canvas viewport with debounced
sampling to prevent main-thread GUI freezing during mouse moves.
"""
from __future__ import annotations

import contextlib
import html
from typing import TYPE_CHECKING, Optional

from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QTimer
from qgis.PyQt.QtWidgets import QToolTip
from qgis.core import (
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .template_engine import compile_raster_hud_html

if TYPE_CHECKING:
    from qgis.gui import QgsMapCanvas


class CanvasHoverHUD(QObject):
    """Passive event filter monitoring canvas mouse moves with debouncing."""

    def __init__(
        self,
        canvas: "QgsMapCanvas",
        debounce_ms: int = 250,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent or canvas)
        self.canvas = canvas
        self.debounce_ms = debounce_ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_debounce_timeout)

        self._last_screen_pos = QPoint()
        self._last_global_pos = QPoint()
        self._active_raster_layers: list[QgsRasterLayer] = []
        self._active_vector_layer: Optional[QgsVectorLayer] = None
        self._composite_mode = False
        self._is_active = False

    def set_active_raster(self, layer: Optional[QgsRasterLayer]) -> None:
        """Set a single target raster layer."""
        self._active_raster_layers = [layer] if (layer and layer.isValid()) else []

    def set_target_rasters(self, layers: list[QgsRasterLayer]) -> None:
        """Set multiple raster layers for composite multi-raster inspection."""
        self._active_raster_layers = [lyr for lyr in layers if lyr and lyr.isValid()]

    def set_vector_layer(self, layer: Optional[QgsVectorLayer]) -> None:
        """Set optional vector layer for composite vector+raster drilldown."""
        self._active_vector_layer = layer if (layer and layer.isValid()) else None

    def set_composite_mode(self, enabled: bool) -> None:
        self._composite_mode = enabled

    def start(self) -> None:
        """Install viewport event filter and activate hover listening."""
        if not self._is_active and self.canvas and self.canvas.viewport():
            self.canvas.viewport().installEventFilter(self)
            self._is_active = True

    def stop(self) -> None:
        """Uninstall viewport event filter and hide tooltips."""
        if self._is_active and self.canvas and self.canvas.viewport():
            self._timer.stop()
            with contextlib.suppress(Exception):
                self.canvas.viewport().removeEventFilter(self)
            self._is_active = False
            QToolTip.hideText()

    def is_active(self) -> bool:
        return self._is_active

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._is_active and event.type() == QEvent.Type.MouseMove:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._last_screen_pos = pos
            self._last_global_pos = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )
            self._timer.start(self.debounce_ms)

        elif self._is_active and event.type() == QEvent.Type.Leave:
            self._timer.stop()
            QToolTip.hideText()

        return super().eventFilter(watched, event)

    def _on_debounce_timeout(self) -> None:
        if not self._is_active or (not self._active_raster_layers and not self._active_vector_layer):
            return

        map_pt = self.canvas.getCoordinateTransform().toMapCoordinates(self._last_screen_pos)

        # Composite HUD Builder
        hud_lines = [
            '<table width="280" cellspacing="0" cellpadding="0" '
            'style="font-family:Segoe UI, sans-serif; background-color:#0f172a; '
            'border:1px solid #38bdf8; border-collapse:collapse; border-radius:5px;">',
            '<tr><td colspan="2" bgcolor="#0284c7" style="color:#ffffff; font-size:11px; font-weight:bold; padding:4px 6px;">'
            '&#128065; Live Canvas Inspector HUD</td></tr>',
            f'<tr><td colspan="2" style="font-size:9px; color:#94a3b8; padding:2px 6px; background-color:#1e293b; '
            f'border-bottom:1px solid #334155;">X: {map_pt.x():.2f} &nbsp;|&nbsp; Y: {map_pt.y():.2f}</td></tr>',
        ]

        found_any = False

        # 1. Vector Inspection (if enabled)
        if self._active_vector_layer and self._active_vector_layer.isValid():
            vlayer = self._active_vector_layer
            # Buffer search box for tolerance
            search_rect = self.canvas.extent()
            # Point in geometry check using spatial filter
            pt_geom = QgsGeometry.fromPointXY(map_pt)
            req = QgsFeatureRequest().setFilterRect(pt_geom.buffer(self.canvas.mapUnitsPerPixel() * 3, 4).boundingBox())
            matched_feature = None
            for feat in vlayer.getFeatures(req):
                if feat.geometry().intersects(pt_geom) or feat.geometry().distance(pt_geom) <= self.canvas.mapUnitsPerPixel() * 2:
                    matched_feature = feat
                    break

            if matched_feature:
                found_any = True
                f_name = matched_feature.attribute(0) or f"ID {matched_feature.id()}"
                hud_lines.append(
                    f'<tr><td colspan="2" bgcolor="#1e293b" style="color:#38bdf8; font-size:10px; font-weight:bold; padding:3px 6px;">'
                    f'&#128506; {html.escape(vlayer.name())}: {html.escape(str(f_name))}</td></tr>'
                )

        # 2. Raster Layer(s) Sampling
        for rlayer in self._active_raster_layers:
            if not rlayer.extent().contains(map_pt):
                continue

            provider = rlayer.dataProvider()
            if not provider:
                continue

            found_any = True
            hud_lines.append(
                f'<tr><td colspan="2" bgcolor="#1e293b" style="color:#34d399; font-size:10px; font-weight:bold; padding:3px 6px;">'
                f'&#9638; {html.escape(rlayer.name())}</td></tr>'
            )

            band_count = min(3, rlayer.bandCount())
            for b in range(1, band_count + 1):
                val, ok = provider.sample(map_pt, b)
                val_str = f"{val:.2f}" if (ok and val is not None and isinstance(val, (int, float))) else "NoData"
                hud_lines.append(
                    f'<tr><td width="55%" style="color:#94a3b8; font-size:9.5px; padding:2px 6px; border-bottom:1px solid #1e293b;">'
                    f'Band {b}</td>'
                    f'<td width="45%" align="right" style="color:#ffffff; font-size:10px; font-weight:bold; padding:2px 6px; border-bottom:1px solid #1e293b;">'
                    f'{val_str}</td></tr>'
                )

        hud_lines.append('</table>')

        if found_any:
            QToolTip.showText(self._last_global_pos, "\n".join(hud_lines), self.canvas)
        else:
            QToolTip.hideText()
