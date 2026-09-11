"""Main dock panel for Qgis Advanced Map Tips&Actions."""
from __future__ import annotations

import contextlib
import html
import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from ..core.action_builder import AVAILABLE_ACTIONS, apply_actions_to_layer
from ..core.raster_hud import CanvasHoverHUD
from ..core.template_engine import (
    PALETTES,
    Archetype,
    TemplateConfig,
    compile_maptip_html,
)
from .theme import apply_adaptive_theme

if TYPE_CHECKING:
    from qgis.gui import QgisInterface


class QgisMapTipsDock(QDockWidget):
    """Dockable studio for designing MapTips and managing layer actions."""

    def __init__(self, iface: "QgisInterface", parent: Optional[QWidget] = None) -> None:
        super().__init__("Qgis Advanced Map Tips&Actions", parent or iface.mainWindow())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.setObjectName("QgisMapTipsDock")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self._hud = CanvasHoverHUD(self.canvas, debounce_ms=250, parent=self)
        self._current_layer: Optional[QgsMapLayer] = None

        self._init_ui()
        apply_adaptive_theme(self)

        # Sync and connect native MapTips action
        self._sync_maptip_action_state()
        if hasattr(self.iface, "actionMapTips") and self.iface.actionMapTips():
            with contextlib.suppress(Exception):
                self.iface.actionMapTips().toggled.connect(self._sync_maptip_action_state)

        # Connect layer signals
        QgsProject.instance().layersAdded.connect(self._refresh_layers)
        QgsProject.instance().layersRemoved.connect(self._refresh_layers)
        self.iface.currentLayerChanged.connect(self._on_qgis_active_layer_changed)

        self._refresh_layers()

    def _init_ui(self) -> None:
        root = QWidget()
        root.setObjectName("maptipsRoot")
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Hero Header Panel
        hero = QFrame()
        hero.setObjectName("heroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(6, 6, 6, 6)
        hero_layout.setSpacing(4)

        top_row = QHBoxLayout()
        title = QLabel("Qgis Advanced Map Tips&Actions")
        title.setObjectName("heroTitle")

        self.toggle_maptips_btn = QPushButton("💡 MapTips: --")
        self.toggle_maptips_btn.setCheckable(True)
        self.toggle_maptips_btn.setToolTip("Quickly toggle QGIS Canvas MapTips visibility on or off")
        self.toggle_maptips_btn.setStyleSheet(
            "font-size: 8pt; font-weight: bold; background-color: #64748b; color: white; border-radius: 4px; padding: 2px 8px;"
        )
        self.toggle_maptips_btn.clicked.connect(self._toggle_canvas_maptips)

        badge = QLabel("PRO")
        badge.setObjectName("heroBadge")
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.toggle_maptips_btn)
        top_row.addWidget(badge)
        hero_layout.addLayout(top_row)

        layer_row = QHBoxLayout()
        layer_lbl = QLabel("Target Layer:")
        layer_lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._on_target_layer_selected)
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Refresh layer list")
        self.refresh_btn.setFixedWidth(28)
        self.refresh_btn.clicked.connect(self._refresh_layers)

        layer_row.addWidget(layer_lbl)
        layer_row.addWidget(self.layer_combo, 1)
        layer_row.addWidget(self.refresh_btn)
        hero_layout.addLayout(layer_row)

        self.layer_info_label = QLabel("Select a layer to start")
        self.layer_info_label.setStyleSheet("font-size: 8pt; color: #64748b;")
        hero_layout.addWidget(self.layer_info_label)

        main_layout.addWidget(hero)

        # 2. Main Tabbed Workspace
        self.tabs = QTabWidget()

        # Tab 1: MapTip Designer
        tab_designer = QWidget()
        self._build_designer_tab(tab_designer)
        self.tabs.addTab(tab_designer, "MapTip Designer")

        # Tab 2: Actions Hub
        tab_actions = QWidget()
        self._build_actions_tab(tab_actions)
        self.tabs.addTab(tab_actions, "Actions Hub")

        # Tab 3: Canvas Hover HUD
        tab_hud = QWidget()
        self._build_hud_tab(tab_hud)
        self.tabs.addTab(tab_hud, "Live Canvas HUD")

        main_layout.addWidget(self.tabs, 1)

        self.setWidget(root)

    def _build_designer_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(6)

        # Preset Toolbar
        preset_box = QHBoxLayout()
        preset_lbl = QLabel("Template Preset:")
        preset_lbl.setStyleSheet("font-size:8.5pt; font-weight:bold;")
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("(Current / Custom)")
        self.preset_combo.addItem("Real Estate Investment", "kpi_real_estate.json")
        self.preset_combo.addItem("Capacity & Occupancy Bar", "progress_capacity.json")
        self.preset_combo.addItem("Land Use Donut Shares", "donut_shares.json")
        self.preset_combo.addItem("Temporal Sparkline Timeline", "sparkline_timeline.json")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QPushButton("Save...")
        self.btn_save_preset.setToolTip("Save current card configuration as JSON preset")
        self.btn_save_preset.clicked.connect(self._save_preset)
        self.btn_load_preset = QPushButton("Load...")
        self.btn_load_preset.setToolTip("Load custom preset from JSON file")
        self.btn_load_preset.clicked.connect(self._load_preset)

        preset_box.addWidget(preset_lbl)
        preset_box.addWidget(self.preset_combo, 1)
        preset_box.addWidget(self.btn_save_preset)
        preset_box.addWidget(self.btn_load_preset)
        scroll_layout.addLayout(preset_box)

        # Style & Layout Group
        grp_style = QGroupBox("Layout & Color Palette")
        form_style = QFormLayout(grp_style)

        self.archetype_combo = QComboBox()
        self.archetype_combo.addItem("Modern KPI Card", Archetype.KPI_CARD)
        self.archetype_combo.addItem("Comparison Progress Bar", Archetype.PROGRESS_BAR)
        self.archetype_combo.addItem("Multi-Metric Donut Chart", Archetype.DONUT_CHART)
        self.archetype_combo.addItem("SVG Sparkline Trend", Archetype.SPARKLINE)
        self.archetype_combo.addItem("Media / Photo Card", Archetype.MEDIA_CARD)
        self.archetype_combo.addItem("Clean Attribute Grid", Archetype.CLEAN_TABLE)
        self.archetype_combo.currentIndexChanged.connect(self._update_preview)
        form_style.addRow("Layout Model:", self.archetype_combo)

        self.palette_combo = QComboBox()
        for key, pinfo in PALETTES.items():
            self.palette_combo.addItem(pinfo["name"], key)
        self.palette_combo.currentIndexChanged.connect(self._update_preview)
        form_style.addRow("Color Theme:", self.palette_combo)

        self.card_width_spin = QSpinBox()
        self.card_width_spin.setRange(200, 600)
        self.card_width_spin.setValue(320)
        self.card_width_spin.setSuffix(" px")
        self.card_width_spin.valueChanged.connect(self._update_preview)
        form_style.addRow("Card Width:", self.card_width_spin)

        scroll_layout.addWidget(grp_style)

        # Field Mapping Group
        grp_fields = QGroupBox("Field Mappings")
        form_fields = QFormLayout(grp_fields)

        self.title_field_combo = QComboBox()
        self.title_field_combo.currentIndexChanged.connect(self._update_preview)
        form_fields.addRow("Title Field:", self.title_field_combo)

        self.sub_field_combo = QComboBox()
        self.sub_field_combo.currentIndexChanged.connect(self._update_preview)
        form_fields.addRow("Subtitle Field:", self.sub_field_combo)

        self.kpi_field_combo = QComboBox()
        self.kpi_field_combo.currentIndexChanged.connect(self._update_preview)
        form_fields.addRow("Main KPI Field:", self.kpi_field_combo)

        self.kpi_label_edit = QLineEdit()
        self.kpi_label_edit.setPlaceholderText("e.g. Total Score / Capacity")
        self.kpi_label_edit.textChanged.connect(self._update_preview)
        form_fields.addRow("KPI Label:", self.kpi_label_edit)

        self.kpi_unit_edit = QLineEdit()
        self.kpi_unit_edit.setPlaceholderText("e.g. m², %, EUR, km/h")
        self.kpi_unit_edit.textChanged.connect(self._update_preview)
        form_fields.addRow("KPI Unit:", self.kpi_unit_edit)

        self.media_field_combo = QComboBox()
        self.media_field_combo.currentIndexChanged.connect(self._update_preview)
        form_fields.addRow("Media/Photo Field:", self.media_field_combo)

        scroll_layout.addWidget(grp_fields)

        # Conditional Formatting Group (Traffic-Light Badges)
        grp_cond = QGroupBox("Conditional Status Badge (Traffic Light)")
        form_cond = QFormLayout(grp_cond)
        self.cb_cond_enable = QCheckBox("Enable Status Badge")
        self.cb_cond_enable.toggled.connect(self._update_preview)
        form_cond.addRow("", self.cb_cond_enable)

        self.cond_field_combo = QComboBox()
        self.cond_field_combo.currentIndexChanged.connect(self._update_preview)
        form_cond.addRow("Rule Field:", self.cond_field_combo)

        cond_row = QHBoxLayout()
        self.cond_op_combo = QComboBox()
        self.cond_op_combo.addItems([">=", ">", "<=", "<", "=="])
        self.cond_op_combo.currentIndexChanged.connect(self._update_preview)
        self.cond_val_edit = QLineEdit("50")
        self.cond_val_edit.textChanged.connect(self._update_preview)
        cond_row.addWidget(self.cond_op_combo)
        cond_row.addWidget(self.cond_val_edit)
        form_cond.addRow("Condition:", cond_row)

        lbl_row = QHBoxLayout()
        self.cond_lbl_true = QLineEdit("High / Pass")
        self.cond_lbl_true.textChanged.connect(self._update_preview)
        self.cond_lbl_false = QLineEdit("Low / Attention")
        self.cond_lbl_false.textChanged.connect(self._update_preview)
        lbl_row.addWidget(self.cond_lbl_true)
        lbl_row.addWidget(self.cond_lbl_false)
        form_cond.addRow("Labels (True / False):", lbl_row)

        scroll_layout.addWidget(grp_cond)

        # Relational / Cross-Layer Spatial Metrics
        grp_rel = QGroupBox("Cross-Layer Relational Metric")
        form_rel = QFormLayout(grp_rel)
        self.cb_rel_enable = QCheckBox("Add Spatial/Relational Metric")
        self.cb_rel_enable.toggled.connect(self._update_preview)
        form_rel.addRow("", self.cb_rel_enable)

        self.rel_layer_combo = QComboBox()
        self.rel_layer_combo.currentIndexChanged.connect(self._update_preview)
        form_rel.addRow("Related Layer:", self.rel_layer_combo)

        self.rel_op_combo = QComboBox()
        self.rel_op_combo.addItem("Spatial Intersects (Count)", ("intersects", "count"))
        self.rel_op_combo.addItem("Spatial Contains (Count)", ("contains", "count"))
        self.rel_op_combo.addItem("Nearest Neighbor (Name/ID)", ("nearest", "first"))
        self.rel_op_combo.currentIndexChanged.connect(self._update_preview)
        form_rel.addRow("Relationship:", self.rel_op_combo)

        self.rel_label_edit = QLineEdit("Connected Objects")
        self.rel_label_edit.textChanged.connect(self._update_preview)
        form_rel.addRow("Metric Label:", self.rel_label_edit)

        scroll_layout.addWidget(grp_rel)

        # Attribute Checklist
        grp_attrs = QGroupBox("Detail Attributes (Checked to include)")
        attr_layout = QVBoxLayout(grp_attrs)
        self.attrs_list = QListWidget()
        self.attrs_list.setMaximumHeight(130)
        self.attrs_list.itemChanged.connect(self._update_preview)
        attr_layout.addWidget(self.attrs_list)
        scroll_layout.addWidget(grp_attrs)

        # Live Preview Group
        grp_preview = QGroupBox("Live Preview & Expression Code")
        prev_layout = QVBoxLayout(grp_preview)

        self.preview_tabs = QTabWidget()
        self.preview_box = QTextBrowser()
        self.preview_box.setObjectName("previewBox")
        self.preview_box.setMinimumHeight(180)
        self.preview_tabs.addTab(self.preview_box, "Rendered Card")

        self.expr_box = QPlainTextEdit()
        self.expr_box.setReadOnly(True)
        self.expr_box.setMinimumHeight(180)
        self.expr_box.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 8pt; background-color: #0f172a; color: #38bdf8; border-radius: 4px; padding: 4px;"
        )
        self.preview_tabs.addTab(self.expr_box, "Expression Code")
        prev_layout.addWidget(self.preview_tabs)

        prev_btn_row = QHBoxLayout()
        self.copy_html_btn = QPushButton("📋 Copy HTML / Expression")
        self.copy_html_btn.setToolTip("Copy the compiled MapTip HTML expression to the clipboard")
        self.copy_html_btn.clicked.connect(self._copy_html_to_clipboard)
        self.preview_status_lbl = QLabel("")
        self.preview_status_lbl.setStyleSheet("font-size: 8pt; color: #10b981; font-weight: bold;")
        prev_btn_row.addWidget(self.copy_html_btn)
        prev_btn_row.addWidget(self.preview_status_lbl)
        prev_btn_row.addStretch()
        prev_layout.addLayout(prev_btn_row)

        scroll_layout.addWidget(grp_preview)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # Bottom Action Buttons
        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Apply MapTip to Layer")
        self.apply_btn.setObjectName("primaryAction")
        self.apply_btn.clicked.connect(self._apply_maptip_to_layer)

        self.clear_btn = QPushButton("Clear MapTip")
        self.clear_btn.setObjectName("secondaryAction")
        self.clear_btn.clicked.connect(self._clear_maptip_from_layer)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.apply_btn, 1)
        layout.addLayout(btn_layout)

    def _build_actions_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        info = QLabel(
            "Select 1-click actions to inject into the active vector layer. "
            "Actions use dynamic CRS transformation, point-on-surface calculation, "
            "and cross-layer spatial selection."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 8.5pt; color: #475569;")
        layout.addWidget(info)

        grp_actions = QGroupBox("Universal Action Library")
        act_layout = QVBoxLayout(grp_actions)
        act_layout.setSpacing(6)

        self.action_checkboxes: dict[str, QCheckBox] = {}
        for item in AVAILABLE_ACTIONS:
            cb = QCheckBox(f"{item['name']} — {item['description']}")
            cb.setChecked(item["key"] in ("google_satellite", "google_streetview", "copy_clipboard", "export_card_report"))
            act_layout.addWidget(cb)
            self.action_checkboxes[item["key"]] = cb

        # Open File Option
        file_box = QHBoxLayout()
        self.cb_open_file = QCheckBox("Open File/Link from Attribute:")
        self.file_field_combo = QComboBox()
        file_box.addWidget(self.cb_open_file)
        file_box.addWidget(self.file_field_combo, 1)
        act_layout.addLayout(file_box)

        # Select Intersecting in Another Layer
        sel_box = QHBoxLayout()
        self.cb_sel_intersect = QCheckBox("Select Intersecting in Layer:")
        self.sel_layer_combo = QComboBox()
        sel_box.addWidget(self.cb_sel_intersect)
        sel_box.addWidget(self.sel_layer_combo, 1)
        act_layout.addLayout(sel_box)

        layout.addWidget(grp_actions)
        layout.addStretch()

        self.inject_actions_btn = QPushButton("Inject Selected Actions into Layer")
        self.inject_actions_btn.setObjectName("primaryAction")
        self.inject_actions_btn.clicked.connect(self._apply_actions)
        layout.addWidget(self.inject_actions_btn)

    def _build_hud_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        info = QLabel(
            "Live Canvas HUD enables non-blocking pixel value inspection when hovering over "
            "raster layers (DEM, Slope, NDVI, Orthophoto) with debounced sampling, custom reticle cursor, "
            "and composite vector+raster multi-layer inspection."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 8.5pt; color: #475569;")
        layout.addWidget(info)

        grp_hud = QGroupBox("HUD Inspection Controls")
        form_hud = QFormLayout(grp_hud)

        self.hud_enable_cb = QCheckBox("Enable Live Canvas Hover HUD")
        self.hud_enable_cb.toggled.connect(self._toggle_hud)
        form_hud.addRow("", self.hud_enable_cb)

        self.hud_cursor_cb = QCheckBox("Use Precision Reticle Cursor on Canvas")
        self.hud_cursor_cb.setChecked(True)
        self.hud_cursor_cb.setToolTip("Replaces the default hand cursor with an inspection crosshair & locator badge")
        self.hud_cursor_cb.toggled.connect(lambda c: self._hud.set_use_custom_cursor(c))
        form_hud.addRow("", self.hud_cursor_cb)

        self.hud_pin_cb = QCheckBox("📌 Pin / Freeze Tooltip (Shift+Click canvas to toggle)")
        self.hud_pin_cb.setToolTip("Freezes current tooltip stationary on canvas so it will not close or move")
        self.hud_pin_cb.toggled.connect(lambda c: self._hud.set_pinned(c))
        self._hud.pinStateChanged.connect(self.hud_pin_cb.setChecked)
        form_hud.addRow("", self.hud_pin_cb)

        self.hud_composite_cb = QCheckBox("Composite Mode (Inspect All Visible Rasters + Top Vector)")
        self.hud_composite_cb.toggled.connect(self._on_hud_composite_toggled)
        form_hud.addRow("", self.hud_composite_cb)

        self.hud_raster_combo = QComboBox()
        self.hud_raster_combo.currentIndexChanged.connect(self._on_hud_raster_changed)
        form_hud.addRow("Primary Raster:", self.hud_raster_combo)

        self.hud_debounce_spin = QSpinBox()
        self.hud_debounce_spin.setRange(100, 1000)
        self.hud_debounce_spin.setValue(250)
        self.hud_debounce_spin.setSuffix(" ms")
        self.hud_debounce_spin.valueChanged.connect(self._on_hud_debounce_changed)
        form_hud.addRow("Dwell Debounce:", self.hud_debounce_spin)

        layout.addWidget(grp_hud)

        # Live Inspected Values in Dock (Permanent View)
        grp_feed = QGroupBox("Live Sampled Values Feed (Permanent View)")
        feed_layout = QVBoxLayout(grp_feed)
        self.hud_live_browser = QTextBrowser()
        self.hud_live_browser.setMinimumHeight(140)
        self.hud_live_browser.setStyleSheet(
            "background-color: #0f172a; color: #f8fafc; border-radius: 4px; border: 1px solid #334155;"
        )
        self.hud_live_browser.setHtml(
            "<div style='color:#64748b; font-size:9pt; padding:10px;'>"
            "Hover over the map canvas to inspect raster bands and vector features. "
            "Values remain permanently visible here even after moving the mouse away.</div>"
        )
        feed_layout.addWidget(self.hud_live_browser)
        self._hud.sampleUpdated.connect(lambda html_val, _: self.hud_live_browser.setHtml(html_val))
        layout.addWidget(grp_feed)

        layout.addStretch()

    # ──────────────────────────────────────────────────────────────────────────
    # Layer & Event Handlers
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_layers(self) -> None:
        prev_id = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.hud_raster_combo.blockSignals(True)
        self.rel_layer_combo.blockSignals(True)
        self.sel_layer_combo.blockSignals(True)

        self.layer_combo.clear()
        self.hud_raster_combo.clear()
        self.rel_layer_combo.clear()
        self.sel_layer_combo.clear()

        layers = list(QgsProject.instance().mapLayers().values())
        for lyr in layers:
            icon = "🗺️ " if isinstance(lyr, QgsVectorLayer) else "▦ "
            self.layer_combo.addItem(f"{icon}{lyr.name()}", lyr.id())
            if isinstance(lyr, QgsVectorLayer):
                self.rel_layer_combo.addItem(lyr.name(), lyr.name())
                self.sel_layer_combo.addItem(lyr.name(), lyr.name())
            elif isinstance(lyr, QgsRasterLayer):
                self.hud_raster_combo.addItem(f"▦ {lyr.name()}", lyr.id())

        self.layer_combo.blockSignals(False)
        self.hud_raster_combo.blockSignals(False)
        self.rel_layer_combo.blockSignals(False)
        self.sel_layer_combo.blockSignals(False)

        idx = self.layer_combo.findData(prev_id)
        if idx >= 0:
            self.layer_combo.setCurrentIndex(idx)
        elif self.layer_combo.count() > 0:
            self.layer_combo.setCurrentIndex(0)
        else:
            self._on_target_layer_selected(-1)

    def _on_qgis_active_layer_changed(self, layer: Optional[QgsMapLayer]) -> None:
        if layer:
            idx = self.layer_combo.findData(layer.id())
            if idx >= 0 and idx != self.layer_combo.currentIndex():
                self.layer_combo.setCurrentIndex(idx)

    def _on_target_layer_selected(self, index: int) -> None:
        if index < 0 or self.layer_combo.count() == 0:
            self._current_layer = None
            self.layer_info_label.setText("No layer selected")
            return

        lyr_id = self.layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(lyr_id)
        self._current_layer = layer

        if not layer or not layer.isValid():
            self.layer_info_label.setText("Invalid layer")
            return

        if isinstance(layer, QgsVectorLayer):
            cnt = layer.featureCount()
            geom = layer.geometryType()
            geom_names = {0: "Point", 1: "Line", 2: "Polygon", 3: "Unknown", 4: "Null"}
            self.layer_info_label.setText(
                f"Vector ({geom_names.get(geom, 'Unknown')}) · {cnt:,} features · CRS: {layer.crs().authid()}"
            )
            self._populate_vector_fields(layer)
            self._hud.set_vector_layer(layer)
        elif isinstance(layer, QgsRasterLayer):
            self.layer_info_label.setText(
                f"Raster · {layer.bandCount()} bands · {layer.width()}x{layer.height()} · CRS: {layer.crs().authid()}"
            )
            self._hud.set_active_raster(layer)

        self._update_preview()

    def _populate_vector_fields(self, layer: QgsVectorLayer) -> None:
        combos = [
            self.title_field_combo,
            self.sub_field_combo,
            self.kpi_field_combo,
            self.media_field_combo,
            self.file_field_combo,
            self.cond_field_combo,
        ]
        for cb in combos:
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("(None)", "")

        self.attrs_list.blockSignals(True)
        self.attrs_list.clear()

        fields = layer.fields()
        for f in fields:
            name = f.name()
            for cb in combos:
                cb.addItem(name, name)

            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.attrs_list.addItem(item)

        for name in fields.names():
            nl = name.lower()
            if any(k in nl for k in ("ad", "name", "title", "id", "label")):
                self.title_field_combo.setCurrentText(name)
                break

        for name in fields.names():
            nl = name.lower()
            if any(k in nl for k in ("tip", "tur", "type", "fonksiyon", "class", "kat")):
                self.sub_field_combo.setCurrentText(name)
                break

        for name in fields.names():
            nl = name.lower()
            if any(k in nl for k in ("alan", "area", "skor", "score", "fiyat", "deger", "count")):
                self.kpi_field_combo.setCurrentText(name)
                self.cond_field_combo.setCurrentText(name)
                break

        for cb in combos:
            cb.blockSignals(False)
        self.attrs_list.blockSignals(False)

    def _build_config_from_ui(self) -> TemplateConfig:
        config = TemplateConfig()
        config.archetype = self.archetype_combo.currentData()
        config.palette_key = self.palette_combo.currentData()
        config.card_width = self.card_width_spin.value()
        config.title_field = self.title_field_combo.currentData() or ""
        config.subtitle_field = self.sub_field_combo.currentData() or ""
        config.kpi_field = self.kpi_field_combo.currentData() or ""
        config.kpi_label = self.kpi_label_edit.text().strip()
        config.kpi_unit = self.kpi_unit_edit.text().strip()
        config.media_field = self.media_field_combo.currentData() or ""

        # Conditional badge
        if self.cb_cond_enable.isChecked() and self.cond_field_combo.currentData():
            config.conditional_rules = [
                {
                    "field": self.cond_field_combo.currentData(),
                    "op": self.cond_op_combo.currentText(),
                    "val": self.cond_val_edit.text().strip() or "0",
                    "label_true": self.cond_lbl_true.text().strip(),
                    "label_false": self.cond_lbl_false.text().strip(),
                    "color_true": "#ef4444" if ">=" in self.cond_op_combo.currentText() else "#10b981",
                    "color_false": "#10b981" if ">=" in self.cond_op_combo.currentText() else "#ef4444",
                }
            ]

        # Relational metric
        if self.cb_rel_enable.isChecked() and self.rel_layer_combo.currentText():
            op_data = self.rel_op_combo.currentData()
            config.relational_metrics = [
                {
                    "target_layer": self.rel_layer_combo.currentText(),
                    "op": op_data[0],
                    "aggregate": op_data[1],
                    "field": "id",
                    "label": self.rel_label_edit.text().strip(),
                }
            ]

        # Attributes
        attrs = []
        for i in range(self.attrs_list.count()):
            it = self.attrs_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                fld = it.text()
                if fld not in (config.title_field, config.kpi_field):
                    attrs.append((fld, fld))
        config.attribute_fields = attrs

        # Sparklines
        if config.archetype == Archetype.SPARKLINE:
            config.sparkline_fields = [fld for fld, _ in attrs[:5]]

        return config

    def _update_preview(self) -> None:
        config = self._build_config_from_ui()
        raw_html = compile_maptip_html(config)
        self._current_raw_html = raw_html
        if hasattr(self, "expr_box"):
            self.expr_box.setPlainText(raw_html)

        if isinstance(self._current_layer, QgsVectorLayer) and self._current_layer.isValid():
            sample_feature = None
            selected = self._current_layer.selectedFeatures()
            if selected:
                sample_feature = selected[0]
            else:
                for feat in self._current_layer.getFeatures():
                    sample_feature = feat
                    break

            if sample_feature:
                ctx = QgsExpressionContext()
                ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(self._current_layer))
                ctx.setFeature(sample_feature)
                evaluated_html = QgsExpression.replaceExpressionText(raw_html, ctx)
                self.preview_box.setHtml(evaluated_html)
                return

        self.preview_box.setHtml(raw_html)

    def _copy_html_to_clipboard(self) -> None:
        text = getattr(self, "_current_raw_html", "")
        if not text:
            config = self._build_config_from_ui()
            text = compile_maptip_html(config)
            self._current_raw_html = text
        QApplication.clipboard().setText(text)
        if hasattr(self, "preview_status_lbl"):
            self.preview_status_lbl.setText("Copied!")
            QTimer.singleShot(2500, lambda: self.preview_status_lbl.setText(""))

    def _toggle_canvas_maptips(self) -> None:
        if hasattr(self.iface, "actionMapTips") and self.iface.actionMapTips():
            self.iface.actionMapTips().trigger()
            self._sync_maptip_action_state()

    def _sync_maptip_action_state(self, checked: Optional[bool] = None) -> None:
        if not hasattr(self, "toggle_maptips_btn"):
            return
        if not hasattr(self.iface, "actionMapTips") or not self.iface.actionMapTips():
            self.toggle_maptips_btn.setEnabled(False)
            self.toggle_maptips_btn.setText("💡 MapTips: N/A")
            return
        is_active = self.iface.actionMapTips().isChecked() if checked is None else checked
        self.toggle_maptips_btn.setChecked(is_active)
        if is_active:
            self.toggle_maptips_btn.setText("💡 MapTips: ON")
            self.toggle_maptips_btn.setStyleSheet(
                "font-size: 8pt; font-weight: bold; background-color: #10b981; color: white; border-radius: 4px; padding: 2px 8px;"
            )
        else:
            self.toggle_maptips_btn.setText("💡 MapTips: OFF")
            self.toggle_maptips_btn.setStyleSheet(
                "font-size: 8pt; font-weight: bold; background-color: #64748b; color: white; border-radius: 4px; padding: 2px 8px;"
            )

    def _apply_maptip_to_layer(self) -> None:
        if not isinstance(self._current_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Qgis MapTips", "Please select a vector layer to apply the MapTip.")
            return

        config = self._build_config_from_ui()
        compiled_html = compile_maptip_html(config)
        self._current_layer.setMapTipTemplate(compiled_html)

        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushSuccess(
                "Qgis MapTips", f"MapTip applied successfully to '{self._current_layer.name()}'."
            )
        else:
            QMessageBox.information(self, "Qgis MapTips", "MapTip applied successfully!")

    def _clear_maptip_from_layer(self) -> None:
        if isinstance(self._current_layer, QgsVectorLayer):
            self._current_layer.setMapTipTemplate("")
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushInfo(
                    "Qgis MapTips", f"MapTip cleared from '{self._current_layer.name()}'."
                )

    def _apply_actions(self) -> None:
        if not isinstance(self._current_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Qgis MapTips", "Please select a vector layer to inject actions.")
            return

        selected_keys = [k for k, cb in self.action_checkboxes.items() if cb.isChecked()]
        file_field = self.file_field_combo.currentData() if self.cb_open_file.isChecked() else ""
        if self.cb_open_file.isChecked() and file_field:
            selected_keys.append("open_file")

        intersect_tgt = self.sel_layer_combo.currentText() if self.cb_sel_intersect.isChecked() else ""
        if self.cb_sel_intersect.isChecked() and intersect_tgt:
            selected_keys.append("select_intersects")

        count = apply_actions_to_layer(
            self._current_layer,
            selected_keys,
            file_field=file_field,
            intersect_target_layer=intersect_tgt,
        )
        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushSuccess(
                "Qgis MapTips", f"{count} actions added to layer '{self._current_layer.name()}'."
            )
        else:
            QMessageBox.information(self, "Qgis MapTips", f"{count} actions added successfully!")

    def _on_preset_selected(self, index: int) -> None:
        preset_file = self.preset_combo.currentData()
        if not preset_file:
            return

        presets_dir = Path(__file__).resolve().parent.parent / "templates"
        preset_path = presets_dir / preset_file
        if preset_path.exists():
            cfg = TemplateConfig.load_json(preset_path)
            self._apply_config_to_ui(cfg)

    def _apply_config_to_ui(self, cfg: TemplateConfig) -> None:
        idx_arch = self.archetype_combo.findData(cfg.archetype)
        if idx_arch >= 0:
            self.archetype_combo.setCurrentIndex(idx_arch)

        idx_pal = self.palette_combo.findData(cfg.palette_key)
        if idx_pal >= 0:
            self.palette_combo.setCurrentIndex(idx_pal)

        self.card_width_spin.setValue(cfg.card_width)
        if cfg.kpi_label:
            self.kpi_label_edit.setText(cfg.kpi_label)
        if cfg.kpi_unit:
            self.kpi_unit_edit.setText(cfg.kpi_unit)

        self._update_preview()

    def _save_preset(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Card Preset", "", "JSON Files (*.json)")
        if path:
            cfg = self._build_config_from_ui()
            cfg.save_json(path)
            QMessageBox.information(self, "Qgis MapTips", f"Preset saved to {path}")

    def _load_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Card Preset", "", "JSON Files (*.json)")
        if path:
            cfg = TemplateConfig.load_json(path)
            self._apply_config_to_ui(cfg)

    def _toggle_hud(self, checked: bool) -> None:
        if checked:
            self._hud.start()
        else:
            self._hud.stop()

    def _on_hud_composite_toggled(self, checked: bool) -> None:
        self._hud.set_composite_mode(checked)
        if checked:
            rasters = [lyr for lyr in QgsProject.instance().mapLayers().values() if isinstance(lyr, QgsRasterLayer)]
            self._hud.set_target_rasters(rasters)
        else:
            self._on_hud_raster_changed(self.hud_raster_combo.currentIndex())

    def _on_hud_raster_changed(self, index: int) -> None:
        lyr_id = self.hud_raster_combo.currentData()
        layer = QgsProject.instance().mapLayer(lyr_id)
        if isinstance(layer, QgsRasterLayer):
            self._hud.set_active_raster(layer)

    def _on_hud_debounce_changed(self, val: int) -> None:
        self._hud.debounce_ms = val

    def unload(self) -> None:
        """Clean up listeners and filters on plugin unload."""
        self._hud.stop()
        with contextlib.suppress(Exception):
            QgsProject.instance().layersAdded.disconnect(self._refresh_layers)
            QgsProject.instance().layersRemoved.disconnect(self._refresh_layers)
            self.iface.currentLayerChanged.disconnect(self._on_qgis_active_layer_changed)
