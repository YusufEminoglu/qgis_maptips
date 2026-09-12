"""Lightweight, modern collapsible container for progressive UI disclosure.

Allows advanced configurations to remain neatly folded out of sight until
needed by power users, ensuring the primary workspace remains clean and calm.
"""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleSection(QWidget):
    """A clean, styled collapsible section with header toggle button."""

    def __init__(
        self,
        title: str = "Advanced Configurations",
        parent: Optional[QWidget] = None,
        initially_expanded: bool = False,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._is_expanded = initially_expanded

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(4)

        # Header Toggle Bar
        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("collapsibleHeader")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(initially_expanded)
        btn_cursor = getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor", None)
        if btn_cursor is not None:
            self.toggle_btn.setCursor(btn_cursor)
        self.toggle_btn.clicked.connect(self._on_toggled)
        main_layout.addWidget(self.toggle_btn)

        # Content Container
        self.content_area = QFrame()
        self.content_area.setObjectName("collapsibleContent")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(6)
        self.content_area.setVisible(initially_expanded)

        main_layout.addWidget(self.content_area)
        self._update_header_text()

    def _update_header_text(self) -> None:
        arrow = "▼" if self._is_expanded else "▶"
        self.toggle_btn.setText(f"{arrow}  {self._title}")

    def _on_toggled(self) -> None:
        self._is_expanded = not self._is_expanded
        self.content_area.setVisible(self._is_expanded)
        self._update_header_text()

    def set_content_layout(self, layout: QVBoxLayout) -> None:
        # Reparent into content area
        QWidget().setLayout(self.content_layout)
        self.content_layout = layout
        self.content_area.setLayout(layout)

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self.content_layout.addLayout(layout)

    def is_expanded(self) -> bool:
        return self._is_expanded

    def set_expanded(self, expanded: bool) -> None:
        self._is_expanded = expanded
        self.toggle_btn.setChecked(expanded)
        self.content_area.setVisible(expanded)
        self._update_header_text()
