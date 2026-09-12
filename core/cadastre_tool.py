"""Interactive canvas cadastre tool for TKGM MEGSIS queries.

Enables 1-click cadastral parcel retrieval directly from the QGIS map canvas
without requiring any vector layer to be selected. Queries official TKGM MEGSIS
web API, constructs polygon geometry, creates/appends to a styled vector layer
with Turkish fields and centroid-inside labels, and configures instant MapTip cards.
"""
from __future__ import annotations

import contextlib
import datetime
import json
from typing import TYPE_CHECKING, Any, Optional

try:
    from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
    from qgis.PyQt.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
    from qgis.PyQt.QtWidgets import QApplication
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsFeature,
        QgsFeatureRequest,
        QgsGeometry,
        QgsPalLayerSettings,
        QgsPointXY,
        QgsProject,
        QgsTextBufferSettings,
        QgsTextFormat,
        QgsVectorLayer,
        QgsVectorLayerSimpleLabeling,
    )
    from qgis.gui import QgsMapCanvas, QgsMapTool
except ImportError:  # Pure-Python test environment fallback
    class QPoint:  # type: ignore
        def __init__(self, x: int = 0, y: int = 0) -> None:
            self.x, self.y = x, y

    class Qt:  # type: ignore
        class MouseButton:
            LeftButton = 1

        class CursorShape:
            WaitCursor = 3
            PointingHandCursor = 13

        class PenStyle:
            NoPen = 0

        class GlobalColor:
            transparent = 0

    def pyqtSignal(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        class Signal:
            def emit(self, *a: Any, **kw: Any) -> None:
                pass

            def connect(self, fn: Any) -> None:
                pass

            def disconnect(self, fn: Any) -> None:
                pass

        return Signal()

    class QgsPointXY:  # type: ignore
        def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
            self._x, self._y = float(x), float(y)

        def x(self) -> float:
            return self._x

        def y(self) -> float:
            return self._y

    class QgsGeometry:  # type: ignore
        def __init__(self, rings: Any = None) -> None:
            self._rings = rings

        def isEmpty(self) -> bool:
            return False

        @classmethod
        def fromPolygonXY(cls, rings: Any) -> Any:
            return cls(rings)

        @classmethod
        def fromMultiPolygonXY(cls, polys: Any) -> Any:
            return cls(polys)

    class QgsFeatureRequest:  # type: ignore
        class Flag:
            NoGeometry = 1
        NoGeometry = 1

        def setFilterExpression(self, expr: str) -> Any:
            return self

        def setFlags(self, flags: Any) -> Any:
            return self

        def setLimit(self, limit: int) -> Any:
            return self

    class QgsMapCanvas:  # type: ignore
        pass

    class QgsMapTool:  # type: ignore
        def __init__(self, canvas: Any = None) -> None:
            self._canvas = canvas

        def setCursor(self, cursor: Any) -> None:
            pass

        def toMapCoordinates(self, pos: Any) -> Any:
            return QgsPointXY(0.0, 0.0)

    class QgsProject:  # type: ignore
        pass

    class QgsVectorLayer:  # type: ignore
        def setLabeling(self, labeling: Any) -> None:
            pass

        def setLabelsEnabled(self, enabled: bool) -> None:
            pass

        def setMapTipTemplate(self, template: str) -> None:
            pass

        def renderer(self) -> Any:
            return None

        def fields(self) -> Any:
            return []

        def dataProvider(self) -> Any:
            class Prov:
                def addFeatures(self, f: Any) -> None:
                    pass

            return Prov()

        def triggerRepaint(self) -> None:
            pass

        def getFeatures(self) -> Any:
            return []

        def selectByIds(self, ids: Any) -> None:
            pass

    class QgsFeature:  # type: ignore
        def __init__(self, fields: Any = None) -> None:
            pass

        def setGeometry(self, g: Any) -> None:
            pass

        def setAttributes(self, attrs: Any) -> None:
            pass

        def id(self) -> int:
            return 1

    class QgsCoordinateReferenceSystem:  # type: ignore
        def __init__(self, authid: str = "") -> None:
            self.authid = authid

    class QgsCoordinateTransform:  # type: ignore
        def __init__(self, src: Any = None, dest: Any = None, proj: Any = None) -> None:
            pass

        def transform(self, pt: Any) -> Any:
            return pt

    class QgsPalLayerSettings:  # type: ignore
        class Placement:
            AroundPoint = 0
            Horizontal = 1

        def __init__(self) -> None:
            self.fieldName = ""
            self.isExpression = False
            self.centroidInside = False
            self.placement = 0

        def setFormat(self, fmt: Any) -> None:
            pass

    class QgsVectorLayerSimpleLabeling:  # type: ignore
        def __init__(self, settings: Any = None) -> None:
            pass

    class QgsTextFormat:  # type: ignore
        def font(self) -> Any:
            class DummyFont:
                def setPointSize(self, s: int) -> None:
                    pass

                def setBold(self, b: bool) -> None:
                    pass

            return DummyFont()

        def setFont(self, f: Any) -> None:
            pass

        def setColor(self, c: Any) -> None:
            pass

        def setBuffer(self, b: Any) -> None:
            pass

    class QgsTextBufferSettings:  # type: ignore
        def setEnabled(self, e: bool) -> None:
            pass

        def setSize(self, s: float) -> None:
            pass

        def setColor(self, c: Any) -> None:
            pass

    class QCursor:  # type: ignore
        def __init__(self, *args: Any) -> None:
            pass

    class QColor:  # type: ignore
        def __init__(self, *args: Any) -> None:
            pass

    class QPainter:  # type: ignore
        class RenderHint:
            Antialiasing = 1

        def __init__(self, *args: Any) -> None:
            pass

        def setRenderHint(self, *args: Any) -> None:
            pass

        def setPen(self, *args: Any) -> None:
            pass

        def setBrush(self, *args: Any) -> None:
            pass

        def drawLine(self, *args: Any) -> None:
            pass

        def drawEllipse(self, *args: Any) -> None:
            pass

        def drawRoundedRect(self, *args: Any) -> None:
            pass

        def drawPolygon(self, *args: Any) -> None:
            pass

        def end(self) -> None:
            pass

    class QPen:  # type: ignore
        def __init__(self, *args: Any) -> None:
            pass

    class QPixmap:  # type: ignore
        def __init__(self, *args: Any) -> None:
            pass

        def fill(self, *args: Any) -> None:
            pass

    class QApplication:  # type: ignore
        @staticmethod
        def clipboard() -> Any:
            class Clip:
                def setText(self, text: str) -> None:
                    pass

            return Clip()

        @staticmethod
        def setOverrideCursor(cursor: Any) -> None:
            pass

        @staticmethod
        def restoreOverrideCursor() -> None:
            pass

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

# Turkish Layer Name and Schema
CADASTRE_LAYER_NAME = "TKGM Parselleri (TR)"
CADASTRE_LAYER_URI = (
    "Polygon?crs=EPSG:4326"
    "&field=il:string(50)"
    "&field=ilce:string(50)"
    "&field=mahalle:string(50)"
    "&field=ada_no:string(20)"
    "&field=parsel_no:string(20)"
    "&field=alan_m2:double"
    "&field=nitelik:string(100)"
    "&field=mevkii:string(100)"
    "&field=ozet:string(80)"
    "&field=sorgu_tarihi:string(30)"
)

# Daily query tracking in session
_DAILY_QUERY_COUNT = 0
_DAILY_QUERY_DATE = ""


def record_tkgm_query() -> int:
    """Increments and returns the in-session daily query count."""
    global _DAILY_QUERY_COUNT, _DAILY_QUERY_DATE
    today = datetime.date.today().isoformat()
    if _DAILY_QUERY_DATE != today:
        _DAILY_QUERY_DATE = today
        _DAILY_QUERY_COUNT = 0
    _DAILY_QUERY_COUNT += 1
    return _DAILY_QUERY_COUNT


def get_daily_query_count() -> int:
    """Returns the total number of queries executed today in this session."""
    today = datetime.date.today().isoformat()
    if _DAILY_QUERY_DATE != today:
        return 0
    return _DAILY_QUERY_COUNT


def create_cadastre_cursor() -> QCursor:
    """Creates a high-visibility amber crosshair reticle cursor with parcel badge."""
    pix = QPixmap(32, 32)
    trans = Qt.GlobalColor.transparent if hasattr(Qt, "GlobalColor") else getattr(Qt, "transparent", 0)
    pix.fill(trans)

    p = QPainter(pix)
    hint = QPainter.RenderHint.Antialiasing if hasattr(QPainter, "RenderHint") else getattr(QPainter, "Antialiasing", 0)
    p.setRenderHint(hint)

    cx, cy = 12, 12

    # Outer dark shadow / halo
    p.setPen(QPen(QColor(15, 23, 42, 220), 3.0))
    p.drawLine(cx - 7, cy, cx + 7, cy)
    p.drawLine(cx, cy - 7, cx, cy + 7)

    # Inner bright amber core
    p.setPen(QPen(QColor(245, 158, 11, 255), 1.5))
    p.drawLine(cx - 6, cy, cx + 6, cy)
    p.drawLine(cx, cy - 6, cx, cy + 6)

    # Center target dot
    no_pen = Qt.PenStyle.NoPen if hasattr(Qt, "PenStyle") else getattr(Qt, "NoPen", 0)
    p.setPen(no_pen)
    p.setBrush(QColor(217, 119, 6, 255))
    p.drawEllipse(cx - 2, cy - 2, 4, 4)

    # Mini indicator badge at top-right quadrant
    p.setPen(QPen(QColor(15, 23, 42, 200), 1.0))
    p.setBrush(QColor(245, 158, 11, 240))
    p.drawRoundedRect(17, 2, 13, 11, 2.5, 2.5)

    # Mini parcel symbol (building/polygon) inside badge
    p.setPen(no_pen)
    p.setBrush(QColor(255, 255, 255, 240))
    p.drawPolygon([
        QPoint(23, 4),
        QPoint(19, 7),
        QPoint(21, 11),
        QPoint(26, 11),
        QPoint(27, 7),
    ])

    p.end()
    return QCursor(pix, cx, cy)


def is_in_turkey_bounds(lat: float, lon: float) -> bool:
    """Returns True if the coordinates fall roughly within the Republic of Turkey."""
    return 35.0 <= lat <= 43.0 and 25.0 <= lon <= 45.0


def query_tkgm_megsis(lat: float, lon: float) -> tuple[bool, dict[str, Any], str]:
    """Queries official TKGM MEGSIS API for cadastral parcel at WGS84 lat/lon.

    Returns (success: bool, data: dict, error_message: str).
    """
    record_tkgm_query()
    count = get_daily_query_count()

    try:
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtNetwork import QNetworkRequest
        from qgis.core import QgsNetworkAccessManager

        url = f"https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api/parsel/{lat:.6f}/{lon:.6f}/"
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
        req.setRawHeader(b"Accept", b"application/json, text/plain, */*")
        req.setRawHeader(b"Referer", b"https://parselsorgu.tkgm.gov.tr/")
        req.setRawHeader(b"Origin", b"https://parselsorgu.tkgm.gov.tr")
        req.setRawHeader(b"Accept-Language", b"tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7")
        req.setRawHeader(b"sec-ch-ua", b'"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"')
        req.setRawHeader(b"sec-ch-ua-mobile", b"?0")
        req.setRawHeader(b"sec-ch-ua-platform", b'"Windows"')
        req.setRawHeader(b"sec-fetch-dest", b"empty")
        req.setRawHeader(b"sec-fetch-mode", b"cors")
        req.setRawHeader(b"sec-fetch-site", b"same-site")

        if hasattr(QNetworkRequest, "Attribute"):
            req.setAttribute(QNetworkRequest.Attribute.FollowRedirectsAttribute, True)
        else:
            with contextlib.suppress(AttributeError):
                req.setAttribute(getattr(QNetworkRequest, "FollowRedirectsAttribute", 0), True)

        nam = QgsNetworkAccessManager.instance()
        reply = nam.blockingGet(req)

        status_code = None
        if hasattr(QNetworkRequest, "Attribute"):
            status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        else:
            with contextlib.suppress(AttributeError):
                status_code = reply.attribute(getattr(QNetworkRequest, "HttpStatusCodeAttribute", 0))

        if status_code == 403:
            return False, {}, (
                f"TKGM günlük sorgu kotası doldu (HTTP 403 Forbidden). "
                f"Bugün bu oturumda yapılan sorgu: {count}. TKGM MEGSİS servisi IP başına "
                f"günlük yaklaşık 100 sorgu fair-use limiti uygulamaktadır. "
                f"Limit genellikle gece yarısı sıfırlanır."
            )

        if status_code is not None and status_code != 200:
            return False, {}, f"TKGM sunucusu HTTP {status_code} yanıtı döndürdü (Sorgu: {count})"

        raw_bytes = reply.content().data()
        if not raw_bytes:
            return False, {}, "TKGM MEGSİS servisinden boş yanıt döndü"

        text = raw_bytes.decode("utf-8", errors="replace")
        data = json.loads(text)
        return True, data, ""
    except Exception as exc:
        return False, {}, str(exc)


def parse_tkgm_response(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Parses MEGSIS GeoJSON response into a structured parcel dictionary with Turkish keys."""
    if not isinstance(data, dict):
        return None

    feat_data = data
    if "features" in data and isinstance(data["features"], list):
        if not data["features"]:
            return None
        feat_data = data["features"][0]

    props = feat_data.get("properties") or {}
    geom_data = feat_data.get("geometry") or {}

    coords = geom_data.get("coordinates")
    geom_type = geom_data.get("type", "Polygon")

    if not coords:
        return None

    qgs_geom = None
    with contextlib.suppress(Exception):
        if geom_type == "Polygon" and isinstance(coords, list):
            rings = [[QgsPointXY(float(c[0]), float(c[1])) for c in ring] for ring in coords]
            qgs_geom = QgsGeometry.fromPolygonXY(rings)
        elif geom_type == "MultiPolygon" and isinstance(coords, list):
            polys = [[[QgsPointXY(float(c[0]), float(c[1])) for c in ring] for ring in poly] for poly in coords]
            qgs_geom = QgsGeometry.fromMultiPolygonXY(polys)

    if qgs_geom is None or qgs_geom.isEmpty():
        return None

    il = str(props.get("ilAd", "") or "").strip()
    ilce = str(props.get("ilceAd", "") or "").strip()
    mah = str(props.get("mahalleAd", "") or "").strip()
    ada = str(props.get("adaNo", "") or "").strip()
    parsel = str(props.get("parselNo", "") or "").strip()
    alan_raw = str(props.get("alan", "") or "").replace(",", ".").strip()
    try:
        alan = float(alan_raw) if alan_raw else 0.0
    except ValueError:
        alan = 0.0
    nitelik = str(props.get("nitelik", "") or "").strip()
    mevkii = str(props.get("mevkii", "") or "").strip()
    ozet = str(props.get("ozet", "") or f"{mah} {ada}/{parsel}").strip()

    parcel_key = f"{il}-{ilce}-{mah}-{ada}/{parsel}" if (il and ada and parsel) else ozet

    return {
        "il": il,
        "ilce": ilce,
        "mahalle": mah,
        "ada_no": ada,
        "parsel_no": parsel,
        "alan_m2": alan,
        "nitelik": nitelik,
        "mevkii": mevkii,
        "ozet": parcel_key,
        "summary": ozet,
        "geometry": qgs_geom,
    }


def get_or_create_cadastre_layer(project: Optional[QgsProject] = None) -> QgsVectorLayer:
    """Returns the existing TKGM cadastre memory layer or creates and styles a new one."""
    proj = project or QgsProject.instance()
    layers = proj.mapLayersByName(CADASTRE_LAYER_NAME)
    if layers:
        return layers[0]

    layer = QgsVectorLayer(CADASTRE_LAYER_URI, CADASTRE_LAYER_NAME, "memory")

    # Cadastral Amber Boundary and Semi-transparent Fill
    renderer = layer.renderer()
    if renderer:
        sym = renderer.symbol()
        if sym and sym.symbolLayerCount() > 0:
            sym.setColor(QColor(245, 158, 11, 45))
            sl = sym.symbolLayer(0)
            if sl:
                sl.setStrokeColor(QColor(217, 119, 6, 255))
                sl.setStrokeWidth(0.6)

    # Configure Default Labeling: Ada No / Parsel No inside polygon center with subtle buffer
    with contextlib.suppress(Exception):
        pal = QgsPalLayerSettings()
        pal.fieldName = "concat(\"ada_no\", ' / ', \"parsel_no\")"
        pal.isExpression = True
        pal.centroidInside = True

        if hasattr(QgsPalLayerSettings, "Placement"):
            around_pt = getattr(QgsPalLayerSettings.Placement, "AroundPoint", None)
            horizontal = getattr(QgsPalLayerSettings.Placement, "Horizontal", 0)
            pal.placement = around_pt if around_pt is not None else horizontal

        text_format = QgsTextFormat()
        font = text_format.font()
        font.setPointSize(9)
        font.setBold(True)
        text_format.setFont(font)
        text_format.setColor(QColor(120, 53, 15))  # #78350f rich dark amber

        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(0.7)  # 0.7mm subtle crisp halo
        buffer_settings.setColor(QColor(255, 255, 255, 230))
        text_format.setBuffer(buffer_settings)

        pal.setFormat(text_format)
        labeling = QgsVectorLayerSimpleLabeling(pal)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)

    # Configure sleek Amber MapTip Card in Turkish
    with contextlib.suppress(Exception):
        from .template_engine import Archetype, TemplateConfig, compile_maptip_html

        cfg = TemplateConfig(
            archetype=Archetype.KPI_CARD,
            palette_key="amber",
            card_width=320,
            title_field="ozet",
            subtitle_field="mevkii",
            kpi_field="alan_m2",
            kpi_label="PARSEL ALANI",
            kpi_unit="m²",
            attribute_fields=[
                ("il", "İl"),
                ("ilce", "İlçe"),
                ("mahalle", "Mahalle"),
                ("ada_no", "Ada No"),
                ("parsel_no", "Parsel No"),
                ("nitelik", "Nitelik"),
                ("sorgu_tarihi", "Sorgu Tarihi"),
            ],
            footer_text="TKGM MEGSİS Resmi Kadastro",
            show_action_buttons=True,
            card_action_keys=["google_satellite", "google_streetview", "copy_clipboard", "export_card_report"],
        )
        layer.setMapTipTemplate(compile_maptip_html(cfg))

    # Configure 1-Click Layer Actions
    with contextlib.suppress(Exception):
        from .action_builder import apply_actions_to_layer

        apply_actions_to_layer(layer, ["google_satellite", "google_streetview", "copy_clipboard", "export_card_report"])

    proj.addMapLayer(layer)
    return layer


def add_parcel_feature(
    layer: QgsVectorLayer, parcel_info: dict[str, Any]
) -> tuple[bool, str, Optional[QgsFeature]]:
    """Adds a parsed cadastral parcel feature into the vector layer.

    Returns (is_new: bool, status_message: str, feature: Optional[QgsFeature]).
    """
    key = parcel_info.get("ozet") or f"{parcel_info.get('mahalle')}_{parcel_info.get('ada_no')}_{parcel_info.get('parsel_no')}"

    # Fast indexed / filtered check for existing feature (without fetching geometries)
    safe_key = str(key).replace("'", "''")
    req = (
        QgsFeatureRequest()
        .setFilterExpression(f'"ozet" = \'{safe_key}\'')
        .setFlags(QgsFeatureRequest.Flag.NoGeometry)
        .setLimit(1)
    )
    for ft in layer.getFeatures(req):
        return False, f"Parsel {key} zaten katmanda mevcut.", ft

    geom = parcel_info.get("geometry")
    if geom is None or geom.isEmpty():
        return False, "Geçersiz veya boş parsel geometrisi.", None

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    area_val = parcel_info.get("alan_m2") or 0.0

    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    feat.setAttributes([
        parcel_info.get("il", ""),
        parcel_info.get("ilce", ""),
        parcel_info.get("mahalle", ""),
        parcel_info.get("ada_no", ""),
        parcel_info.get("parsel_no", ""),
        area_val,
        parcel_info.get("nitelik", ""),
        parcel_info.get("mevkii", ""),
        key,
        now_str,
    ])

    layer.dataProvider().addFeatures([feat])
    layer.triggerRepaint()
    return True, f"İndirilen parsel: {key} ({area_val:,.1f} m²)", feat


class InteractiveCadastreTool(QgsMapTool):
    """Canvas click tool that queries TKGM MEGSIS cadastre at clicked coordinates
    and automatically downloads the official parcel polygon into QGIS.
    """

    parcelAcquired = pyqtSignal(dict)

    def __init__(self, canvas: QgsMapCanvas, iface: Optional["QgisInterface"] = None) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self._cursor = create_cadastre_cursor()
        self.setCursor(self._cursor)

    def canvasReleaseEvent(self, event: Any) -> None:
        btn = event.button()
        left_btn = Qt.MouseButton.LeftButton if hasattr(Qt, "MouseButton") else getattr(Qt, "LeftButton", 1)
        if btn != left_btn:
            return

        map_pt = self.toMapCoordinates(event.pos())

        src_crs = self.canvas.mapSettings().destinationCrs()
        wgs_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        tr = QgsCoordinateTransform(src_crs, wgs_crs, QgsProject.instance())

        try:
            pt_wgs = tr.transform(map_pt)
            lat = round(pt_wgs.y(), 6)
            lon = round(pt_wgs.x(), 6)
        except Exception as exc:
            self._notify_user(f"Koordinat dönüşüm hatası: {exc}", is_warning=True)
            return

        if not is_in_turkey_bounds(lat, lon):
            self._notify_user(
                f"TKGM kadastro sorgusu yalnızca Türkiye sınırları için geçerlidir. Tıklanan nokta ({lat:.4f}, {lon:.4f}) sınır dışındadır.",
                is_warning=True,
            )
            return

        self._notify_user(f"TKGM MEGSİS sorgulanıyor ({lat:.5f}, {lon:.5f})...", is_warning=False)
        wait_cursor = Qt.CursorShape.WaitCursor if hasattr(Qt, "CursorShape") else getattr(Qt, "WaitCursor", 3)
        QApplication.setOverrideCursor(wait_cursor)
        try:
            ok, data, err = query_tkgm_megsis(lat, lon)
            if not ok or not data:
                self._notify_user(f"TKGM MEGSİS sorgu hatası: {err}", is_warning=True)
                return

            info = parse_tkgm_response(data)
            if not info or not info.get("geometry"):
                self._notify_user(
                    f"Koordinatta ({lat:.5f}, {lon:.5f}) kadastro parseli bulunamadı. (Bölge kadastro dışı, tescilsiz veya su alanı olabilir).",
                    is_warning=True,
                )
                return

            layer = get_or_create_cadastre_layer(QgsProject.instance())
            is_new, msg, feat = add_parcel_feature(layer, info)

            # Flash feature geometry on map canvas
            if info.get("geometry") and hasattr(self.canvas, "flashGeometries"):
                with contextlib.suppress(Exception):
                    self.canvas.flashGeometries([info["geometry"]], crs=wgs_crs)

            # Select feature in layer
            if feat is not None and feat.id() is not None:
                layer.selectByIds([feat.id()])

            summary = (
                f"🏛️ TKGM: {info.get('il')} / {info.get('ilce')} / {info.get('mahalle')} | "
                f"Ada: {info.get('ada_no')}, Parsel: {info.get('parsel_no')} | "
                f"Alan: {info.get('alan_m2', 0):,.1f} m² | {info.get('nitelik', '')}"
            )
            QApplication.clipboard().setText(summary)
            query_num = get_daily_query_count()
            self._notify_user(f"{msg} [Bugünkü Sorgu: {query_num}] (Bilgiler panoya kopyalandı)", is_warning=False)
            self.parcelAcquired.emit(info)
        finally:
            QApplication.restoreOverrideCursor()

    def _notify_user(self, text: str, is_warning: bool = False) -> None:
        if self.iface and hasattr(self.iface, "messageBar"):
            bar = self.iface.messageBar()
            if is_warning:
                bar.pushWarning("TKGM Kadastro", text)
            else:
                bar.pushInfo("TKGM Kadastro", text)
        elif self.canvas and hasattr(self.canvas, "messageBar"):
            bar = self.canvas.messageBar()
            if is_warning:
                bar.pushWarning("TKGM Kadastro", text)
            else:
                bar.pushInfo("TKGM Kadastro", text)
