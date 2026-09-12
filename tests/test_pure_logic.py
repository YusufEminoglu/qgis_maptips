"""Pure-Python logic and security unit tests for qgis_maptips."""
import os
import re
import tempfile
import unittest

from qgis_maptips.core.chart_engine import (
    build_progress_bar_table,
    build_segmented_bar_table,
    build_svg_donut_data_uri,
    build_svg_media_placeholder,
    build_svg_sparkline,
)
from qgis_maptips.core.template_engine import (
    Archetype,
    TemplateConfig,
    build_card_action_buttons_row,
    build_conditional_badge_html,
    build_relational_metric_row,
    build_safe_attribute_expr,
    compile_maptip_html,
    compile_raster_hud_html,
)
from qgis_maptips.core.action_builder import (
    AVAILABLE_ACTIONS,
    LAT_EXPR,
    LON_EXPR,
    build_custom_url_action,
    build_open_file_action,
    build_select_intersecting_action,
    get_layer_actions,
    remove_all_actions,
)
from qgis_maptips.core.cadastre_tool import (
    CADASTRE_LAYER_NAME,
    CADASTRE_LAYER_URI,
    get_daily_query_count,
    is_in_turkey_bounds,
    parse_tkgm_response,
    record_tkgm_query,
)


class TestChartEngine(unittest.TestCase):
    def test_progress_bar_table(self):
        html = build_progress_bar_table('"capacity"', '100', bar_color="#10b981")
        self.assertIn('<table width="100%"', html)
        self.assertIn('clamp(0.0, round(100.0 * (coalesce(try(to_real("capacity"), 0.0)', html)
        self.assertIn('bgcolor="#10b981"', html)

    def test_segmented_bar_table(self):
        segments = [('"a"', "Category A", "#ef4444"), ('"b"', "Category B", "#3b82f6")]
        html = build_segmented_bar_table(segments)
        self.assertIn("Category A", html)
        self.assertIn("Category B", html)
        self.assertIn('bgcolor="#ef4444"', html)
        self.assertIn('bgcolor="#3b82f6"', html)

    def test_svg_donut_data_uri(self):
        slices = [('"val1"', "Slice 1", "#10b981"), ('"val2"', "Slice 2", "#3b82f6")]
        img_tag = build_svg_donut_data_uri(slices, size=80)
        self.assertTrue(img_tag.startswith("<img src='data:image/svg+xml;utf8,<svg"))
        self.assertIn("stroke-dasharray", img_tag)
        self.assertIn("%2310b981", img_tag)
        self.assertIn("coalesce", img_tag)

    def test_svg_donut_empty(self):
        self.assertEqual(build_svg_donut_data_uri([]), "")

    def test_svg_sparkline(self):
        fields = ["pop_2020", "pop_2021", "pop_2022", "pop_2024"]
        spark_tag = build_svg_sparkline(fields, width=140, height=28)
        self.assertTrue(spark_tag.startswith("<img src='data:image/svg+xml;utf8,<svg"))
        self.assertIn("max(0.001", spark_tag)
        self.assertIn("pop_2020", spark_tag)

    def test_svg_media_placeholder(self):
        uri = build_svg_media_placeholder(width=280, height=120)
        self.assertTrue(uri.startswith("data:image/svg+xml;utf8,<svg"))
        self.assertIn("No Photo Available", uri)


class TestTemplateEngine(unittest.TestCase):
    def test_compile_kpi_card(self):
        cfg = TemplateConfig(
            archetype=Archetype.KPI_CARD,
            palette_key="emerald",
            card_width=320,
            title_field="name",
            subtitle_field="category",
            kpi_field="score",
            kpi_label="Quality Score",
            kpi_unit="pts",
            attribute_fields=[("area", "Total Area"), ("status", "Current Status")],
            footer_text="Verified Data",
        )
        html = compile_maptip_html(cfg)
        self.assertIn('width="320"', html)
        self.assertIn('[% "name" %]', html)
        self.assertIn('[% "category" %]', html)
        self.assertIn('"score"', html)
        self.assertIn('pts', html)
        self.assertIn('Total Area', html)
        self.assertIn('Verified Data', html)

    def test_safe_attribute_expr(self):
        expr = build_safe_attribute_expr("area", format_numbers=True, decimal_places=2, null_text="—")
        self.assertIn('"area" IS NULL', expr)
        self.assertIn("with_variable('v'", expr)
        self.assertIn('format_number(@v, 0)', expr)
        self.assertIn('format_number(@v, 2)', expr)
        self.assertIn("'—'", expr)

        raw_expr = build_safe_attribute_expr("notes", format_numbers=False, null_text="N/A")
        self.assertEqual(raw_expr, "coalesce(nullif(to_string(\"notes\"), ''), 'N/A')")

    def test_media_card_fallbacks(self):
        cfg_ph = TemplateConfig(archetype=Archetype.MEDIA_CARD, media_field="photo_url", media_fallback="placeholder")
        html_ph = compile_maptip_html(cfg_ph)
        self.assertIn("No Photo Available", html_ph)

        cfg_hide = TemplateConfig(archetype=Archetype.MEDIA_CARD, media_field="photo_url", media_fallback="hide")
        html_hide = compile_maptip_html(cfg_hide)
        self.assertIn("length(trim(coalesce(to_string(\"photo_url\"), '')))", html_hide)

    def test_compile_progress_bar_card(self):
        cfg = TemplateConfig(
            archetype=Archetype.PROGRESS_BAR,
            title_field="id",
            kpi_field="pct",
            progress_max_expr="100",
        )
        html = compile_maptip_html(cfg)
        self.assertIn('clamp(0.0', html)

    def test_compile_donut_card(self):
        cfg = TemplateConfig(
            archetype=Archetype.DONUT_CHART,
            title_field="district",
            donut_fields=[("res", "Residential", "#3b82f6"), ("com", "Commercial", "#10b981")],
        )
        html = compile_maptip_html(cfg)
        self.assertIn('data:image/svg+xml;utf8,<svg', html)
        self.assertIn('"res"', html)
        self.assertIn('"com"', html)
        self.assertIn('Residential', html)
        self.assertIn('Commercial', html)

    def test_conditional_badge(self):
        rule = {
            "field": "risk_level",
            "op": ">=",
            "val": "70",
            "color_true": "#ef4444",
            "color_false": "#10b981",
            "label_true": "High Risk",
            "label_false": "Safe",
        }
        badge_html = build_conditional_badge_html(rule)
        self.assertIn('CASE WHEN ("risk_level" >= 70) THEN \'#ef4444\' ELSE \'#10b981\' END', badge_html)
        self.assertIn('High Risk', badge_html)

    def test_relational_metric_row(self):
        metric = {
            "target_layer": "buildings",
            "op": "intersects",
            "aggregate": "count",
            "field": "id",
            "label": "Building Count",
        }
        row_html = build_relational_metric_row(metric, {"text_secondary": "#64748b", "accent": "#10b981", "border": "#ccc"}, "#fff")
        self.assertIn("array_length(overlay_intersects('buildings'))", row_html)
        self.assertIn("Building Count", row_html)

    def test_preset_serialization_roundtrip(self):
        cfg = TemplateConfig(
            archetype=Archetype.SPARKLINE,
            palette_key="purple",
            card_width=350,
            sparkline_fields=["y1", "y2", "y3"],
            conditional_rules=[{"field": "v", "op": ">", "val": "10"}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "preset.json")
            cfg.save_json(fpath)
            loaded = TemplateConfig.load_json(fpath)
            self.assertEqual(loaded.archetype, Archetype.SPARKLINE)
            self.assertEqual(loaded.palette_key, "purple")
            self.assertEqual(loaded.card_width, 350)
            self.assertEqual(loaded.sparkline_fields, ["y1", "y2", "y3"])

    def test_compile_raster_hud(self):
        hud_html = compile_raster_hud_html(palette_key="slate", band_count=3)
        self.assertIn("Raster Cell Inspector", hud_html)
        self.assertIn("Band 1", hud_html)
        self.assertIn("Band 3", hud_html)
        self.assertIn("{band_1_val}", hud_html)

    def test_card_width_custom_and_clamping(self):
        cfg = TemplateConfig(card_width=450)
        html = compile_maptip_html(cfg)
        self.assertIn('width="450"', html)
        self.assertIn('style="width:450px; min-width:450px; max-width:450px;', html)

        # Clamped below minimum (180)
        cfg_min = TemplateConfig(card_width=100)
        html_min = compile_maptip_html(cfg_min)
        self.assertIn('width="180"', html_min)
        self.assertIn('style="width:180px; min-width:180px; max-width:180px;', html_min)

        # Clamped above maximum (800)
        cfg_max = TemplateConfig(card_width=1200)
        html_max = compile_maptip_html(cfg_max)
        self.assertIn('width="800"', html_max)
        self.assertIn('style="width:800px; min-width:800px; max-width:800px;', html_max)

    def test_card_action_buttons_row(self):
        row_html = build_card_action_buttons_row(["google_satellite", "google_streetview", "copy_clipboard"], {
            "sub_bg": "#115e59", "sub_text": "#ccfbf1", "row_alt": "#f8fafc", "border": "#e2e8f0", "text_secondary": "#64748b"
        })
        self.assertIn("Quick Actions", row_html)
        self.assertIn("Google Sat", row_html)
        self.assertIn("Street View", row_html)
        self.assertIn("action:copy_clipboard", row_html)
        self.assertIn("https://www.google.com/maps", row_html)


class TestActionBuilder(unittest.TestCase):
    def test_available_actions(self):
        self.assertGreaterEqual(len(AVAILABLE_ACTIONS), 6)
        keys = {act["key"] for act in AVAILABLE_ACTIONS}
        self.assertIn("google_satellite", keys)
        self.assertIn("google_streetview", keys)
        self.assertIn("copy_clipboard", keys)
        self.assertIn("export_card_report", keys)

    def test_wgs84_expression(self):
        self.assertIn("@layer_crs", LAT_EXPR)
        self.assertIn("point_on_surface", LAT_EXPR)
        self.assertIn("@layer_crs", LON_EXPR)
        self.assertIn("point_on_surface", LON_EXPR)

    def test_open_file_action(self):
        act = build_open_file_action("photo_url")
        self.assertEqual(act["command"], '[% "photo_url" %]')

    def test_select_intersecting_action(self):
        act = build_select_intersecting_action("Parcels")
        self.assertIn("mapLayersByName('Parcels')", act["command"])
        self.assertIn("f.geometry().intersects(geom)", act["command"])
        self.assertIn("QgsCoordinateTransform", act["command"])

    def test_custom_url_action(self):
        act = build_custom_url_action("ERP Portal", "https://erp.corp/item/[% \"id\" %]")
        self.assertEqual(act["command"], "https://erp.corp/item/[% \"id\" %]")

    def test_tkgm_action(self):
        actions_map = {act["key"]: act for act in AVAILABLE_ACTIONS}
        self.assertIn("tkgm_cadastre", actions_map)

        act = actions_map["tkgm_cadastre"]
        self.assertIn("Parsel Sorgu", act["name"])
        self.assertIn("(Turkey Only)", act["description"])
        self.assertEqual(act["type"], "OpenUrl")
        self.assertIn("https://parselsorgu.tkgm.gov.tr/#ara/cografi/", act["command"])

        # Card buttons ribbon row
        row_html_tkgm = build_card_action_buttons_row(["tkgm_cadastre"], {
            "sub_bg": "#115e59", "sub_text": "#ccfbf1", "row_alt": "#f8fafc", "border": "#e2e8f0", "text_secondary": "#64748b"
        })
        self.assertIn("Parsel Sorgu", row_html_tkgm)
        self.assertIn("https://parselsorgu.tkgm.gov.tr/#ara/cografi/", row_html_tkgm)

    def test_zoom_and_buffer_actions(self):
        actions_map = {act["key"]: act for act in AVAILABLE_ACTIONS}
        self.assertIn("zoom_feature", actions_map)
        self.assertIn("buffer_feature", actions_map)

        zoom_act = actions_map["zoom_feature"]
        self.assertIn("is_geo", zoom_act["command"])
        self.assertIn("canvas.refresh()", zoom_act["command"])

        buf_act = actions_map["buffer_feature"]
        self.assertIn("Feature Buffers (Temp)", buf_act["command"])
        self.assertIn("insertLayer", buf_act["command"])


    def test_card_action_buttons_row_wrapping(self):
        # When 6 buttons are given, they should wrap into rows of max 3 (i.e. at least 2 <tr> rows)
        all_keys = ["google_satellite", "google_streetview", "yandex_maps", "tkgm_cadastre", "copy_clipboard", "export_card_report"]
        row_html = build_card_action_buttons_row(all_keys, {
            "sub_bg": "#115e59", "sub_text": "#ccfbf1", "row_alt": "#f8fafc", "border": "#e2e8f0", "text_secondary": "#64748b"
        }, card_width=320)
        self.assertGreaterEqual(row_html.count("<tr>"), 2)


class TestCadastreTool(unittest.TestCase):
    """Tests for the interactive TKGM MEGSIS cadastre query and parsing logic."""

    def test_is_in_turkey_bounds(self):
        # Within Turkey
        self.assertTrue(is_in_turkey_bounds(39.93, 32.85))   # Ankara
        self.assertTrue(is_in_turkey_bounds(41.01, 28.97))   # Istanbul
        self.assertTrue(is_in_turkey_bounds(38.42, 27.14))   # Izmir
        self.assertTrue(is_in_turkey_bounds(36.88, 30.70))   # Antalya
        self.assertTrue(is_in_turkey_bounds(39.75, 43.05))   # Agri

        # Outside Turkey
        self.assertFalse(is_in_turkey_bounds(51.5074, -0.1278)) # London
        self.assertFalse(is_in_turkey_bounds(48.8566, 2.3522))  # Paris
        self.assertFalse(is_in_turkey_bounds(40.7128, -74.0060))# New York
        self.assertFalse(is_in_turkey_bounds(35.6762, 139.6503))# Tokyo
        self.assertFalse(is_in_turkey_bounds(0.0, 0.0))         # Null Island

    def test_parse_tkgm_response_polygon(self):
        mock_data = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [27.174361, 39.11051],
                        [27.174500, 39.11055],
                        [27.174480, 39.11020],
                        [27.174300, 39.11025],
                        [27.174361, 39.11051],
                    ]
                ],
            },
            "properties": {
                "ilAd": "İZMİR",
                "ilceAd": "BERGAMA",
                "mahalleAd": "ERTUĞRUL",
                "adaNo": "123",
                "parselNo": "4",
                "alan": "542,18",
                "nitelik": "Kargir Ev ve Bahçesi",
                "mevkii": "Köyiçi",
                "ozet": "İzmir, Bergama, Ertuğrul, 123 Ada, 4 Parsel",
            },
        }
        res = parse_tkgm_response(mock_data)
        self.assertIsNotNone(res)
        self.assertEqual(res["il"], "İZMİR")
        self.assertEqual(res["ilce"], "BERGAMA")
        self.assertEqual(res["mahalle"], "ERTUĞRUL")
        self.assertEqual(res["ada_no"], "123")
        self.assertEqual(res["parsel_no"], "4")
        self.assertAlmostEqual(res["alan_m2"], 542.18, places=2)
        self.assertEqual(res["nitelik"], "Kargir Ev ve Bahçesi")
        self.assertEqual(res["mevkii"], "Köyiçi")
        self.assertEqual(res["ozet"], "İZMİR-BERGAMA-ERTUĞRUL-123/4")
        self.assertIsNotNone(res["geometry"])

    def test_parse_tkgm_response_multipolygon(self):
        mock_data = {
            "type": "Feature",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [27.1, 39.1],
                            [27.2, 39.1],
                            [27.2, 39.2],
                            [27.1, 39.1],
                        ]
                    ]
                ],
            },
            "properties": {
                "ilAd": "ANKARA",
                "ilceAd": "ÇANKAYA",
                "mahalleAd": "KAVAKLIDERE",
                "adaNo": "500",
                "parselNo": "12",
                "alan": "1250.50",
                "nitelik": "Arsa",
                "mevkii": "Tunalı",
            },
        }
        res = parse_tkgm_response(mock_data)
        self.assertIsNotNone(res)
        self.assertEqual(res["il"], "ANKARA")
        self.assertEqual(res["ada_no"], "500")
        self.assertEqual(res["parsel_no"], "12")
        self.assertAlmostEqual(res["alan_m2"], 1250.50, places=2)
        self.assertIsNotNone(res["geometry"])

    def test_parse_tkgm_empty_or_invalid(self):
        self.assertIsNone(parse_tkgm_response({}))
        self.assertIsNone(parse_tkgm_response(None))
        self.assertIsNone(parse_tkgm_response({"features": []}))
        self.assertIsNone(parse_tkgm_response({"geometry": None}))

    def test_cadastre_layer_schema(self):
        self.assertEqual(CADASTRE_LAYER_NAME, "TKGM Parselleri (TR)")
        for field in ("il", "ilce", "mahalle", "ada_no", "parsel_no", "alan_m2", "nitelik", "mevkii", "ozet", "sorgu_tarihi"):
            self.assertIn(f"field={field}:", CADASTRE_LAYER_URI)

    def test_daily_query_counter(self):
        c1 = record_tkgm_query()
        self.assertGreaterEqual(c1, 1)
        self.assertEqual(get_daily_query_count(), c1)


class TestQt6EnumSafety(unittest.TestCase):
    """Ensure no bare Qt.* unscoped members exist in the plugin source."""

    FORBIDDEN_BARE_PATTERNS = [
        re.compile(r"\bQt\.(LeftButton|RightButton|MiddleButton)\b"),
        re.compile(r"\bQt\.(Key_\w+)\b"),
        re.compile(r"\bQt\.(SolidLine|DashLine|NoPen)\b"),
        re.compile(r"\bQt\.(SolidPattern|NoBrush)\b"),
        re.compile(r"\bQt\.(WA_TransparentForMouseEvents|WA_DeleteOnClose)\b"),
        re.compile(r"\bQt\.(WindowStaysOnTopHint|ToolTip)\b"),
        re.compile(r"\bQt\.(PointingHandCursor)\b"),
    ]

    def test_no_unscoped_qt_enums(self):
        pkg_root = os.path.dirname(os.path.dirname(__file__))
        violations = []
        for root, _, files in os.walk(pkg_root):
            if "tests" in root or "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path, "r", encoding="utf-8") as py_file:
                        content = py_file.read()
                        for pat in self.FORBIDDEN_BARE_PATTERNS:
                            m = pat.search(content)
                            if m:
                                violations.append(f"{f}: {m.group(0)}")
        self.assertEqual(violations, [], f"Forbidden bare Qt enums found: {violations}")


if __name__ == "__main__":
    unittest.main()
