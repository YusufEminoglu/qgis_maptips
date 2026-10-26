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


def test_zoom_and_buffer_logic(iface):
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    from qgis_maptips.core.action_builder import create_feature_buffer, zoom_to_feature

    lyr = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "Test Zoom Buffer", "memory")
    f = QgsFeature(lyr.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(32.85, 39.93)))
    f.setAttributes(["Ankara"])
    lyr.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(lyr)

    feat = next(lyr.getFeatures())
    z_ok = zoom_to_feature(iface.mapCanvas(), lyr, feat, iface)
    b_ok = create_feature_buffer(lyr, feat, 50.0, iface)

    buf_layers = QgsProject.instance().mapLayersByName("Feature Buffers (Temp)")
    has_buf_layer = len(buf_layers) > 0 and buf_layers[0].featureCount() > 0

    return _ok("zoom_to_feature and create_feature_buffer execution", z_ok and b_ok and has_buf_layer)


def test_action_studio_and_spatial_helpers(iface):
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    from qgis_maptips.core.action_builder import (
        audit_feature_geometry,
        copy_feature_as_geojson,
        copy_feature_wkt_and_coords,
        extract_feature_to_scratch_layer,
        flash_pan_to_feature,
        inject_or_update_custom_action,
        remove_action_by_id,
        select_nearby_in_layer,
    )
    from qgis_maptips.dialogs.dock import QgisMapTipsDock

    lyr = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer", "Studio Test Layer", "memory")
    f = QgsFeature(lyr.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(27.14, 38.42)))
    f.setAttributes(["Izmir", 4500000])
    lyr.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(lyr)

    feat = next(lyr.getFeatures())
    fp_ok = flash_pan_to_feature(iface.mapCanvas(), lyr, feat, iface)
    near_cnt = select_nearby_in_layer(lyr, feat, 250.0, iface)
    ext_lyr = extract_feature_to_scratch_layer(lyr, feat, iface)
    audit_txt = audit_feature_geometry(lyr, feat, iface)
    gjson_txt = copy_feature_as_geojson(lyr, feat, iface)
    wkt_txt = copy_feature_wkt_and_coords(lyr, feat, iface)

    dock = QgisMapTipsDock(iface)
    has_4_tabs = dock.tabs.count() == 4
    dock._open_template_in_studio("buffer_feature")
    dock.studio_param_spin.setValue(180.0)
    dock._on_studio_apply_numeric_param()
    has_180 = "180.0" in dock.studio_code_edit.toPlainText()

    inj_ok = inject_or_update_custom_action(
        lyr, "Custom Buffer 180m", "Buf 180m", "GenericPython", dock.studio_code_edit.toPlainText()
    )
    del_ok = remove_action_by_id(lyr, "Custom Buffer 180m")

    dock.unload()
    dock.close()
    return _ok(
        "Action Studio customizer & spatial helpers execution",
        bool(fp_ok and near_cnt >= 1 and ext_lyr and audit_txt and gjson_txt and wkt_txt and has_4_tabs and has_180 and inj_ok and del_ok),
    )


def _parcels_with_trees():
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle

    parcels = QgsVectorLayer(
        "Polygon?crs=EPSG:32635&field=fid:integer&field=name:string&field=score:double&field=photo:string"
        "&field=res:double&field=com:double",
        "Card Parcels", "memory")
    feat = QgsFeature(parcels.fields())
    feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(500000, 4250000, 500040, 4250030)))
    feat.setAttributes([7, "Kordon <Plot> & Co", 72.5, "", 60.0, 40.0])
    parcels.dataProvider().addFeatures([feat])
    trees = QgsVectorLayer("Point?crs=EPSG:32635&field=label:string", "Card Trees", "memory")
    for i in range(3):
        tree = QgsFeature(trees.fields())
        tree.setGeometry(QgsGeometry.fromWkt(f"Point({500010 + i * 5} 4250010)"))
        tree.setAttributes([f"tree {i}"])
        trees.dataProvider().addFeatures([tree])
    QgsProject.instance().addMapLayers([parcels, trees])
    return parcels, trees


def _evaluate(layer, text):
    import re

    from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils

    feature = next(layer.getFeatures())
    ctx = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    ctx.setFeature(feature)
    errors = []
    for block in re.findall(r"\[%(.*?)%\]", text, re.S):
        expr = QgsExpression(block)
        expr.evaluate(ctx)
        if expr.hasParserError() or expr.hasEvalError():
            errors.append((expr.parserErrorString() or expr.evalErrorString(), block[:80]))
    return QgsExpression.replaceExpressionText(text, ctx), errors


def test_cards_evaluate_cleanly():
    """Every card type evaluates on a real feature; values are escaped, counts are counts."""
    from qgis.core import QgsProject

    from qgis_maptips.core.template_engine import Archetype, TemplateConfig, compile_maptip_html

    parcels, trees = _parcels_with_trees()
    common = dict(title_field="name", attribute_fields=[("score", "Score"), ("name", "Name")])
    configs = [
        TemplateConfig(archetype=Archetype.KPI_CARD, kpi_field="score",
                       conditional_rules=[{"field": "score", "op": ">=", "val": "70"}],
                       relational_metrics=[
                           {"target_layer": "Card Trees", "op": "intersects", "aggregate": "count"},
                           {"target_layer": "Card Trees", "op": "nearest", "field": "label"},
                       ], **common),
        TemplateConfig(archetype=Archetype.PROGRESS_BAR, kpi_field="score", **common),
        TemplateConfig(archetype=Archetype.DONUT_CHART, donut_fields=[("res", "Res", "#10b981"),
                                                                        ("com", "Com", "#3b82f6")], **common),
        TemplateConfig(archetype=Archetype.SPARKLINE, sparkline_fields=["res", "com"], **common),
        TemplateConfig(archetype=Archetype.MEDIA_CARD, media_field="photo", **common),
        TemplateConfig(archetype=Archetype.MEDIA_CARD, media_field="photo", media_fallback="hide", **common),
        TemplateConfig(archetype=Archetype.CLEAN_TABLE, **common),
    ]
    problems = []
    kpi_html = media_html = ""
    for cfg in configs:
        out, errors = _evaluate(parcels, compile_maptip_html(cfg))
        problems += errors
        if "[%" in out:
            problems.append(("unevaluated block", cfg.archetype.value))
        if cfg.archetype == Archetype.KPI_CARD:
            kpi_html = out
        if cfg.archetype == Archetype.MEDIA_CARD and cfg.media_fallback == "placeholder":
            media_html = out
    # The value keeps its "<Plot>" as text instead of becoming a tag.
    escaped = "Kordon &lt;Plot&gt; &amp; Co" in kpi_html
    # Three trees intersect the parcel; overlay_intersects without an
    # expression used to return a boolean and the row showed raw [% %] text.
    counted = ">3</td>" in kpi_html.replace(" ", "")
    nearest = "tree 0" in kpi_html
    # The placeholder SVG must stay inside its src attribute.
    placeholder = 'src="data:image/svg+xml;utf8,%3Csvg' in media_html and 'No Photo Available"' not in media_html
    QgsProject.instance().removeMapLayers([parcels.id(), trees.id()])
    return _ok(
        "every card type evaluates; values escaped, counts and placeholder correct",
        not problems and escaped and counted and nearest and placeholder,
        f"problems={problems[:2]} escaped={escaped} counted={counted} nearest={nearest} placeholder={placeholder}",
    )


def test_hud_footer_goes_into_the_outer_table():
    from qgis_maptips.core.raster_hud import add_footer_row
    from qgis_maptips.core.template_engine import Archetype, TemplateConfig, compile_maptip_html

    card = compile_maptip_html(TemplateConfig(
        archetype=Archetype.PROGRESS_BAR, title_field="name", kpi_field="v",
        conditional_rules=[{"field": "v", "op": ">", "val": "1"}]))
    nested = card.count("</table>")
    out = add_footer_row(card, "<tr><td>PIN</td></tr>")
    once = out.count("PIN") == 1 and out.rstrip().endswith("<tr><td>PIN</td></tr></table>")
    return _ok("HUD pin footer is added once, to the outer card table", nested > 1 and once,
               f"nested tables={nested}")


def test_dock_sample_has_geometry(iface):
    from qgis.core import QgsCoordinateTransformContext, QgsProject, QgsVectorFileWriter

    from qgis_maptips.dialogs.dock import QgisMapTipsDock

    # A file layer: the memory provider ignores the NoGeometry request flag,
    # so only a GeoPackage shows whether the sample comes without geometry.
    memory, trees = _parcels_with_trees()
    path = os.path.join(tempfile.mkdtemp(prefix="maptips_sample_"), "parcels.gpkg")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    QgsVectorFileWriter.writeAsVectorFormatV3(memory, path, QgsCoordinateTransformContext(), options)
    parcels = QgsVectorLayer(path, "Sample Parcels", "ogr")
    QgsProject.instance().addMapLayer(parcels)
    dock = QgisMapTipsDock(iface)
    dock._refresh_layers()
    idx = dock.layer_combo.findData(parcels.id())
    dock.layer_combo.setCurrentIndex(idx)
    dock._on_target_layer_selected(idx)
    dock._reload_sample_features()
    dock._update_preview()
    sample = getattr(dock, "_current_sample_feat", None)
    has_geom = bool(sample is not None and sample.hasGeometry())
    dock.unload()
    dock.close()
    QgsProject.instance().removeMapLayers([parcels.id(), memory.id(), trees.id()])
    # Zoom, buffer, TKGM and the studio test run all act on this feature.
    return _ok("designer sample feature carries geometry", idx >= 0 and has_geom)


def test_reapplying_actions_replaces_instead_of_duplicating():
    from qgis_maptips.core.action_builder import apply_actions_to_layer

    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=id:string", "Reapply", "memory")
    apply_actions_to_layer(layer, ["google_satellite", "copy_clipboard"])
    first = sorted(a.name() for a in layer.actions().actions())
    apply_actions_to_layer(layer, ["google_satellite", "copy_clipboard"], clear_existing_plugin_actions=True)
    second = sorted(a.name() for a in layer.actions().actions())
    return _ok("re-applying actions replaces same-named ones", first == second and len(second) == 2,
               f"{first} -> {second}")


def test_action_url_without_path():
    from qgis.PyQt.QtCore import QUrl

    from qgis_maptips.core.action_builder import ActionUrlHandler

    handler = ActionUrlHandler(None)
    try:
        handler.handleUrl(QUrl("action:?layer=missing&id=1"))
        ok = True
    except AttributeError as exc:
        ok = False
        print("   ", exc)
    return _ok("action: link with an empty key is ignored, not an AttributeError", ok)


def test_batch_enhance_picks_name_and_runs_on_main_thread():
    from qgis.core import (
        Qgis,
        QgsFeature,
        QgsProcessingAlgorithm,
        QgsProcessingContext,
        QgsProcessingFeedback,
        QgsProject,
    )

    from qgis_maptips.processing.enhance_all_layers import EnhanceAllLayersAlgorithm

    alg = EnhanceAllLayersAlgorithm()
    flag = getattr(getattr(Qgis, "ProcessingAlgorithmFlag", None), "NoThreading", None)
    if flag is None:
        flag = QgsProcessingAlgorithm.FlagNoThreading
    main_thread = bool(alg.flags() & flag)

    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=fid:integer&field=width:double&field=name:string",
                           "Batch", "memory")
    feature = QgsFeature(layer.fields())
    feature.setAttributes([1, 2.0, "Alsancak"])
    layer.dataProvider().addFeatures([feature])
    QgsProject.instance().addMapLayer(layer)
    alg.initAlgorithm()
    alg.processAlgorithm({"PALETTE": 0, "INCLUDE_ACTIONS": False, "OVERWRITE_EXISTING": True},
                         QgsProcessingContext(), QgsProcessingFeedback())
    titled_by_name = 'to_string("name")' in layer.mapTipTemplate().split("</tr>")[0]
    QgsProject.instance().removeMapLayer(layer.id())
    return _ok("batch enhance titles cards by name and runs on the main thread",
               main_thread and titled_by_name, f"main_thread={main_thread} name={titled_by_name}")


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
        test_zoom_and_buffer_logic(iface),
        test_action_studio_and_spatial_helpers(iface),
        test_cards_evaluate_cleanly(),
        test_hud_footer_goes_into_the_outer_table(),
        test_dock_sample_has_geometry(iface),
        test_reapplying_actions_replaces_instead_of_duplicating(),
        test_action_url_without_path(),
        test_batch_enhance_picks_name_and_runs_on_main_thread(),
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
