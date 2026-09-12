"""Palette-aware styling for the Qgis Advanced Map Tips&Actions studio dock.

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
    """Generate dynamic stylesheet for the Qgis MapTips dock."""
    t = dock_color_tokens(palette)
    return f"""
QWidget#maptipsRoot {{
    background-color: {t['surface']};
    color: {t['text']};
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 6px;
    margin: 0px 0px 0px 0px;
}}
QScrollBar::handle:vertical {{
    background: {t['border']};
    min-height: 24px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 6px;
    margin: 0px 0px 0px 0px;
}}
QScrollBar::handle:horizontal {{
    background: {t['border']};
    min-width: 24px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['accent']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* Form inputs */
QLineEdit, QSpinBox, QComboBox {{
    background-color: {t['input_surface']};
    color: {t['input_text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 2px 6px;
    min-height: 22px;
    font-size: 8.5pt;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {t['accent']};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid {t['border']};
}}

/* Hero Panel */
QFrame#heroPanel {{
    background-color: {t['hero']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 6px 8px;
}}
QLabel#heroMark {{
    background-color: {t['accent']};
    color: #ffffff;
    font-weight: 800;
    font-size: 10pt;
    border-radius: 5px;
}}
QLabel#heroTitle {{
    font-size: 11pt;
    font-weight: bold;
    color: {t['text']};
}}
QLabel#heroEyebrow {{
    color: {t['accent']};
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#heroBadge {{
    color: {t['accent']};
    background-color: {t['status']};
    border: 1px solid {t['accent']};
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 7.5pt;
    font-weight: 600;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {t['border']};
    background-color: {t['surface']};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {t['card']};
    color: {t['text']};
    padding: 4px 10px;
    margin-right: 2px;
    border: 1px solid {t['border']};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-size: 8.5pt;
}}
QTabBar::tab:selected {{
    background-color: {t['tab_active']};
    color: {t['accent']};
    font-weight: bold;
    border-color: {t['accent']};
}}

/* Group Boxes & Sections */
QGroupBox {{
    font-weight: bold;
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 6px;
    padding-top: 8px;
    background-color: {t['card']};
    font-size: 8.5pt;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {t['text']};
}}

/* Buttons */
QPushButton#primaryAction {{
    background-color: {t['accent']};
    color: {t['accent_text']};
    border: 1px solid {t['accent']};
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 8.5pt;
    font-weight: bold;
}}
QPushButton#primaryAction:hover {{
    background-color: {t['accent_hover']};
}}
QPushButton#secondaryAction {{
    background-color: {t['card']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 8.5pt;
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
QListWidget {{
    background-color: {t['input_surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 2px;
    font-size: 8pt;
}}
QListWidget::item {{
    padding: 3px 5px;
    border-bottom: 1px solid {t['border']};
}}
QListWidget::item:selected {{
    background-color: {t['accent']};
    color: {t['accent_text']};
    border-radius: 3px;
}}
QPushButton#presetChip {{
    background-color: {t['card']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 7.5pt;
    font-weight: 600;
}}
QPushButton#presetChip:hover {{
    border-color: {t['accent']};
    color: {t['accent']};
    background-color: {t['hero']};
}}
QLabel#layerBadge {{
    color: {t['text']};
    background-color: {t['card']};
    border: 1px solid {t['border']};
    border-radius: 3px;
    padding: 2px 5px;
    font-size: 7.5pt;
}}
QPushButton#quietButton {{
    background-color: {t['card']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 8pt;
    font-weight: 600;
}}
QPushButton#quietButton:hover {{
    border-color: {t['accent']};
    color: {t['accent']};
    background-color: {t['hero']};
}}
QPushButton#collapsibleHeader {{
    background-color: {t['card']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 8.5pt;
    font-weight: 600;
    text-align: left;
}}
QPushButton#collapsibleHeader:hover {{
    border-color: {t['accent']};
    background-color: {t['hero']};
}}
QFrame#collapsibleContent {{
    border-left: 2px solid {t['accent']};
    margin-left: 4px;
    padding-left: 6px;
    background-color: transparent;
}}
QListWidget {{
    background-color: {t['input_surface']};
    color: {t['input_text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 2px;
}}
QListWidget::item {{
    padding: 3px 6px;
    border-bottom: 1px solid {t['border']};
}}
QListWidget::item:selected {{
    background-color: {t['selection']};
    color: #ffffff;
    border-radius: 3px;
}}
"""


def apply_adaptive_theme(widget: QWidget) -> None:
    """Apply the adaptive palette-derived theme to a widget."""
    widget.setStyleSheet(dock_stylesheet(widget.palette()))
