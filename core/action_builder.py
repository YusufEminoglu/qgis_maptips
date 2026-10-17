"""Action Builder Engine for Qgis Advanced Map Tips&Actions.

Injects native QGIS actions (QgsAction) onto vector layers, providing:
1. 22 battle-tested, customizable Action Templates across 5 categories:
   - Web & Street Navigation (Google Satellite, Street View, Directions, OSM, OSM iD Editor, Yandex, Bing Aerial, Mapillary)
   - Geometry & Spatial Analysis (Smart Zoom, Pan & Flash, Custom Buffer, Select Nearby Within Radius, Extract Feature Layer, Geometry & Coordinate Audit)
   - Attribute, Export & Clipboard (Copy Key-Value Attributes, Copy GeoJSON, Copy WKT & Coords, Standalone HTML Card Report)
   - Cadastral & Urban Planning (TKGM Parsel Sorgu Web Portal, TKGM Instant Parcel Polygon Downloader)
   - External Portals & Forms (Native QGIS Feature Form Dialog, Wikimedia GeoHack Coordinate Portal)
2. Interactive Action Studio helpers to create, revise, update, delete, test-run, and export/import custom actions.
3. Universal `action:` URL handler so every template and custom action can be triggered 1-click from MapTip HTML cards.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import Any, Callable, Optional
from urllib.parse import parse_qs

try:
    from qgis.PyQt.QtCore import QObject, QUrl
    from qgis.PyQt.QtGui import QColor, QDesktopServices
    from qgis.PyQt.QtWidgets import QApplication, QMessageBox
    from qgis.core import (
        QgsAction,
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsDistanceArea,
        QgsExpression,
        QgsExpressionContext,
        QgsExpressionContextUtils,
        QgsFeature,
        QgsFeatureRequest,
        QgsField,
        QgsGeometry,
        QgsMapLayer,
        QgsProject,
        QgsRectangle,
        QgsVectorLayer,
        QgsWkbTypes,
    )
except ImportError:  # Fallback for pure-Python unit tests outside QGIS
    QObject = object  # type: ignore
    QUrl = None  # type: ignore
    QColor = None  # type: ignore
    QDesktopServices = None  # type: ignore
    QApplication = None  # type: ignore
    QMessageBox = None  # type: ignore
    QgsAction = None  # type: ignore
    QgsCoordinateReferenceSystem = None  # type: ignore
    QgsCoordinateTransform = None  # type: ignore
    QgsDistanceArea = None  # type: ignore
    QgsExpression = None  # type: ignore
    QgsExpressionContext = None  # type: ignore
    QgsExpressionContextUtils = None  # type: ignore
    QgsFeature = Any  # type: ignore
    QgsFeatureRequest = None  # type: ignore
    QgsField = None  # type: ignore
    QgsGeometry = None  # type: ignore
    QgsMapLayer = Any  # type: ignore
    QgsProject = None  # type: ignore
    QgsRectangle = None  # type: ignore
    QgsVectorLayer = Any  # type: ignore
    QgsWkbTypes = None  # type: ignore


def is_layer_alive(layer: Any) -> bool:
    """Safely check if a PyQGIS QgsMapLayer C++ wrapper is alive and valid."""
    if layer is None:
        return False
    try:
        try:
            from qgis.PyQt import sip
            if sip.isdeleted(layer):
                return False
        except ImportError:
            pass
        _ = layer.id()
        return bool(layer.isValid())
    except (RuntimeError, ReferenceError, AttributeError):
        return False


def zoom_to_feature(canvas: Any, layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None) -> bool:
    """Safely zoom map canvas to a feature with adaptive CRS padding and highlight."""
    if not canvas or not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return False
    geom = feat.geometry()
    if geom.isEmpty():
        return False

    with contextlib.suppress(Exception):
        layer.selectByIds([feat.id()])

    bbox = geom.boundingBox()
    canvas_crs = canvas.mapSettings().destinationCrs()
    if layer.crs() != canvas_crs and layer.crs().isValid() and canvas_crs.isValid():
        with contextlib.suppress(Exception):
            tr = QgsCoordinateTransform(layer.crs(), canvas_crs, QgsProject.instance())
            bbox = tr.transformBoundingBox(bbox)

    is_geo = canvas_crs.isGeographic() if canvas_crs.isValid() else False
    pad = 0.0015 if is_geo else 150.0
    min_span = 0.0001 if is_geo else 5.0

    if bbox.width() < min_span and bbox.height() < min_span:
        pt = bbox.center()
        bbox = QgsRectangle(pt.x() - pad, pt.y() - pad, pt.x() + pad, pt.y() + pad)
    else:
        bbox.scale(1.35)

    canvas.setExtent(bbox)
    if hasattr(canvas, "flashGeometries"):
        with contextlib.suppress(Exception):
            canvas.flashGeometries([geom], crs=layer.crs())
    canvas.refresh()

    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushSuccess(
            "Qgis MapTips", f"Zoomed to feature ID {feat.id()} in '{layer.name()}'."
        )
    return True


def flash_pan_to_feature(canvas: Any, layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None) -> bool:
    """Pan map canvas to center on feature without changing zoom scale and flash geometry."""
    if not canvas or not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return False
    geom = feat.geometry()
    if geom.isEmpty():
        return False

    with contextlib.suppress(Exception):
        layer.selectByIds([feat.id()])

    pos = geom.pointOnSurface() if not geom.pointOnSurface().isEmpty() else geom.centroid()
    pt = pos.asPoint()
    canvas_crs = canvas.mapSettings().destinationCrs()
    if layer.crs() != canvas_crs and layer.crs().isValid() and canvas_crs.isValid():
        with contextlib.suppress(Exception):
            tr = QgsCoordinateTransform(layer.crs(), canvas_crs, QgsProject.instance())
            pt = tr.transform(pt)

    canvas.setCenter(pt)
    if hasattr(canvas, "flashGeometries"):
        with contextlib.suppress(Exception):
            canvas.flashGeometries([geom], crs=layer.crs())
    canvas.refresh()

    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushInfo(
            "Qgis MapTips", f"Centered & flashed feature ID {feat.id()} in '{layer.name()}'."
        )
    return True


def create_feature_buffer(
    layer: QgsVectorLayer, feat: QgsFeature, dist_m: float = 50.0, iface: Any = None
) -> bool:
    """Create a visible metric buffer around a feature in a dedicated top-level temporary layer."""
    if not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return False
    geom = feat.geometry()
    if geom.isEmpty():
        return False

    proj = QgsProject.instance()
    crs = layer.crs()
    if crs.isGeographic():
        tr_to = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem("EPSG:3857"), proj)
        tr_back = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:3857"), crs, proj)
        g_copy = QgsGeometry(geom)
        g_copy.transform(tr_to)
        buf_geom = g_copy.buffer(dist_m, 16)
        buf_geom.transform(tr_back)
    else:
        buf_geom = geom.buffer(dist_m, 16)

    if buf_geom.isEmpty():
        return False

    buf_name = "Feature Buffers (Temp)"
    existing = [
        lyr for lyr in proj.mapLayersByName(buf_name)
        if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer) and lyr.crs() == crs
    ]
    if existing:
        buf_lyr = existing[0]
    else:
        uri = (
            f"Polygon?crs={crs.authid()}"
            "&field=source_layer:string(80)"
            "&field=source_fid:integer"
            "&field=buffer_m:double"
        )
        buf_lyr = QgsVectorLayer(uri, buf_name, "memory")
        renderer = buf_lyr.renderer()
        if renderer and renderer.symbol() and renderer.symbol().symbolLayerCount() > 0:
            sym = renderer.symbol()
            sym.setColor(QColor(14, 165, 233, 55))
            sl = sym.symbolLayer(0)
            if sl:
                sl.setStrokeColor(QColor(2, 132, 199, 255))
                sl.setStrokeWidth(0.7)
        proj.addMapLayer(buf_lyr, False)
        proj.layerTreeRoot().insertLayer(0, buf_lyr)

    f = QgsFeature(buf_lyr.fields())
    f.setGeometry(buf_geom)
    f.setAttributes([layer.name(), int(feat.id()), float(dist_m)])
    buf_lyr.dataProvider().addFeatures([f])
    buf_lyr.updateExtents()
    buf_lyr.triggerRepaint()

    canvas = iface.mapCanvas() if (iface and hasattr(iface, "mapCanvas")) else None
    if canvas:
        if hasattr(canvas, "flashGeometries"):
            with contextlib.suppress(Exception):
                canvas.flashGeometries([buf_geom], crs=crs)
        canvas.refresh()

    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushSuccess(
            "Qgis MapTips", f"Created {dist_m:.0f}m buffer for feature ID {feat.id()} in '{buf_name}'."
        )
    return True


def select_nearby_in_layer(
    layer: QgsVectorLayer, feat: QgsFeature, radius_m: float = 100.0, iface: Any = None
) -> int:
    """Select all features in the same layer within `radius_m` meters of `feat`."""
    if not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return 0
    geom = feat.geometry()
    if geom.isEmpty():
        return 0

    proj = QgsProject.instance()
    crs = layer.crs()
    if crs.isGeographic():
        tr_to = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem("EPSG:3857"), proj)
        tr_back = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:3857"), crs, proj)
        g_copy = QgsGeometry(geom)
        g_copy.transform(tr_to)
        search_geom = g_copy.buffer(radius_m, 12)
        search_geom.transform(tr_back)
    else:
        search_geom = geom.buffer(radius_m, 12)

    req = QgsFeatureRequest().setFilterRect(search_geom.boundingBox())
    ids = [
        f.id() for f in layer.getFeatures(req)
        if f.hasGeometry() and f.geometry().intersects(search_geom)
    ]
    layer.selectByIds(ids)

    canvas = iface.mapCanvas() if (iface and hasattr(iface, "mapCanvas")) else None
    if canvas:
        if hasattr(canvas, "flashGeometries"):
            with contextlib.suppress(Exception):
                canvas.flashGeometries([search_geom], crs=crs)
        canvas.refresh()

    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushSuccess(
            "Qgis MapTips",
            f"Selected {len(ids)} feature(s) within {radius_m:.0f}m of ID {feat.id()} in '{layer.name()}'.",
        )
    return len(ids)


def extract_feature_to_scratch_layer(
    layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None
) -> Optional[QgsVectorLayer]:
    """Copy a single feature (geometry + schema + attributes) into a dedicated scratch memory layer."""
    if not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return None

    proj = QgsProject.instance()
    wkb_str = QgsWkbTypes.displayString(layer.wkbType()) if QgsWkbTypes else "Polygon"
    if not wkb_str or wkb_str == "Unknown":
        geom_map = {0: "Point", 1: "LineString", 2: "Polygon"}
        wkb_str = geom_map.get(layer.geometryType(), "Polygon")

    out_name = f"Extracted Features ({layer.name()})"
    existing = [
        lyr for lyr in proj.mapLayersByName(out_name)
        if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer)
    ]
    if existing:
        out_lyr = existing[0]
    else:
        out_lyr = QgsVectorLayer(f"{wkb_str}?crs={layer.crs().authid()}", out_name, "memory")
        out_lyr.dataProvider().addAttributes(layer.fields().toList())
        out_lyr.updateFields()
        proj.addMapLayer(out_lyr, False)
        proj.layerTreeRoot().insertLayer(0, out_lyr)

    new_feat = QgsFeature(out_lyr.fields())
    new_feat.setGeometry(QgsGeometry(feat.geometry()))
    new_feat.setAttributes(feat.attributes())
    out_lyr.dataProvider().addFeatures([new_feat])
    out_lyr.updateExtents()
    out_lyr.triggerRepaint()

    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushSuccess(
            "Qgis MapTips", f"Extracted feature ID {feat.id()} into '{out_name}'."
        )
    return out_lyr


def audit_feature_geometry(layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None) -> str:
    """Compute ellipsoidal area, perimeter/length, vertex count, and WGS84 coordinates; copy to clipboard."""
    if not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return ""
    geom = feat.geometry()
    if geom.isEmpty():
        return ""

    proj = QgsProject.instance()
    da = QgsDistanceArea()
    da.setSourceCrs(layer.crs(), proj.transformContext())
    ellipsoid = proj.ellipsoid() or "WGS84"
    da.setEllipsoid(ellipsoid)

    pos = geom.pointOnSurface() if not geom.pointOnSurface().isEmpty() else geom.centroid()
    pt = pos.asPoint()
    lat, lon = pt.y(), pt.x()
    with contextlib.suppress(Exception):
        tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), proj)
        wgs = tr.transform(pt)
        lat, lon = wgs.y(), wgs.x()

    verts = sum(1 for _ in geom.vertices())
    gtype = layer.geometryType()
    metrics = [
        f"Layer: {layer.name()} (Feature ID: {feat.id()})",
        f"CRS: {layer.crs().authid()} | Ellipsoid: {ellipsoid}",
        f"WGS84 Centroid: {lat:.6f}, {lon:.6f}",
        f"Native Centroid: X={pt.x():.3f}, Y={pt.y():.3f}",
        f"Vertices: {verts}",
    ]
    if gtype == 2:  # Polygon
        area_m2 = da.measureArea(geom)
        perim_m = da.measurePerimeter(geom)
        metrics.append(f"Area: {area_m2:,.2f} m² ({area_m2 / 10000.0:,.4f} ha)")
        metrics.append(f"Perimeter: {perim_m:,.2f} m ({perim_m / 1000.0:,.3f} km)")
    elif gtype == 1:  # Line
        len_m = da.measureLength(geom)
        metrics.append(f"Length: {len_m:,.2f} m ({len_m / 1000.0:,.3f} km)")

    summary = "\n".join(metrics)
    if QApplication:
        QApplication.clipboard().setText(summary)

    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        short_msg = " | ".join(metrics[2:])
        iface.messageBar().pushSuccess("Geometry Audit (Copied)", short_msg)
    return summary


def copy_feature_as_geojson(layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None) -> str:
    """Export feature geometry (transformed to EPSG:4326) and attributes as RFC 7946 GeoJSON to clipboard."""
    if not is_layer_alive(layer) or not feat:
        return ""
    props = {}
    for field in layer.fields():
        val = feat[field.name()]
        if val is not None and not isinstance(val, (int, float, str, bool)):
            val = str(val)
        props[field.name()] = val

    geom_dict = None
    if feat.hasGeometry() and not feat.geometry().isEmpty():
        g_copy = QgsGeometry(feat.geometry())
        with contextlib.suppress(Exception):
            if layer.crs().authid() != "EPSG:4326":
                tr = QgsCoordinateTransform(
                    layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance()
                )
                g_copy.transform(tr)
        with contextlib.suppress(Exception):
            geom_dict = json.loads(g_copy.asJson())

    geojson_obj = {
        "type": "Feature",
        "id": feat.id(),
        "properties": props,
        "geometry": geom_dict,
    }
    text = json.dumps(geojson_obj, ensure_ascii=False, indent=2)
    if QApplication:
        QApplication.clipboard().setText(text)
    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushSuccess(
            "Qgis MapTips", f"Copied Feature #{feat.id()} as GeoJSON (WGS84) to clipboard."
        )
    return text


def copy_feature_wkt_and_coords(layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None) -> str:
    """Copy WGS84 coordinates, native coordinates, and WKT geometry string to clipboard."""
    if not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return ""
    geom = feat.geometry()
    if geom.isEmpty():
        return ""

    pos = geom.pointOnSurface() if not geom.pointOnSurface().isEmpty() else geom.centroid()
    pt = pos.asPoint()
    lat, lon = pt.y(), pt.x()
    with contextlib.suppress(Exception):
        tr = QgsCoordinateTransform(
            layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance()
        )
        wgs = tr.transform(pt)
        lat, lon = wgs.y(), wgs.x()

    wkt_str = geom.asWkt(precision=6)
    text = (
        f"WGS84 (Lat, Lon): {lat:.6f}, {lon:.6f}\n"
        f"Native ({layer.crs().authid()}): {pt.x():.3f}, {pt.y():.3f}\n"
        f"WKT: {wkt_str}"
    )
    if QApplication:
        QApplication.clipboard().setText(text)
    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushSuccess(
            "Qgis MapTips", f"Copied WKT & coordinates ({lat:.5f}, {lon:.5f}) to clipboard."
        )
    return text


def open_qgis_feature_form(layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None) -> bool:
    """Open QGIS native feature attribute form dialog for the given feature."""
    if not is_layer_alive(layer) or not feat:
        return False
    target_iface = iface
    if target_iface is None:
        with contextlib.suppress( Exception):
            from qgis.utils import iface as qgis_iface
            target_iface = qgis_iface
    if target_iface and hasattr(target_iface, "openFeatureForm"):
        target_iface.openFeatureForm(layer, feat, False)
        return True
    return False


def download_tkgm_parcel_for_feature(layer: QgsVectorLayer, feat: QgsFeature, iface: Any = None) -> bool:
    """Query TKGM MEGSIS at the feature's surface point and add the official parcel to QGIS."""
    if not is_layer_alive(layer) or not feat or not feat.hasGeometry():
        return False
    from .cadastre_tool import (
        add_parcel_feature,
        get_or_create_cadastre_layer,
        is_in_turkey_bounds,
        parse_tkgm_response,
        query_tkgm_megsis,
    )

    geom = feat.geometry()
    pos = geom.pointOnSurface() if not geom.pointOnSurface().isEmpty() else geom.centroid()
    pt = pos.asPoint()
    tr = QgsCoordinateTransform(
        layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance()
    )
    wgs = tr.transform(pt)
    lat, lon = round(wgs.y(), 6), round(wgs.x(), 6)

    if not is_in_turkey_bounds(lat, lon):
        if iface and hasattr(iface, "messageBar") and iface.messageBar():
            iface.messageBar().pushWarning(
                "TKGM Cadastre", f"Coordinates ({lat}, {lon}) are outside Turkey bounds."
            )
        return False

    ok, data, err = query_tkgm_megsis(lat, lon)
    if not ok or not data:
        if iface and hasattr(iface, "messageBar") and iface.messageBar():
            iface.messageBar().pushWarning("TKGM Cadastre", f"TKGM query failed: {err}")
        return False

    info = parse_tkgm_response(data)
    if not info:
        if iface and hasattr(iface, "messageBar") and iface.messageBar():
            iface.messageBar().pushWarning("TKGM Cadastre", "No parcel found at feature coordinates.")
        return False

    cad_layer = get_or_create_cadastre_layer(QgsProject.instance())
    _, msg, _ = add_parcel_feature(cad_layer, info)
    if iface and hasattr(iface, "messageBar") and iface.messageBar():
        iface.messageBar().pushSuccess("TKGM Cadastre", msg)
    return True


class ActionUrlHandler(QObject):
    """Global Qt URL handler for `action:` links inside MapTips and HTML Previews."""

    def __init__(self, iface: Any = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.iface = iface

    def handleUrl(self, url: QUrl) -> None:
        scheme = url.scheme()
        if scheme != "action":
            QDesktopServices.openUrl(url)
            return

        action_key = url.path() or url.Authority() or url.toString().replace("action:", "").split("?")[0]
        action_key = action_key.strip("/")
        query = parse_qs(url.query())

        layer_id = query.get("layer", [""])[0]
        fid_str = query.get("id", [""])[0]

        layer: Optional[QgsVectorLayer] = None
        if layer_id:
            lyr = QgsProject.instance().mapLayer(layer_id)
            if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer):
                layer = lyr
        if layer is None and self.iface and hasattr(self.iface, "activeLayer"):
            lyr = self.iface.activeLayer()
            if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer):
                layer = lyr

        if not is_layer_alive(layer):
            return

        feat: Optional[QgsFeature] = None
        if fid_str:
            with contextlib.suppress(ValueError):
                fid = int(fid_str)
                req = QgsFeatureRequest().setFilterFid(fid)
                for f in layer.getFeatures(req):
                    feat = f
                    break

        if feat is None:
            sel = layer.selectedFeatures()
            if sel:
                feat = sel[0]
            else:
                for f in layer.getFeatures():
                    feat = f
                    break

        if feat is None:
            return

        execute_template_or_layer_action(layer, feat, action_key, self.iface)


def execute_template_or_layer_action(
    layer: QgsVectorLayer,
    feat: QgsFeature,
    action_key: str,
    iface: Any = None,
) -> bool:
    """Execute a template action key or a registered layer action on `feat`."""
    if not is_layer_alive(layer) or not feat:
        return False

    canvas = iface.mapCanvas() if (iface and hasattr(iface, "mapCanvas")) else None

    if action_key == "copy_clipboard":
        lines = [f"{field.name()}: {feat[field.name()]}" for field in layer.fields()]
        if QApplication:
            QApplication.clipboard().setText("\n".join(lines))
        if iface and hasattr(iface, "messageBar") and iface.messageBar():
            iface.messageBar().pushSuccess(
                "Qgis MapTips", f"Copied {len(lines)} attributes from '{layer.name()}' to clipboard."
            )
        return True

    if action_key == "copy_geojson":
        return bool(copy_feature_as_geojson(layer, feat, iface))

    if action_key == "copy_wkt_coords":
        return bool(copy_feature_wkt_and_coords(layer, feat, iface))

    if action_key == "export_card_report":
        ctx = QgsExpressionContext()
        ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        ctx.setFeature(feat)
        raw_tip = layer.mapTipTemplate()
        if not raw_tip:
            from .raster_hud import evaluate_vector_feature_maptip
            evaluated = evaluate_vector_feature_maptip(layer, feat)
        else:
            evaluated = QgsExpression.replaceExpressionText(raw_tip, ctx)

        full_html = (
            '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Feature Card Report</title>'
            '<style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:30px;background:#f8fafc;display:flex;justify-content:center;}'
            '.card-wrap{box-shadow:0 10px 25px rgba(0,0,0,0.1);background:#fff;border-radius:6px;overflow:hidden;}'
            '</style></head><body><div class="card-wrap">' + evaluated + '</div></body></html>'
        )
        tmp = os.path.join(tempfile.gettempdir(), f"feature_card_report_{feat.id()}.html")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(full_html)
        if QDesktopServices and QUrl:
            QDesktopServices.openUrl(QUrl.fromLocalFile(tmp))
        if iface and hasattr(iface, "messageBar") and iface.messageBar():
            iface.messageBar().pushSuccess("Qgis MapTips", "Opened standalone HTML card report in browser.")
        return True

    if action_key in ("zoom_feature", "zoom"):
        return zoom_to_feature(canvas, layer, feat, iface)

    if action_key == "flash_pan_feature":
        return flash_pan_to_feature(canvas, layer, feat, iface)

    if action_key in ("buffer_feature", "buffer"):
        return create_feature_buffer(layer, feat, 50.0, iface)

    if action_key == "select_nearby_features":
        select_nearby_in_layer(layer, feat, 100.0, iface)
        return True

    if action_key == "extract_feature_layer":
        return extract_feature_to_scratch_layer(layer, feat, iface) is not None

    if action_key == "measure_geometry_summary":
        return bool(audit_feature_geometry(layer, feat, iface))

    if action_key == "open_attribute_form":
        return open_qgis_feature_form(layer, feat, iface)

    if action_key == "tkgm_instant_download":
        return download_tkgm_parcel_for_feature(layer, feat, iface)

    if action_key in ("tkgm_cadastre", "tkgm", "parsel"):
        if not feat.hasGeometry():
            return False
        with contextlib.suppress(Exception):
            pos = feat.geometry().pointOnSurface() if not feat.geometry().pointOnSurface().isEmpty() else feat.geometry().centroid()
            pt = pos.asPoint()
            tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
            wgs = tr.transform(pt)
            lat, lon = round(wgs.y(), 6), round(wgs.x(), 6)
            url_str = f"https://parselsorgu.tkgm.gov.tr/#ara/cografi/{lat}/{lon}"
            if QDesktopServices and QUrl:
                QDesktopServices.openUrl(QUrl(url_str))
            return True
        return False

    # Check if key matches any template in AVAILABLE_ACTIONS (e.g. OpenUrl templates)
    actions_map = {a["key"]: a for a in AVAILABLE_ACTIONS}
    if action_key in actions_map:
        act_def = actions_map[action_key]
        if act_def["type"] == "OpenUrl":
            ctx = QgsExpressionContext()
            ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
            ctx.setFeature(feat)
            expanded_url = QgsExpression.replaceExpressionText(act_def["command"], ctx)
            if QDesktopServices and QUrl:
                QDesktopServices.openUrl(QUrl(expanded_url.strip()))
            return True

    # Finally, check if the layer has a matching QgsAction by shortTitle or name
    mgr = layer.actions()
    for act in mgr.actions():
        st = act.shortTitle() if hasattr(act, "shortTitle") else ""
        if action_key in (act.name(), st, str(act.id())):
            with contextlib.suppress(Exception):
                mgr.doActionFeature(act.id(), feat)
                return True

    return False


_GLOBAL_ACTION_HANDLER: Optional[ActionUrlHandler] = None


def register_action_url_handler(iface: Any = None) -> None:
    """Register `action:` scheme handler with QDesktopServices."""
    global _GLOBAL_ACTION_HANDLER
    if QDesktopServices is None:
        return
    if _GLOBAL_ACTION_HANDLER is None:
        _GLOBAL_ACTION_HANDLER = ActionUrlHandler(iface)
    QDesktopServices.setUrlHandler("action", _GLOBAL_ACTION_HANDLER, "handleUrl")


def unregister_action_url_handler() -> None:
    """Unregister `action:` scheme handler on plugin unload."""
    global _GLOBAL_ACTION_HANDLER
    if QDesktopServices is None:
        return
    with contextlib.suppress(Exception):
        QDesktopServices.unsetUrlHandler("action")
    _GLOBAL_ACTION_HANDLER = None


# Universal QGIS Expression to transform feature centroid/surface-point to WGS84 (EPSG:4326)
LAT_EXPR = "y(transform(point_on_surface($geometry), @layer_crs, 'EPSG:4326'))"
LON_EXPR = "x(transform(point_on_surface($geometry), @layer_crs, 'EPSG:4326'))"

# Action Categories for UI Filtering & Organization
ACTION_CATEGORIES: list[str] = [
    "🌐 Web & Street Navigation",
    "📐 Geometry & Spatial Analysis",
    "📋 Attribute, Export & Clipboard",
    "🏛️ Cadastral & Urban Planning",
    "🔗 External Portals & Forms",
]

# Common Expression Tokens for the Action Studio Token Inserter
STUDIO_EXPRESSION_TOKENS: list[tuple[str, str, str]] = [
    ("WGS84 Latitude", f"[% {LAT_EXPR} %]", "Feature surface-point latitude in EPSG:4326"),
    ("WGS84 Longitude", f"[% {LON_EXPR} %]", "Feature surface-point longitude in EPSG:4326"),
    ("Feature ID ($id)", "[% $id %]", "Internal ID of the clicked feature"),
    ("Layer ID (@layer_id)", "[% @layer_id %]", "Active QGIS layer identifier"),
    ("Layer Name (@layer_name)", "[% @layer_name %]", "Active QGIS layer display name"),
    ("Layer CRS (@layer_crs)", "[% @layer_crs %]", "Auth ID of the layer CRS (e.g. EPSG:4326)"),
    ("Native X ($x)", "[% x(point_on_surface($geometry)) %]", "X coordinate in layer's native CRS"),
    ("Native Y ($y)", "[% y(point_on_surface($geometry)) %]", "Y coordinate in layer's native CRS"),
    ("Ellipsoidal Area ($area)", "[% round($area, 2) %]", "Ellipsoidal area of polygon in m²"),
    ("Perimeter ($perimeter)", "[% round($perimeter, 2) %]", "Ellipsoidal perimeter of polygon in m"),
    ("Length ($length)", "[% round($length, 2) %]", "Ellipsoidal length of line in m"),
    ("WKT Geometry", "[% geom_to_wkt($geometry, 6) %]", "Well-Known Text geometry representation"),
]


# ──────────────────────────────────────────────────────────────────────────────
# 22 Ready-to-Use, Customizable QGIS Action Templates
# ──────────────────────────────────────────────────────────────────────────────

AVAILABLE_ACTIONS: list[dict[str, Any]] = [
    # 1. Google Maps Satellite
    {
        "key": "google_satellite",
        "category": "🌐 Web & Street Navigation",
        "icon": "🌐",
        "name": "Open in Google Maps (Satellite)",
        "short_title": "Google Sat",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens Google Maps aerial satellite view centered on the feature's surface centroid (EPSG:4326).",
        "command": f"https://www.google.com/maps/@?api=1&map_action=map&center=[% {LAT_EXPR} %],[% {LON_EXPR} %]&zoom=19&basemap=satellite",
    },
    # 2. Google Street View
    {
        "key": "google_streetview",
        "category": "🌐 Web & Street Navigation",
        "icon": "📍",
        "name": "Open in Google Street View",
        "short_title": "Street View",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Launches interactive 360° Google Street View panorama at the feature's exact WGS84 coordinates.",
        "command": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=[% {LAT_EXPR} %],[% {LON_EXPR} %]",
    },
    # 3. Google Maps Driving Directions
    {
        "key": "google_directions",
        "category": "🌐 Web & Street Navigation",
        "icon": "🚗",
        "name": "Google Maps Driving Directions to Feature",
        "short_title": "Directions",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens Google Maps route planner with this feature's WGS84 coordinates set as the destination.",
        "command": f"https://www.google.com/maps/dir/?api=1&destination=[% {LAT_EXPR} %],[% {LON_EXPR} %]&travelmode=driving",
    },
    # 4. OpenStreetMap Inspector
    {
        "key": "openstreetmap",
        "category": "🌐 Web & Street Navigation",
        "icon": "🗺️",
        "name": "Open in OpenStreetMap Inspector",
        "short_title": "OSM Map",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens OpenStreetMap with a marker pin at zoom level 18 for the clicked feature.",
        "command": f"https://www.openstreetmap.org/?mlat=[% {LAT_EXPR} %]&mlon=[% {LON_EXPR} %]#map=18/[% {LAT_EXPR} %]/[% {LON_EXPR} %]",
    },
    # 5. OpenStreetMap iD Editor
    {
        "key": "osm_id_editor",
        "category": "🌐 Web & Street Navigation",
        "icon": "✏️",
        "name": "Edit Location in OpenStreetMap (iD Editor)",
        "short_title": "OSM Edit",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens the OpenStreetMap iD web editor directly at zoom 19 on the feature's coordinates.",
        "command": f"https://www.openstreetmap.org/edit?editor=id#map=19/[% {LAT_EXPR} %]/[% {LON_EXPR} %]",
    },
    # 6. Yandex Maps & Panorama
    {
        "key": "yandex_maps",
        "category": "🌐 Web & Street Navigation",
        "icon": "🧭",
        "name": "Open in Yandex Maps & Panorama",
        "short_title": "Yandex Map",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens Yandex hybrid satellite & street map centered on the feature's WGS84 coordinates.",
        "command": f"https://yandex.com/maps/?ll=[% {LON_EXPR} %],[% {LAT_EXPR} %]&z=19&l=sat,skl",
    },
    # 7. Bing Maps Aerial View
    {
        "key": "bing_aerial",
        "category": "🌐 Web & Street Navigation",
        "icon": "🛰️",
        "name": "Open in Bing Maps Aerial View",
        "short_title": "Bing Aerial",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens Microsoft Bing Maps high-resolution aerialortho imagery at zoom 19.",
        "command": f"https://www.bing.com/maps?cp=[% {LAT_EXPR} %]~[% {LON_EXPR} %]&lvl=19&style=a",
    },
    # 8. Mapillary Street Imagery
    {
        "key": "mapillary_street",
        "category": "🌐 Web & Street Navigation",
        "icon": "📷",
        "name": "Open in Mapillary Street-Level Imagery",
        "short_title": "Mapillary",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens Mapillary crowd-sourced street-level photo sequences at the feature's coordinates.",
        "command": f"https://www.mapillary.com/app/?lat=[% {LAT_EXPR} %]&lng=[% {LON_EXPR} %]&z=17",
    },
    # 9. Smart Zoom & Center to Feature
    {
        "key": "zoom_feature",
        "category": "📐 Geometry & Spatial Analysis",
        "icon": "🔍",
        "name": "Zoom & Center to Feature (Adaptive Padding)",
        "short_title": "Zoom To",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Selects the feature, transforms its bounding box to canvas CRS with smart padding, and flashes its geometry.",
        "command": (
            "# Customizable Parameters\n"
            "PADDING_SCALE = 1.35  # Bounding box expansion factor\n"
            "POINT_PAD_M = 150.0   # Padding in meters for single point features\n\n"
            "from qgis.core import QgsProject, QgsFeatureRequest, QgsCoordinateTransform, QgsRectangle\n"
            "from qgis.utils import iface\n"
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
            "if layer and iface:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat and feat.hasGeometry():\n"
            "        layer.selectByIds([feat.id()])\n"
            "        geom = feat.geometry()\n"
            "        bbox = geom.boundingBox()\n"
            "        canvas = iface.mapCanvas()\n"
            "        c_crs = canvas.mapSettings().destinationCrs()\n"
            "        if layer.crs() != c_crs:\n"
            "            tr = QgsCoordinateTransform(layer.crs(), c_crs, QgsProject.instance())\n"
            "            bbox = tr.transformBoundingBox(bbox)\n"
            "        is_geo = c_crs.isGeographic()\n"
            "        pad = (POINT_PAD_M / 111320.0) if is_geo else POINT_PAD_M\n"
            "        min_span = 0.0001 if is_geo else 5.0\n"
            "        if bbox.width() < min_span and bbox.height() < min_span:\n"
            "            pt = bbox.center()\n"
            "            bbox = QgsRectangle(pt.x() - pad, pt.y() - pad, pt.x() + pad, pt.y() + pad)\n"
            "        else:\n"
            "            bbox.scale(PADDING_SCALE)\n"
            "        canvas.setExtent(bbox)\n"
            "        if hasattr(canvas, 'flashGeometries'):\n"
            "            canvas.flashGeometries([geom], crs=layer.crs())\n"
            "        canvas.refresh()\n"
        ),
    },
    # 10. Pan & Flash Highlight Feature
    {
        "key": "flash_pan_feature",
        "category": "📐 Geometry & Spatial Analysis",
        "icon": "✨",
        "name": "Pan & Flash Highlight Feature on Canvas",
        "short_title": "Flash & Pan",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Pans the map canvas to center on the feature without altering the current zoom scale, and flashes its geometry.",
        "command": (
            "# Centers canvas on feature while keeping current map scale\n"
            "from qgis.core import QgsProject, QgsFeatureRequest, QgsCoordinateTransform\n"
            "from qgis.utils import iface\n"
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
            "if layer and iface:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat and feat.hasGeometry():\n"
            "        geom = feat.geometry()\n"
            "        pos = geom.pointOnSurface() if not geom.pointOnSurface().isEmpty() else geom.centroid()\n"
            "        pt = pos.asPoint()\n"
            "        canvas = iface.mapCanvas()\n"
            "        c_crs = canvas.mapSettings().destinationCrs()\n"
            "        if layer.crs() != c_crs:\n"
            "            tr = QgsCoordinateTransform(layer.crs(), c_crs, QgsProject.instance())\n"
            "            pt = tr.transform(pt)\n"
            "        canvas.setCenter(pt)\n"
            "        if hasattr(canvas, 'flashGeometries'):\n"
            "            canvas.flashGeometries([geom], crs=layer.crs())\n"
            "        canvas.refresh()\n"
        ),
    },
    # 11. Buffer Feature (Customizable Distance)
    {
        "key": "buffer_feature",
        "category": "📐 Geometry & Spatial Analysis",
        "icon": "🎯",
        "name": "Buffer Feature (50m Temp Layer)",
        "short_title": "Buffer 50m",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Generates a metric buffer zone around the clicked feature in a styled temporary layer. Revise BUFFER_DIST_M below for custom distances!",
        "command": (
            "# Customizable Parameters — edit BUFFER_DIST_M or BUFFER_LAYER_NAME:\n"
            "BUFFER_DIST_M = 50.0\n"
            "BUFFER_LAYER_NAME = 'Feature Buffers (Temp)'\n\n"
            "from qgis.PyQt.QtGui import QColor\n"
            "from qgis.core import (\n"
            "    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,\n"
            "    QgsFeatureRequest, QgsCoordinateReferenceSystem, QgsCoordinateTransform\n"
            ")\n"
            "from qgis.utils import iface\n"
            "proj = QgsProject.instance()\n"
            "layer = proj.mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat and feat.hasGeometry():\n"
            "        geom = feat.geometry()\n"
            "        crs = layer.crs()\n"
            "        if crs.isGeographic():\n"
            "            tr_to = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem('EPSG:3857'), proj)\n"
            "            tr_back = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:3857'), crs, proj)\n"
            "            g_copy = QgsGeometry(geom)\n"
            "            g_copy.transform(tr_to)\n"
            "            buf_geom = g_copy.buffer(BUFFER_DIST_M, 16)\n"
            "            buf_geom.transform(tr_back)\n"
            "        else:\n"
            "            buf_geom = geom.buffer(BUFFER_DIST_M, 16)\n"
            "        existing = [l for l in proj.mapLayersByName(BUFFER_LAYER_NAME) if isinstance(l, QgsVectorLayer) and l.crs() == crs]\n"
            "        if existing:\n"
            "            buf_lyr = existing[0]\n"
            "        else:\n"
            "            uri = f'Polygon?crs={crs.authid()}&field=source_layer:string(80)&field=source_fid:integer&field=buffer_m:double'\n"
            "            buf_lyr = QgsVectorLayer(uri, BUFFER_LAYER_NAME, 'memory')\n"
            "            if buf_lyr.renderer() and buf_lyr.renderer().symbol():\n"
            "                sym = buf_lyr.renderer().symbol()\n"
            "                sym.setColor(QColor(14, 165, 233, 55))\n"
            "                if sym.symbolLayerCount() > 0:\n"
            "                    sym.symbolLayer(0).setStrokeColor(QColor(2, 132, 199, 255))\n"
            "                    sym.symbolLayer(0).setStrokeWidth(0.7)\n"
            "            proj.addMapLayer(buf_lyr, False)\n"
            "            proj.layerTreeRoot().insertLayer(0, buf_lyr)\n"
            "        f = QgsFeature(buf_lyr.fields())\n"
            "        f.setGeometry(buf_geom)\n"
            "        f.setAttributes([layer.name(), int(feat.id()), float(BUFFER_DIST_M)])\n"
            "        buf_lyr.dataProvider().addFeatures([f])\n"
            "        buf_lyr.updateExtents()\n"
            "        buf_lyr.triggerRepaint()\n"
            "        if iface:\n"
            "            iface.mapCanvas().refresh()\n"
            "            iface.messageBar().pushSuccess('Buffer Action', f'Created {BUFFER_DIST_M:.0f}m buffer for ID [% $id %].')\n"
        ),
    },
    # 12. Select Nearby Features Within Radius
    {
        "key": "select_nearby_features",
        "category": "📐 Geometry & Spatial Analysis",
        "icon": "📡",
        "name": "Select Nearby Features Within Radius (100m)",
        "short_title": "Select Nearby",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Selects all neighboring features in the same layer within SEARCH_RADIUS_M meters of the clicked feature.",
        "command": (
            "# Customizable Parameters — edit SEARCH_RADIUS_M (in meters):\n"
            "SEARCH_RADIUS_M = 100.0\n\n"
            "from qgis.core import (\n"
            "    QgsProject, QgsGeometry, QgsFeatureRequest,\n"
            "    QgsCoordinateReferenceSystem, QgsCoordinateTransform\n"
            ")\n"
            "from qgis.utils import iface\n"
            "proj = QgsProject.instance()\n"
            "layer = proj.mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat and feat.hasGeometry():\n"
            "        geom = feat.geometry()\n"
            "        crs = layer.crs()\n"
            "        if crs.isGeographic():\n"
            "            tr_to = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem('EPSG:3857'), proj)\n"
            "            tr_back = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:3857'), crs, proj)\n"
            "            g_copy = QgsGeometry(geom)\n"
            "            g_copy.transform(tr_to)\n"
            "            search_geom = g_copy.buffer(SEARCH_RADIUS_M, 12)\n"
            "            search_geom.transform(tr_back)\n"
            "        else:\n"
            "            search_geom = geom.buffer(SEARCH_RADIUS_M, 12)\n"
            "        q = QgsFeatureRequest().setFilterRect(search_geom.boundingBox())\n"
            "        ids = [f.id() for f in layer.getFeatures(q) if f.hasGeometry() and f.geometry().intersects(search_geom)]\n"
            "        layer.selectByIds(ids)\n"
            "        if iface:\n"
            "            if hasattr(iface.mapCanvas(), 'flashGeometries'):\n"
            "                iface.mapCanvas().flashGeometries([search_geom], crs=crs)\n"
            "            iface.messageBar().pushSuccess('Proximity Select', f'Selected {len(ids)} features within {SEARCH_RADIUS_M:.0f}m.')\n"
        ),
    },
    # 13. Extract Feature to Scratch Memory Layer
    {
        "key": "extract_feature_layer",
        "category": "📐 Geometry & Spatial Analysis",
        "icon": "📤",
        "name": "Extract Feature to New Scratch Layer",
        "short_title": "Extract Layer",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Copies the clicked feature (geometry + all attributes) into a dedicated scratch memory layer at the top of the layer tree.",
        "command": (
            "# Extracts clicked feature into a dedicated memory layer\n"
            "from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFeatureRequest, QgsWkbTypes\n"
            "from qgis.utils import iface\n"
            "proj = QgsProject.instance()\n"
            "layer = proj.mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat and feat.hasGeometry():\n"
            "        wkb_str = QgsWkbTypes.displayString(layer.wkbType()) or 'Polygon'\n"
            "        out_name = f'Extracted Features ({layer.name()})'\n"
            "        existing = [l for l in proj.mapLayersByName(out_name) if isinstance(l, QgsVectorLayer)]\n"
            "        if existing:\n"
            "            out_lyr = existing[0]\n"
            "        else:\n"
            "            out_lyr = QgsVectorLayer(f'{wkb_str}?crs={layer.crs().authid()}', out_name, 'memory')\n"
            "            out_lyr.dataProvider().addAttributes(layer.fields().toList())\n"
            "            out_lyr.updateFields()\n"
            "            proj.addMapLayer(out_lyr, False)\n"
            "            proj.layerTreeRoot().insertLayer(0, out_lyr)\n"
            "        nf = QgsFeature(out_lyr.fields())\n"
            "        nf.setGeometry(QgsGeometry(feat.geometry()))\n"
            "        nf.setAttributes(feat.attributes())\n"
            "        out_lyr.dataProvider().addFeatures([nf])\n"
            "        out_lyr.updateExtents()\n"
            "        out_lyr.triggerRepaint()\n"
            "        if iface:\n"
            "            iface.messageBar().pushSuccess('Extract Feature', f'Copied feature #[% $id %] to {out_name}.')\n"
        ),
    },
    # 14. Ellipsoidal Geometry & Coordinate Audit
    {
        "key": "measure_geometry_summary",
        "category": "📐 Geometry & Spatial Analysis",
        "icon": "📏",
        "name": "Geometry & Coordinate Audit (Ellipsoidal Area/Length)",
        "short_title": "Geom Audit",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Calculates exact ellipsoidal area (m² / ha), perimeter/length, vertex count, and WGS84 coordinates, copying the audit to clipboard.",
        "command": (
            "# Computes ellipsoidal area, perimeter/length, vertices & WGS84 coordinates\n"
            "from qgis.PyQt.QtWidgets import QApplication\n"
            "from qgis.core import (\n"
            "    QgsProject, QgsDistanceArea, QgsFeatureRequest,\n"
            "    QgsCoordinateReferenceSystem, QgsCoordinateTransform\n"
            ")\n"
            "from qgis.utils import iface\n"
            "proj = QgsProject.instance()\n"
            "layer = proj.mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat and feat.hasGeometry():\n"
            "        geom = feat.geometry()\n"
            "        da = QgsDistanceArea()\n"
            "        da.setSourceCrs(layer.crs(), proj.transformContext())\n"
            "        da.setEllipsoid(proj.ellipsoid() or 'WGS84')\n"
            "        pos = geom.pointOnSurface() if not geom.pointOnSurface().isEmpty() else geom.centroid()\n"
            "        pt = pos.asPoint()\n"
            "        tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem('EPSG:4326'), proj)\n"
            "        wgs = tr.transform(pt)\n"
            "        verts = sum(1 for _ in geom.vertices())\n"
            "        lines = [\n"
            "            f'Layer: {layer.name()} (Feature #[% $id %])',\n"
            "            f'WGS84: {wgs.y():.6f}, {wgs.x():.6f}',\n"
            "            f'Vertices: {verts}',\n"
            "        ]\n"
            "        if layer.geometryType() == 2:\n"
            "            a = da.measureArea(geom)\n"
            "            p = da.measurePerimeter(geom)\n"
            "            lines.append(f'Area: {a:,.2f} m² ({a/10000.0:,.4f} ha)')\n"
            "            lines.append(f'Perimeter: {p:,.2f} m')\n"
            "        elif layer.geometryType() == 1:\n"
            "            l = da.measureLength(geom)\n"
            "            lines.append(f'Length: {l:,.2f} m ({l/1000.0:,.3f} km)')\n"
            "        QApplication.clipboard().setText('\\n'.join(lines))\n"
            "        if iface:\n"
            "            iface.messageBar().pushSuccess('Geometry Audit (Copied)', ' | '.join(lines[1:]))\n"
        ),
    },
    # 15. Copy Feature Attributes to Clipboard
    {
        "key": "copy_clipboard",
        "category": "📋 Attribute, Export & Clipboard",
        "icon": "📋",
        "name": "Copy Feature Attributes to Clipboard",
        "short_title": "Copy Attrs",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Copies all attribute field names and values of the clicked feature as formatted key-value text to the system clipboard.",
        "command": (
            "# Customizable Parameters — leave INCLUDE_FIELDS empty for all fields, or specify ['name', 'area']:\n"
            "INCLUDE_FIELDS = []\n\n"
            "from qgis.PyQt.QtWidgets import QApplication\n"
            "from qgis.core import QgsProject, QgsFeatureRequest\n"
            "from qgis.utils import iface\n"
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    for feat in layer.getFeatures(req):\n"
            "        fields = [f.name() for f in layer.fields() if not INCLUDE_FIELDS or f.name() in INCLUDE_FIELDS]\n"
            "        lines = [f'{fn}: {feat[fn]}' for fn in fields]\n"
            "        QApplication.clipboard().setText('\\n'.join(lines))\n"
            "        if iface:\n"
            "            iface.messageBar().pushSuccess('Qgis MapTips', f'Copied {len(lines)} attributes to clipboard.')\n"
            "        break\n"
        ),
    },
    # 16. Copy Feature as GeoJSON (WGS84)
    {
        "key": "copy_geojson",
        "category": "📋 Attribute, Export & Clipboard",
        "icon": "🧬",
        "name": "Copy Feature as GeoJSON (WGS84) to Clipboard",
        "short_title": "Copy GeoJSON",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Exports the feature's geometry (reprojected to EPSG:4326) and all attributes as an RFC 7946 GeoJSON Feature to the clipboard.",
        "command": (
            "# Exports clicked feature as formatted RFC 7946 GeoJSON (WGS84)\n"
            "import json\n"
            "from qgis.PyQt.QtWidgets import QApplication\n"
            "from qgis.core import (\n"
            "    QgsProject, QgsGeometry, QgsFeatureRequest,\n"
            "    QgsCoordinateReferenceSystem, QgsCoordinateTransform\n"
            ")\n"
            "from qgis.utils import iface\n"
            "proj = QgsProject.instance()\n"
            "layer = proj.mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat:\n"
            "        props = {f.name(): (feat[f.name()] if isinstance(feat[f.name()], (int, float, str, bool)) or feat[f.name()] is None else str(feat[f.name()])) for f in layer.fields()}\n"
            "        geom_dict = None\n"
            "        if feat.hasGeometry() and not feat.geometry().isEmpty():\n"
            "            g = QgsGeometry(feat.geometry())\n"
            "            if layer.crs().authid() != 'EPSG:4326':\n"
            "                tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem('EPSG:4326'), proj)\n"
            "                g.transform(tr)\n"
            "            geom_dict = json.loads(g.asJson())\n"
            "        geojson_str = json.dumps({'type': 'Feature', 'id': feat.id(), 'properties': props, 'geometry': geom_dict}, ensure_ascii=False, indent=2)\n"
            "        QApplication.clipboard().setText(geojson_str)\n"
            "        if iface:\n"
            "            iface.messageBar().pushSuccess('Qgis MapTips', 'Copied Feature #[% $id %] as GeoJSON to clipboard.')\n"
        ),
    },
    # 17. Copy WKT Geometry & WGS84 Coordinates
    {
        "key": "copy_wkt_coords",
        "category": "📋 Attribute, Export & Clipboard",
        "icon": "📐",
        "name": "Copy WKT Geometry & WGS84 Coordinates",
        "short_title": "Copy WKT",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Copies the feature's WGS84 Lat/Lon, native CRS X/Y coordinates, and full WKT geometry string to the clipboard.",
        "command": (
            "# Customizable Parameters:\n"
            "WKT_PRECISION = 6\n\n"
            "from qgis.PyQt.QtWidgets import QApplication\n"
            "from qgis.core import (\n"
            "    QgsProject, QgsFeatureRequest,\n"
            "    QgsCoordinateReferenceSystem, QgsCoordinateTransform\n"
            ")\n"
            "from qgis.utils import iface\n"
            "proj = QgsProject.instance()\n"
            "layer = proj.mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat and feat.hasGeometry():\n"
            "        geom = feat.geometry()\n"
            "        pos = geom.pointOnSurface() if not geom.pointOnSurface().isEmpty() else geom.centroid()\n"
            "        pt = pos.asPoint()\n"
            "        tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem('EPSG:4326'), proj)\n"
            "        wgs = tr.transform(pt)\n"
            "        text = f'WGS84 (Lat, Lon): {wgs.y():.6f}, {wgs.x():.6f}\\nNative ({layer.crs().authid()}): {pt.x():.3f}, {pt.y():.3f}\\nWKT: {geom.asWkt(WKT_PRECISION)}'\n"
            "        QApplication.clipboard().setText(text)\n"
            "        if iface:\n"
            "            iface.messageBar().pushSuccess('Qgis MapTips', f'Copied WKT & coordinates ({wgs.y():.5f}, {wgs.x():.5f}).')\n"
        ),
    },
    # 18. Export Feature Card to HTML Report
    {
        "key": "export_card_report",
        "category": "📋 Attribute, Export & Clipboard",
        "icon": "📄",
        "name": "Export Feature Card to HTML Report",
        "short_title": "HTML Report",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Renders the layer's HTML MapTip card for the clicked feature into a standalone, printable HTML report in the browser.",
        "command": (
            "import os, tempfile\n"
            "from qgis.PyQt.QtCore import QUrl\n"
            "from qgis.PyQt.QtGui import QDesktopServices\n"
            "from qgis.core import QgsProject, QgsFeatureRequest, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils\n"
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    for feat in layer.getFeatures(req):\n"
            "        ctx = QgsExpressionContext()\n"
            "        ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))\n"
            "        ctx.setFeature(feat)\n"
            "        html_card = QgsExpression.replaceExpressionText(layer.mapTipTemplate(), ctx)\n"
            "        full_html = '<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Feature Report</title><style>body{font-family:sans-serif;padding:24px;background:#f8fafc;}</style></head><body>' + html_card + '</body></html>'\n"
            "        tmp = os.path.join(tempfile.gettempdir(), 'feature_card_report_[% $id %].html')\n"
            "        with open(tmp, 'w', encoding='utf-8') as f:\n"
            "            f.write(full_html)\n"
            "        QDesktopServices.openUrl(QUrl.fromLocalFile(tmp))\n"
            "        break\n"
        ),
    },
    # 19. Open in TKGM Parsel Sorgu (Web)
    {
        "key": "tkgm_cadastre",
        "category": "🏛️ Cadastral & Urban Planning",
        "icon": "🏛️",
        "name": "Open in TKGM Parsel Sorgu (Web)",
        "short_title": "Parsel Sorgu",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens Turkey's official TKGM Parsel Sorgu web portal directly at the feature's WGS84 coordinates (Turkey Only).",
        "command": f"https://parselsorgu.tkgm.gov.tr/#ara/cografi/[% {LAT_EXPR} %]/[% {LON_EXPR} %]",
    },
    # 20. TKGM Instant Parcel Polygon Downloader (Python)
    {
        "key": "tkgm_instant_download",
        "category": "🏛️ Cadastral & Urban Planning",
        "icon": "⚡",
        "name": "Download Official TKGM Parcel at Feature (TR)",
        "short_title": "TKGM Parcel",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Queries the official TKGM MEGSIS API at the feature's surface centroid and adds the parcel polygon into 'TKGM Parselleri (TR)' (Turkey Only).",
        "command": (
            "# Queries official TKGM MEGSIS API and adds parcel polygon to QGIS project\n"
            "from qgis.core import QgsProject, QgsFeatureRequest\n"
            "from qgis.utils import iface\n"
            "from qgis_maptips.core.action_builder import download_tkgm_parcel_for_feature\n"
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
            "if layer:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat:\n"
            "        download_tkgm_parcel_for_feature(layer, feat, iface)\n"
        ),
    },
    # 21. Open Native QGIS Feature Attribute Form
    {
        "key": "open_attribute_form",
        "category": "🔗 External Portals & Forms",
        "icon": "🗂️",
        "name": "Open QGIS Feature Attribute Form Dialog",
        "short_title": "Attr Form",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens QGIS's native Feature Attribute Form dialog to inspect or edit all fields of the clicked feature.",
        "command": (
            "# Opens native QGIS Feature Form for inspecting/editing attributes\n"
            "from qgis.core import QgsProject, QgsFeatureRequest\n"
            "from qgis.utils import iface\n"
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
            "if layer and iface:\n"
            "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
            "    feat = next(layer.getFeatures(req), None)\n"
            "    if feat:\n"
            "        iface.openFeatureForm(layer, feat, False)\n"
        ),
    },
    # 22. Wikimedia GeoHack Coordinate Portal
    {
        "key": "wikipedia_geosearch",
        "category": "🔗 External Portals & Forms",
        "icon": "🌍",
        "name": "Wikimedia GeoHack Coordinate Intelligence Portal",
        "short_title": "GeoHack Wiki",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": "Opens Wikimedia GeoHack at the feature's coordinates with instant links to 50+ global topographic, geological, and satellite maps.",
        "command": f"https://geohack.toolforge.org/geohack.php?params=[% {LAT_EXPR} %]_N_[% {LON_EXPR} %]_E",
    },
]


def get_action_template_by_key(key: str) -> Optional[dict[str, Any]]:
    """Return a copy of the action template dict matching `key`, or None."""
    for act in AVAILABLE_ACTIONS:
        if act["key"] == key:
            return dict(act)
    return None


def build_open_file_action(field_name: str) -> dict[str, Any]:
    """Build an action definition that opens a local file path or URL stored in a field."""
    safe_fld = field_name.replace('"', '""')
    return {
        "key": f"open_file_{field_name}",
        "category": "🔗 External Portals & Forms",
        "icon": "📂",
        "name": f'Open File / Attachment ({field_name})',
        "short_title": f"Open {field_name}",
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": f"Opens the document, PDF, image, or web link stored in field '{field_name}'.",
        "command": f'[% "{safe_fld}" %]',
    }


def build_select_intersecting_action(target_layer_name: str) -> dict[str, Any]:
    """Build a Python action that selects features in a target layer intersecting the clicked feature."""
    safe_target = target_layer_name.replace("'", "\\'")
    cmd = (
        f"# Selects features in '{safe_target}' that spatially intersect the clicked feature\n"
        f"TARGET_LAYER_NAME = '{safe_target}'\n\n"
        "from qgis.core import QgsProject, QgsFeatureRequest, QgsGeometry, QgsCoordinateTransform\n"
        "from qgis.utils import iface\n"
        "proj = QgsProject.instance()\n"
        "src_layer = proj.mapLayer('[% @layer_id %]')\n"
        "tgt_layers = proj.mapLayersByName(TARGET_LAYER_NAME)\n"
        "if src_layer and tgt_layers:\n"
        "    tgt_layer = tgt_layers[0]\n"
        "    req = QgsFeatureRequest().setFilterFid([% $id %])\n"
        "    for feat in src_layer.getFeatures(req):\n"
        "        geom = QgsGeometry(feat.geometry())\n"
        "        if src_layer.crs() != tgt_layer.crs():\n"
        "            tr = QgsCoordinateTransform(src_layer.crs(), tgt_layer.crs(), proj)\n"
        "            geom.transform(tr)\n"
        "        bbox_req = QgsFeatureRequest().setFilterRect(geom.boundingBox())\n"
        "        ids = [f.id() for f in tgt_layer.getFeatures(bbox_req) if f.geometry().intersects(geom)]\n"
        "        tgt_layer.selectByIds(ids)\n"
        "        if iface:\n"
        "            iface.messageBar().pushInfo('Qgis MapTips', f'Selected {len(ids)} intersecting features in {tgt_layer.name()}')\n"
        "        break\n"
    )
    return {
        "key": f"select_intersects_{target_layer_name}",
        "category": "📐 Geometry & Spatial Analysis",
        "icon": "🔗",
        "name": f"Select Intersecting in '{target_layer_name}'",
        "short_title": f"Select {target_layer_name}",
        "type": "GenericPython",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": f"Selects all features in '{target_layer_name}' that spatially intersect the clicked feature.",
        "command": cmd,
    }


def build_custom_url_action(name: str, url_template: str) -> dict[str, Any]:
    """Build a custom user-defined URL action."""
    return {
        "key": f"custom_url_{name}",
        "category": "🔗 External Portals & Forms",
        "icon": "🔗",
        "name": name,
        "short_title": name[:18],
        "type": "OpenUrl",
        "scopes": ["Canvas", "Feature", "Field", "Layer", "Form"],
        "description": f"Custom URL action: {name}",
        "command": url_template,
    }


def _resolve_qgis_action_type(type_str: str) -> Any:
    """Resolve string ('OpenUrl' / 'GenericPython') to QgsAction.ActionType enum."""
    try:
        ActionTypeEnum = QgsAction.ActionType
    except AttributeError:
        ActionTypeEnum = QgsAction
    if "OpenUrl" in str(type_str) or str(type_str) == "0":
        return ActionTypeEnum.OpenUrl
    return ActionTypeEnum.GenericPython


def inject_or_update_custom_action(
    layer: QgsVectorLayer,
    name: str,
    short_title: str,
    action_type: str,
    command: str,
    scopes: Optional[list[str]] = None,
    overwrite: bool = True,
) -> bool:
    """Inject a new QgsAction or update an existing one (by name) on `layer`."""
    if not is_layer_alive(layer) or not name.strip() or not command.strip():
        return False

    mgr = layer.actions()
    if overwrite:
        for existing in list(mgr.actions()):
            if existing.name().strip().lower() == name.strip().lower():
                mgr.removeAction(existing.id())

    qgs_type = _resolve_qgis_action_type(action_type)
    target_scopes = set(scopes) if scopes else {"Canvas", "Feature", "Field", "Layer", "Form"}
    qgs_act = QgsAction(
        qgs_type,
        name.strip(),
        command,
        "",
        False,
        short_title.strip() or name.strip()[:18],
        target_scopes,
    )
    mgr.addAction(qgs_act)
    return True


def remove_action_by_id(layer: QgsVectorLayer, action_id: Any) -> bool:
    """Remove a single QgsAction from `layer` by its UUID/ID or name."""
    if not is_layer_alive(layer):
        return False
    mgr = layer.actions()
    for act in list(mgr.actions()):
        if str(act.id()) == str(action_id) or act.name() == str(action_id):
            mgr.removeAction(act.id())
            return True
    return False


def apply_actions_to_layer(
    layer: QgsVectorLayer,
    selected_keys: list[str],
    file_field: str = "",
    intersect_target_layer: str = "",
    custom_actions: Optional[list[dict[str, str]]] = None,
    clear_existing_plugin_actions: bool = False,
) -> int:
    """Inject selected actions into the vector layer's QgsActionManager."""
    if not is_layer_alive(layer):
        return 0

    action_mgr = layer.actions()
    existing_names = {act.name() for act in action_mgr.actions()}

    actions_to_add: list[dict[str, Any]] = []
    available_map = {act["key"]: act for act in AVAILABLE_ACTIONS}

    for key in selected_keys:
        if key in available_map:
            actions_to_add.append(available_map[key])

    if file_field and "open_file" in selected_keys:
        actions_to_add.append(build_open_file_action(file_field))

    if intersect_target_layer and "select_intersects" in selected_keys:
        actions_to_add.append(build_select_intersecting_action(intersect_target_layer))

    if custom_actions:
        for ca in custom_actions:
            if ca.get("name") and ca.get("command"):
                actions_to_add.append(
                    {
                        "name": ca["name"],
                        "short_title": ca.get("short_title", ca["name"][:18]),
                        "type": ca.get("type", "OpenUrl"),
                        "scopes": ca.get("scopes", ["Canvas", "Feature", "Field", "Layer", "Form"]),
                        "command": ca["command"],
                    }
                )

    added_count = 0
    for act_def in actions_to_add:
        if act_def["name"] in existing_names and not clear_existing_plugin_actions:
            continue

        act_type = _resolve_qgis_action_type(act_def.get("type", "OpenUrl"))
        scopes = set(act_def.get("scopes") or ["Canvas", "Feature", "Field", "Layer", "Form"])
        qgs_act = QgsAction(
            act_type,
            act_def["name"],
            act_def["command"],
            "",
            False,
            act_def.get("short_title", act_def["name"]),
            scopes,
        )
        action_mgr.addAction(qgs_act)
        existing_names.add(act_def["name"])
        added_count += 1

    return added_count


def get_layer_actions(layer: QgsVectorLayer) -> list[dict[str, Any]]:
    """Return a list of dictionaries describing currently registered actions on the layer."""
    if not is_layer_alive(layer):
        return []
    result = []
    for act in layer.actions().actions():
        type_str = str(act.type())
        is_url = "OpenUrl" in type_str or type_str == "0"
        result.append(
            {
                "id": act.id(),
                "name": act.name(),
                "short_title": act.shortTitle() if hasattr(act, "shortTitle") else act.name(),
                "type": "OpenUrl" if is_url else "GenericPython",
                "command": act.command(),
                "scopes": sorted(list(act.actionScopes())) if hasattr(act, "actionScopes") else ["Canvas"],
            }
        )
    return result


def remove_all_actions(layer: QgsVectorLayer) -> int:
    """Clear all actions from the vector layer."""
    if not is_layer_alive(layer):
        return 0
    mgr = layer.actions()
    acts = list(mgr.actions())
    count = len(acts)
    mgr.clearActions()
    return count


def export_actions_to_json(actions: list[dict[str, Any]], filepath: str) -> int:
    """Export a list of action dictionaries to a portable JSON file."""
    serializable = []
    for act in actions:
        serializable.append(
            {
                "name": act.get("name", "Custom Action"),
                "short_title": act.get("short_title", act.get("name", "Action")[:18]),
                "type": act.get("type", "GenericPython"),
                "scopes": list(act.get("scopes") or ["Canvas", "Feature", "Field", "Layer", "Form"]),
                "command": act.get("command", ""),
                "category": act.get("category", "Custom"),
                "description": act.get("description", ""),
            }
        )
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"qgis_maptips_actions": serializable}, f, ensure_ascii=False, indent=2)
    return len(serializable)


def import_actions_from_json(filepath: str) -> list[dict[str, Any]]:
    """Load a list of action dictionaries from a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "qgis_maptips_actions" in data:
        items = data["qgis_maptips_actions"]
    elif isinstance(data, list):
        items = data
    else:
        return []
    valid = []
    for it in items:
        if isinstance(it, dict) and it.get("name") and it.get("command"):
            valid.append(
                {
                    "name": str(it["name"]),
                    "short_title": str(it.get("short_title") or it["name"][:18]),
                    "type": str(it.get("type") or "GenericPython"),
                    "scopes": list(it.get("scopes") or ["Canvas", "Feature", "Field", "Layer", "Form"]),
                    "command": str(it["command"]),
                    "category": str(it.get("category") or "Custom"),
                    "description": str(it.get("description") or ""),
                }
            )
    return valid
