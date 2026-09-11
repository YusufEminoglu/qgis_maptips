"""QGIS lifecycle for Qgis Advanced Map Tips&Actions."""
from __future__ import annotations

import contextlib
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QAction, QIcon
from qgis.PyQt.QtWidgets import QMessageBox

from .dialogs.dock import QgisMapTipsDock


class QgisMapTipsPlugin:
    """Plugin entry point for Qgis Advanced Map Tips&Actions studio."""

    MENU_NAME = "&Qgis Advanced Map Tips&Actions"

    def __init__(self, iface) -> None:
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.about_action = None
        self.dock = None

    def initGui(self) -> None:
        if self.iface is None:
            return

        icon_path = os.path.join(self.plugin_dir, "icons", "icon.png")
        icon = QIcon(icon_path)

        self.action = QAction(icon, "Qgis Advanced Map Tips&Actions", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_dock)

        self.iface.addPluginToMenu(self.MENU_NAME, self.action)
        self.iface.addToolBarIcon(self.action)

        self.about_action = QAction("About Qgis Advanced Map Tips&Actions", self.iface.mainWindow())
        self.about_action.triggered.connect(self._show_about)
        self.iface.addPluginToMenu(self.MENU_NAME, self.about_action)

    def unload(self) -> None:
        if self.dock is not None:
            self.dock.unload()
            self.iface.removeDockWidget(self.dock)
            self.dock.setParent(None)
            self.dock.deleteLater()
            self.dock = None

        if self.action is not None:
            self.iface.removePluginMenu(self.MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            with contextlib.suppress(TypeError):
                self.action.triggered.disconnect(self._toggle_dock)
            self.action.setParent(None)
            self.action.deleteLater()
            self.action = None

        if self.about_action is not None:
            self.iface.removePluginMenu(self.MENU_NAME, self.about_action)
            with contextlib.suppress(TypeError):
                self.about_action.triggered.disconnect(self._show_about)
            self.about_action.setParent(None)
            self.about_action.deleteLater()
            self.about_action = None

    def _toggle_dock(self, visible: bool) -> None:
        if self.dock is None:
            self.dock = QgisMapTipsDock(self.iface, self.iface.mainWindow())
            self.dock.visibilityChanged.connect(self.action.setChecked)
            self.iface.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea,
                self.dock,
            )
            self.dock.setVisible(True)
            self.dock.raise_()
            return

        self.dock.setVisible(bool(visible))
        if visible:
            self.dock.raise_()

    def _show_about(self) -> None:
        QMessageBox.information(
            self.iface.mainWindow() if self.iface else None,
            "About Qgis Advanced Map Tips&Actions",
            "<h3>Qgis Advanced Map Tips&Actions</h3>"
            "<p><b>Version:</b> 0.1.0<br/>"
            "<b>Author:</b> Yusuf Eminoğlu<br/>"
            "<b>License:</b> GPL-3.0-or-later</p>"
            "<p>Design responsive Qt-safe HTML cards, zero-dependency micro-charts "
            "(progress bars, SVG donuts), and 1-click dynamic web and spatial actions "
            "for vector and raster layers in QGIS 3.28+ and QGIS 4.</p>",
        )
