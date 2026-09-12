"""Action builder for QGIS vector layers.

Generates portable, dynamic CRS-aware web navigation actions, local document
launchers, cross-layer spatial selectors, and report exporters compatible with
both QGIS 3.28+ and QGIS 4.
"""
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

try:
    from qgis.PyQt import sip
except ImportError:
    sip = None

if TYPE_CHECKING:
    from qgis.core import QgsVectorLayer


def is_layer_alive(layer: Any) -> bool:
    """Safely check whether a QgsMapLayer instance is alive in C++ and valid.

    Prevents SIP 'wrapped C/C++ object of type ... has been deleted' RuntimeError.
    """
    if layer is None:
        return False
    if sip is not None:
        with contextlib.suppress(TypeError, ValueError):
            if sip.isdeleted(layer):
                return False
    try:
        return bool(layer.isValid())
    except (RuntimeError, ReferenceError, AttributeError):
        return False


def zoom_to_feature(canvas: Any, layer: Any, feat: Any, iface: Any = None) -> bool:
    """Zoom and center map canvas to feature with CRS-aware adaptive padding."""
    if not canvas or not is_layer_alive(layer) or not feat:
        return False
    if not hasattr(feat, "hasGeometry") or not feat.hasGeometry() or feat.geometry().isEmpty():
        return False

    try:
        from qgis.core import QgsCoordinateTransform, QgsProject
        geom = feat.geometry()
        box = geom.boundingBox()
        dest_crs = canvas.mapSettings().destinationCrs() if hasattr(canvas, "mapSettings") else layer.crs()
        if layer.crs() != dest_crs:
            with contextlib.suppress(Exception):
                tr = QgsCoordinateTransform(layer.crs(), dest_crs, QgsProject.instance())
                box = tr.transformBoundingBox(box)

        is_geo = dest_crs.isGeographic() if hasattr(dest_crs, "isGeographic") else False
        max_dim = max(box.width(), box.height())
        if is_geo:
            pad = max(0.001, max_dim * 0.25)
        else:
            pad = max(30.0, max_dim * 0.25)

        canvas.setExtent(box.buffered(pad))
        canvas.refresh()
        if iface and hasattr(iface, "messageBar") and iface.messageBar():
            fid = feat.id() if hasattr(feat, "id") else ""
            iface.messageBar().pushSuccess("Qgis MapTips", f"Zoomed to feature {fid}.")
        return True
    except Exception:
        return False


def create_feature_buffer(layer: Any, feat: Any, dist_m: float = 50.0, iface: Any = None) -> bool:
    """Generate a spatial buffer polygon into a temporary memory layer with CRS awareness."""
    if not is_layer_alive(layer) or not feat:
        return False
    if not hasattr(feat, "hasGeometry") or not feat.hasGeometry() or feat.geometry().isEmpty():
        return False

    try:
        import math
        from qgis.PyQt.QtGui import QColor
        from qgis.core import QgsFeature, QgsProject, QgsVectorLayer

        geom = feat.geometry()
        if layer.crs().isGeographic():
            pt = geom.centroid().asPoint() if not geom.centroid().isEmpty() else None
            lat = pt.y() if pt else 39.0
            meters_per_deg = 111320.0 * max(0.2, math.cos(math.radians(lat)))
            dist_crs = dist_m / meters_per_deg
        else:
            dist_crs = dist_m

        buf_geom = geom.buffer(dist_crs, 24)
        if not buf_geom or buf_geom.isEmpty():
            return False

        layers = QgsProject.instance().mapLayersByName("Feature Buffers (Temp)")
        b_layer = layers[0] if layers and is_layer_alive(layers[0]) else None
        if not b_layer:
            uri = f"Polygon?crs={layer.crs().authid()}&field=src_id:string(30)&field=src_layer:string(80)&field=dist_m:double"
            b_layer = QgsVectorLayer(uri, "Feature Buffers (Temp)", "memory")
            b_layer.setOpacity(0.55)
            sym = b_layer.renderer().symbol() if b_layer.renderer() else None
            if sym:
                sym.setColor(QColor(6, 182, 212, 60))
                if sym.symbolLayerCount() > 0:
                    sym.symbolLayer(0).setStrokeColor(QColor(8, 145, 178))
                    sym.symbolLayer(0).setStrokeWidth(0.8)
            QgsProject.instance().addMapLayer(b_layer, False)
            root = QgsProject.instance().layerTreeRoot()
            if root:
                root.insertLayer(0, b_layer)
            else:
                QgsProject.instance().addMapLayer(b_layer)

        f_new = QgsFeature(b_layer.fields())
        f_new.setGeometry(buf_geom)
        fid_str = str(feat.id()) if hasattr(feat, "id") else ""
        layer_name = layer.name() if hasattr(layer, "name") else ""
        f_new.setAttributes([fid_str, layer_name, float(dist_m)])
        b_layer.dataProvider().addFeatures([f_new])
        b_layer.updateExtents()
        b_layer.triggerRepaint()

        canvas = iface.mapCanvas() if (iface and hasattr(iface, "mapCanvas")) else None
        if canvas:
            canvas.refresh()

        if iface and hasattr(iface, "messageBar") and iface.messageBar():
            iface.messageBar().pushSuccess(
                "Qgis MapTips", f"Created {dist_m:.0f}m buffer in 'Feature Buffers (Temp)' layer."
            )
        return True
    except Exception:
        return False



# Dynamic WGS84 coordinates that automatically resolve layer CRS, handle Turkish/European decimal commas, and guarantee point on surface
LAT_EXPR = "[% with_variable('wgs', transform(coalesce(point_on_surface($geometry), centroid($geometry)), coalesce(@layer_crs, 'EPSG:4326'), 'EPSG:4326'), coalesce(to_string(round(y(@wgs), 6)), '0.0')) %]"
LON_EXPR = "[% with_variable('wgs', transform(coalesce(point_on_surface($geometry), centroid($geometry)), coalesce(@layer_crs, 'EPSG:4326'), 'EPSG:4326'), coalesce(to_string(round(x(@wgs), 6)), '0.0')) %]"

# Self-contained portable Python script for copying attributes to clipboard
CLIPBOARD_PYTHON_CODE = (
    "from qgis.PyQt.QtWidgets import QApplication\n"
    "from qgis.core import QgsProject\n"
    "from qgis.utils import iface\n"
    "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
    "if not layer and iface:\n"
    "    layer = iface.activeLayer()\n"
    "feat = layer.getFeature([% $id %]) if layer else None\n"
    "if not feat and layer:\n"
    "    sel = layer.selectedFeatures()\n"
    "    feat = sel[0] if sel else None\n"
    "if feat and layer:\n"
    "    lines = [f'{fld.name()}: {feat[fld.name()]}' for fld in layer.fields()]\n"
    "    text = '\\n'.join(lines)\n"
    "    QApplication.clipboard().setText(text)\n"
    "    if hasattr(iface, 'messageBar') and iface.messageBar():\n"
    "        iface.messageBar().pushSuccess('Qgis MapTips', f'Copied {len(lines)} attributes to clipboard.')\n"
)

# 1-Click HTML Card Report Opener
EXPORT_CARD_REPORT_PYTHON_CODE = (
    "import tempfile, os\n"
    "from qgis.PyQt.QtCore import QUrl\n"
    "from qgis.PyQt.QtGui import QDesktopServices\n"
    "from qgis.core import QgsProject, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils\n"
    "from qgis.utils import iface\n"
    "layer = QgsProject.instance().mapLayer('[% @layer_id %]')\n"
    "if not layer and iface:\n"
    "    layer = iface.activeLayer()\n"
    "feat = layer.getFeature([% $id %]) if layer else None\n"
    "if not feat and layer:\n"
    "    sel = layer.selectedFeatures()\n"
    "    feat = sel[0] if sel else None\n"
    "tmpl = layer.mapTipTemplate() if layer else ''\n"
    "if feat and tmpl:\n"
    "    ctx = QgsExpressionContext()\n"
    "    ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))\n"
    "    ctx.setFeature(feat)\n"
    "    html_text = QgsExpression.replaceExpressionText(tmpl, ctx)\n"
    "    full_html = ('<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Feature Report</title>'\n"
    "                 '<style>body{font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif;padding:30px;background:#f8fafc;display:flex;justify-content:center;}'\n"
    "                 '.card-wrap{box-shadow:0 10px 25px rgba(0,0,0,0.1);background:#fff;border-radius:6px;overflow:hidden;}'\n"
    "                 '</style></head><body><div class=\"card-wrap\">' + html_text + '</div></body></html>')\n"
    "    fid = feat.id() if hasattr(feat, 'id') else 1\n"
    "    tmp = os.path.join(tempfile.gettempdir(), f'feature_card_{fid}.html')\n"
    "    with open(tmp, 'w', encoding='utf-8') as f:\n"
    "        f.write(full_html)\n"
    "    QDesktopServices.openUrl(QUrl.fromLocalFile(tmp))\n"
    "    if hasattr(iface, 'messageBar') and iface.messageBar():\n"
    "        iface.messageBar().pushSuccess('Qgis MapTips', 'Opened feature card report in browser.')\n"
)

# Instant MEGSIS Cadastral Query Python Action (0.2s API query + adds polygon layer + copies summary)
TKGM_INSTANT_QUERY_PYTHON_CODE = (
    "import datetime, json, contextlib; "
    "from qgis.PyQt.QtCore import QUrl; "
    "from qgis.PyQt.QtGui import QColor; "
    "from qgis.PyQt.QtNetwork import QNetworkRequest; "
    "from qgis.PyQt.QtWidgets import QApplication; "
    "from qgis.core import (QgsProject, QgsCoordinateTransform, QgsCoordinateReferenceSystem, "
    "QgsPointXY, QgsGeometry, QgsVectorLayer, QgsFeature, QgsNetworkAccessManager); "
    "from qgis.utils import iface; "
    "layer = QgsProject.instance().mapLayer('[% @layer_id %]'); "
    "feat = layer.getFeature([% $id %]) if layer else None; "
    "lat, lon = 0.0, 0.0; "
    "if feat and feat.hasGeometry(): "
    "    pos = feat.geometry().pointOnSurface() if not feat.geometry().pointOnSurface().isEmpty() else feat.geometry().centroid(); "
    "    pt = pos.asPoint(); "
    "    tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem('EPSG:4326'), QgsProject.instance()); "
    "    wgs = tr.transform(pt); "
    "    lat, lon = round(wgs.y(), 6), round(wgs.x(), 6); "
    "if lat and lon: "
    "    try: "
    "        url = f'https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api/parsel/{lat}/{lon}/'; "
    "        req = QNetworkRequest(QUrl(url)); "
    "        req.setRawHeader(b'User-Agent', b'Mozilla/5.0'); "
    "        reply = QgsNetworkAccessManager.instance().blockingGet(req); "
    "        data = json.loads(reply.content().data().decode('utf-8')); "
    "        p = data.get('properties', {}); "
    "        il = str(p.get('ilAd', '') or ''); "
    "        ilce = str(p.get('ilceAd', '') or ''); "
    "        mah = str(p.get('mahalleAd', '') or ''); "
    "        ada = str(p.get('adaNo', '') or ''); "
    "        parsel = str(p.get('parselNo', '') or ''); "
    "        alan = str(p.get('alan', '') or ''); "
    "        nitelik = str(p.get('nitelik', '') or ''); "
    "        mevkii = str(p.get('mevkii', '') or ''); "
    "        ozet = str(p.get('ozet', '') or f'{mah}-{ada}/{parsel}'); "
    "        summary = f'TKGM: {il} / {ilce} / {mah} | Block: {ada}, Parcel: {parsel} | Area: {alan} m2 | {nitelik}'; "
    "        QApplication.clipboard().setText(summary); "
    "        coords = data.get('geometry', {}).get('coordinates', []); "
    "        if coords: "
    "            rings = [[QgsPointXY(c[0], c[1]) for c in ring] for ring in coords]; "
    "            poly_geom = QgsGeometry.fromPolygonXY(rings); "
    "            t_layers = QgsProject.instance().mapLayersByName('TKGM Parselleri (TR)'); "
    "            if t_layers: "
    "                t_layer = t_layers[0]; "
    "            else: "
    "                uri = 'Polygon?crs=EPSG:4326&field=il:string(50)&field=ilce:string(50)&field=mahalle:string(50)&field=ada_no:string(20)&field=parsel_no:string(20)&field=alan_m2:double&field=nitelik:string(100)&field=mevkii:string(100)&field=ozet:string(60)&field=sorgu_tarihi:string(30)'; "
    "                t_layer = QgsVectorLayer(uri, 'TKGM Parselleri (TR)', 'memory'); "
    "                sym = t_layer.renderer().symbol(); "
    "                if sym: "
    "                    sym.setColor(QColor(245, 158, 11, 45)); "
    "                    sym.symbolLayer(0).setStrokeColor(QColor(217, 119, 6)); "
    "                    sym.symbolLayer(0).setStrokeWidth(0.6); "
    "                QgsProject.instance().addMapLayer(t_layer); "
    "            existing = {str(ft['ozet']) for ft in t_layer.getFeatures() if ft['ozet']}; "
    "            if ozet not in existing: "
    "                alan_val = float(alan.replace(',', '').strip() or 0.0) if alan else 0.0; "
    "                now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M'); "
    "                f = QgsFeature(t_layer.fields()); "
    "                f.setGeometry(poly_geom); "
    "                f.setAttributes([il, ilce, mah, ada, parsel, alan_val, nitelik, mevkii, ozet, now_str]); "
    "                t_layer.dataProvider().addFeatures([f]); "
    "                t_layer.triggerRepaint(); "
    "        if hasattr(iface, 'messageBar'): "
    "            iface.messageBar().pushInfo('TKGM Cadastre', f'🏛️ {summary} (Copied to clipboard & added to layer)'); "
    "    except Exception as exc: "
    "        if hasattr(iface, 'messageBar'): "
    "            iface.messageBar().pushWarning('TKGM Cadastre', f'TKGM query failed (no parcel found at coordinate or service unavailable): {exc}'); "
)


def _get_action_type(type_name: str):
    """Safely return QgsAction type enum for both QGIS 3 and QGIS 4."""
    from qgis.core import QgsAction
    if hasattr(QgsAction, "ActionType"):
        return getattr(QgsAction.ActionType, type_name)
    return getattr(QgsAction, type_name)


AVAILABLE_ACTIONS = [
    {
        "key": "google_satellite",
        "name": "Google Maps (Satellite)",
        "short_title": "Google Sat",
        "type": "OpenUrl",
        "command": f"https://www.google.com/maps/search/?api=1&query={LAT_EXPR},{LON_EXPR}&basemap=satellite",
        "description": "Open location in Google Maps satellite view",
    },
    {
        "key": "google_streetview",
        "name": "Google Street View",
        "short_title": "Street View",
        "type": "OpenUrl",
        "command": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={LAT_EXPR},{LON_EXPR}",
        "description": "Open location in Google Street View panorama",
    },
    {
        "key": "openstreetmap",
        "name": "OpenStreetMap",
        "short_title": "OSM",
        "type": "OpenUrl",
        "command": f"https://www.openstreetmap.org/?mlat={LAT_EXPR}&mlon={LON_EXPR}#map=18/{LAT_EXPR}/{LON_EXPR}",
        "description": "Open location in OpenStreetMap standard view",
    },
    {
        "key": "yandex_maps",
        "name": "Yandex Maps (Satellite)",
        "short_title": "Yandex",
        "type": "OpenUrl",
        "command": f"https://yandex.com/maps/?ll={LON_EXPR}%2C{LAT_EXPR}&z=19&l=sat",
        "description": "Open location in Yandex Maps satellite view",
    },
    {
        "key": "tkgm_cadastre",
        "name": "TKGM Parsel Sorgu (Web)",
        "short_title": "Parsel Sorgu",
        "type": "OpenUrl",
        "command": f"https://parselsorgu.tkgm.gov.tr/#ara/cografi/{LAT_EXPR}/{LON_EXPR}",
        "description": "Open location in official TKGM Parsel Sorgu web portal (Turkey Only)",
    },
    {
        "key": "copy_clipboard",
        "name": "Copy Attributes to Clipboard",
        "short_title": "Copy",
        "type": "GenericPython",
        "command": CLIPBOARD_PYTHON_CODE,
        "description": "Copy all feature attributes to the system clipboard",
    },
    {
        "key": "export_card_report",
        "name": "Export Feature Card to HTML Report",
        "short_title": "Export Card",
        "type": "GenericPython",
        "command": EXPORT_CARD_REPORT_PYTHON_CODE,
        "description": "Render and open standalone HTML feature card report in browser",
    },
    {
        "key": "zoom_feature",
        "name": "Zoom to Feature",
        "short_title": "Zoom",
        "type": "GenericPython",
        "command": (
            "from qgis.core import QgsProject, QgsCoordinateTransform; from qgis.utils import iface; "
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]'); "
            "if not layer and iface: layer = iface.activeLayer(); "
            "feat = layer.getFeature([% $id %]) if layer else None; "
            "if not feat and layer: sel = layer.selectedFeatures(); feat = sel[0] if sel else None; "
            "if feat and feat.hasGeometry() and iface: "
            "    canvas = iface.mapCanvas(); "
            "    dest_crs = canvas.mapSettings().destinationCrs(); "
            "    box = feat.geometry().boundingBox(); "
            "    if layer.crs() != dest_crs: "
            "        tr = QgsCoordinateTransform(layer.crs(), dest_crs, QgsProject.instance()); "
            "        box = tr.transformBoundingBox(box); "
            "    is_geo = dest_crs.isGeographic(); "
            "    max_dim = max(box.width(), box.height()); "
            "    pad = max(0.001, max_dim * 0.25) if is_geo else max(30.0, max_dim * 0.25); "
            "    canvas.setExtent(box.buffered(pad)); "
            "    canvas.refresh()"
        ),
        "description": "Zoom and center map canvas to this feature with adaptive padding",
    },
    {
        "key": "buffer_feature",
        "name": "Buffer Feature (50m Temp Layer)",
        "short_title": "Buffer",
        "type": "GenericPython",
        "command": (
            "import math; from qgis.core import QgsProject, QgsVectorLayer, QgsFeature; "
            "from qgis.PyQt.QtGui import QColor; from qgis.utils import iface; "
            "layer = QgsProject.instance().mapLayer('[% @layer_id %]'); "
            "if not layer and iface: layer = iface.activeLayer(); "
            "feat = layer.getFeature([% $id %]) if layer else None; "
            "if not feat and layer: sel = layer.selectedFeatures(); feat = sel[0] if sel else None; "
            "if feat and feat.hasGeometry(): "
            "    geom = feat.geometry(); "
            "    if layer.crs().isGeographic(): "
            "        pt = geom.centroid().asPoint() if not geom.centroid().isEmpty() else None; "
            "        lat = pt.y() if pt else 39.0; "
            "        m_deg = 111320.0 * max(0.2, math.cos(math.radians(lat))); "
            "        dist = 50.0 / m_deg; "
            "    else: "
            "        dist = 50.0; "
            "    buf_geom = geom.buffer(dist, 24); "
            "    layers = QgsProject.instance().mapLayersByName('Feature Buffers (Temp)'); "
            "    b_layer = layers[0] if layers else None; "
            "    if not b_layer: "
            "        uri = f'Polygon?crs={layer.crs().authid()}&field=src_id:string(30)&field=dist_m:double'; "
            "        b_layer = QgsVectorLayer(uri, 'Feature Buffers (Temp)', 'memory'); "
            "        b_layer.setOpacity(0.55); "
            "        sym = b_layer.renderer().symbol() if b_layer.renderer() else None; "
            "        if sym: sym.setColor(QColor(6, 182, 212, 60)); sym.symbolLayer(0).setStrokeColor(QColor(8, 145, 178)); sym.symbolLayer(0).setStrokeWidth(0.8); "
            "        QgsProject.instance().addMapLayer(b_layer, False); "
            "        root = QgsProject.instance().layerTreeRoot(); "
            "        root.insertLayer(0, b_layer) if root else QgsProject.instance().addMapLayer(b_layer); "
            "    f_new = QgsFeature(b_layer.fields()); "
            "    f_new.setGeometry(buf_geom); "
            "    f_new.setAttributes([str(feat.id()), 50.0]); "
            "    b_layer.dataProvider().addFeatures([f_new]); "
            "    b_layer.updateExtents(); "
            "    b_layer.triggerRepaint(); "
            "    iface.mapCanvas().refresh() if iface else None; "
            "    iface.messageBar().pushSuccess('Qgis MapTips', 'Created 50m buffer in Feature Buffers (Temp) layer.') if hasattr(iface, 'messageBar') else None"
        ),
        "description": "Generate a 50m spatial buffer polygon into a temporary memory layer",
    },
]


def build_open_file_action(field_name: str) -> dict[str, str]:
    """Return an action definition to open a file/URL stored in a feature field."""
    clean_field = field_name.strip()
    return {
        "key": f"open_file_{clean_field}",
        "name": f"Open File/Link ({clean_field})",
        "short_title": "Open File",
        "type": "OpenUrl",
        "command": f"[% \"{clean_field}\" %]",
        "description": f"Open path or link from attribute '{clean_field}'",
    }


def build_select_intersecting_action(target_layer_name: str) -> dict[str, str]:
    """Return a high-performance Python action selecting intersecting features in another layer."""
    clean_tgt = target_layer_name.strip()
    escaped_tgt = clean_tgt.replace("\\", "\\\\").replace("'", "\\'")
    code = (
        f"from qgis.core import QgsProject, QgsCoordinateTransform, QgsFeatureRequest; "
        f"src = QgsProject.instance().mapLayer('[% @layer_id %]'); "
        f"tgts = QgsProject.instance().mapLayersByName('{escaped_tgt}'); "
        f"if src and tgts: "
        f"    feat = src.getFeature([% $id %]); "
        f"    tgt = tgts[0]; "
        f"    geom = feat.geometry() if feat and feat.hasGeometry() else None; "
        f"    if geom: "
        f"        if src.crs() != tgt.crs(): "
        f"            tr = QgsCoordinateTransform(src.crs(), tgt.crs(), QgsProject.instance()); "
        f"            geom.transform(tr); "
        f"        req = QgsFeatureRequest().setFilterRect(geom.boundingBox()); "
        f"        req.setSubsetOfAttributes([]); "
        f"        ids = [f.id() for f in tgt.getFeatures(req) if f.geometry().intersects(geom)]; "
        f"        tgt.selectByIds(ids); "
        f"        from qgis.utils import iface; "
        f"        iface.messageBar().pushInfo('Qgis MapTips', f'Selected {{len(ids)}} intersecting features in {escaped_tgt}.') if hasattr(iface, 'messageBar') else None"
    )
    return {
        "key": f"select_intersects_{clean_tgt}",
        "name": f"Select Intersecting in '{clean_tgt}'",
        "short_title": f"Select {clean_tgt}",
        "type": "GenericPython",
        "command": code,
        "description": f"Select all features in '{clean_tgt}' that spatially intersect this feature",
    }


def build_custom_url_action(name: str, url_template: str) -> dict[str, str]:
    """Return a custom parameterized URL action."""
    return {
        "key": f"custom_url_{name.lower().replace(' ', '_')}",
        "name": name,
        "short_title": name[:10],
        "type": "OpenUrl",
        "command": url_template,
        "description": f"Custom Web Action: {url_template}",
    }


def apply_actions_to_layer(
    layer: "QgsVectorLayer",
    action_keys: list[str],
    file_field: str = "",
    intersect_target_layer: str = "",
    custom_url_name: str = "",
    custom_url_template: str = "",
) -> int:
    """Add selected actions to the layer's action manager.

    Returns the number of added actions.
    """
    if not is_layer_alive(layer):
        return 0

    from qgis.core import QgsAction

    manager = layer.actions()
    norm_keys = list(dict.fromkeys(["tkgm_cadastre" if k == "tkgm_api_instant" else k for k in action_keys]))
    actions_to_add = [act for act in AVAILABLE_ACTIONS if act["key"] in norm_keys]
    if file_field and "open_file" in norm_keys:
        actions_to_add.append(build_open_file_action(file_field))
    if intersect_target_layer and "select_intersects" in norm_keys:
        actions_to_add.append(build_select_intersecting_action(intersect_target_layer))
    if custom_url_template and "custom_url" in norm_keys:
        actions_to_add.append(build_custom_url_action(custom_url_name or "Custom Web Action", custom_url_template))

    target_names = {item["name"] for item in actions_to_add}
    # Remove older matching actions so they are refreshed with bug-fixed commands, plus any duplicate TKGM actions
    for old_act in list(manager.actions()):
        old_name = old_act.name()
        if old_name in target_names or "tkgm" in old_name.lower():
            with contextlib.suppress(Exception):
                manager.removeAction(old_act.id())

    added_count = 0
    for item in actions_to_add:
        name = item["name"]

        act_type = _get_action_type(item["type"])
        action_obj = QgsAction(
            act_type,
            name,
            item["command"],
            "",  # icon path
            False,  # capture
            item["short_title"],
        )

        with contextlib.suppress(Exception):
            # Set action scopes: Canvas, Feature, Field, Layer, Form
            action_obj.setActionScopes({"Canvas", "Feature", "Field", "Layer", "Form"})

        manager.addAction(action_obj)
        added_count += 1

    if added_count > 0:
        all_acts = list(manager.actions())
        if all_acts:
            with contextlib.suppress(Exception):
                # Set first injected action as default action for Canvas clicks
                manager.setDefaultAction("Canvas", all_acts[-added_count].id())

    return added_count


def get_layer_actions(layer: "QgsVectorLayer") -> list[dict[str, Any]]:
    """Return a list of dictionaries describing all actions currently attached to the layer."""
    if not is_layer_alive(layer):
        return []
    res = []
    manager = layer.actions()
    for act in manager.actions():
        scopes = sorted(list(act.actionScopes())) if hasattr(act, "actionScopes") else []
        res.append({
            "id": act.id(),
            "name": act.name(),
            "short_title": act.shortTitle() if hasattr(act, "shortTitle") else act.name(),
            "type": act.type(),
            "command": act.command(),
            "scopes": scopes,
        })
    return res


def remove_all_actions(layer: "QgsVectorLayer") -> int:
    """Clear all actions from the layer's action manager and return the count removed."""
    if not is_layer_alive(layer):
        return 0
    manager = layer.actions()
    count = len(list(manager.actions()))
    with contextlib.suppress(Exception):
        manager.clearActions()
    return count


try:
    from qgis.PyQt.QtCore import QObject, QUrl, QUrlQuery, pyqtSlot
    from qgis.PyQt.QtGui import QDesktopServices
    from qgis.PyQt.QtWidgets import QApplication
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsExpression,
        QgsExpressionContext,
        QgsExpressionContextUtils,
        QgsProject,
        QgsVectorLayer,
    )
except ImportError:
    class QObject:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None: pass
    class QUrl:  # type: ignore
        pass
    class QUrlQuery:  # type: ignore
        pass
    def pyqtSlot(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        def decorator(fn: Any) -> Any: return fn
        return decorator


class ActionUrlHandler(QObject):
    """Global Qt URL handler for 'action:' scheme links embedded in MapTip cards."""

    def __init__(self, iface: Any = None) -> None:
        super().__init__()
        self.iface = iface

    @pyqtSlot(QUrl)
    def handleUrl(self, url: QUrl) -> None:
        url_str = url.toString()
        query = QUrlQuery(url)
        lyr_id = query.queryItemValue("layer")
        fid_str = query.queryItemValue("id")
        action_key = url.path() or url_str.split("?", 1)[0].replace("action:", "").strip("/")

        layer = QgsProject.instance().mapLayer(lyr_id) if lyr_id else None
        if not layer and self.iface and hasattr(self.iface, "activeLayer"):
            layer = self.iface.activeLayer()

        feat = None
        if layer and fid_str and fid_str.lstrip("-").isdigit():
            with contextlib.suppress(Exception):
                feat = layer.getFeature(int(fid_str))
        if not feat and layer:
            with contextlib.suppress(Exception):
                sel = layer.selectedFeatures()
                feat = sel[0] if sel else None
        if not feat and layer:
            with contextlib.suppress(Exception):
                for f in layer.getFeatures():
                    feat = f
                    break

        if "copy_clipboard" in action_key:
            if feat and layer:
                lines = [f"{field.name()}: {feat[field.name()]}" for field in layer.fields()]
                QApplication.clipboard().setText("\n".join(lines))
                if self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                    self.iface.messageBar().pushSuccess(
                        "Qgis MapTips", f"Copied {len(lines)} attributes to clipboard."
                    )
            elif self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushWarning(
                    "Qgis MapTips", "No feature available to copy attributes from."
                )

        elif "export_card_report" in action_key:
            if feat and layer:
                import os, tempfile
                raw_html = layer.mapTipTemplate()
                ctx = QgsExpressionContext()
                ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
                ctx.setFeature(feat)
                evaluated = QgsExpression.replaceExpressionText(raw_html, ctx)
                full_html = (
                    '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Feature Card Report</title>'
                    '<style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:30px;background:#f8fafc;display:flex;justify-content:center;}'
                    '.card-wrap{box-shadow:0 10px 25px rgba(0,0,0,0.1);background:#fff;border-radius:6px;overflow:hidden;}'
                    '</style></head><body><div class="card-wrap">' + evaluated + '</div></body></html>'
                )
                fid = feat.id() if hasattr(feat, "id") else 1
                tmp = os.path.join(tempfile.gettempdir(), f"feature_card_{fid}.html")
                with open(tmp, "w", encoding="utf-8") as fp:
                    fp.write(full_html)
                QDesktopServices.openUrl(QUrl.fromLocalFile(tmp))
                if self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                    self.iface.messageBar().pushSuccess(
                        "Qgis MapTips", "Opened feature card report in browser."
                    )
            elif self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushWarning(
                    "Qgis MapTips", "No feature available to export report from."
                )

        elif "zoom" in action_key:
            if feat and layer:
                canvas = self.iface.mapCanvas() if (self.iface and hasattr(self.iface, "mapCanvas")) else None
                zoom_to_feature(canvas, layer, feat, self.iface)
            elif self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushWarning("Qgis MapTips", "No feature available to zoom to.")

        elif "buffer" in action_key:
            if feat and layer:
                create_feature_buffer(layer, feat, 50.0, self.iface)
            elif self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushWarning("Qgis MapTips", "No feature available to buffer.")

        elif "tkgm" in action_key or "parsel" in action_key:
            if feat and layer and feat.hasGeometry():
                pos = feat.geometry().pointOnSurface() if not feat.geometry().pointOnSurface().isEmpty() else feat.geometry().centroid()
                pt = pos.asPoint()
                tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
                wgs = tr.transform(pt)
                lat, lon = round(wgs.y(), 6), round(wgs.x(), 6)
                url_web = f"https://parselsorgu.tkgm.gov.tr/#ara/cografi/{lat}/{lon}"
                QDesktopServices.openUrl(QUrl(url_web))
                if self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                    self.iface.messageBar().pushSuccess("TKGM Parsel Sorgu", f"Opened TKGM Parsel Sorgu in browser ({lat}, {lon}).")
            elif self.iface and hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushWarning("TKGM Parsel Sorgu", "No feature with valid geometry found to open Parsel Sorgu.")



