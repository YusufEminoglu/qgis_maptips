"""Action builder for QGIS vector layers.

Generates portable, dynamic CRS-aware web navigation actions, local document
launchers, cross-layer spatial selectors, and report exporters compatible with
both QGIS 3.28+ and QGIS 4.
"""
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qgis.core import QgsVectorLayer

# Dynamic WGS84 coordinates that automatically resolve layer CRS, handle Turkish/European decimal commas, and guarantee point on surface
LAT_EXPR = "[% with_variable('wgs', transform(coalesce(point_on_surface($geometry), centroid($geometry)), coalesce(@layer_crs, 'EPSG:4326'), 'EPSG:4326'), coalesce(to_string(round(y(@wgs), 6)), '0.0')) %]"
LON_EXPR = "[% with_variable('wgs', transform(coalesce(point_on_surface($geometry), centroid($geometry)), coalesce(@layer_crs, 'EPSG:4326'), 'EPSG:4326'), coalesce(to_string(round(x(@wgs), 6)), '0.0')) %]"

# Self-contained portable Python script for copying attributes to clipboard
CLIPBOARD_PYTHON_CODE = (
    "from qgis.PyQt.QtWidgets import QApplication; "
    "from qgis.core import QgsProject; "
    "layer = QgsProject.instance().mapLayer('[% @layer_id %]'); "
    "feat = layer.getFeature([% $id %]) if layer else None; "
    "lines = [f'{field.name()}: {feat[field.name()]}' for field in layer.fields()] if feat else []; "
    "QApplication.clipboard().setText('\\n'.join(lines)); "
    "from qgis.utils import iface; "
    "iface.messageBar().pushInfo('Qgis MapTips', 'Attributes copied to clipboard.') if hasattr(iface, 'messageBar') else None"
)

# 1-Click HTML Card Report Opener
EXPORT_CARD_REPORT_PYTHON_CODE = (
    "import tempfile, webbrowser, os; "
    "from qgis.core import QgsProject, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils; "
    "layer = QgsProject.instance().mapLayer('[% @layer_id %]'); "
    "feat = layer.getFeature([% $id %]) if layer else None; "
    "tmpl = layer.mapTipTemplate() if layer else ''; "
    "if feat and tmpl: "
    "    ctx = QgsExpressionContext(); "
    "    ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer)); "
    "    ctx.setFeature(feat); "
    "    html_text = QgsExpression.replaceExpressionText(tmpl, ctx); "
    "    full_html = ('<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Feature Report</title>' "
    "                 '<style>body{font-family:sans-serif;padding:30px;background:#f8fafc;display:flex;justify-content:center;}' "
    "                 '.card-wrap{box-shadow:0 10px 25px rgba(0,0,0,0.1);background:#fff;border-radius:6px;overflow:hidden;}' "
    "                 '</style></head><body><div class=\"card-wrap\">' + html_text + '</div></body></html>'); "
    "    tmp = os.path.join(tempfile.gettempdir(), f'feature_card_[% $id %].html'); "
    "    with open(tmp, 'w', encoding='utf-8') as f: f.write(full_html); "
    "    webbrowser.open(f'file:///{tmp}')"
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
        "name": "TKGM Instant Cadastre (Turkey Only)",
        "short_title": "TKGM (TR)",
        "type": "GenericPython",
        "command": TKGM_INSTANT_QUERY_PYTHON_CODE,
        "description": "Instant official cadastral query via MEGSIS API: adds parcel boundary to map & copies details (Turkey Only)",
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
    """Return a Python action selecting intersecting features in another layer."""
    clean_tgt = target_layer_name.strip()
    code = (
        f"from qgis.core import QgsProject; "
        f"src = QgsProject.instance().mapLayer('[% @layer_id %]'); "
        f"tgts = QgsProject.instance().mapLayersByName('{clean_tgt}'); "
        f"if src and tgts: "
        f"    feat = src.getFeature([% $id %]); "
        f"    tgt = tgts[0]; "
        f"    ids = [f.id() for f in tgt.getFeatures() if f.geometry().intersects(feat.geometry())]; "
        f"    tgt.selectByIds(ids); "
        f"    from qgis.utils import iface; "
        f"    iface.messageBar().pushInfo('Qgis MapTips', f'Selected {{len(ids)}} intersecting features in {clean_tgt}.') if hasattr(iface, 'messageBar') else None"
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
) -> int:
    """Add selected actions to the layer's action manager.

    Returns the number of added actions.
    """
    if not layer or not layer.isValid():
        return 0

    from qgis.core import QgsAction

    manager = layer.actions()
    norm_keys = list(dict.fromkeys(["tkgm_cadastre" if k == "tkgm_api_instant" else k for k in action_keys]))
    actions_to_add = [act for act in AVAILABLE_ACTIONS if act["key"] in norm_keys]
    if file_field and "open_file" in norm_keys:
        actions_to_add.append(build_open_file_action(file_field))
    if intersect_target_layer and "select_intersects" in norm_keys:
        actions_to_add.append(build_select_intersecting_action(intersect_target_layer))

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
    if not layer or not layer.isValid():
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
    if not layer or not layer.isValid():
        return 0
    manager = layer.actions()
    count = len(list(manager.actions()))
    with contextlib.suppress(Exception):
        manager.clearActions()
    return count

