"""Live Canvas Hover HUD for raster and composite multi-layer inspection.

Installs a passive event filter on the QGIS map canvas viewport with debounced
sampling, a custom high-visibility inspection reticle cursor, persistent dwelling,
and freeze/pinning capability to prevent main-thread GUI freezing or tooltip flickering.
"""
from __future__ import annotations

import contextlib
import html
from typing import TYPE_CHECKING, Optional

from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import QToolTip
from qgis.core import (
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsRasterLayer,
    QgsVectorLayer,
)

if TYPE_CHECKING:
    from qgis.gui import QgsMapCanvas


def create_inspection_cursor() -> QCursor:
    """Creates a custom, high-visibility 32x32 inspection reticle with mini tooltip badge."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent if hasattr(Qt, "GlobalColor") else Qt.transparent)

    p = QPainter(pix)
    p.setRenderHint(
        QPainter.RenderHint.Antialiasing if hasattr(QPainter, "RenderHint") else QPainter.Antialiasing
    )

    cx, cy = 12, 12

    # Outer dark shadow / border for high contrast against light maps
    p.setPen(QPen(QColor(15, 23, 42, 220), 3.0))
    p.drawLine(cx - 7, cy, cx + 7, cy)
    p.drawLine(cx, cy - 7, cx, cy + 7)

    # Inner crisp white core for high contrast against dark maps
    p.setPen(QPen(QColor(255, 255, 255, 255), 1.5))
    p.drawLine(cx - 6, cy, cx + 6, cy)
    p.drawLine(cx, cy - 6, cx, cy + 6)

    # Vibrant electric cyan center crosshair dot
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(6, 182, 212, 255))
    p.drawEllipse(cx - 2, cy - 2, 4, 4)

    # Mini indicator card badge at top-right quadrant
    p.setPen(QPen(QColor(15, 23, 42, 200), 1.0))
    p.setBrush(QColor(6, 182, 212, 240))
    p.drawRoundedRect(17, 2, 13, 11, 2.5, 2.5)

    # Mini lightning / locator glyph inside the badge
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 240))
    p.drawPolygon([
        QPoint(24, 4),
        QPoint(21, 8),
        QPoint(23, 8),
        QPoint(22, 11),
        QPoint(26, 7),
        QPoint(24, 7),
    ])

    p.end()
    return QCursor(pix, cx, cy)


class CanvasHoverHUD(QObject):
    """Passive event filter monitoring canvas mouse moves with debouncing and unique cursor."""

    # Emitted on each successful sample: (html_table, summary_status)
    sampleUpdated = pyqtSignal(str, str)
    pinStateChanged = pyqtSignal(bool)

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
        self._pinned = False
        self._use_custom_cursor = True
        self._inspection_cursor: Optional[QCursor] = None
        with contextlib.suppress(Exception):
            self._inspection_cursor = create_inspection_cursor()
        self._last_sampled_html = ""

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

    def set_use_custom_cursor(self, enabled: bool) -> None:
        """Toggle unique inspection cursor on canvas."""
        self._use_custom_cursor = enabled
        if self._is_active and self.canvas and self.canvas.viewport():
            if enabled and self._inspection_cursor:
                self.canvas.viewport().setCursor(self._inspection_cursor)
            else:
                with contextlib.suppress(Exception):
                    self.canvas.viewport().unsetCursor()

    def set_pinned(self, pinned: bool) -> None:
        """Pin/freeze current tooltip so it remains stationary on canvas."""
        self._pinned = pinned
        self.pinStateChanged.emit(pinned)
        if self._is_active and self._last_sampled_html:
            self._display_hud(self._last_sampled_html)

    def is_pinned(self) -> bool:
        return self._pinned

    def start(self) -> None:
        """Install viewport event filter and activate hover listening with unique cursor."""
        if not self._is_active and self.canvas and self.canvas.viewport():
            self.canvas.viewport().installEventFilter(self)
            self._is_active = True
            if self._use_custom_cursor and self._inspection_cursor:
                self.canvas.viewport().setCursor(self._inspection_cursor)

    def stop(self) -> None:
        """Uninstall viewport event filter, restore cursor, and hide tooltips."""
        if self._is_active and self.canvas and self.canvas.viewport():
            self._timer.stop()
            with contextlib.suppress(Exception):
                self.canvas.viewport().removeEventFilter(self)
            self._is_active = False
            self._pinned = False
            self.pinStateChanged.emit(False)
            if self.canvas and self.canvas.viewport():
                with contextlib.suppress(Exception):
                    self.canvas.viewport().unsetCursor()
            QToolTip.hideText()

    def is_active(self) -> bool:
        return self._is_active

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self._is_active:
            return super().eventFilter(watched, event)

        etype = event.type()
        ev_mouse_move = QEvent.Type.MouseMove if hasattr(QEvent, "Type") else QEvent.MouseMove
        ev_enter = QEvent.Type.Enter if hasattr(QEvent, "Type") else QEvent.Enter
        ev_leave = QEvent.Type.Leave if hasattr(QEvent, "Type") else QEvent.Leave
        ev_press = QEvent.Type.MouseButtonPress if hasattr(QEvent, "Type") else QEvent.MouseButtonPress

        # Enforce unique inspection cursor across viewport events
        if self._use_custom_cursor and self._inspection_cursor and self.canvas and self.canvas.viewport():
            if etype in (ev_mouse_move, ev_enter):
                vp = self.canvas.viewport()
                if vp and vp.cursor().shape() != self._inspection_cursor.shape():
                    vp.setCursor(self._inspection_cursor)

        if etype == ev_mouse_move:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            global_pos = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )
            dist = (pos - self._last_screen_pos).manhattanLength()
            self._last_screen_pos = pos
            self._last_global_pos = global_pos

            # If not pinned, schedule debounced sampling
            if not self._pinned:
                if dist >= 3 or not self._timer.isActive():
                    self._timer.start(self.debounce_ms)

        elif etype == ev_press:
            # Shift+Click on canvas toggles pin/freeze state
            btn_left = getattr(Qt.MouseButton, "LeftButton", None)
            mod_shift = getattr(Qt.KeyboardModifier, "ShiftModifier", None)
            if hasattr(event, "button") and event.button() == btn_left:
                if hasattr(event, "modifiers") and (event.modifiers() & mod_shift):
                    self.set_pinned(not self._pinned)

        elif etype == ev_leave:
            # Verify if mouse cursor genuinely left the canvas viewport boundary
            vp = self.canvas.viewport() if self.canvas else None
            if vp:
                local_pos = vp.mapFromGlobal(QCursor.pos())
                if not vp.rect().contains(local_pos):
                    self._timer.stop()
                    if not self._pinned:
                        QToolTip.hideText()

        return super().eventFilter(watched, event)

    def _on_debounce_timeout(self) -> None:
        if not self._is_active or (not self._active_raster_layers and not self._active_vector_layer):
            return
        if self._pinned:
            return

        map_pt = self.canvas.getCoordinateTransform().toMapCoordinates(self._last_screen_pos)

        # Composite HUD Builder
        hud_lines = [
            '<table width="290" cellspacing="0" cellpadding="0" '
            'style="font-family:Segoe UI, sans-serif; background-color:#0f172a; '
            'border:1.5px solid #0284c7; border-collapse:collapse; border-radius:6px;">',
            '<tr><td colspan="2" bgcolor="#0284c7" style="color:#ffffff; font-size:11px; font-weight:bold; padding:5px 8px;">'
            '&#128065; Live Canvas Inspector HUD</td></tr>',
            f'<tr><td colspan="2" style="font-size:9px; color:#94a3b8; padding:3px 8px; background-color:#1e293b; '
            f'border-bottom:1px solid #334155;">X: {map_pt.x():.2f} &nbsp;|&nbsp; Y: {map_pt.y():.2f}</td></tr>',
        ]

        found_any = False
        status_text = f"X: {map_pt.x():.2f}, Y: {map_pt.y():.2f}"

        # 1. Vector Inspection (if enabled)
        if self._active_vector_layer and self._active_vector_layer.isValid():
            vlayer = self._active_vector_layer
            pt_geom = QgsGeometry.fromPointXY(map_pt)
            tol = self.canvas.mapUnitsPerPixel() * 4
            req = QgsFeatureRequest().setFilterRect(pt_geom.buffer(tol, 4).boundingBox())
            matched_feature = None
            for feat in vlayer.getFeatures(req):
                if feat.geometry().intersects(pt_geom) or feat.geometry().distance(pt_geom) <= tol:
                    matched_feature = feat
                    break

            if matched_feature:
                found_any = True
                f_name = matched_feature.attribute(0) or f"ID {matched_feature.id()}"
                hud_lines.append(
                    f'<tr><td colspan="2" bgcolor="#1e293b" style="color:#38bdf8; font-size:10px; font-weight:bold; padding:4px 8px;">'
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
                f'<tr><td colspan="2" bgcolor="#1e293b" style="color:#34d399; font-size:10px; font-weight:bold; padding:4px 8px;">'
                f'&#9638; {html.escape(rlayer.name())}</td></tr>'
            )

            band_count = min(4, rlayer.bandCount())
            for b in range(1, band_count + 1):
                val, ok = provider.sample(map_pt, b)
                val_str = f"{val:.2f}" if (ok and val is not None and isinstance(val, (int, float))) else "NoData"
                hud_lines.append(
                    f'<tr><td width="55%" style="color:#cbd5e1; font-size:9.5px; padding:3px 8px; border-bottom:1px solid #1e293b;">'
                    f'Band {b}</td>'
                    f'<td width="45%" align="right" style="color:#38bdf8; font-size:10px; font-weight:bold; padding:3px 8px; border-bottom:1px solid #1e293b;">'
                    f'{val_str}</td></tr>'
                )

        hud_lines.append('</table>')
        final_html = "\n".join(hud_lines)

        if found_any:
            self._last_sampled_html = final_html
            self.sampleUpdated.emit(final_html, status_text)
            self._display_hud(final_html)
        else:
            if not self._pinned:
                QToolTip.hideText()

    def _display_hud(self, html_content: str) -> None:
        """Displays tooltip offset from cursor with generous dwell duration."""
        if not html_content:
            QToolTip.hideText()
            return

        # Add pin status indicator in footer
        if self._pinned:
            footer = (
                '<tr><td colspan="2" bgcolor="#1e293b" style="font-size:8.5px; color:#f59e0b; padding:3px 8px; '
                'border-top:1px solid #334155; text-align:right;">&#128204; Pinned (Shift+Click or uncheck to unlock)</td></tr>'
            )
        else:
            footer = (
                '<tr><td colspan="2" bgcolor="#0f172a" style="font-size:8px; color:#64748b; padding:2px 8px; '
                'border-top:1px solid #334155; text-align:right;">Shift+Click canvas to pin HUD</td></tr>'
            )
        display_html = html_content.replace('</table>', f'{footer}</table>')

        # Offset by +22px, +22px so the mouse cursor never collides with the tooltip window!
        offset_pos = self._last_global_pos + QPoint(22, 22)
        tolerance_rect = QRect(
            self._last_screen_pos.x() - 15,
            self._last_screen_pos.y() - 15,
            30,
            30,
        )
        vp = self.canvas.viewport() if self.canvas else self.canvas
        # Show for 30000 ms (30 seconds) instead of disappearing immediately!
        QToolTip.showText(offset_pos, display_html, vp, tolerance_rect, 30000)
