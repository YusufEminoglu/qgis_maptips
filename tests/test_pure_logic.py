"""Pure-Python logic and security unit tests for zero2maptips."""
import os
import re
import unittest

from qgis_maptips.core.chart_engine import (
    build_progress_bar_table,
    build_segmented_bar_table,
    build_svg_donut_data_uri,
)
from qgis_maptips.core.template_engine import (
    Archetype,
    TemplateConfig,
    compile_maptip_html,
    compile_raster_hud_html,
)
from qgis_maptips.core.action_builder import (
    AVAILABLE_ACTIONS,
    LAT_EXPR,
    LON_EXPR,
    build_open_file_action,
)


class TestChartEngine(unittest.TestCase):
    def test_progress_bar_table(self):
        html = build_progress_bar_table('"capacity"', '100', bar_color="#10b981")
        self.assertIn('<table width="100%"', html)
        self.assertIn('clamp(0.0, round(100.0 * (coalesce("capacity", 0))', html)
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
        self.assertTrue(img_tag.startswith('<img src="data:image/svg+xml;utf8,<svg'))
        self.assertIn('stroke-dasharray="[% clamp(0.0, round(100.0 * (coalesce("val1", 0))', img_tag)


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
        self.assertIn('[% "score" %] pts', html)
        self.assertIn('Total Area', html)
        self.assertIn('Verified Data', html)

    def test_compile_progress_bar_card(self):
        cfg = TemplateConfig(
            archetype=Archetype.PROGRESS_BAR,
            title_field="id",
            kpi_field="pct",
            progress_max_expr="100",
        )
        html = compile_maptip_html(cfg)
        self.assertIn('clamp(0.0', html)

    def test_compile_raster_hud(self):
        hud_html = compile_raster_hud_html(palette_key="slate", band_count=3)
        self.assertIn("Raster Cell Inspector", hud_html)
        self.assertIn("Band 1", hud_html)
        self.assertIn("Band 3", hud_html)
        self.assertIn("{band_1_val}", hud_html)


class TestActionBuilder(unittest.TestCase):
    def test_available_actions(self):
        self.assertGreaterEqual(len(AVAILABLE_ACTIONS), 5)
        keys = {act["key"] for act in AVAILABLE_ACTIONS}
        self.assertIn("google_satellite", keys)
        self.assertIn("google_streetview", keys)
        self.assertIn("copy_clipboard", keys)

    def test_wgs84_expression(self):
        self.assertIn("@layer_crs", LAT_EXPR)
        self.assertIn("point_on_surface", LAT_EXPR)
        self.assertIn("@layer_crs", LON_EXPR)
        self.assertIn("point_on_surface", LON_EXPR)

    def test_open_file_action(self):
        act = build_open_file_action("photo_url")
        self.assertEqual(act["command"], '[% "photo_url" %]')


class TestQt6EnumSafety(unittest.TestCase):
    """Ensure no bare Qt.* unscoped members exist in the plugin source."""

    FORBIDDEN_BARE_PATTERNS = [
        re.compile(r"\bQt\.(LeftButton|RightButton|MiddleButton)\b"),
        re.compile(r"\bQt\.(Key_\w+)\b"),
        re.compile(r"\bQt\.(SolidLine|DashLine|NoPen)\b"),
        re.compile(r"\bQt\.(SolidPattern|NoBrush)\b"),
        re.compile(r"\bQt\.(WA_TransparentForMouseEvents|WA_DeleteOnClose)\b"),
        re.compile(r"\bQt\.(WindowStaysOnTopHint|ToolTip)\b"),
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
