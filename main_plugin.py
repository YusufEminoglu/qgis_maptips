"""QGIS lifecycle for Qgis Advanced Map Tips&Actions."""
from __future__ import annotations

import contextlib
import os
from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QAction, QIcon
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsApplication

from .dialogs.dock import QgisMapTipsDock
from .processing.provider import QgisMapTipsProvider


class QgisMapTipsPlugin:
    """Plugin entry point for Qgis Advanced Map Tips&Actions studio."""

    MENU_NAME = "&Qgis Advanced Map Tips&Actions"

    def __init__(self, iface) -> None:
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.cadastre_action = None
        self.manual_action = None
        self.rate_action = None
        self.about_action = None
        self.dock = None
        self.provider = None
        self.cadastre_tool = None

    def initProcessing(self) -> None:
        if self.provider is not None:
            return
        registry = QgsApplication.processingRegistry()
        if registry.providerById(QgisMapTipsProvider.PROVIDER_ID) is None:
            provider = QgisMapTipsProvider()
            if registry.addProvider(provider):
                self.provider = provider

    def initGui(self) -> None:
        self.initProcessing()

        if self.iface is None:
            return

        icon_path = os.path.join(self.plugin_dir, "icons", "icon.png")
        icon = QIcon(icon_path)

        # 1. Main Studio Toggle Action
        self.action = QAction(icon, "Qgis Advanced Map Tips&Actions Studio", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_dock)
        self.iface.addPluginToMenu(self.MENU_NAME, self.action)
        self.iface.addToolBarIcon(self.action)

        # 2. Interactive Canvas Cadastre Picker Action (Turkey Only, menu only - no toolbar icon)
        self.cadastre_action = QAction(
            "⚡ TKGM Canvas Cadastre Picker (Turkey Only)",
            self.iface.mainWindow(),
        )
        self.cadastre_action.setCheckable(True)
        self.cadastre_action.setToolTip(
            "Click anywhere on the map canvas to query and download the official cadastral parcel polygon (No layer needed, Turkey only)"
        )
        self.cadastre_action.triggered.connect(self._toggle_cadastre_tool)
        self.iface.addPluginToMenu(self.MENU_NAME, self.cadastre_action)

        # Sync tool active state with canvas
        canvas = self.iface.mapCanvas() if hasattr(self.iface, "mapCanvas") else None
        if canvas and hasattr(canvas, "mapToolSet"):
            with contextlib.suppress(Exception):
                canvas.mapToolSet.connect(self._on_map_tool_changed)

        # 3. User Manual & Online Guide Action
        self.manual_action = QAction("📖 User Manual & Online Guide...", self.iface.mainWindow())
        self.manual_action.triggered.connect(self._show_manual)
        self.iface.addPluginToMenu(self.MENU_NAME, self.manual_action)

        # 4. Rate Plugin Action
        self.rate_action = QAction("⭐ Rate Plugin on QGIS Hub...", self.iface.mainWindow())
        self.rate_action.triggered.connect(self._rate_plugin)
        self.iface.addPluginToMenu(self.MENU_NAME, self.rate_action)

        # 5. About Action
        self.about_action = QAction("About Qgis Advanced Map Tips&Actions", self.iface.mainWindow())
        self.about_action.triggered.connect(self._show_about)
        self.iface.addPluginToMenu(self.MENU_NAME, self.about_action)

        # 6. Global Action URL Scheme Handler (enables 1-click card actions from canvas MapTips)
        from .core.action_builder import ActionUrlHandler
        from qgis.PyQt.QtGui import QDesktopServices
        self.action_url_handler = ActionUrlHandler(self.iface)
        QDesktopServices.setUrlHandler("action", self.action_url_handler, "handleUrl")

    def unload(self) -> None:
        if hasattr(self, "action_url_handler") and self.action_url_handler is not None:
            with contextlib.suppress(Exception):
                from qgis.PyQt.QtGui import QDesktopServices
                QDesktopServices.unsetUrlHandler("action")
            self.action_url_handler = None

        canvas = self.iface.mapCanvas() if self.iface and hasattr(self.iface, "mapCanvas") else None
        if canvas and hasattr(canvas, "mapToolSet"):
            with contextlib.suppress(Exception):
                canvas.mapToolSet.disconnect(self._on_map_tool_changed)

        if self.cadastre_tool is not None:
            if canvas and canvas.mapTool() == self.cadastre_tool:
                canvas.unsetMapTool(self.cadastre_tool)
            self.cadastre_tool = None

        if self.cadastre_action is not None:
            self.iface.removePluginMenu(self.MENU_NAME, self.cadastre_action)
            with contextlib.suppress(TypeError):
                self.cadastre_action.triggered.disconnect(self._toggle_cadastre_tool)
            self.cadastre_action.setParent(None)
            self.cadastre_action.deleteLater()
            self.cadastre_action = None

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

        if self.manual_action is not None:
            self.iface.removePluginMenu(self.MENU_NAME, self.manual_action)
            with contextlib.suppress(TypeError):
                self.manual_action.triggered.disconnect(self._show_manual)
            self.manual_action.setParent(None)
            self.manual_action.deleteLater()
            self.manual_action = None

        if self.rate_action is not None:
            self.iface.removePluginMenu(self.MENU_NAME, self.rate_action)
            with contextlib.suppress(TypeError):
                self.rate_action.triggered.disconnect(self._rate_plugin)
            self.rate_action.setParent(None)
            self.rate_action.deleteLater()
            self.rate_action = None

        if self.about_action is not None:
            self.iface.removePluginMenu(self.MENU_NAME, self.about_action)
            with contextlib.suppress(TypeError):
                self.about_action.triggered.disconnect(self._show_about)
            self.about_action.setParent(None)
            self.about_action.deleteLater()
            self.about_action = None

        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    def toggle_cadastre_tool(self, enable: Optional[bool] = None) -> None:
        """Programmatic toggle for the canvas cadastre tool."""
        canvas = self.iface.mapCanvas() if self.iface else None
        if not canvas:
            return

        target_state = (not (canvas.mapTool() == self.cadastre_tool)) if enable is None else bool(enable)
        self._toggle_cadastre_tool(target_state)

    def _toggle_cadastre_tool(self, checked: bool) -> None:
        canvas = self.iface.mapCanvas() if self.iface else None
        if not canvas:
            return

        if checked:
            if self.cadastre_tool is None:
                from .core.cadastre_tool import InteractiveCadastreTool
                self.cadastre_tool = InteractiveCadastreTool(canvas, self.iface)
                if hasattr(self.cadastre_tool, "deactivated"):
                    self.cadastre_tool.deactivated.connect(self._on_cadastre_tool_deactivated)
            canvas.setMapTool(self.cadastre_tool)
            if self.cadastre_action and not self.cadastre_action.isChecked():
                self.cadastre_action.setChecked(True)
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushInfo(
                    "TKGM Cadastre Picker",
                    "🎯 Canvas Cadastre Picker Active: Click anywhere on map canvas (over satellite basemap or blank) to download parcel.",
                )
        else:
            if self.cadastre_tool and canvas.mapTool() == self.cadastre_tool:
                canvas.unsetMapTool(self.cadastre_tool)
            if self.cadastre_action and self.cadastre_action.isChecked():
                self.cadastre_action.setChecked(False)

        if self.dock and hasattr(self.dock, "sync_cadastre_tool_state"):
            self.dock.sync_cadastre_tool_state(checked)

    def _on_cadastre_tool_deactivated(self) -> None:
        if self.cadastre_action and self.cadastre_action.isChecked():
            self.cadastre_action.setChecked(False)
        if self.dock and hasattr(self.dock, "sync_cadastre_tool_state"):
            self.dock.sync_cadastre_tool_state(False)

    def _on_map_tool_changed(self, new_tool) -> None:
        is_ours = bool(self.cadastre_tool and new_tool == self.cadastre_tool)
        if self.cadastre_action and self.cadastre_action.isChecked() != is_ours:
            self.cadastre_action.setChecked(is_ours)
        if self.dock and hasattr(self.dock, "sync_cadastre_tool_state"):
            self.dock.sync_cadastre_tool_state(is_ours)

    def _toggle_dock(self, visible: bool) -> None:
        if self.dock is None:
            self.dock = QgisMapTipsDock(self.iface, self.iface.mainWindow(), plugin=self)
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
        import configparser

        ver = "0.2.0"
        with contextlib.suppress(Exception):
            cp = configparser.ConfigParser()
            cp.read(str(self.plugin_dir / "metadata.txt"), encoding="utf-8")
            if cp.has_option("general", "version"):
                ver = cp.get("general", "version").strip()

        QMessageBox.information(
            self.iface.mainWindow() if self.iface else None,
            "About Qgis Advanced Map Tips&Actions",
            "<h3>Qgis Advanced Map Tips&Actions</h3>"
            f"<p><b>Version:</b> {ver}<br/>"
            "<b>Author:</b> Yusuf Eminoğlu<br/>"
            "<b>Repository:</b> <a href='https://gitlab.com/geophilo1/qgis_maptips'>https://gitlab.com/geophilo1/qgis_maptips</a> (GitLab)<br/>"
            "<b>Issues:</b> <a href='https://gitlab.com/geophilo1/qgis_maptips/-/issues'>GitLab Issues</a><br/>"
            "<b>License:</b> GPL-3.0-or-later</p>"
            "<p>Design responsive Qt-safe HTML cards, zero-dependency micro-charts "
            "(progress bars, SVG donuts, sparklines), conditional status badges, "
            "and 1-click dynamic web and spatial actions for vector and raster layers in QGIS 3.28+ and QGIS 4.</p>"
            "<p><b>🛠️ Interactive Action Studio:</b> Browse 22 ready-to-use URL & PyQGIS action templates across 5 categories, "
            "insert layer fields and spatial expressions, revise parameters/code, test-run on sample features, and export/import JSON action packs.</p>"
            "<hr/>"
            "<p><b>🎯 Instant Canvas Cadastre Picker:</b> 1-click official TKGM MEGSİS parcel query and polygon "
            "download directly from map canvas coordinates without selecting any vector layer (Turkey Only).</p>"
            "<hr/>"
            "<p><b>Special Thanks:</b> Sincere gratitude to "
            "<a href='https://github.com/geographyclub'>geographyclub</a> "
            "for creative inspiration on QGIS layout HTML styling, compact card aesthetics, and advanced attribute expressions; "
            "and to <a href='https://github.com/okansafak/qgistkgmplugin'>Okan Şafak (qgistkgmplugin)</a> "
            "for pioneering creative inspiration on 1-click canvas cadastre parcel downloading from TKGM MEGSİS.</p>"
            "<p><b>Third-Party Notice:</b> MEGSİS cadastral queries are subject to fair-use rate limits and daily quotas (~100 queries/day). "
            "See <code>THIRD_PARTY.md</code> for full terms and service policies.</p>",
        )

    def _show_manual(self) -> None:
        from .dialogs.quick_manual import QuickManualDialog

        dlg = QuickManualDialog(self.iface.mainWindow() if self.iface else None)
        dlg.exec()

    def _rate_plugin(self) -> None:
        import webbrowser

        webbrowser.open("https://plugins.qgis.org/plugins/qgis_maptips/")
        if self.iface and hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushInfo(
                "Qgis MapTips", "⭐ Thank you for your support! Opening QGIS Plugin Hub review page."
            )
