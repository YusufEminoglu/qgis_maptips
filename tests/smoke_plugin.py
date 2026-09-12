"""Lifecycle smoke test for qgis_maptips.

Verifies imports, metadata integrity, classFactory, and full initGui() -> _toggle_dock() -> unload()
lifecycle against a mock/stub QgisInterface in headless QGIS runtime.
"""
from __future__ import annotations

import configparser
import contextlib
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.core import (
    QgsApplication,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas

PACKAGE = "qgis_maptips"


def _ok(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" - {detail}" if detail else ""))
    return bool(condition)


class _Canvas(QgsMapCanvas):
    def __init__(self, parent=None):
        super().__init__(parent)


class _MessageBar:
    def pushInfo(self, title: str, msg: str) -> None:
        pass

    def pushSuccess(self, title: str, msg: str) -> None:
        pass

    def pushWarning(self, title: str, msg: str) -> None:
        pass

    def pushCritical(self, title: str, msg: str) -> None:
        pass


class _Iface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._main = QMainWindow()
        self._canvas = _Canvas(self._main)
        self._msg_bar = _MessageBar()
        self.toolbar_icons = []
        self.menu_entries = []
        self.docks = []

    def mainWindow(self):
        return self._main

    def mapCanvas(self):
        return self._canvas

    def messageBar(self):
        return self._msg_bar

    def addToolBarIcon(self, action):
        self.toolbar_icons.append(action)

    def removeToolBarIcon(self, action):
        if action in self.toolbar_icons:
            self.toolbar_icons.remove(action)

    def addPluginToMenu(self, name, action):
        self.menu_entries.append((name, action))

    def removePluginMenu(self, name, action):
        self.menu_entries = [e for e in self.menu_entries if e != (name, action)]

    def addDockWidget(self, area, dock):
        self.docks.append(dock)

    def removeDockWidget(self, dock):
        if dock in self.docks:
            self.docks.remove(dock)


def test_metadata():
    p = PLUGIN_DIR / "metadata.txt"
    if not p.is_file():
        return _ok("metadata.txt exists", False, f"missing at {p}")
    cp = configparser.ConfigParser()
    cp.read(str(p), encoding="utf-8")
    has_general = cp.has_section("general")
    return _ok(
        "metadata.txt is valid INI with [general]",
        has_general and cp.has_option("general", "name"),
    )


def test_class_factory():
    mod = __import__(PACKAGE, fromlist=["classFactory"])
    fn = getattr(mod, "classFactory", None)
    return _ok("classFactory() exported", callable(fn))


def test_lifecycle(iface):
    app = QgsApplication.instance()
    mod = __import__(PACKAGE, fromlist=["classFactory"])
    plugin = mod.classFactory(iface)

    plugin.initGui()
    if app:
        app.processEvents()

    # Toggle dock open
    plugin._toggle_dock(True)
    if app:
        app.processEvents()

    # Toggle dock close
    plugin._toggle_dock(False)
    if app:
        app.processEvents()

    plugin.unload()
    if app:
        app.sendPostedEvents()
        app.processEvents()

    return _ok(
        "initGui -> _toggle_dock -> unload cycle completed cleanly",
        not iface.menu_entries and not iface.toolbar_icons,
    )


def test_maptip_injection():
    from qgis_maptips.core.template_engine import Archetype, TemplateConfig, compile_maptip_html

    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=val:integer", "Test Vector", "memory")
    cfg = TemplateConfig(
        archetype=Archetype.KPI_CARD,
        title_field="name",
        kpi_field="val",
        card_width=300,
    )
    compiled = compile_maptip_html(cfg)
    layer.setMapTipTemplate(compiled)
    return _ok("compile_maptip_html and layer.setMapTipTemplate()", layer.mapTipTemplate() == compiled)


def test_action_injection():
    from qgis_maptips.core.action_builder import apply_actions_to_layer

    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=id:string", "Test Parcels", "memory")
    added = apply_actions_to_layer(layer, ["google_satellite", "copy_clipboard"])
    actions = layer.actions().actions()
    return _ok("apply_actions_to_layer registered actions", added == 2 and len(actions) == 2)


def test_processing_provider():
    from qgis_maptips.processing.provider import QgisMapTipsProvider
    provider = QgisMapTipsProvider()
    provider.loadAlgorithms()
    algs = provider.algorithms()
    names = [a.name() for a in algs]
    has_both = "enhance_all_layers" in names and "export_layer_cards_report" in names
    return _ok(f"QgisMapTipsProvider loaded {len(algs)} algorithms ({', '.join(names)})", has_both)


def test_layer_removal_safety(iface):
    from qgis.core import QgsProject
    from qgis_maptips.dialogs.dock import QgisMapTipsDock

    app = QgsApplication.instance()
    lyr = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "Removal Test Layer", "memory")
    QgsProject.instance().addMapLayer(lyr)

    dock = QgisMapTipsDock(iface)
    if app:
        app.processEvents()

    # Trigger layer removal from project while dock is bound
    QgsProject.instance().removeMapLayer(lyr.id())
    if app:
        app.processEvents()

    dock.unload()
    dock.close()
    return _ok("dock safely handles layer removal without SIP RuntimeError", True)


def run_all(iface):
    print("=" * 60)
    print(" qgis_maptips - lifecycle & core smoke tests")
    print("=" * 60)
    results = [
        test_metadata(),
        test_class_factory(),
        test_lifecycle(iface),
        test_layer_removal_safety(iface),
        test_maptip_injection(),
        test_action_injection(),
        test_processing_provider(),
    ]
    passed = sum(1 for r in results if r)
    print("-" * 60)
    print(f"  {passed}/{len(results)} passed")
    return passed == len(results)


def main():
    app = QgsApplication.instance()
    owns_app = app is None
    profile = None
    if owns_app:
        profile = tempfile.TemporaryDirectory(prefix="qgis_maptips-smoke-")
        app = QgsApplication([], True, profile.name, "external")
        app.initQgis()
    iface = _Iface()
    try:
        return run_all(iface)
    finally:
        with contextlib.suppress(Exception):
            iface.mainWindow().close()
        if owns_app:
            with contextlib.suppress(Exception):
                app.exitQgis()
            with contextlib.suppress(Exception):
                profile.cleanup()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
