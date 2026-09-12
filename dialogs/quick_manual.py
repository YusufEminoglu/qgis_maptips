"""Compact built-in Quick Manual dialog for Qgis Advanced Map Tips&Actions.

Provides a fast, step-by-step visual walkthrough of all core capabilities
directly inside QGIS, with 1-click links to the comprehensive online guide
on geophilo.com and the official QGIS Plugin Hub rating page.
"""
from __future__ import annotations

import webbrowser
from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class QuickManualDialog(QDialog):
    """Modern, compact built-in user guide dialog."""

    WEB_MANUAL_URL = "https://geophilo.com/qgis_maptips/"
    QGIS_HUB_URL = "https://plugins.qgis.org/plugins/qgis_maptips/"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Qgis Advanced Map Tips & Actions — Quick Guide")
        self.resize(680, 540)
        self.setMinimumSize(540, 420)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. Header Banner
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        mark = QLabel("MT")
        mark.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f766e, stop:1 #0d9488); "
            "color: #ffffff; font-weight: 800; font-size: 13pt; border-radius: 6px; padding: 4px 8px;"
        )
        align_center = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignCenter", 0)
        mark.setAlignment(align_center)
        header_layout.addWidget(mark)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_eyebrow = QLabel("GEOPHILO APPLIED SPATIAL LABS")
        lbl_eyebrow.setStyleSheet("font-size: 7.5pt; font-weight: bold; color: #0d9488; letter-spacing: 0.5px;")
        lbl_title = QLabel("MapTips Studio — Quick User Guide")
        lbl_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #0f172a;")
        title_box.addWidget(lbl_eyebrow)
        title_box.addWidget(lbl_title)
        header_layout.addLayout(title_box, 1)

        self.btn_web_guide_top = QPushButton("🌐 Full Web Guide")
        self.btn_web_guide_top.setToolTip("Open full illustrated reference manual on geophilo.com")
        self.btn_web_guide_top.setStyleSheet(
            "QPushButton { background: #0f766e; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 5px 12px; font-size: 8.5pt; }"
            "QPushButton:hover { background: #115e59; }"
        )
        cursor_hand = getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor", None)
        if cursor_hand is not None:
            self.btn_web_guide_top.setCursor(cursor_hand)
        self.btn_web_guide_top.clicked.connect(self._open_web_guide)
        header_layout.addWidget(self.btn_web_guide_top)

        layout.addWidget(header)

        # 2. Tabbed Walkthrough Stages
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        tabs.addTab(self._create_stage_tab(
            "🚀 Quick Start (1-Click)",
            [
                ("Step 1: Select Active Layer", "Pick any vector layer in your QGIS project from the top dropdown."),
                ("Step 2: Pick a Quick Preset Chip", "Click one of the 4 instant chips: <b>🏢 KPI</b>, <b>⚡ Bar</b>, <b>🍩 Donut</b>, or <b>📈 Trend</b> to populate proven visual templates."),
                ("Step 3: Click 'Apply MapTip to Layer'", "Click the primary green button at the bottom. The HTML expression is written directly to the layer style."),
                ("Step 4: Hover Over Map Features", "Ensure the MapTips icon on the QGIS canvas toolbar (or the dock's iOS switch) is ON. Hover over any feature on the canvas to see your interactive card!"),
            ],
            "💡 <b>Tip:</b> MapTips are saved inside layer properties and project files. Anyone opening your project will see the styled cards even without this plugin installed!"
        ), "1. Quick Start")

        tabs.addTab(self._create_stage_tab(
            "🎨 Card Design & Styling",
            [
                ("Universal Archetypes", "Choose between <b>KPI Card</b> (big numbers + units), <b>Progress Bar</b> (target comparison), <b>Donut Chart</b> (multi-attribute shares), <b>Sparkline Trend</b> (temporal bars), or <b>Media Card</b> (photo viewers)."),
                ("Color Palettes", "6 publication-ready palettes: <b>Emerald Studio</b>, <b>Classic Blue</b>, <b>Dark Slate</b>, <b>Crimson Alert</b>, <b>Modern Purple</b>, and <b>Cadastral Amber</b>."),
                ("Automatic Number Formatting", "Numbers are automatically formatted with thousands separators (e.g. <code>1,250,000</code>) and customizable decimal precision. Missing values show clean dashes (<code>—</code>) instead of blank errors."),
                ("Conditional Status Badges", "Under Advanced Options, define threshold rules (e.g. <code>Risk >= 70</code>) to render dynamic Red/Green alert pills directly inside cards."),
                ("Cross-Layer Relational Metrics", "Count spatial intersections (e.g. buildings inside parcel) or fetch nearest neighbor attributes without running GIS spatial joins!"),
            ],
            "💡 <b>Tip:</b> Use the <b>Sample Feature Navigator</b> (<code>◀ Prev</code> / <code>Next ▶</code> / <code>🔀 Cycle</code>) to preview live data from real features without leaving the designer!"
        ), "2. Card Design")

        tabs.addTab(self._create_stage_tab(
            "⚡ 1-Click Action Hub",
            [
                ("Web Navigation Actions", "1-click injection of dynamic CRS-aware actions: <b>Google Maps (Satellite)</b>, <b>Google Street View</b>, <b>OpenStreetMap</b>, <b>Yandex Maps</b>, and <b>TKGM Parsel Sorgu (Web)</b>."),
                ("Point-on-Surface Math", "Coordinates are calculated using surface centroids and transformed to EPSG:4326 on the fly, guaranteeing valid pin drops for irregular polygons."),
                ("Desktop Tools & Spatial Ops", "Inject <b>Copy Attributes to Clipboard</b>, <b>Export HTML Report</b>, <b>Zoom to Feature (Adaptive CRS Padding)</b>, or <b>Buffer Feature (50m Temp Layer)</b>."),
                ("Cross-Layer Spatial Selectors", "Select all features in a target layer (e.g. parcels, trees, pipes) that spatially intersect the clicked polygon."),
                ("3 Execution Scenarios", "Trigger actions directly from <b>MapTip card pills</b>, from canvas click using the yellow gear <b>Canvas Action Tool</b>, or right-clicking in <b>Attribute Tables</b>."),
            ],
            "💡 <b>Tip:</b> Layer actions write directly into QGIS's native <code>QgsActionManager</code>, preserving full portability across users and workspaces."
        ), "3. Actions Hub")

        tabs.addTab(self._create_stage_tab(
            "🇹🇷 Instant Canvas Cadastre (TKGM)",
            [
                ("1-Click Canvas Cadastre Tool", "Under Actions Hub, click <b>⚡ Click Canvas to Download</b>. An amber crosshair cursor activates on the map canvas to download real parcel polygons into QGIS."),
                ("Anywhere Canvas Query", "Click anywhere in Turkey without needing a selected layer or satellite provider. The tool queries the official TKGM MEGSİS API at the clicked coordinate."),
                ("Automatic Polygon Vector Layer", "Parses official coordinates and adds the parcel boundary into the <code>TKGM Parselleri (TR)</code> memory layer."),
                ("Centroid-Inside Labeling", "New parcels automatically receive crisp <code>ada_no / parsel_no</code> labels placed inside the polygon with subtle text buffers."),
                ("1-Click Web Portal Navigation", "Click the <b>Parsel Sorgu</b> action button in MapTip cards to open the exact parcel location directly in the official TKGM Parsel Sorgu web portal in your browser."),
            ],
            "💡 <b>Tip:</b> You can both download raw parcel polygons to the canvas via the 1-click tool, and open official cadastral records in the browser via MapTip action buttons."
        ), "4. TKGM Cadastre")

        tabs.addTab(self._create_stage_tab(
            "🎯 Live Canvas Hover HUD",
            [
                ("Non-Blocking Pixel Inspection", "Inspect elevation, slope, NDVI, RGB values, or bathymetry simply by hovering the mouse over the canvas."),
                ("Configurable Dwell Debouncing", "Debounced at 250 ms by default to eliminate lag and prevent main-thread UI stutter on heavy GeoTIFF / VRT rasters."),
                ("Precision Reticle Cursor", "Replaces the default arrow with a high-contrast inspection reticle and target locator badge."),
                ("📌 Pin / Freeze Stationary", "Press <b>Shift + Click</b> anywhere on the canvas to freeze the current tooltip stationary so you can examine the numbers or copy them."),
                ("Composite Multi-Layer Mode", "Inspect all visible rasters plus the top vector polygon simultaneously in a single cohesive card feed."),
            ],
            "💡 <b>Tip:</b> Sampled values also stream permanently into the dock's <b>Live Sampled Values Feed</b>, remaining readable even after moving the mouse outside QGIS."
        ), "5. Live HUD")

        layout.addWidget(tabs, 1)

        # 3. Footer Bar: Rating, Full Guide & Close
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        self.btn_rate = QPushButton("⭐ Rate Plugin on QGIS Hub")
        self.btn_rate.setToolTip("Leave a 5-star review on the official QGIS Plugin Hub")
        self.btn_rate.setStyleSheet(
            "QPushButton { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; font-weight: bold; border-radius: 4px; padding: 5px 12px; font-size: 8.5pt; }"
            "QPushButton:hover { background: #fde68a; color: #78350f; }"
        )
        if cursor_hand is not None:
            self.btn_rate.setCursor(cursor_hand)
        self.btn_rate.clicked.connect(self._open_qgis_hub_rating)
        footer_layout.addWidget(self.btn_rate)

        footer_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setStyleSheet(
            "QPushButton { background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px 16px; font-size: 8.5pt; }"
            "QPushButton:hover { background: #e2e8f0; }"
        )
        self.btn_close.clicked.connect(self.accept)
        footer_layout.addWidget(self.btn_close)

        layout.addWidget(footer)

    def _create_stage_tab(
        self,
        title: str,
        steps: list[tuple[str, str]],
        tip: str = "",
    ) -> QWidget:
        """Create a styled scrollable stage page."""
        page = QWidget()
        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        p_layout = QVBoxLayout(content)
        p_layout.setContentsMargins(10, 10, 10, 10)
        p_layout.setSpacing(8)

        header_lbl = QLabel(title)
        header_lbl.setStyleSheet("font-size: 10.5pt; font-weight: bold; color: #0f766e; margin-bottom: 2px;")
        p_layout.addWidget(header_lbl)

        for step_title, step_desc in steps:
            card = QWidget()
            card.setStyleSheet(
                "QWidget { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 5px; padding: 6px; }"
            )
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(6, 4, 6, 4)
            c_layout.setSpacing(2)

            st_lbl = QLabel(f"<b>{step_title}</b>")
            st_lbl.setStyleSheet("font-size: 8.5pt; color: #1e293b;")
            sd_lbl = QLabel(step_desc)
            sd_lbl.setWordWrap(True)
            sd_lbl.setStyleSheet("font-size: 8pt; color: #475569; line-height: 1.4;")

            c_layout.addWidget(st_lbl)
            c_layout.addWidget(sd_lbl)
            p_layout.addWidget(card)

        if tip:
            tip_box = QLabel(tip)
            tip_box.setWordWrap(True)
            tip_box.setStyleSheet(
                "background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 5px; "
                "padding: 6px 10px; color: #166534; font-size: 8pt;"
            )
            p_layout.addWidget(tip_box)

        p_layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    def _open_web_guide(self) -> None:
        webbrowser.open(self.WEB_MANUAL_URL)

    def _open_qgis_hub_rating(self) -> None:
        webbrowser.open(self.QGIS_HUB_URL)
