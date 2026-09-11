"""Palette-aware styling for the 02Maptips studio dock.

Derives surfaces, cards, borders, and typography from the active Qt palette
to guarantee optimal readability across QGIS light, dark, and high-contrast themes.
"""
from __future__ import annotations

from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QApplication, QWidget


def _hex(color: QColor) -> str:
    return color.name()


def _mix(first: QColor, second: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(first.red() * (1.0 - amount) + second.red() * amount),
        round(first.green() * (1.0 - amount) + second.green() * amount),
        round(first.blue() * (1.0 - amount) + second.blue() * amount),
    )


def _contrast_text(background: QColor) -> QColor:
    lum = (
        0.2126 * background.red()
        + 0.7152 * background.green()
        + 0.0722 * background.blue()
    )
    return QColor("#0f172a") if lum >= 150 else QColor("#ffffff")


def dock_color_tokens(palette: QPalette | None = None) -> dict[str, str]:
    """Calculate theme color tokens from the current application palette."""
    active = palette or QApplication.palette()
    window = active.color(QPalette.ColorRole.Window)
    base = active.color(QPalette.ColorRole.Base)
    text = active.color(QPalette.ColorRole.WindowText)
    input_text = active.color(QPalette.ColorRole.Text)
    button = active.color(QPalette.ColorRole.Button)
    button_text = active.color(QPalette.ColorRole.ButtonText)
    highlight = active.color(QPalette.ColorRole.Highlight)

    dark = window.lightness() < 128
    white = QColor("#ffffff")

    # Emerald-cyan modern accent
    accent = QColor("#10b981" if dark else "#0f766e")
    accent_hover = QColor("#34d399" if dark else "#115e59")
    accent_text = _contrast_text(accent)

    surface = _mix(window, white, 0.06) if dark else _mix(window, base, 0.75)
    card = _mix(window, white, 0.12) if dark else base
    input_surface = _mix(base, white, 0.05) if dark else base
    hero = _mix(surface, accent, 0.14 if dark else 0.08)
    tab_active = _mix(surface, accent, 0.22 if dark else 0.12)
    border = _mix(text, surface, 0.78 if dark else 0.84)
    subtle = _mix(text, surface, 0.42 if dark else 0.38)
    status = _mix(accent, surface, 0.78 if dark else 0.88)

    return {
        "surface": _hex(surface),
        "card": _hex(card),
        "input_surface": _hex(input_surface),
        "hero": _hex(hero),
        "tab_active": _hex(tab_active),
        "text": _hex(text),
        "input_text": _hex(input_text),
        "button": _hex(button),
        "button_text": _hex(button_text),
        "border": _hex(border),
        "subtle": _hex(subtle),
        "accent": _hex(accent),
        "accent_hover": _hex(accent_hover),
        "accent_text": _hex(accent_text),
        "status": _hex(status),
        "selection": _hex(highlight if highlight.isValid() else accent),
    }


def dock_stylesheet(palette: QPalette | None = None) -> str:
    """Generate dynamic stylesheet for the 02Maptips dock."""
    t = dock_color_tokens(palette)
    return f"""
QWidget#maptipsRoot {{
    background-color: {t['surface']};
    color: {t['text']};
}}
QFrame#heroPanel {{
    background-color: {t['hero']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 8px;
}}
QLabel#heroTitle {{
    font-size: 13pt;
    font-weight: bold;
    color: {t['text']};
}}
QLabel#heroBadge {{
    color: {t['accent']};
    background-color: {t['status']};
    border: 1px solid {t['accent']};
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 8pt;
    font-weight: 600;
}}
QTabWidget::pane {{
    border: 1px solid {t['border']};
    background-color: {t['surface']};
    border-radius: 6px;
}}
QTabBar::tab {{
    background-color: {t['card']};
    color: {t['text']};
    padding: 6px 12px;
    margin-right: 2px;
    border: 1px solid {t['border']};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}}
QTabBar::tab:selected {{
    background-color: {t['tab_active']};
    color: {t['accent']};
    font-weight: bold;
    border-color: {t['accent']};
}}
QGroupBox {{
    font-weight: bold;
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 10px;
    background-color: {t['card']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {t['text']};
}}
QPushButton#primaryAction {{
    background-color: {t['accent']};
    color: {t['accent_text']};
    border: 1px solid {t['accent']};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 9pt;
    font-weight: bold;
}}
QPushButton#primaryAction:hover {{
    background-color: {t['accent_hover']};
}}
QPushButton#secondaryAction {{
    background-color: {t['card']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton#secondaryAction:hover {{
    border-color: {t['accent']};
    color: {t['accent']};
}}
QTextBrowser#previewBox {{
    background-color: {t['input_surface']};
    border: 1px solid {t['border']};
    border-radius: 6px;
}}
"""


def apply_adaptive_theme(widget: QWidget) -> None:
    """Apply the adaptive palette-derived theme to a widget."""
    widget.setStyleSheet(dock_stylesheet(widget.palette()))
