"""Interactive Canvas MapTip Inspector & Pin Engine.

Provides an interactive passive event filter on the QGIS map canvas viewport:
1. Real-time vector feature inspection on hover with instant MapTip card rendering.
2. Canvas feature glow highlighting (QgsHighlight) with cyan hover / gold pin styling.
3. 1-Click / Shift+Click Pin & Freeze mode: locks the MapTip stationary on canvas
   so users can read, select text, click action links, and compare features without
   the tooltip vanishing on mouse movement.
4. Smooth dismissal with Escape key or clicking blank canvas.
5. High-visibility optional inspection reticle cursor.
6. Seamless fallback to raster cell sampling when hovering raster layers.
"""
from __future__ import annotations

import contextlib
import html
from typing import TYPE_CHECKING, Optional

from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import QToolTip
from qgis.core import (
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsHighlight

from .action_builder import is_layer_alive

if TYPE_CHECKING:
    from qgis.gui import QgsMapCanvas


def create_inspection_cursor() -> QCursor:
    """Create a custom, high-visibility 32x32 inspection reticle with mini tooltip badge."""
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


def evaluate_vector_feature_maptip(layer: QgsVectorLayer, feat: QgsFeature) -> str:
    """Evaluate feature MapTip template or return clean fallback card HTML."""
    if not is_layer_alive(layer) or not feat:
        return ""
    with contextlib.suppress(Exception):
        if hasattr(feat, "isValid") and not feat.isValid():
            return ""

    template = layer.mapTipTemplate()
    if template and template.strip():
        with contextlib.suppress(Exception):
            ctx = QgsExpressionContext()
            ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
            ctx.setFeature(feat)
            rendered = QgsExpression.replaceExpressionText(template, ctx)
            if rendered and rendered.strip():
                return rendered

    # Clean fallback card showing primary attributes
    fields = layer.fields()
    title_val = str(feat.attribute(0) or f"Feature #{feat.id()}")
    rows = []
    for i, fld in enumerate(fields):
        if i >= 6:
            break
        val = feat.attribute(fld.name())
        val_str = "NULL" if val is None else str(val)
        rows.append(
            f'<tr><td style="color:#94a3b8; font-size:9.5px; padding:2px 6px; border-bottom:1px solid #1e293b;">{html.escape(fld.name())}</td>'
            f'<td style="color:#f8fafc; font-size:9.5px; font-weight:bold; padding:2px 6px; border-bottom:1px solid #1e293b; text-align:right;">{html.escape(val_str)}</td></tr>'
        )

    return (
        '<table width="280" cellspacing="0" cellpadding="0" '
        'style="font-family:Segoe UI, sans-serif; background-color:#0f172a; border:1.5px solid #0284c7; '
        'border-collapse:collapse; border-radius:6px; overflow:hidden;">'
        f'<tr><td colspan="2" bgcolor="#0284c7" style="color:#ffffff; font-size:11px; font-weight:bold; padding:5px 8px;">'
        f'&#128506; {html.escape(layer.name())}</td></tr>'
        f'<tr><td colspan="2" bgcolor="#1e293b" style="color:#38bdf8; font-size:10px; font-weight:bold; padding:4px 8px;">'
        f'{html.escape(title_val)}</td></tr>'
        f'{"".join(rows)}'
        '</table>'
    )


class CanvasHoverHUD(QObject):
    """Interactive Canvas MapTip Inspector & Pinning Engine with vector highlight."""

    # Signals
    featureHovered = pyqtSignal(object, object, str)  # (QgsVectorLayer, QgsFeature, html)
    featurePinned = pyqtSignal(object, object, str)   # (QgsVectorLayer, QgsFeature, html)
    cleared = pyqtSignal()
    pinStateChanged = pyqtSignal(bool)
    sampleUpdated = pyqtSignal(str, str)              # (html, summary_status)

    def __init__(
        self,
        canvas: "QgsMapCanvas",
        debounce_ms: int = 200,
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

        self._active_vector_layer: Optional[QgsVectorLayer] = None
        self._active_raster_layers: list[QgsRasterLayer] = []
        self._composite_mode = False

        self._hud_enabled = False
        self._cursor_enabled = False
        self._use_custom_cursor = True  # High-visibility reticle cursor enabled by default
        self._filter_installed = False
        self._pinned = False
        self._highlight_enabled = True
        self._click_to_pin = True

        self._current_feature: Optional[QgsFeature] = None
        self._current_layer: Optional[QgsVectorLayer] = None
        self._last_sampled_html = ""

        self._highlight: Optional[QgsHighlight] = None
        self._inspection_cursor: Optional[QCursor] = None
        with contextlib.suppress(Exception):
            self._inspection_cursor = create_inspection_cursor()

    def _apply_cursor(self, enabled: bool) -> None:
        """Apply or remove custom inspection cursor on both canvas and viewport."""
        vp = self.canvas.viewport() if self.canvas else None
        if not vp:
            return
        if enabled and self._use_custom_cursor and self._inspection_cursor:
            vp.setCursor(self._inspection_cursor)
            with contextlib.suppress(Exception):
                if hasattr(self.canvas, "setCursor"):
                    self.canvas.setCursor(self._inspection_cursor)
        else:
            with contextlib.suppress(Exception):
                vp.unsetCursor()
            with contextlib.suppress(Exception):
                if hasattr(self.canvas, "unsetCursor"):
                    self.canvas.unsetCursor()

    def _sync_canvas_event_filter(self) -> None:
        """Attach or detach viewport event filter based on inspector state."""
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

        self._apply_cursor(self._cursor_enabled and self._use_custom_cursor)

    def set_cursor_mode(self, enabled: bool) -> None:
        """Toggle unique inspection reticle cursor."""
        self._cursor_enabled = enabled
        self._sync_canvas_event_filter()

    def set_use_custom_cursor(self, enabled: bool) -> None:
        """Toggle preference for high-visibility reticle cursor."""
        self._use_custom_cursor = enabled
        self._sync_canvas_event_filter()

    def set_hud_mode(self, enabled: bool) -> None:
        """Activate or deactivate interactive canvas MapTip inspector."""
        self._hud_enabled = enabled
        if not enabled:
            self._timer.stop()
            self.set_pinned(False)
            self._clear_highlight()
            QToolTip.hideText()
        self._sync_canvas_event_filter()

    def set_highlight_enabled(self, enabled: bool) -> None:
        """Toggle canvas feature glowing highlight."""
        self._highlight_enabled = enabled
        if not enabled:
            self._clear_highlight()

    def set_click_to_pin(self, enabled: bool) -> None:
        """Toggle whether left clicking on canvas pins the inspected card."""
        self._click_to_pin = enabled

    def set_active_vector(self, layer: Optional[QgsVectorLayer]) -> None:
        """Set primary target vector layer for feature inspection."""
        self._active_vector_layer = layer if is_layer_alive(layer) else None
        if not self._pinned:
            self._clear_highlight()

    def set_active_raster(self, layer: Optional[QgsRasterLayer]) -> None:
        """Set fallback raster layer."""
        self._active_raster_layers = [layer] if is_layer_alive(layer) else []

    def set_target_rasters(self, layers: list[QgsRasterLayer]) -> None:
        self._active_raster_layers = [lyr for lyr in layers if is_layer_alive(lyr)]

    def set_vector_layer(self, layer: Optional[QgsVectorLayer]) -> None:
        self.set_active_vector(layer)

    def set_composite_mode(self, enabled: bool) -> None:
        self._composite_mode = enabled

    def is_active(self) -> bool:
        return self._hud_enabled

    def is_pinned(self) -> bool:
        return self._pinned

    def start(self) -> None:
        self.set_hud_mode(True)

    def stop(self) -> None:
        self.set_hud_mode(False)
        self.set_cursor_mode(False)
        self._pinned = False
        self._clear_highlight()
        self.pinStateChanged.emit(False)
        QToolTip.hideText()

    def _update_highlight(self, geom: QgsGeometry, layer: QgsVectorLayer, pinned: bool = False) -> None:
        """Render glowing boundary outline on canvas around the inspected feature."""
        if not self._highlight_enabled or not self.canvas or not geom or not layer:
            self._clear_highlight()
            return

        with contextlib.suppress(Exception):
            if self._highlight:
                self._highlight.hide()
                self._highlight = None

            self._highlight = QgsHighlight(self.canvas, geom, layer)
            if pinned:
                # Golden amber glow when pinned
                self._highlight.setColor(QColor(245, 158, 11, 230))
                self._highlight.setFillColor(QColor(245, 158, 11, 45))
                self._highlight.setWidth(3.0)
            else:
                # Electric cyan glow when hovering
                self._highlight.setColor(QColor(6, 182, 212, 220))
                self._highlight.setFillColor(QColor(6, 182, 212, 35))
                self._highlight.setWidth(2.0)

            self._highlight.show()

    def _clear_highlight(self) -> None:
        """Safely remove canvas highlight item."""
        if self._highlight:
            with contextlib.suppress(Exception):
                self._highlight.hide()
            self._highlight = None

    def set_pinned(self, pinned: bool) -> None:
        """Pin / freeze current card stationary on canvas, or unpin cleanly."""
        self._pinned = pinned
        if pinned:
            self._pinned_global_pos = self._last_global_pos
            self._pinned_screen_pos = self._last_screen_pos
            if self._current_feature and is_layer_alive(self._current_layer) and self._current_feature.hasGeometry():
                self._update_highlight(self._current_feature.geometry(), self._current_layer, pinned=True)
            if self._last_sampled_html:
                self._display_hud(self._last_sampled_html)
            self.pinStateChanged.emit(True)
            if is_layer_alive(self._current_layer) and self._current_feature:
                self.featurePinned.emit(self._current_layer, self._current_feature, self._last_sampled_html)
        else:
            self._clear_highlight()
            QToolTip.hideText()
            self.pinStateChanged.emit(False)
            self.cleared.emit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        etype = event.type()
        if hasattr(QEvent, "Type"):
            ev_mouse_move = QEvent.Type.MouseMove
            ev_enter = QEvent.Type.Enter
            ev_leave = QEvent.Type.Leave
            ev_press = QEvent.Type.MouseButtonPress
            ev_key_press = QEvent.Type.KeyPress
        else:
            ev_mouse_move = getattr(QEvent, "MouseMove", 5)
            ev_enter = getattr(QEvent, "Enter", 10)
            ev_leave = getattr(QEvent, "Leave", 11)
            ev_press = getattr(QEvent, "MouseButtonPress", 2)
            ev_key_press = getattr(QEvent, "KeyPress", 6)

        vp = self.canvas.viewport() if self.canvas else None

        # Enforce custom cursor if enabled
        if self._cursor_enabled and self._use_custom_cursor and self._inspection_cursor and vp:
            if etype in (ev_mouse_move, ev_enter):
                vp.setCursor(self._inspection_cursor)

        if not self._hud_enabled:
            return super().eventFilter(watched, event)

        # 1. Escape key dismisses pinned tooltip
        if etype == ev_key_press:
            key_esc = getattr(Qt.Key, "Key_Escape", None) if hasattr(Qt, "Key") else getattr(Qt, "Key_Escape", None)
            if hasattr(event, "key") and event.key() == key_esc:
                if self._pinned:
                    self.set_pinned(False)
                    return True

        # 2. Mouse Move Handling
        elif etype == ev_mouse_move:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            global_pos = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )
            self._last_screen_pos = pos
            self._last_global_pos = global_pos

            if not self._pinned:
                self._timer.start(self.debounce_ms)
            else:
                # If pinned, ensure tooltip stays visible
                if not QToolTip.isVisible() and self._last_sampled_html:
                    self._display_hud(self._last_sampled_html)

        # 3. Mouse Click Handling (Click to Pin or Unpin)
        elif etype == ev_press:
            btn_left = getattr(Qt.MouseButton, "LeftButton", None) if hasattr(Qt, "MouseButton") else getattr(Qt, "LeftButton", None)
            mod_shift = getattr(Qt.KeyboardModifier, "ShiftModifier", None) if hasattr(Qt, "KeyboardModifier") else getattr(Qt, "ShiftModifier", None)
            is_left = hasattr(event, "button") and event.button() == btn_left
            is_shift = bool(hasattr(event, "modifiers") and mod_shift and (event.modifiers() & mod_shift))

            if is_left:
                if self._click_to_pin or is_shift:
                    if self._current_feature and not self._pinned:
                        self.set_pinned(True)
                        return True
                    elif self._pinned:
                        # Clicked again while pinned: unpin
                        self.set_pinned(False)
                        return True

        # 4. Canvas Leave
        elif etype == ev_leave:
            if vp:
                local_pos = vp.mapFromGlobal(QCursor.pos())
                if not vp.rect().contains(local_pos):
                    self._timer.stop()
                    if not self._pinned:
                        self._clear_highlight()
                        QToolTip.hideText()

        return super().eventFilter(watched, event)

    def _resolve_target_vector_layer(self) -> Optional[QgsVectorLayer]:
        """Resolve the vector layer to inspect: active vector or top visible vector layer."""
        if is_layer_alive(self._active_vector_layer):
            return self._active_vector_layer

        curr = self.canvas.currentLayer() if self.canvas else None
        if is_layer_alive(curr) and isinstance(curr, QgsVectorLayer):
            return curr

        # Fallback to first visible vector layer in project
        for lyr in QgsProject.instance().mapLayers().values():
            if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer):
                return lyr
        return None

    def _on_debounce_timeout(self) -> None:
        if not self._hud_enabled or self._pinned or not self.canvas:
            return

        canvas_crs = self.canvas.mapSettings().destinationCrs()
        map_pt = self.canvas.getCoordinateTransform().toMapCoordinates(self._last_screen_pos)
        project = QgsProject.instance()

        # 1. Primary: Vector Feature Inspection & Card Evaluation
        vlayer = self._resolve_target_vector_layer()
        matched_feature: Optional[QgsFeature] = None

        if is_layer_alive(vlayer):
            vlayer_crs = vlayer.crs()
            if vlayer_crs != canvas_crs and canvas_crs.isValid() and vlayer_crs.isValid():
                tr_v = QgsCoordinateTransform(canvas_crs, vlayer_crs, project)
                v_pt = map_pt
                with contextlib.suppress(Exception):
                    v_pt = tr_v.transform(map_pt)
            else:
                v_pt = map_pt

            pt_geom = QgsGeometry.fromPointXY(v_pt)
            tol = self.canvas.mapUnitsPerPixel() * 5.0
            if vlayer_crs.isGeographic() and not canvas_crs.isGeographic():
                tol = tol / 111320.0

            req = (
                QgsFeatureRequest()
                .setFilterRect(pt_geom.buffer(tol, 4).boundingBox())
                .setLimit(5)
            )

            for feat in vlayer.getFeatures(req):
                if not feat.hasGeometry():
                    continue
                geom = feat.geometry()
                if geom.intersects(pt_geom) or geom.distance(pt_geom) <= tol:
                    matched_feature = feat
                    break

        if matched_feature and vlayer:
            self._current_feature = matched_feature
            self._current_layer = vlayer
            card_html = evaluate_vector_feature_maptip(vlayer, matched_feature)
            status_text = f"Feature #{matched_feature.id()} ({vlayer.name()})"

            self._last_sampled_html = card_html
            self._update_highlight(matched_feature.geometry(), vlayer, pinned=False)
            self.sampleUpdated.emit(card_html, status_text)
            self.featureHovered.emit(vlayer, matched_feature, card_html)
            self._display_hud(card_html)
            return

        # 2. Secondary Fallback: Raster Cell Sampling (if raster layer active)
        target_rasters = self._active_raster_layers or [
            lyr for lyr in project.mapLayers().values() if is_layer_alive(lyr) and isinstance(lyr, QgsRasterLayer)
        ]

        if target_rasters:
            rlayer = target_rasters[0]
            rlayer_crs = rlayer.crs()
            sample_pt = map_pt
            if rlayer_crs != canvas_crs and canvas_crs.isValid() and rlayer_crs.isValid():
                tr_r = QgsCoordinateTransform(canvas_crs, rlayer_crs, project)
                with contextlib.suppress(Exception):
                    sample_pt = tr_r.transform(map_pt)

            if rlayer.extent().contains(sample_pt) and rlayer.dataProvider():
                provider = rlayer.dataProvider()
                lines = [
                    '<table width="260" cellspacing="0" cellpadding="0" '
                    'style="font-family:Segoe UI, sans-serif; background-color:#0f172a; border:1px solid #0284c7; '
                    'border-collapse:collapse; border-radius:6px; overflow:hidden;">',
                    f'<tr><td colspan="2" bgcolor="#0284c7" style="color:#ffffff; font-size:11px; font-weight:bold; padding:4px 8px;">'
                    f'&#9638; {html.escape(rlayer.name())}</td></tr>',
                    f'<tr><td colspan="2" style="font-size:8.5px; color:#94a3b8; padding:2px 8px; background-color:#1e293b; '
                    f'border-bottom:1px solid #334155;">X: {sample_pt.x():.2f} &nbsp;|&nbsp; Y: {sample_pt.y():.2f}</td></tr>',
                ]
                band_cnt = min(4, rlayer.bandCount())
                for b in range(1, band_cnt + 1):
                    val, ok = provider.sample(sample_pt, b)
                    val_str = f"{val:.2f}" if (ok and val is not None and isinstance(val, (int, float))) else "NoData"
                    lines.append(
                        f'<tr><td style="color:#cbd5e1; font-size:9.5px; padding:2px 8px; border-bottom:1px solid #1e293b;">Band {b}</td>'
                        f'<td align="right" style="color:#38bdf8; font-size:10px; font-weight:bold; padding:2px 8px; border-bottom:1px solid #1e293b;">{val_str}</td></tr>'
                    )
                lines.append('</table>')
                raster_html = "\n".join(lines)
                status_text = f"X: {map_pt.x():.2f}, Y: {map_pt.y():.2f}"
                self._current_feature = None
                self._current_layer = None
                self._last_sampled_html = raster_html
                self._clear_highlight()
                self.sampleUpdated.emit(raster_html, status_text)
                self._display_hud(raster_html)
                return

        # 3. Blank Canvas
        self._current_feature = None
        self._current_layer = None
        self._clear_highlight()
        if not self._pinned:
            QToolTip.hideText()
            self.cleared.emit()

    def _display_hud(self, html_content: str) -> None:
        """Display tooltip with generous dwell duration and pin status badge."""
        if not html_content:
            QToolTip.hideText()
            return

        vp = self.canvas.viewport() if self.canvas else self.canvas

        if self._pinned:
            footer = (
                '<tr><td colspan="2" bgcolor="#1e293b" style="font-size:8.5px; color:#f59e0b; padding:4px 8px; '
                'border-top:1px solid #334155; text-align:right;">&#128204; <b>PINNED</b> (Click canvas or press Esc to unpin)</td></tr>'
            )
            base_pos = self._pinned_global_pos if not self._pinned_global_pos.isNull() else self._last_global_pos
            offset_pos = base_pos + QPoint(20, 20)
            # Huge tolerance rect prevents Qt from dismissing pinned tooltip
            tolerance_rect = QRect(-500000, -500000, 1000000, 1000000)
        else:
            footer = (
                '<tr><td colspan="2" bgcolor="#0f172a" style="font-size:8px; color:#64748b; padding:3px 8px; '
                'border-top:1px solid #334155; text-align:right;">&#128161; Click canvas to <b>PIN</b> this card</td></tr>'
            )
            offset_pos = self._last_global_pos + QPoint(20, 20)
            tolerance_rect = vp.rect() if (vp and hasattr(vp, "rect")) else QRect(0, 0, 10000, 10000)

        display_html = html_content.replace('</table>', f'{footer}</table>')
        QToolTip.showText(offset_pos, display_html, vp, tolerance_rect, 60000)


# Alias for backward compatibility
CanvasMapTipInspector = CanvasHoverHUD
