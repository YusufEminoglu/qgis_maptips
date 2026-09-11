"""Live Canvas Hover HUD for raster layers and active layer inspection.

Installs a passive event filter on the QGIS map canvas viewport with debounced
sampling to prevent main-thread GUI freezing during mouse moves.
"""
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Optional

from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QTimer
from qgis.PyQt.QtWidgets import QToolTip
from qgis.core import QgsPointXY, QgsRasterLayer

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
        self._active_raster_layer: Optional[QgsRasterLayer] = None
        self._is_active = False

    def set_active_raster(self, layer: Optional[QgsRasterLayer]) -> None:
        """Set the target raster layer to inspect on hover."""
        self._active_raster_layer = layer if (layer and layer.isValid()) else None

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
            # Dual Qt5/Qt6 mouse coordinate retrieval
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._last_screen_pos = pos
            self._last_global_pos = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )
            # Reset timer on move
            self._timer.start(self.debounce_ms)

        elif self._is_active and event.type() == QEvent.Type.Leave:
            self._timer.stop()
            QToolTip.hideText()

        return super().eventFilter(watched, event)

    def _on_debounce_timeout(self) -> None:
        if not self._is_active or not self._active_raster_layer:
            return

        layer = self._active_raster_layer
        if not layer.isValid():
            return

        # Convert screen pos to map coords
        map_pt = self.canvas.getCoordinateTransform().toMapCoordinates(self._last_screen_pos)

        # Check extent boundary
        if not layer.extent().contains(map_pt):
            QToolTip.hideText()
            return

        band_count = min(4, layer.bandCount())
        values = {}
        provider = layer.dataProvider()
        if not provider:
            return

        for b in range(1, band_count + 1):
            val, ok = provider.sample(map_pt, b)
            if ok and val is not None:
                values[f"band_{b}_val"] = f"{val:.3f}" if isinstance(val, float) else str(val)
            else:
                values[f"band_{b}_val"] = "NoData"

        values["coord_x"] = f"{map_pt.x():.2f}"
        values["coord_y"] = f"{map_pt.y():.2f}"

        template = compile_raster_hud_html(palette_key="slate", card_width=240, band_count=band_count)
        html_content = template.format(**values)

        QToolTip.showText(self._last_global_pos, html_content, self.canvas)
