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

# Dynamic WGS84 coordinates that automatically resolve layer CRS and guarantee point on surface
LAT_EXPR = "[% with_variable('wgs', transform(coalesce(point_on_surface($geometry), centroid($geometry)), @layer_crs, 'EPSG:4326'), format_number(y(@wgs), 7)) %]"
LON_EXPR = "[% with_variable('wgs', transform(coalesce(point_on_surface($geometry), centroid($geometry)), @layer_crs, 'EPSG:4326'), format_number(x(@wgs), 7)) %]"

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
        "name": "Yandex Haritalar",
        "short_title": "Yandex",
        "type": "OpenUrl",
        "command": f"https://yandex.com.tr/harita/?ll={LON_EXPR}%2C{LAT_EXPR}&z=19&l=sat",
        "description": "Open location in Yandex Maps satellite view",
    },
    {
        "key": "tkgm_cadastre",
        "name": "TKGM Parsel Sorgu",
        "short_title": "TKGM",
        "type": "OpenUrl",
        "command": f"https://parselsorgu.tkgm.gov.tr/#ara/cografi/{LAT_EXPR}/{LON_EXPR}/19",
        "description": "Open national cadastre portal at point coordinates",
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
    existing_names = {action.name() for action in manager.actions()}

    actions_to_add = [act for act in AVAILABLE_ACTIONS if act["key"] in action_keys]
    if file_field and "open_file" in action_keys:
        actions_to_add.append(build_open_file_action(file_field))
    if intersect_target_layer and "select_intersects" in action_keys:
        actions_to_add.append(build_select_intersecting_action(intersect_target_layer))

    added_count = 0
    for item in actions_to_add:
        name = item["name"]
        if name in existing_names:
            continue

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
            # Set action scopes: Canvas, Feature, Field
            action_obj.setActionScopes({"Canvas", "Feature", "Field"})

        manager.addAction(action_obj)
        added_count += 1

    return added_count
