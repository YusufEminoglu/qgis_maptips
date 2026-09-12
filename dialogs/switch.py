"""iOS-style animated toggle switch widget.

Provides a smooth sliding pill switch with green (ON) and red (OFF) states,
accessible keyboard handling, and Qt5/Qt6 dual-runtime compatibility.
"""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from qgis.PyQt.QtGui import QBrush, QColor, QFont, QPainter, QPen
from qgis.PyQt.QtWidgets import QAbstractButton, QWidget


class IOSToggleSwitch(QAbstractButton):
    """An iOS-style sliding pill toggle switch with smooth animated state transitions."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        default_on: bool = True,
        on_color: str = "#10b981",
        off_color: str = "#ef4444",
        width: int = 54,
        height: int = 26,
    ) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self._on_color = QColor(on_color)
        self._off_color = QColor(off_color)
        self._offset: float = 1.0 if default_on else 0.0
        self.setChecked(default_on)
        self.setFixedSize(width, height)
        cursor = getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor", None)
        if cursor is not None:
            self.setCursor(cursor)

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(170)
        curve_type = getattr(QEasingCurve, "Type", QEasingCurve)
        easing = getattr(curve_type, "InOutCubic", None) or getattr(QEasingCurve, "InOutCubic", 0)
        self._anim.setEasingCurve(easing)
        self.toggled.connect(self._start_animation)

    @pyqtProperty(float)
    def offset(self) -> float:
        return self._offset

    @offset.setter
    def offset(self, val: float) -> None:
        self._offset = max(0.0, min(1.0, float(val)))
        self.update()

    def _start_animation(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setCheckedSilently(self, checked: bool) -> None:
        """Update checked state without triggering animation or extra signals."""
        self.blockSignals(True)
        self.setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self.blockSignals(False)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        render_hint_class = getattr(QPainter, "RenderHint", QPainter)
        render_hint = getattr(render_hint_class, "Antialiasing", 0)
        p.setRenderHint(render_hint)
        r = self.rect()

        t = self._offset

        # Interpolate track background color between OFF (red) and ON (green)
        cr = int(round(self._off_color.red() * (1.0 - t) + self._on_color.red() * t))
        cg = int(round(self._off_color.green() * (1.0 - t) + self._on_color.green() * t))
        cb = int(round(self._off_color.blue() * (1.0 - t) + self._on_color.blue() * t))
        track_color = QColor(cr, cg, cb)

        pen_style_class = getattr(Qt, "PenStyle", Qt)
        no_pen = getattr(pen_style_class, "NoPen", 0)
        p.setPen(no_pen)
        p.setBrush(QBrush(track_color))
        radius = r.height() / 2.0
        p.drawRoundedRect(QRectF(r), radius, radius)

        # Draw status text label (ON / OFF)
        p.setPen(QColor(255, 255, 255, 230))
        font = p.font()
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)

        align_class = getattr(Qt, "AlignmentFlag", Qt)
        align_vc = getattr(align_class, "AlignVCenter", 0)
        align_left = getattr(align_class, "AlignLeft", 0)
        align_right = getattr(align_class, "AlignRight", 0)

        if t > 0.5:
            # ON label visible on the left side
            p.drawText(QRectF(7, 0, 22, r.height()), align_vc | align_left, "ON")
        else:
            # OFF label visible on the right side
            p.drawText(QRectF(r.width() - 27, 0, 22, r.height()), align_vc | align_right, "OFF")

        # Subtle shadow and ring around thumb for depth
        thumb_size = r.height() - 4.0
        thumb_x = 2.0 + t * (r.width() - thumb_size - 4.0)
        thumb_y = 2.0

        # Thumb drop shadow
        p.setPen(no_pen)
        p.setBrush(QBrush(QColor(0, 0, 0, 45)))
        p.drawEllipse(QRectF(thumb_x, thumb_y + 1.2, thumb_size, thumb_size))

        # Thumb body
        p.setBrush(QBrush(QColor(255, 255, 255, 255)))
        p.setPen(QPen(QColor(0, 0, 0, 30), 0.8))
        p.drawEllipse(QRectF(thumb_x, thumb_y, thumb_size, thumb_size))

        p.end()
