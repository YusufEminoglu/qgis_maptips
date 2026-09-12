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
        self._pinned_global_pos = QPoint()
        self._pinned_screen_pos = QPoint()
        self._active_raster_layers: list[QgsRasterLayer] = []
        self._active_vector_layer: Optional[QgsVectorLayer] = None
        self._composite_mode = False
        self._filter_installed = False
        self._hud_enabled = False
        self._cursor_enabled = False
        self._pinned = False
        self._use_custom_cursor = True
        self._inspection_cursor: Optional[QCursor] = None
        with contextlib.suppress(Exception):
            self._inspection_cursor = create_inspection_cursor()
        self._last_sampled_html = ""

    def _sync_canvas_event_filter(self) -> None:
        """Dynamically attach or detach canvas viewport event filter based on active flags."""
        vp = self.canvas.viewport() if self.canvas else None
        if not vp:
            return

        should_listen = self._hud_enabled or self._cursor_enabled
        if should_listen and not self._filter_installed:
            vp.installEventFilter(self)
            self._filter_installed = True
        elif not should_listen and self._filter_installed:
            with contextlib.suppress(Exception):
                vp.removeEventFilter(self)
            self._filter_installed = False

        if self._cursor_enabled and self._use_custom_cursor and self._inspection_cursor:
            vp.setCursor(self._inspection_cursor)
        elif not self._cursor_enabled:
            with contextlib.suppress(Exception):
                vp.unsetCursor()

    def set_cursor_mode(self, enabled: bool) -> None:
        """Toggle unique inspection reticle cursor on canvas."""
        self._cursor_enabled = enabled
        self._sync_canvas_event_filter()

    def set_hud_mode(self, enabled: bool) -> None:
        """Toggle live HUD inspection sampling and hover tooltips."""
        self._hud_enabled = enabled
        if not enabled:
            self._timer.stop()
            if not self._pinned:
                QToolTip.hideText()
        self._sync_canvas_event_filter()

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
        """Toggle unique inspection cursor preference."""
        self._use_custom_cursor = enabled
        self._sync_canvas_event_filter()

    def set_pinned(self, pinned: bool) -> None:
        """Pin/freeze current tooltip so it remains stationary on canvas."""
        self._pinned = pinned
        if pinned:
            # Lock position to currently hovered position
            self._pinned_global_pos = self._last_global_pos
            self._pinned_screen_pos = self._last_screen_pos
        self.pinStateChanged.emit(pinned)
        if self._hud_enabled:
            if self._last_sampled_html:
                self._display_hud(self._last_sampled_html)
            elif pinned:
                standby_html = (
                    '<table width="260" cellspacing="0" cellpadding="0" '
                    'style="font-family:Segoe UI, sans-serif; background-color:#0f172a; '
                    'border:1.5px solid #f59e0b; border-collapse:collapse; border-radius:6px;">'
                    '<tr><td bgcolor="#f59e0b" style="color:#0f172a; font-size:11px; font-weight:bold; padding:5px 8px;">'
                    '&#128204; HUD Pinned (Ready)</td></tr>'
                    '<tr><td style="color:#cbd5e1; font-size:9.5px; padding:8px;">'
                    'Live HUD is locked. Shift+Click the canvas or uncheck to unlock.</td></tr>'
                    '</table>'
                )
                self._display_hud(standby_html)

    def is_pinned(self) -> bool:
        return self._pinned

    def start(self) -> None:
        """Activate both HUD hover sampling and inspection cursor."""
        self.set_hud_mode(True)
        self.set_cursor_mode(True)

    def stop(self) -> None:
        """Deactivate HUD hover sampling, restore cursor, and clear tooltips."""
        self.set_hud_mode(False)
        self.set_cursor_mode(False)
        self._pinned = False
        self.pinStateChanged.emit(False)
        QToolTip.hideText()

    def is_active(self) -> bool:
        return self._hud_enabled

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        etype = event.type()
        ev_mouse_move = QEvent.Type.MouseMove if hasattr(QEvent, "Type") else QEvent.MouseMove
        ev_enter = QEvent.Type.Enter if hasattr(QEvent, "Type") else QEvent.Enter
        ev_leave = QEvent.Type.Leave if hasattr(QEvent, "Type") else QEvent.Leave
        ev_press = QEvent.Type.MouseButtonPress if hasattr(QEvent, "Type") else QEvent.MouseButtonPress

        vp = self.canvas.viewport() if self.canvas else None

        # 1. Enforce unique inspection cursor across viewport events
        if self._cursor_enabled and self._use_custom_cursor and self._inspection_cursor and vp:
            if etype in (ev_mouse_move, ev_enter):
                if vp.cursor().shape() != self._inspection_cursor.shape():
                    vp.setCursor(self._inspection_cursor)

        # If HUD sampling is disabled, pass through events immediately
        if not self._hud_enabled:
            return super().eventFilter(watched, event)

        # 2. Mouse Move Handling
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
            else:
                # If pinned, ensure the tooltip stays visible if Qt tried to dismiss it
                if not QToolTip.isVisible() and self._last_sampled_html:
                    self._display_hud(self._last_sampled_html)

        elif etype == ev_press:
            # Shift+Click on canvas toggles pin/freeze state
            btn_left = getattr(Qt.MouseButton, "LeftButton", None)
            mod_shift = getattr(Qt.KeyboardModifier, "ShiftModifier", None)
            if hasattr(event, "button") and event.button() == btn_left:
                if hasattr(event, "modifiers") and (event.modifiers() & mod_shift):
                    self.set_pinned(not self._pinned)
                    return True  # Consume click to avoid disrupting map selection

        elif etype == ev_leave:
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

        vp = self.canvas.viewport() if self.canvas else self.canvas

        # Add pin status indicator in footer
        if self._pinned:
            footer = (
                '<tr><td colspan="2" bgcolor="#1e293b" style="font-size:8.5px; color:#f59e0b; padding:3px 8px; '
                'border-top:1px solid #334155; text-align:right;">&#128204; Pinned (Shift+Click or uncheck to unlock)</td></tr>'
            )
            # Use frozen position so moving the mouse does not shift the pinned card
            base_pos = self._pinned_global_pos if not self._pinned_global_pos.isNull() else self._last_global_pos
            offset_pos = base_pos + QPoint(22, 22)
            # Infinite tolerance rect prevents Qt from dismissing pinned tooltip on mouse moves
            tolerance_rect = QRect(-500000, -500000, 1000000, 1000000)
        else:
            footer = (
                '<tr><td colspan="2" bgcolor="#0f172a" style="font-size:8px; color:#64748b; padding:2px 8px; '
                'border-top:1px solid #334155; text-align:right;">Shift+Click canvas to pin HUD</td></tr>'
            )
            offset_pos = self._last_global_pos + QPoint(22, 22)
            # When unpinned, use canvas viewport rect so cursor moving inside canvas does NOT flicker/close
            tolerance_rect = vp.rect() if (vp and hasattr(vp, "rect")) else QRect(0, 0, 10000, 10000)

        display_html = html_content.replace('</table>', f'{footer}</table>')
        # Show for 60 seconds
        QToolTip.showText(offset_pos, display_html, vp, tolerance_rect, 60000)
