"""Main dock panel for Qgis Advanced Map Tips&Actions."""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from qgis.PyQt.QtCore import QEvent, Qt, QTimer, QUrl
from qgis.PyQt.QtGui import QColor, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
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
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

DEFAULT_DONUT_PALETTE: list[str] = [
    "#10b981", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4", "#f97316", "#14b8a6"
]
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsFeatureRequest,
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from ..core.action_builder import (
    AVAILABLE_ACTIONS,
    apply_actions_to_layer,
    create_feature_buffer,
    get_layer_actions,
    is_layer_alive,
    remove_all_actions,
    zoom_to_feature,
)
from ..core.raster_hud import CanvasHoverHUD, evaluate_vector_feature_maptip
from ..core.template_engine import (
    PALETTES,
    Archetype,
    TemplateConfig,
    compile_maptip_html,
)
from ..core.cadastre_tool import (
    add_parcel_feature,
    get_or_create_cadastre_layer,
    is_in_turkey_bounds,
    parse_tkgm_response,
    query_tkgm_megsis,
)
from .collapsible import CollapsibleSection
from .switch import IOSToggleSwitch
from .theme import apply_adaptive_theme

if TYPE_CHECKING:
    from qgis.gui import QgisInterface


def _is_numeric_field(field: Any) -> bool:
    """Check if a QgsField represents numeric data across QGIS 3 & 4 runtimes."""
    if hasattr(field, "isNumeric"):
        return bool(field.isNumeric())
    typeName = getattr(field, "typeName", lambda: "")().lower()
    return any(k in typeName for k in ("int", "double", "real", "num", "float", "decimal", "long"))


class QgisMapTipsDock(QDockWidget):
    """Dockable studio for designing MapTips and managing layer actions."""

    def __init__(
        self,
        iface: "QgisInterface",
        parent: Optional[QWidget] = None,
        plugin: Optional[Any] = None,
    ) -> None:
        super().__init__("Qgis Advanced Map Tips&Actions", parent or iface.mainWindow())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        self.setObjectName("QgisMapTipsDock")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self._hud = CanvasHoverHUD(self.canvas, debounce_ms=250, parent=self)
        self._current_layer: Optional[QgsMapLayer] = None
        self._current_layer_id: Optional[str] = None
        self._cadastre_tool: Optional[Any] = None

        # Debounced preview timer (150ms) to ensure fluid typing & UI responsiveness
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._update_preview)

        self._init_ui()
        apply_adaptive_theme(self)

        # Connect interactive inspector HUD signals
        self._hud.featureHovered.connect(self._on_hud_feature_hovered)
        self._hud.featurePinned.connect(self._on_hud_feature_pinned)
        self._hud.pinStateChanged.connect(self._on_hud_pin_state_changed)
        self._hud.cleared.connect(self._on_hud_cleared)

        # Sync and connect native MapTips action
        self._sync_maptip_action_state()
        if hasattr(self.iface, "actionMapTips") and self.iface.actionMapTips():
            with contextlib.suppress(Exception):
                self.iface.actionMapTips().toggled.connect(self._sync_maptip_action_state)

        # Connect layer signals
        QgsProject.instance().layersWillBeRemoved.connect(self._on_layers_will_be_removed)
        QgsProject.instance().layersAdded.connect(self._refresh_layers)
        QgsProject.instance().layersRemoved.connect(self._refresh_layers)
        self.iface.currentLayerChanged.connect(self._on_qgis_active_layer_changed)

        self._refresh_layers()

    def _schedule_preview_update(self) -> None:
        """Debounce live card preview updates to prevent UI stutter during typing."""
        if hasattr(self, "_preview_timer"):
            self._preview_timer.start()
        else:
            self._update_preview()

    def changeEvent(self, event: Any) -> None:
        """Dynamically adapt dock styles when QGIS theme or OS palette changes."""
        if event and hasattr(event, "type"):
            ev_type = event.type()
            pal_change = getattr(QEvent.Type, "PaletteChange", None)
            app_pal_change = getattr(QEvent.Type, "ApplicationPaletteChange", None)
            if ev_type in (pal_change, app_pal_change):
                apply_adaptive_theme(self)
        super().changeEvent(event)

    def closeEvent(self, event: Any) -> None:
        """Safely detach HUD reticle cursor and stop canvas event filters on dock close."""
        if hasattr(self, "_hud") and self._hud:
            self._hud.stop()
        super().closeEvent(event)

    def _init_ui(self) -> None:
        root = QWidget()
        root.setObjectName("maptipsRoot")
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(5)

        # 1. Compact Sleek Hero Panel
        hero = QFrame()
        hero.setObjectName("heroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(8, 6, 8, 6)
        hero_layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        hero_mark = QLabel("MT")
        hero_mark.setObjectName("heroMark")
        align_center = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignCenter", 0)
        hero_mark.setAlignment(align_center)
        hero_mark.setFixedSize(26, 26)
        top_row.addWidget(hero_mark)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        eyebrow = QLabel("ADVANCED MAP TIPS & ACTIONS")
        eyebrow.setObjectName("heroEyebrow")
        title = QLabel("MapTips Studio")
        title.setObjectName("heroTitle")
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        top_row.addLayout(title_box, 1)

        # Compact animated iOS Toggle Switch for MapTips
        switch_box = QHBoxLayout()
        switch_box.setSpacing(4)
        self.maptips_switch_lbl = QLabel("MapTips")
        self.maptips_switch_lbl.setStyleSheet("font-size: 8pt; font-weight: bold; color: #475569;")
        self.maptips_switch = IOSToggleSwitch(default_on=True, width=46, height=22)
        self.maptips_switch.setToolTip("Toggle QGIS Canvas MapTips visibility (Green: ON / Red: OFF)")
        self.maptips_switch.toggled.connect(self._on_maptips_switch_toggled)
        switch_box.addWidget(self.maptips_switch_lbl)
        switch_box.addWidget(self.maptips_switch)

        badge = QLabel("PRO")
        badge.setObjectName("heroBadge")
        top_row.addLayout(switch_box)
        top_row.addWidget(badge)

        # Quick Manual & Rate Plugin Buttons
        cursor_hand = getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor", None)
        self.btn_manual = QPushButton("📖")
        self.btn_manual.setObjectName("quietButton")
        self.btn_manual.setToolTip("Open Quick User Guide & Online Manual (geophilo.com)")
        self.btn_manual.setFixedSize(22, 22)
        if cursor_hand is not None:
            self.btn_manual.setCursor(cursor_hand)
        self.btn_manual.clicked.connect(self._open_quick_manual)

        self.btn_rate = QPushButton("⭐")
        self.btn_rate.setObjectName("quietButton")
        self.btn_rate.setToolTip("Rate Plugin on QGIS Hub (5 Stars)")
        self.btn_rate.setFixedSize(22, 22)
        if cursor_hand is not None:
            self.btn_rate.setCursor(cursor_hand)
        self.btn_rate.clicked.connect(self._open_rate_plugin)

        top_row.addWidget(self.btn_manual)
        top_row.addWidget(self.btn_rate)
        hero_layout.addLayout(top_row)

        # Single compact row for target layer + refresh + status pill
        layer_row = QHBoxLayout()
        layer_row.setSpacing(5)
        layer_lbl = QLabel("Layer:")
        layer_lbl.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._on_target_layer_selected)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("quietButton")
        self.refresh_btn.setToolTip("Refresh layer list")
        self.refresh_btn.setFixedWidth(24)
        self.refresh_btn.setFixedHeight(22)
        self.refresh_btn.clicked.connect(self._refresh_layers)

        self.layer_info_label = QLabel("None")
        self.layer_info_label.setObjectName("layerBadge")
        self.layer_info_label.setMaximumWidth(120)

        layer_row.addWidget(layer_lbl)
        layer_row.addWidget(self.layer_combo, 1)
        layer_row.addWidget(self.refresh_btn)
        layer_row.addWidget(self.layer_info_label)
        hero_layout.addLayout(layer_row)

        main_layout.addWidget(hero)

        # 2. Main Tabbed Workspace
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Tab 1: MapTip Designer
        tab_designer = QWidget()
        self._build_designer_tab(tab_designer)
        self.tabs.addTab(tab_designer, "MapTip Designer")

        # Tab 2: Actions Hub
        tab_actions = QWidget()
        self._build_actions_tab(tab_actions)
        self.tabs.addTab(tab_actions, "Actions Hub")

        # Tab 3: Interactive Canvas Pin & Inspect
        tab_hud = QWidget()
        self._build_hud_tab(tab_hud)
        self.tabs.addTab(tab_hud, "📌 Pin & Inspect")

        self.tabs.currentChanged.connect(lambda _: self._sync_cursor_state())
        main_layout.addWidget(self.tabs, 1)

        self.setWidget(root)

    def _build_designer_tab(self, parent: QWidget) -> None:
        outer_layout = QVBoxLayout(parent)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(6, 6, 6, 6)
        scroll_layout.setSpacing(5)

        # 1. Quick Presets Chips Bar
        chips_box = QHBoxLayout()
        chips_box.setSpacing(4)
        chips_lbl = QLabel("Presets:")
        chips_lbl.setStyleSheet("font-size: 7.5pt; font-weight: bold; color: #64748b;")
        chips_box.addWidget(chips_lbl)

        presets_quick = [
            ("🏢 KPI", "kpi_real_estate.json"),
            ("⚡ Bar", "progress_capacity.json"),
            ("🍩 Donut", "donut_shares.json"),
            ("📈 Trend", "sparkline_timeline.json"),
        ]
        for title, pfile in presets_quick:
            chip = QPushButton(title)
            chip.setObjectName("presetChip")
            cursor = getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor", None)
            if cursor is not None:
                chip.setCursor(cursor)
            chip.setToolTip(f"Instantly load {title} template")
            chip.clicked.connect(lambda _, f=pfile: self._load_preset_by_file(f))
            chips_box.addWidget(chip)
        chips_box.addStretch()
        scroll_layout.addLayout(chips_box)

        # 2. Preset Toolbar
        preset_box = QHBoxLayout()
        preset_box.setSpacing(4)
        preset_lbl = QLabel("Template:")
        preset_lbl.setStyleSheet("font-size:8pt; font-weight:bold;")
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("(Current / Custom)")
        self.preset_combo.addItem("Real Estate Investment", "kpi_real_estate.json")
        self.preset_combo.addItem("Capacity & Occupancy Bar", "progress_capacity.json")
        self.preset_combo.addItem("Land Use Donut Shares", "donut_shares.json")
        self.preset_combo.addItem("Temporal Sparkline Timeline", "sparkline_timeline.json")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QPushButton("Save...")
        self.btn_save_preset.setObjectName("quietButton")
        self.btn_save_preset.setToolTip("Save current card configuration as JSON preset")
        self.btn_save_preset.clicked.connect(self._save_preset)
        self.btn_load_preset = QPushButton("Load...")
        self.btn_load_preset.setObjectName("quietButton")
        self.btn_load_preset.setToolTip("Load custom preset from JSON file")
        self.btn_load_preset.clicked.connect(self._load_preset)

        preset_box.addWidget(preset_lbl)
        preset_box.addWidget(self.preset_combo, 1)
        preset_box.addWidget(self.btn_save_preset)
        preset_box.addWidget(self.btn_load_preset)
        scroll_layout.addLayout(preset_box)

        # 3. Collapsible: Layout Model & Color Palette
        self.section_style = CollapsibleSection("🎨 Layout & Color Theme", initially_expanded=True)
        form_style = QFormLayout()
        form_style.setContentsMargins(4, 4, 4, 4)
        form_style.setSpacing(4)

        self.archetype_combo = QComboBox()
        self.archetype_combo.addItem("Modern KPI Card", Archetype.KPI_CARD)
        self.archetype_combo.addItem("Comparison Progress Bar", Archetype.PROGRESS_BAR)
        self.archetype_combo.addItem("Multi-Metric Donut Chart", Archetype.DONUT_CHART)
        self.archetype_combo.addItem("SVG Sparkline Trend", Archetype.SPARKLINE)
        self.archetype_combo.addItem("Media / Photo Card", Archetype.MEDIA_CARD)
        self.archetype_combo.addItem("Clean Attribute Grid", Archetype.CLEAN_TABLE)
        self.archetype_combo.currentIndexChanged.connect(self._on_archetype_changed)
        form_style.addRow("Layout:", self.archetype_combo)

        self.palette_combo = QComboBox()
        for key, pinfo in PALETTES.items():
            self.palette_combo.addItem(pinfo["name"], key)
        self.palette_combo.currentIndexChanged.connect(self._update_preview)
        form_style.addRow("Palette:", self.palette_combo)

        self.card_width_spin = QSpinBox()
        self.card_width_spin.setRange(180, 800)
        self.card_width_spin.setSingleStep(10)
        self.card_width_spin.setValue(320)
        self.card_width_spin.setSuffix(" px")
        self.card_width_spin.valueChanged.connect(self._schedule_preview_update)
        form_style.addRow("Width:", self.card_width_spin)

        self.cb_card_actions = QCheckBox("Show 1-Click Action Buttons Ribbon")
        self.cb_card_actions.setChecked(True)
        self.cb_card_actions.toggled.connect(self._update_preview)
        form_style.addRow("", self.cb_card_actions)

        # Wrap policy for narrow docks
        wrap_policy = getattr(getattr(QFormLayout, "RowWrapPolicy", QFormLayout), "WrapLongRows", None)
        if wrap_policy is not None:
            form_style.setRowWrapPolicy(wrap_policy)

        self.section_style.add_layout(form_style)
        scroll_layout.addWidget(self.section_style)

        # 4. Collapsible: Core Field Mappings
        self.section_fields = CollapsibleSection("🏷️ Core Field Mappings", initially_expanded=True)
        form_fields = QFormLayout()
        form_fields.setContentsMargins(4, 4, 4, 4)
        form_fields.setSpacing(4)
        if wrap_policy is not None:
            form_fields.setRowWrapPolicy(wrap_policy)

        self.title_field_combo = QComboBox()
        self.title_field_combo.currentIndexChanged.connect(self._update_preview)
        form_fields.addRow("Title:", self.title_field_combo)

        self.sub_field_combo = QComboBox()
        self.sub_field_combo.currentIndexChanged.connect(self._update_preview)
        form_fields.addRow("Subtitle:", self.sub_field_combo)

        self.kpi_field_combo = QComboBox()
        self.kpi_field_combo.currentIndexChanged.connect(self._update_preview)
        form_fields.addRow("Main KPI:", self.kpi_field_combo)

        self.progress_max_edit = QLineEdit("100")
        self.progress_max_edit.setPlaceholderText("e.g. 100 or 'capacity'")
        self.progress_max_edit.textChanged.connect(self._schedule_preview_update)
        form_fields.addRow("Max Value:", self.progress_max_edit)

        self.kpi_label_edit = QLineEdit()
        self.kpi_label_edit.setPlaceholderText("e.g. Total Score / Capacity")
        self.kpi_label_edit.textChanged.connect(self._schedule_preview_update)
        form_fields.addRow("KPI Label:", self.kpi_label_edit)

        self.kpi_unit_edit = QLineEdit()
        self.kpi_unit_edit.setPlaceholderText("e.g. m², %, EUR, km/h")
        self.kpi_unit_edit.textChanged.connect(self._schedule_preview_update)
        form_fields.addRow("KPI Unit:", self.kpi_unit_edit)

        self.section_fields.add_layout(form_fields)
        scroll_layout.addWidget(self.section_fields)

        # 4b. Collapsible: Donut Chart Slices (Dynamic, visible when Donut Chart is active)
        self.sec_donut = CollapsibleSection("🍩 Donut Chart Slices", initially_expanded=True)
        donut_layout = QVBoxLayout()
        donut_layout.setContentsMargins(4, 4, 4, 4)
        donut_layout.setSpacing(4)

        donut_hint = QLabel("Select 2–6 numeric attributes to slice the proportional donut.")
        donut_hint.setStyleSheet("font-size: 7.5pt; color: #64748b; margin-bottom: 2px;")
        donut_layout.addWidget(donut_hint)

        self.donut_slices_container = QVBoxLayout()
        self.donut_slices_container.setSpacing(3)
        donut_layout.addLayout(self.donut_slices_container)

        self._donut_slice_rows: list[dict[str, Any]] = []

        donut_btn_row = QHBoxLayout()
        donut_btn_row.setSpacing(4)
        self.btn_add_donut_slice = QPushButton("➕ Add Slice")
        self.btn_add_donut_slice.setObjectName("quietButton")
        self.btn_add_donut_slice.clicked.connect(self._on_add_donut_slice_clicked)

        self.btn_auto_donut = QPushButton("✨ Auto-Detect Numeric")
        self.btn_auto_donut.setObjectName("quietButton")
        self.btn_auto_donut.setToolTip("Scan active layer and auto-populate numeric attributes")
        self.btn_auto_donut.clicked.connect(self._auto_detect_donut_fields)

        donut_btn_row.addWidget(self.btn_add_donut_slice)
        donut_btn_row.addWidget(self.btn_auto_donut)
        donut_btn_row.addStretch()
        donut_layout.addLayout(donut_btn_row)

        self.sec_donut.add_layout(donut_layout)
        scroll_layout.addWidget(self.sec_donut)
        self.sec_donut.setVisible(self.archetype_combo.currentData() == Archetype.DONUT_CHART)

        # 5. Collapsible: Advanced Options (Media, Formatting, Rules)
        self.adv_section = CollapsibleSection("⚙️ Advanced Options (Media, Rules, Metrics)", initially_expanded=False)
        form_adv = QFormLayout()
        form_adv.setContentsMargins(4, 4, 4, 4)
        form_adv.setSpacing(4)

        self.media_field_combo = QComboBox()
        self.media_field_combo.currentIndexChanged.connect(self._update_preview)
        form_adv.addRow("Photo Field:", self.media_field_combo)

        self.combo_media_fallback = QComboBox()
        self.combo_media_fallback.addItem("Show SVG Placeholder", "placeholder")
        self.combo_media_fallback.addItem("Collapse & Hide Row", "hide")
        self.combo_media_fallback.currentIndexChanged.connect(self._update_preview)
        form_adv.addRow("Missing Photo:", self.combo_media_fallback)

        self.cb_format_numbers = QCheckBox("Format Numbers (e.g. 1,250)")
        self.cb_format_numbers.setChecked(True)
        self.cb_format_numbers.toggled.connect(self._update_preview)
        form_adv.addRow("", self.cb_format_numbers)

        self.spin_decimals = QSpinBox()
        self.spin_decimals.setRange(0, 6)
        self.spin_decimals.setValue(2)
        self.spin_decimals.setSuffix(" dec.")
        self.spin_decimals.valueChanged.connect(self._schedule_preview_update)
        form_adv.addRow("Decimals:", self.spin_decimals)

        self.edit_null_text = QLineEdit("—")
        self.edit_null_text.textChanged.connect(self._schedule_preview_update)
        form_adv.addRow("Null Text:", self.edit_null_text)

        # Conditional Badge
        self.cb_cond_enable = QCheckBox("Enable Status Badge")
        self.cb_cond_enable.toggled.connect(self._update_preview)
        form_adv.addRow("Status Badge:", self.cb_cond_enable)

        self.cond_field_combo = QComboBox()
        self.cond_field_combo.currentIndexChanged.connect(self._update_preview)
        form_adv.addRow("Rule Field:", self.cond_field_combo)

        cond_row = QHBoxLayout()
        cond_row.setSpacing(4)
        self.cond_op_combo = QComboBox()
        self.cond_op_combo.addItems([">=", ">", "<=", "<", "="])
        self.cond_op_combo.currentIndexChanged.connect(self._update_preview)
        self.cond_val_edit = QLineEdit("50")
        self.cond_val_edit.textChanged.connect(self._schedule_preview_update)
        cond_row.addWidget(self.cond_op_combo)
        cond_row.addWidget(self.cond_val_edit)
        form_adv.addRow("Threshold:", cond_row)

        lbl_row = QHBoxLayout()
        lbl_row.setSpacing(4)
        self.cond_lbl_true = QLineEdit("Pass")
        self.cond_lbl_true.textChanged.connect(self._schedule_preview_update)
        self.cond_lbl_false = QLineEdit("Alert")
        self.cond_lbl_false.textChanged.connect(self._schedule_preview_update)
        lbl_row.addWidget(self.cond_lbl_true)
        lbl_row.addWidget(self.cond_lbl_false)
        form_adv.addRow("Labels (T / F):", lbl_row)

        # Relational Metric
        self.cb_rel_enable = QCheckBox("Add Relational Metric")
        self.cb_rel_enable.toggled.connect(self._update_preview)
        form_adv.addRow("Cross-Layer:", self.cb_rel_enable)

        self.rel_layer_combo = QComboBox()
        self.rel_layer_combo.currentIndexChanged.connect(self._update_preview)
        form_adv.addRow("Target Layer:", self.rel_layer_combo)

        self.rel_op_combo = QComboBox()
        self.rel_op_combo.addItem("Spatial Intersects (Count)", ("intersects", "count"))
        self.rel_op_combo.addItem("Spatial Contains (Count)", ("contains", "count"))
        self.rel_op_combo.addItem("Nearest Neighbor (ID)", ("nearest", "first"))
        self.rel_op_combo.currentIndexChanged.connect(self._update_preview)
        form_adv.addRow("Operation:", self.rel_op_combo)

        self.rel_label_edit = QLineEdit("Connected Objects")
        self.rel_label_edit.textChanged.connect(self._update_preview)
        form_adv.addRow("Metric Label:", self.rel_label_edit)

        # Attributes list
        attr_box = QVBoxLayout()
        attr_lbl = QLabel("Detail Attributes (Checked to include):")
        attr_lbl.setStyleSheet("font-size: 8pt; font-weight: bold; color: #475569;")
        self.attrs_list = QListWidget()
        self.attrs_list.setMaximumHeight(95)
        self.attrs_list.itemChanged.connect(self._update_preview)
        attr_box.addWidget(attr_lbl)
        attr_box.addWidget(self.attrs_list)

        self.adv_section.add_layout(form_adv)
        self.adv_section.add_layout(attr_box)
        scroll_layout.addWidget(self.adv_section)

        # 6. Collapsible: Live Preview & Expression
        self.section_preview = CollapsibleSection("👁️ Live Preview & Expression", initially_expanded=True)
        prev_layout = QVBoxLayout()
        prev_layout.setContentsMargins(4, 4, 4, 4)
        prev_layout.setSpacing(4)

        # Sample Feature Navigator
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)
        self.btn_prev_feat = QPushButton("◀ Prev")
        self.btn_prev_feat.setObjectName("quietButton")
        self.btn_prev_feat.clicked.connect(self._nav_prev_feature)

        self.feat_nav_lbl = QLabel("Sample Feature: 1")
        self.feat_nav_lbl.setStyleSheet("font-size: 7.5pt; font-weight: 600; color: #64748b;")
        align_center = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignCenter", 0)
        self.feat_nav_lbl.setAlignment(align_center)

        self.btn_next_feat = QPushButton("Next ▶")
        self.btn_next_feat.setObjectName("quietButton")
        self.btn_next_feat.clicked.connect(self._nav_next_feature)

        self.btn_cycle_feat = QPushButton("🔀 Cycle")
        self.btn_cycle_feat.setObjectName("quietButton")
        self.btn_cycle_feat.clicked.connect(self._nav_cycle_feature)

        nav_row.addWidget(self.btn_prev_feat)
        nav_row.addWidget(self.feat_nav_lbl, 1)
        nav_row.addWidget(self.btn_next_feat)
        nav_row.addWidget(self.btn_cycle_feat)
        prev_layout.addLayout(nav_row)

        self.preview_tabs = QTabWidget()
        self.preview_box = QTextBrowser()
        self.preview_box.setObjectName("previewBox")
        self.preview_box.setMinimumHeight(120)
        self.preview_box.setMaximumHeight(260)
        self.preview_box.setOpenLinks(False)
        self.preview_box.anchorClicked.connect(self._on_preview_link_clicked)
        self.preview_tabs.addTab(self.preview_box, "Rendered Card")

        self.expr_box = QPlainTextEdit()
        self.expr_box.setReadOnly(True)
        self.expr_box.setMinimumHeight(120)
        self.expr_box.setMaximumHeight(260)
        self.expr_box.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 7.5pt; background-color: #0f172a; color: #38bdf8; border-radius: 4px; padding: 4px;"
        )
        self.preview_tabs.addTab(self.expr_box, "Expression Code")
        prev_layout.addWidget(self.preview_tabs)

        prev_btn_row = QHBoxLayout()
        self.copy_html_btn = QPushButton("📋 Copy HTML / Expression")
        self.copy_html_btn.setObjectName("quietButton")
        self.copy_html_btn.clicked.connect(self._copy_html_to_clipboard)
        self.preview_status_lbl = QLabel("")
        self.preview_status_lbl.setStyleSheet("font-size: 7.5pt; color: #10b981; font-weight: bold;")
        prev_btn_row.addWidget(self.copy_html_btn)
        prev_btn_row.addWidget(self.preview_status_lbl)
        prev_btn_row.addStretch()
        prev_layout.addLayout(prev_btn_row)

        self.section_preview.add_layout(prev_layout)
        scroll_layout.addWidget(self.section_preview)

        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll, 1)

        # Bottom Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(6, 4, 6, 6)
        btn_layout.setSpacing(6)
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.setObjectName("secondaryAction")
        self.clear_btn.clicked.connect(self._clear_maptip_from_layer)

        self.apply_btn = QPushButton("🚀 Apply MapTip to Layer")
        self.apply_btn.setObjectName("primaryAction")
        self.apply_btn.clicked.connect(self._apply_maptip_to_layer)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.apply_btn, 1)
        outer_layout.addLayout(btn_layout)

    def _build_actions_tab(self, parent: QWidget) -> None:
        outer_layout = QVBoxLayout(parent)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # 1. Collapsible: Action Library
        self.sec_actions = CollapsibleSection("⚡ 1-Click Action Library", initially_expanded=True)
        act_box = QVBoxLayout()
        act_box.setContentsMargins(4, 4, 4, 4)
        act_box.setSpacing(4)

        self.action_checkboxes: dict[str, QCheckBox] = {}
        for item in AVAILABLE_ACTIONS:
            cb = QCheckBox(item["name"])
            cb.setToolTip(item["description"])
            cb.setChecked(item["key"] in ("google_satellite", "google_streetview", "tkgm_cadastre", "copy_clipboard", "export_card_report"))
            act_box.addWidget(cb)
            self.action_checkboxes[item["key"]] = cb

        # Open File Option
        file_box = QHBoxLayout()
        file_box.setSpacing(4)
        self.cb_open_file = QCheckBox("Open File/Link:")
        self.cb_open_file.setToolTip("Open local file path or URL stored in an attribute")
        self.file_field_combo = QComboBox()
        file_box.addWidget(self.cb_open_file)
        file_box.addWidget(self.file_field_combo, 1)
        act_box.addLayout(file_box)

        # Select Intersecting in Another Layer
        sel_box = QHBoxLayout()
        sel_box.setSpacing(4)
        self.cb_sel_intersect = QCheckBox("Select Intersecting:")
        self.cb_sel_intersect.setToolTip("Select intersecting features in target layer upon click")
        self.sel_layer_combo = QComboBox()
        sel_box.addWidget(self.cb_sel_intersect)
        sel_box.addWidget(self.sel_layer_combo, 1)
        act_box.addLayout(sel_box)

        self.inject_actions_btn = QPushButton("⚡ Inject Selected Actions into Layer")
        self.inject_actions_btn.setObjectName("primaryAction")
        cursor = getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor", None)
        if cursor is not None:
            self.inject_actions_btn.setCursor(cursor)
        self.inject_actions_btn.clicked.connect(self._apply_actions)
        act_box.addWidget(self.inject_actions_btn)

        self.sec_actions.add_layout(act_box)
        layout.addWidget(self.sec_actions)

        # 2. Collapsible: Active Actions Inventory
        self.sec_inventory = CollapsibleSection("📋 Layer Actions Inventory", initially_expanded=True)
        inv_box = QVBoxLayout()
        inv_box.setContentsMargins(4, 4, 4, 4)
        inv_box.setSpacing(4)

        self.active_actions_header = QLabel("No active actions on current layer")
        self.active_actions_header.setStyleSheet("font-size: 7.5pt; font-weight: bold; color: #0f766e;")
        inv_box.addWidget(self.active_actions_header)

        self.active_actions_list = QListWidget()
        self.active_actions_list.setMaximumHeight(85)
        self.active_actions_list.setStyleSheet(
            "QListWidget { border: 1px solid #cbd5e1; border-radius: 4px; background: #ffffff; padding: 2px; font-size: 8pt; }"
            "QListWidget::item { padding: 3px 5px; border-bottom: 1px solid #f1f5f9; }"
            "QListWidget::item:selected { background: #0f766e; color: #ffffff; border-radius: 3px; }"
        )
        inv_box.addWidget(self.active_actions_list)

        inv_btn_row = QHBoxLayout()
        inv_btn_row.setSpacing(4)
        self.btn_run_action = QPushButton("▶ Run on Feature")
        self.btn_run_action.setObjectName("quietButton")
        self.btn_run_action.setToolTip("Run selected action using the current sample feature")
        self.btn_run_action.clicked.connect(self._on_run_selected_action)

        self.btn_activate_qgis_tool = QPushButton("🎯 Canvas Action Tool")
        self.btn_activate_qgis_tool.setObjectName("quietButton")
        self.btn_activate_qgis_tool.setToolTip("Activate QGIS canvas 'Run Feature Action' tool to click map features")
        self.btn_activate_qgis_tool.clicked.connect(self._on_activate_qgis_action_tool)

        self.btn_clear_actions = QPushButton("🗑 Clear Actions")
        self.btn_clear_actions.setObjectName("quietButton")
        self.btn_clear_actions.setToolTip("Remove actions from the active layer")
        self.btn_clear_actions.clicked.connect(self._on_clear_layer_actions)

        inv_btn_row.addWidget(self.btn_run_action)
        inv_btn_row.addWidget(self.btn_activate_qgis_tool)
        inv_btn_row.addWidget(self.btn_clear_actions)
        inv_box.addLayout(inv_btn_row)

        self.sec_inventory.add_layout(inv_box)
        layout.addWidget(self.sec_inventory)

        # 3. Collapsible: Quick Canvas Cadastre (TKGM)
        self.sec_cadastre = CollapsibleSection("🇹🇷 Quick Canvas Cadastre (TKGM)", initially_expanded=True)
        cad_box = QVBoxLayout()
        cad_box.setContentsMargins(4, 4, 4, 4)
        cad_box.setSpacing(4)

        cadastre_strip = QFrame()
        cadastre_strip.setObjectName("cadastreCompactStrip")
        cadastre_strip.setStyleSheet(
            "QFrame#cadastreCompactStrip { background: #fffbeb; border: 1px solid #fde68a; border-radius: 4px; padding: 4px 6px; }"
        )
        cad_strip_layout = QVBoxLayout(cadastre_strip)
        cad_strip_layout.setContentsMargins(4, 4, 4, 4)
        cad_strip_layout.setSpacing(4)

        top_cad_row = QHBoxLayout()
        top_cad_row.setSpacing(5)
        tr_badge = QLabel("🇹🇷 TR")
        tr_badge.setStyleSheet(
            "background: #dc2626; color: #ffffff; font-weight: bold; font-size: 7pt; border-radius: 2px; padding: 1px 3px;"
        )
        tr_badge.setToolTip("Republic of Turkey Cadastral Coverage Only (TKGM MEGSİS)")
        cad_lbl = QLabel("<b>Instant Canvas Cadastre:</b>")
        cad_lbl.setStyleSheet("font-size: 8pt; color: #78350f;")
        top_cad_row.addWidget(tr_badge)
        top_cad_row.addWidget(cad_lbl)
        top_cad_row.addStretch()
        cad_strip_layout.addLayout(top_cad_row)

        self.btn_canvas_cadastre = QPushButton("⚡ Click Canvas to Download Parcel")
        self.btn_canvas_cadastre.setObjectName("amberCompact")
        self.btn_canvas_cadastre.setToolTip(
            "Click anywhere on map canvas to query and download the parcel polygon into QGIS without selecting a layer (Turkey Only, ~100 daily fair-use quota)"
        )
        self.btn_canvas_cadastre.setStyleSheet(
            "QPushButton { background: #d97706; color: #ffffff; font-weight: bold; border-radius: 3px; padding: 4px 8px; font-size: 8pt; }"
            "QPushButton:hover { background: #b45309; }"
        )
        if cursor is not None:
            self.btn_canvas_cadastre.setCursor(cursor)
        self.btn_canvas_cadastre.clicked.connect(self._toggle_canvas_cadastre_tool)
        cad_strip_layout.addWidget(self.btn_canvas_cadastre)

        cad_note = QLabel("1-click parcel download into 'TKGM Parselleri (TR)' layer with centroid labels.")
        cad_note.setStyleSheet("font-size: 7.5pt; color: #92400e;")
        cad_note.setWordWrap(True)
        cad_strip_layout.addWidget(cad_note)

        cad_box.addWidget(cadastre_strip)
        self.sec_cadastre.add_layout(cad_box)
        layout.addWidget(self.sec_cadastre)

        # 4. Collapsible: 3 Ways to Trigger Layer Actions Guide
        self.sec_guide = CollapsibleSection("💡 3 Ways to Trigger Layer Actions", initially_expanded=False)
        guide_box = QFrame()
        guide_box.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 4px; }"
        )
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.setContentsMargins(4, 4, 4, 4)
        guide_layout.setSpacing(2)
        guide_item1 = QLabel("1. <b>Inside MapTip:</b> Hover feature on canvas, click action pills directly.")
        guide_item1.setStyleSheet("font-size: 7.5pt; color: #475569;")
        guide_item2 = QLabel("2. <b>On Canvas:</b> Click '🎯 Canvas Action Tool' and click any feature on map.")
        guide_item2.setStyleSheet("font-size: 7.5pt; color: #475569;")
        guide_item3 = QLabel("3. <b>In Tables:</b> Right-click any row in Attribute Table or Identify dialog.")
        guide_item3.setStyleSheet("font-size: 7.5pt; color: #475569;")
        guide_layout.addWidget(guide_item1)
        guide_layout.addWidget(guide_item2)
        guide_layout.addWidget(guide_item3)
        self.sec_guide.add_widget(guide_box)
        layout.addWidget(self.sec_guide)

        layout.addStretch()
        scroll.setWidget(scroll_content)
        outer_layout.addWidget(scroll)

    def _build_hud_tab(self, parent: QWidget) -> None:
        outer_layout = QVBoxLayout(parent)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Collapsible: Inspector & Pin Controls
        self.sec_hud_ctrl = CollapsibleSection("🎯 Canvas MapTip Inspector & Pin", initially_expanded=True)
        form_hud = QFormLayout()
        form_hud.setContentsMargins(4, 4, 4, 4)
        form_hud.setSpacing(4)

        hud_switch_row = QHBoxLayout()
        hud_switch_lbl = QLabel("Interactive Inspector Active:")
        hud_switch_lbl.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        self.hud_switch = IOSToggleSwitch(default_on=False, width=46, height=22)
        self.hud_switch.setToolTip("Activate real-time canvas feature inspection & 1-click pinning")
        self.hud_switch.toggled.connect(self._toggle_hud)
        hud_switch_row.addWidget(hud_switch_lbl)
        hud_switch_row.addStretch()
        hud_switch_row.addWidget(self.hud_switch)
        form_hud.addRow(hud_switch_row)

        self.hud_pin_cb = QCheckBox("📌 Click Canvas to PIN / Freeze Card")
        self.hud_pin_cb.setChecked(True)
        self.hud_pin_cb.setToolTip("Click any feature on canvas to freeze its card in place so buttons can be clicked")
        self.hud_pin_cb.toggled.connect(lambda c: self._hud.set_click_to_pin(c))
        form_hud.addRow("", self.hud_pin_cb)

        self.hud_highlight_cb = QCheckBox("✨ Glowing Feature Highlight on Canvas")
        self.hud_highlight_cb.setChecked(True)
        self.hud_highlight_cb.setToolTip("Draws an outline on the canvas around the inspected feature (Cyan=hover, Gold=pinned)")
        self.hud_highlight_cb.toggled.connect(lambda c: self._hud.set_highlight_enabled(c))
        form_hud.addRow("", self.hud_highlight_cb)

        self.hud_cursor_cb = QCheckBox("🎯 High-Visibility Reticle Cursor")
        self.hud_cursor_cb.setChecked(True)
        self.hud_cursor_cb.setToolTip("Replaces standard pointer with inspection crosshairs on canvas")
        self.hud_cursor_cb.toggled.connect(self._on_hud_cursor_toggled)
        form_hud.addRow("", self.hud_cursor_cb)

        self.hud_debounce_spin = QSpinBox()
        self.hud_debounce_spin.setRange(100, 1000)
        self.hud_debounce_spin.setValue(200)
        self.hud_debounce_spin.setSuffix(" ms")
        self.hud_debounce_spin.valueChanged.connect(self._on_hud_debounce_changed)
        form_hud.addRow("Dwell Debounce:", self.hud_debounce_spin)

        self.sec_hud_ctrl.add_layout(form_hud)
        layout.addWidget(self.sec_hud_ctrl)

        # 2. Collapsible: Inspected / Pinned Feature Hub
        self.sec_hud_feed = CollapsibleSection("📌 Inspected / Pinned Feature Hub", initially_expanded=True)
        hub_layout = QVBoxLayout()
        hub_layout.setContentsMargins(4, 4, 4, 4)
        hub_layout.setSpacing(5)

        self.hud_status_badge = QLabel("⚪ Standby — Hover over map or click any feature to pin")
        self.hud_status_badge.setStyleSheet(
            "background-color: #1e293b; color: #94a3b8; font-size: 8pt; font-weight: bold; "
            "padding: 5px 8px; border-radius: 4px; border: 1px solid #334155;"
        )
        hub_layout.addWidget(self.hud_status_badge)

        # Action Buttons Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(4)

        self.btn_hud_pin = QPushButton("📌 Pin Card")
        self.btn_hud_pin.setToolTip("Toggle pin/freeze of the current card on canvas")
        self.btn_hud_pin.setStyleSheet("font-size: 8pt; font-weight: bold; padding: 4px 6px;")
        self.btn_hud_pin.clicked.connect(self._on_hud_toggle_pin)
        actions_row.addWidget(self.btn_hud_pin)

        self.btn_hud_zoom = QPushButton("🔍 Zoom")
        self.btn_hud_zoom.setToolTip("Zoom canvas directly to this inspected feature")
        self.btn_hud_zoom.setStyleSheet("font-size: 8pt; padding: 4px 6px;")
        self.btn_hud_zoom.clicked.connect(self._on_hud_zoom_feature)
        actions_row.addWidget(self.btn_hud_zoom)

        self.btn_hud_copy = QPushButton("📋 Copy")
        self.btn_hud_copy.setToolTip("Copy all attributes of this feature to clipboard")
        self.btn_hud_copy.setStyleSheet("font-size: 8pt; padding: 4px 6px;")
        self.btn_hud_copy.clicked.connect(self._on_hud_copy_feature)
        actions_row.addWidget(self.btn_hud_copy)

        self.btn_hud_export = QPushButton("📄 Report")
        self.btn_hud_export.setToolTip("Export feature card report as HTML and open in browser")
        self.btn_hud_export.setStyleSheet("font-size: 8pt; padding: 4px 6px;")
        self.btn_hud_export.clicked.connect(self._on_hud_export_feature)
        actions_row.addWidget(self.btn_hud_export)

        hub_layout.addLayout(actions_row)

        self.hud_live_browser = QTextBrowser()
        self.hud_live_browser.setMinimumHeight(160)
        self.hud_live_browser.setMaximumHeight(300)
        self.hud_live_browser.setStyleSheet(
            "background-color: #0f172a; color: #f8fafc; border-radius: 6px; border: 1px solid #334155; font-size: 8pt;"
        )
        self.hud_live_browser.setHtml(
            "<div style='color:#64748b; font-size:8pt; padding:12px; text-align:center;'>"
            "Hover over any feature on the map canvas to inspect its MapTip card in real time.<br><br>"
            "<b>Click</b> on the feature to <b>PIN</b> it in place so you can click links or examine adjacent layers."
            "</div>"
        )
        hub_layout.addWidget(self.hud_live_browser)
        self.sec_hud_feed.add_layout(hub_layout)
        layout.addWidget(self.sec_hud_feed)

        # 3. Collapsible: Attributes Breakdown
        self.sec_hud_attrs = CollapsibleSection("📋 Feature Attributes Breakdown", initially_expanded=False)
        attr_layout = QVBoxLayout()
        attr_layout.setContentsMargins(4, 4, 4, 4)
        attr_layout.setSpacing(4)

        self.hud_attr_table = QTableWidget()
        self.hud_attr_table.setColumnCount(2)
        self.hud_attr_table.setHorizontalHeaderLabels(["Field", "Value"])
        self.hud_attr_table.horizontalHeader().setStretchLastSection(True)
        self.hud_attr_table.verticalHeader().setVisible(False)
        edit_triggers = getattr(QTableWidget.EditTrigger, "NoEditTriggers", None)
        if edit_triggers is None:
            edit_triggers = getattr(QTableWidget, "NoEditTriggers", None)
        if edit_triggers is not None:
            self.hud_attr_table.setEditTriggers(edit_triggers)
        self.hud_attr_table.setMinimumHeight(120)
        self.hud_attr_table.setMaximumHeight(220)
        self.hud_attr_table.setStyleSheet(
            "QTableWidget { background-color: #0f172a; color: #cbd5e1; gridline-color: #1e293b; font-size: 8pt; border: 1px solid #334155; border-radius: 4px; } "
            "QHeaderView::section { background-color: #1e293b; color: #38bdf8; font-weight: bold; font-size: 8pt; padding: 2px 4px; border: none; }"
        )
        attr_layout.addWidget(self.hud_attr_table)
        self.sec_hud_attrs.add_layout(attr_layout)
        layout.addWidget(self.sec_hud_attrs)

        layout.addStretch()
        scroll.setWidget(scroll_content)
        outer_layout.addWidget(scroll)

    # ──────────────────────────────────────────────────────────────────────────
    # Layer & Event Handlers
    # ──────────────────────────────────────────────────────────────────────────

    def _on_layers_will_be_removed(self, layer_ids: Any) -> None:
        """Safely detach and clear layer bindings before C++ deletion."""
        target_ids = set(layer_ids) if isinstance(layer_ids, (list, tuple, set)) else {str(layer_ids)}
        if self._current_layer_id and self._current_layer_id in target_ids:
            if hasattr(self, "_current_layer") and is_layer_alive(self._current_layer) and isinstance(self._current_layer, QgsVectorLayer):
                with contextlib.suppress(Exception):
                    self._current_layer.selectionChanged.disconnect(self._on_layer_selection_changed)
            self._current_layer = None
            self._current_layer_id = None
            if hasattr(self, "_hud") and self._hud:
                self._hud.set_vector_layer(None)

    def _refresh_layers(self, *args: Any) -> None:
        target_id = None
        active_lyr = self.iface.activeLayer() if hasattr(self.iface, "activeLayer") else None
        if is_layer_alive(active_lyr):
            target_id = active_lyr.id()
        elif self._current_layer_id and QgsProject.instance().mapLayer(self._current_layer_id):
            target_id = self._current_layer_id
        else:
            target_id = self.layer_combo.currentData()

        self.layer_combo.blockSignals(True)
        self.rel_layer_combo.blockSignals(True)
        self.sel_layer_combo.blockSignals(True)

        self.layer_combo.clear()
        self.rel_layer_combo.clear()
        self.sel_layer_combo.clear()

        layers = [lyr for lyr in QgsProject.instance().mapLayers().values() if is_layer_alive(lyr)]
        for lyr in layers:
            icon = "🗺️ " if isinstance(lyr, QgsVectorLayer) else "▦ "
            self.layer_combo.addItem(f"{icon}{lyr.name()}", lyr.id())
            if isinstance(lyr, QgsVectorLayer):
                self.rel_layer_combo.addItem(lyr.name(), lyr.name())
                self.sel_layer_combo.addItem(lyr.name(), lyr.name())

        self.layer_combo.blockSignals(False)
        self.rel_layer_combo.blockSignals(False)
        self.sel_layer_combo.blockSignals(False)

        if self.layer_combo.count() > 0:
            target_idx = -1
            if target_id:
                target_idx = self.layer_combo.findData(target_id)
            if target_idx < 0:
                for i in range(self.layer_combo.count()):
                    lyr = QgsProject.instance().mapLayer(self.layer_combo.itemData(i))
                    if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer):
                        target_idx = i
                        break
                if target_idx < 0:
                    target_idx = 0

            if self.layer_combo.currentIndex() != target_idx:
                self.layer_combo.setCurrentIndex(target_idx)
            # Crucial: Always explicitly invoke _on_target_layer_selected.
            # In Qt, if target_idx == currentIndex (e.g. 0 when 1 item exists),
            # setCurrentIndex does not emit currentIndexChanged!
            self._on_target_layer_selected(target_idx)
        else:
            self._on_target_layer_selected(-1)

    def _on_qgis_active_layer_changed(self, layer: Optional[QgsMapLayer]) -> None:
        if is_layer_alive(layer):
            idx = self.layer_combo.findData(layer.id())
            if idx >= 0:
                if idx != self.layer_combo.currentIndex():
                    self.layer_combo.setCurrentIndex(idx)
                elif self._current_layer is None or (self._current_layer_id != layer.id()):
                    self._on_target_layer_selected(idx)
            else:
                self._refresh_layers()

    def _resolve_target_layer(self) -> Optional[QgsVectorLayer]:
        """Defensively resolves and guarantees an active vector layer is bound if available."""
        if is_layer_alive(self._current_layer) and isinstance(self._current_layer, QgsVectorLayer):
            return self._current_layer

        if hasattr(self.iface, "activeLayer"):
            act = self.iface.activeLayer()
            if is_layer_alive(act) and isinstance(act, QgsVectorLayer):
                idx = self.layer_combo.findData(act.id())
                if idx >= 0:
                    if self.layer_combo.currentIndex() != idx:
                        self.layer_combo.setCurrentIndex(idx)
                    self._on_target_layer_selected(idx)
                    if is_layer_alive(self._current_layer) and isinstance(self._current_layer, QgsVectorLayer):
                        return self._current_layer
                    return act
                else:
                    self._refresh_layers()
                    if is_layer_alive(self._current_layer) and isinstance(self._current_layer, QgsVectorLayer):
                        return self._current_layer

        if self.layer_combo.count() > 0:
            idx = self.layer_combo.currentIndex()
            if idx < 0:
                idx = 0
            lyr_id = self.layer_combo.itemData(idx) or self.layer_combo.currentData()
            if lyr_id:
                lyr = QgsProject.instance().mapLayer(lyr_id)
                if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer):
                    self._on_target_layer_selected(idx)
                    return lyr

            for i in range(self.layer_combo.count()):
                lid = self.layer_combo.itemData(i)
                if lid:
                    lyr = QgsProject.instance().mapLayer(lid)
                    if is_layer_alive(lyr) and isinstance(lyr, QgsVectorLayer):
                        self.layer_combo.setCurrentIndex(i)
                        self._on_target_layer_selected(i)
                        return lyr

        return None

    def _on_target_layer_selected(self, index: int) -> None:
        if hasattr(self, "_current_layer") and is_layer_alive(self._current_layer) and isinstance(self._current_layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                self._current_layer.selectionChanged.disconnect(self._on_layer_selection_changed)

        if index < 0 or self.layer_combo.count() == 0:
            self._current_layer = None
            self._current_layer_id = None
            self.layer_info_label.setText("No layer selected")
            self._update_preview()
            return

        lyr_id = self.layer_combo.itemData(index) if 0 <= index < self.layer_combo.count() else self.layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(lyr_id) if lyr_id else None

        if not is_layer_alive(layer):
            self._current_layer = None
            self._current_layer_id = None
            self.layer_info_label.setText("Invalid layer")
            self._update_preview()
            return

        self._current_layer = layer
        self._current_layer_id = layer.id()

        if isinstance(layer, QgsVectorLayer):
            cnt = layer.featureCount()
            geom = layer.geometryType()
            geom_names = {0: "Point", 1: "Line", 2: "Polygon", 3: "Unknown", 4: "Null"}
            self.layer_info_label.setText(
                f"Vector ({geom_names.get(geom, 'Unknown')}) · {cnt:,} features · CRS: {layer.crs().authid()}"
            )
            self._populate_vector_fields(layer)
            self._hud.set_vector_layer(layer)
            self._refresh_active_actions_list()
            with contextlib.suppress(Exception):
                layer.selectionChanged.connect(self._on_layer_selection_changed)
        elif isinstance(layer, QgsRasterLayer):
            self.layer_info_label.setText(
                f"Raster · {layer.bandCount()} bands · {layer.width()}x{layer.height()} · CRS: {layer.crs().authid()}"
            )
            self._hud.set_active_raster(layer)
            self._refresh_active_actions_list()

        self._update_preview()

    def _on_layer_selection_changed(self) -> None:
        """Reactively synchronize live card preview when canvas feature selection changes."""
        if not is_layer_alive(self._current_layer) or not isinstance(self._current_layer, QgsVectorLayer):
            return
        selected = self._current_layer.selectedFeatures()
        if selected:
            self._sample_features = selected[:25]
            self._sample_feat_index = 0
        else:
            self._reload_sample_features()
        self._schedule_preview_update()

    def _reload_sample_features(self) -> None:
        """Fetch up to 50 sample features for rapid card preview cycling."""
        self._sample_features = []
        self._sample_feat_index = 0
        if is_layer_alive(self._current_layer) and isinstance(self._current_layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                req = QgsFeatureRequest()
                req.setFlags(QgsFeatureRequest.Flag.NoGeometry)
                req.setLimit(50)
                for feat in self._current_layer.getFeatures(req):
                    self._sample_features.append(feat)

    def _populate_vector_fields(self, layer: QgsVectorLayer) -> None:
        combos = [
            self.title_field_combo,
            self.sub_field_combo,
            self.kpi_field_combo,
            self.media_field_combo,
            self.file_field_combo,
            self.cond_field_combo,
        ]
        prev_selections = {cb: (cb.currentData() or cb.currentText()) for cb in combos}

        for cb in combos:
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("(None)", "")

        self.attrs_list.blockSignals(True)
        self.attrs_list.clear()

        fields = layer.fields()
        field_names = fields.names()
        for f in fields:
            name = f.name()
            for cb in combos:
                cb.addItem(name, name)

            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.attrs_list.addItem(item)

        # Cache sample features for responsive live card testing
        self._reload_sample_features()

        # Restore title field or apply heuristic
        prev_title = prev_selections.get(self.title_field_combo)
        if prev_title and prev_title in field_names:
            self.title_field_combo.setCurrentText(prev_title)
        else:
            for name in field_names:
                nl = name.lower()
                if any(k in nl for k in ("ad", "name", "title", "id", "label")):
                    self.title_field_combo.setCurrentText(name)
                    break

        # Restore subtitle field or apply heuristic
        prev_sub = prev_selections.get(self.sub_field_combo)
        if prev_sub and prev_sub in field_names:
            self.sub_field_combo.setCurrentText(prev_sub)
        else:
            for name in field_names:
                nl = name.lower()
                if any(k in nl for k in ("tip", "tur", "type", "fonksiyon", "class", "kat", "status", "kategori")):
                    self.sub_field_combo.setCurrentText(name)
                    break

        # Restore KPI & condition fields or apply heuristic
        prev_kpi = prev_selections.get(self.kpi_field_combo)
        if prev_kpi and prev_kpi in field_names:
            self.kpi_field_combo.setCurrentText(prev_kpi)
            prev_cond = prev_selections.get(self.cond_field_combo)
            if prev_cond and prev_cond in field_names:
                self.cond_field_combo.setCurrentText(prev_cond)
        else:
            for name in field_names:
                nl = name.lower()
                if any(k in nl for k in ("alan", "area", "skor", "score", "fiyat", "price", "deger", "count", "kapasite", "capacity", "nufus", "pop")):
                    self.kpi_field_combo.setCurrentText(name)
                    self.cond_field_combo.setCurrentText(name)
                    if not self.kpi_label_edit.text():
                        if any(k in nl for k in ("alan", "area")):
                            self.kpi_label_edit.setText("Surface Area")
                            self.kpi_unit_edit.setText("m²")
                        elif any(k in nl for k in ("fiyat", "price", "deger")):
                            self.kpi_label_edit.setText("Market Valuation")
                            self.kpi_unit_edit.setText("$")
                        elif any(k in nl for k in ("kapasite", "capacity")):
                            self.kpi_label_edit.setText("Capacity")
                            self.kpi_unit_edit.setText("units")
                        elif any(k in nl for k in ("nufus", "pop")):
                            self.kpi_label_edit.setText("Population")
                            self.kpi_unit_edit.setText("inh.")
                        elif any(k in nl for k in ("skor", "score")):
                            self.kpi_label_edit.setText("Index Score")
                            self.kpi_unit_edit.setText("pts")
                    break

        # Restore media field or apply heuristic
        prev_media = prev_selections.get(self.media_field_combo)
        if prev_media and prev_media in field_names:
            self.media_field_combo.setCurrentText(prev_media)
        else:
            for name in field_names:
                nl = name.lower()
                if any(k in nl for k in ("foto", "photo", "image", "resim", "img", "media", "url")):
                    self.media_field_combo.setCurrentText(name)
                    break

        # Restore file field or apply heuristic
        prev_file = prev_selections.get(self.file_field_combo)
        if prev_file and prev_file in field_names:
            self.file_field_combo.setCurrentText(prev_file)
        else:
            for name in field_names:
                nl = name.lower()
                if any(k in nl for k in ("file", "dosya", "doc", "pdf", "link", "url", "web")):
                    self.file_field_combo.setCurrentText(name)
                    break

        for cb in combos:
            cb.blockSignals(False)
        self.attrs_list.blockSignals(False)

        self._refresh_donut_combos_from_layer()
        if self.archetype_combo.currentData() == Archetype.DONUT_CHART:
            layer_fnames = fields.names()
            valid_slices = [s for s in self._get_donut_slices_from_ui() if s[0] in layer_fnames]
            if len(valid_slices) < 2:
                self._auto_detect_donut_fields()

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

        # Donut Chart
        if config.archetype == Archetype.DONUT_CHART:
            ui_slices = self._get_donut_slices_from_ui()
            if ui_slices:
                config.donut_fields = ui_slices
            elif getattr(self, "_preset_donut_fields", None):
                config.donut_fields = self._preset_donut_fields
            elif attrs:
                donut_palette = DEFAULT_DONUT_PALETTE
                config.donut_fields = [
                    (fld, lbl or fld, donut_palette[i % len(donut_palette)])
                    for i, (fld, lbl) in enumerate(attrs[:5])
                ]

        # Sparklines
        if config.archetype == Archetype.SPARKLINE:
            if getattr(self, "_preset_sparkline_fields", None):
                config.sparkline_fields = self._preset_sparkline_fields
            else:
                config.sparkline_fields = [fld for fld, _ in attrs[:6]]

        config.format_numbers = self.cb_format_numbers.isChecked()
        config.decimal_places = self.spin_decimals.value()
        config.null_text = self.edit_null_text.text().strip() or "—"
        config.media_fallback = self.combo_media_fallback.currentData() or "placeholder"
        config.show_action_buttons = self.cb_card_actions.isChecked()
        if hasattr(self, "action_checkboxes"):
            config.card_action_keys = [k for k, cb in self.action_checkboxes.items() if cb.isChecked()]

        return config

    def _on_archetype_changed(self) -> None:
        arch = self.archetype_combo.currentData()
        if hasattr(self, "sec_donut"):
            is_donut = (arch == Archetype.DONUT_CHART)
            self.sec_donut.setVisible(is_donut)
            if is_donut:
                self.sec_donut.set_expanded(True)
                if not self._donut_slice_rows:
                    self._auto_detect_donut_fields()
        if arch != Archetype.DONUT_CHART:
            self._preset_donut_fields = None
        if arch != Archetype.SPARKLINE:
            self._preset_sparkline_fields = None
        self._update_preview()

    def _refresh_donut_combos_from_layer(self) -> None:
        if not hasattr(self, "_donut_slice_rows") or not is_layer_alive(self._current_layer):
            return
        fields = self._current_layer.fields()
        for row in self._donut_slice_rows:
            combo = row["combo"]
            curr_val = combo.currentData() or combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(None)", "")
            for f in fields:
                fn = f.name()
                is_num = _is_numeric_field(f)
                display_name = f"🔢 {fn}" if is_num else fn
                combo.addItem(display_name, fn)
            idx = combo.findData(curr_val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _add_donut_slice(self, field_name: str = "", label: str = "", color: str = "") -> None:
        if len(self._donut_slice_rows) >= 6:
            return
        if not color:
            color = DEFAULT_DONUT_PALETTE[len(self._donut_slice_rows) % len(DEFAULT_DONUT_PALETTE)]

        row_w = QWidget()
        h = QHBoxLayout(row_w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(3)

        btn_color = QPushButton()
        btn_color.setFixedSize(22, 22)
        btn_color.setStyleSheet(f"background-color: {color}; border: 1px solid #94a3b8; border-radius: 3px;")
        cursor = getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor", None)
        if cursor is not None:
            btn_color.setCursor(cursor)
        btn_color.setToolTip("Click to customize slice color")

        combo_fld = QComboBox()
        combo_fld.addItem("(None)", "")
        if is_layer_alive(self._current_layer):
            for f in self._current_layer.fields():
                fn = f.name()
                is_num = _is_numeric_field(f)
                combo_fld.addItem(f"🔢 {fn}" if is_num else fn, fn)

        if field_name:
            idx = combo_fld.findData(field_name)
            if idx >= 0:
                combo_fld.setCurrentIndex(idx)
            else:
                combo_fld.addItem(field_name, field_name)
                combo_fld.setCurrentText(field_name)

        clean_label = label or (field_name.replace("_", " ").title() if field_name else "")
        edit_lbl = QLineEdit(clean_label)
        edit_lbl.setPlaceholderText("Label")
        edit_lbl.setMaximumWidth(85)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(22, 22)
        btn_del.setObjectName("quietButton")
        btn_del.setToolTip("Remove slice")

        h.addWidget(btn_color)
        h.addWidget(combo_fld, 1)
        h.addWidget(edit_lbl)
        h.addWidget(btn_del)

        row_info = {
            "widget": row_w,
            "btn_color": btn_color,
            "combo": combo_fld,
            "label": edit_lbl,
            "btn_del": btn_del,
            "color": color,
        }
        self._donut_slice_rows.append(row_info)
        self.donut_slices_container.addWidget(row_w)

        def on_color_clicked(checked=False, r=row_info):
            new_color = QColorDialog.getColor(QColor(r["color"]), self, "Select Slice Color")
            if new_color.isValid():
                hex_clr = new_color.name()
                r["color"] = hex_clr
                r["btn_color"].setStyleSheet(f"background-color: {hex_clr}; border: 1px solid #94a3b8; border-radius: 3px;")
                self._update_preview()

        def on_combo_changed(idx=0, r=row_info):
            fn = r["combo"].currentData() or r["combo"].currentText()
            if fn and fn != "(None)":
                current_lbl = r["label"].text().strip()
                if not current_lbl:
                    r["label"].setText(fn.replace("_", " ").title())
            self._update_preview()

        def on_del_clicked(checked=False, r=row_info):
            if r in self._donut_slice_rows:
                self._donut_slice_rows.remove(r)
            r["widget"].setParent(None)
            r["widget"].deleteLater()
            self._update_preview()

        btn_color.clicked.connect(on_color_clicked)
        combo_fld.currentIndexChanged.connect(on_combo_changed)
        edit_lbl.textChanged.connect(self._update_preview)
        btn_del.clicked.connect(on_del_clicked)

    def _on_add_donut_slice_clicked(self) -> None:
        selected_fields = {r["combo"].currentData() for r in self._donut_slice_rows}
        next_field = ""
        if is_layer_alive(self._current_layer):
            for f in self._current_layer.fields():
                fn = f.name()
                is_num = _is_numeric_field(f)
                if is_num and fn not in selected_fields and fn.lower() not in ("fid", "id", "gid", "objectid"):
                    next_field = fn
                    break
        self._add_donut_slice(field_name=next_field)
        self._update_preview()

    def _auto_detect_donut_fields(self) -> None:
        if not is_layer_alive(self._current_layer):
            return
        num_fields = [f.name() for f in self._current_layer.fields() if _is_numeric_field(f)]

        candidates = [
            fn for fn in num_fields
            if fn.lower() not in ("fid", "id", "gid", "objectid", "shape_leng", "shape_area", "st_length", "st_area")
        ]
        if len(candidates) < 2 and num_fields:
            candidates = num_fields

        if not candidates:
            candidates = [f.name() for f in self._current_layer.fields()][:3]

        if candidates:
            self._clear_donut_slice_rows()
            for i, fn in enumerate(candidates[:4]):
                clr = DEFAULT_DONUT_PALETTE[i % len(DEFAULT_DONUT_PALETTE)]
                lbl = fn.replace("_", " ").title()
                self._add_donut_slice(field_name=fn, label=lbl, color=clr)
            self._update_preview()

    def _clear_donut_slice_rows(self) -> None:
        for row in getattr(self, "_donut_slice_rows", []):
            row["widget"].setParent(None)
            row["widget"].deleteLater()
        self._donut_slice_rows.clear()

    def _get_donut_slices_from_ui(self) -> list[tuple[str, str, str]]:
        slices = []
        for row in getattr(self, "_donut_slice_rows", []):
            combo = row["combo"]
            fld = combo.currentData() or combo.currentText()
            if fld and fld != "(None)":
                lbl = row["label"].text().strip() or fld
                slices.append((fld, lbl, row["color"]))
        return slices

    def _set_donut_slices_in_ui(self, slices: list[tuple[str, str, str]]) -> None:
        self._clear_donut_slice_rows()
        for fld, lbl, clr in slices:
            self._add_donut_slice(field_name=fld, label=lbl, color=clr)

    def _nav_prev_feature(self) -> None:
        if getattr(self, "_sample_features", []):
            self._sample_feat_index = (self._sample_feat_index - 1) % len(self._sample_features)
            self._update_preview()

    def _nav_next_feature(self) -> None:
        if getattr(self, "_sample_features", []):
            self._sample_feat_index = (self._sample_feat_index + 1) % len(self._sample_features)
            self._update_preview()

    def _nav_cycle_feature(self) -> None:
        if getattr(self, "_sample_features", []):
            jump = max(1, len(self._sample_features) // 4)
            self._sample_feat_index = (self._sample_feat_index + jump) % len(self._sample_features)
            self._update_preview()

    def _update_preview(self) -> None:
        config = self._build_config_from_ui()
        raw_html = compile_maptip_html(config)
        self._current_raw_html = raw_html
        if hasattr(self, "expr_box"):
            self.expr_box.setPlainText(raw_html)

        layer = self._resolve_target_layer()
        if is_layer_alive(layer) and isinstance(layer, QgsVectorLayer):
            sample_feature = None
            has_selection = bool(layer.selectedFeatureCount() > 0)
            if getattr(self, "_sample_features", []):
                idx = max(0, min(getattr(self, "_sample_feat_index", 0), len(self._sample_features) - 1))
                sample_feature = self._sample_features[idx]
                prefix = "Selected " if has_selection else "Feature "
                if hasattr(self, "feat_nav_lbl"):
                    self.feat_nav_lbl.setText(f"{prefix}{idx + 1} of {len(self._sample_features)} (ID: {sample_feature.id()})")
            else:
                with contextlib.suppress(Exception):
                    req = QgsFeatureRequest()
                    req.setFlags(QgsFeatureRequest.Flag.NoGeometry)
                    req.setLimit(1)
                    for feat in layer.getFeatures(req):
                        sample_feature = feat
                        break
                if not sample_feature:
                    with contextlib.suppress(Exception):
                        for feat in layer.getFeatures():
                            sample_feature = feat
                            break
                if sample_feature and hasattr(self, "feat_nav_lbl"):
                    self.feat_nav_lbl.setText(f"Feature ID: {sample_feature.id()}")

            # If layer has no features or features could not be read, synthesize a clean schema-matched mock feature
            if not sample_feature:
                mock_feat = QgsFeature(layer.fields())
                mock_feat.setValid(True)
                for f in layer.fields():
                    fname = f.name()
                    fn_lower = fname.lower()
                    type_lower = f.typeName().lower()
                    if any(k in fn_lower for k in ("id", "fid", "no", "kod", "code")):
                        mock_feat.setAttribute(fname, 101)
                    elif any(k in fn_lower for k in ("alan", "area", "uzunluk", "length", "boyut", "size", "m2", "metre")):
                        mock_feat.setAttribute(fname, 254.50)
                    elif any(k in fn_lower for k in ("tarih", "date", "time", "yil", "year")):
                        mock_feat.setAttribute(fname, "2026-09-12")
                    elif any(k in fn_lower for k in ("fiyat", "price", "deger", "val", "skor", "score", "oran", "rate")):
                        mock_feat.setAttribute(fname, 85.0)
                    elif any(k in fn_lower for k in ("foto", "photo", "image", "img", "url")):
                        mock_feat.setAttribute(fname, "")
                    elif "int" in type_lower or "long" in type_lower or "short" in type_lower:
                        mock_feat.setAttribute(fname, 42)
                    elif "double" in type_lower or "float" in type_lower or "real" in type_lower or "numeric" in type_lower:
                        mock_feat.setAttribute(fname, 73.50)
                    else:
                        mock_feat.setAttribute(fname, f"Sample {fname}")

                sample_feature = mock_feat
                if hasattr(self, "feat_nav_lbl"):
                    self.feat_nav_lbl.setText("Demo Sample (Layer has no records)")

            self._current_sample_feat = sample_feature
            ctx = QgsExpressionContext()
            ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
            ctx.setFeature(sample_feature)
            evaluated_html = QgsExpression.replaceExpressionText(raw_html, ctx)
            centered_html = f'<div align="center" style="margin:4px auto; padding:2px;">{evaluated_html}</div>'
            self.preview_box.setHtml(centered_html)
            if hasattr(self, "preview_tabs"):
                self.preview_tabs.setTabText(0, f"Rendered Card ({config.card_width} px)")
            return

        if hasattr(self, "feat_nav_lbl"):
            self.feat_nav_lbl.setText("No Vector Layer Selected")
        self._current_sample_feat = None
        empty_state_html = (
            '<div align="center" style="margin:20px auto; padding:24px 16px; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; text-align: center; color: #64748b;">'
            '<div style="font-size: 36px; margin-bottom: 8px;">🗺️</div>'
            '<div style="font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 4px;">No Vector Layer Selected</div>'
            '<div style="font-size: 12px; color: #64748b; line-height: 1.5; max-width: 280px; margin: 0 auto;">Select a vector layer above to preview live attribute cards and customized MapTips.</div>'
            '</div>'
        )
        self.preview_box.setHtml(empty_state_html)
        if hasattr(self, "preview_tabs"):
            self.preview_tabs.setTabText(0, f"Rendered Card ({config.card_width} px)")

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

    def _on_maptips_switch_toggled(self, checked: bool) -> None:
        if hasattr(self.iface, "actionMapTips") and self.iface.actionMapTips():
            action = self.iface.actionMapTips()
            if action.isChecked() != checked:
                action.trigger()
        self._sync_cursor_state()

    def _sync_maptip_action_state(self, checked: Optional[bool] = None) -> None:
        if not hasattr(self, "maptips_switch"):
            return
        if not hasattr(self.iface, "actionMapTips") or not self.iface.actionMapTips():
            self.maptips_switch.setEnabled(False)
            return
        is_active = self.iface.actionMapTips().isChecked() if checked is None else checked
        self.maptips_switch.setCheckedSilently(is_active)
        self._sync_cursor_state()

    def _apply_maptip_to_layer(self) -> None:
        layer = self._resolve_target_layer()
        if not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Qgis MapTips", "Please select a vector layer to apply the MapTip.")
            return

        config = self._build_config_from_ui()
        compiled_html = compile_maptip_html(config)
        layer.setMapTipTemplate(compiled_html)

        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushSuccess(
                "Qgis MapTips", f"MapTip applied successfully to '{layer.name()}'."
            )
        else:
            QMessageBox.information(self, "Qgis MapTips", "MapTip applied successfully!")

    def _clear_maptip_from_layer(self) -> None:
        layer = self._resolve_target_layer()
        if isinstance(layer, QgsVectorLayer):
            layer.setMapTipTemplate("")
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushInfo(
                    "Qgis MapTips", f"MapTip cleared from '{layer.name()}'."
                )

    def _apply_actions(self) -> None:
        layer = self._resolve_target_layer()
        if not isinstance(layer, QgsVectorLayer):
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
            layer,
            selected_keys,
            file_field=file_field,
            intersect_target_layer=intersect_tgt,
        )
        self._refresh_active_actions_list()
        self._update_preview()

        # Synchronize layer MapTip card template if action ribbon is enabled
        if self.cb_card_actions.isChecked():
            with contextlib.suppress(Exception):
                cfg = self._build_config_from_ui()
                html_text = compile_maptip_html(cfg)
                layer.setMapTipTemplate(html_text)

        msg = (
            f"{count} actions added to layer '{layer.name()}'.\n"
            f"Active scopes: Canvas, Feature, Field, Layer, Form."
        )
        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushSuccess("Qgis MapTips", msg)
        else:
            QMessageBox.information(self, "Qgis MapTips", msg)

    def _refresh_active_actions_list(self) -> None:
        if not hasattr(self, "active_actions_list"):
            return
        self.active_actions_list.clear()
        layer = self._resolve_target_layer()
        if not is_layer_alive(layer) or not isinstance(layer, QgsVectorLayer):
            self.active_actions_header.setText("Select a valid vector layer to view active actions")
            return

        actions = get_layer_actions(layer)
        if not actions:
            self.active_actions_header.setText(f"No actions currently attached to '{layer.name()}'. Click 'Inject' above.")
            return

        self.active_actions_header.setText(f"Active on '{layer.name()}' ({len(actions)} actions):")
        for act in actions:
            name_lower = act["name"].lower()
            if "satellite" in name_lower or "google" in name_lower:
                icon = "🌐"
            elif "street" in name_lower:
                icon = "📍"
            elif "osm" in name_lower or "openstreet" in name_lower:
                icon = "🗺️"
            elif "yandex" in name_lower:
                icon = "🧭"
            elif "tkgm" in name_lower:
                icon = "⚡" if ("hızlı" in name_lower or "instant" in name_lower or "0.2s" in name_lower) else "🏛️"
            elif "clipboard" in name_lower or "copy" in name_lower:
                icon = "📋"
            elif "report" in name_lower:
                icon = "📄"
            elif "intersect" in name_lower:
                icon = "🔗"
            elif "zoom" in name_lower:
                icon = "🔍"
            elif "buffer" in name_lower:
                icon = "🎯"
            else:
                icon = "⚡"

            scopes = act.get("scopes", [])
            scope_tag = f"[{', '.join(scopes)}]" if scopes else "[Canvas]"
            item_text = f"{icon} {act['name']}  —  {scope_tag}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, act)
            self.active_actions_list.addItem(item)

    def _on_run_selected_action(self) -> None:
        layer = self._resolve_target_layer()
        if not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Qgis MapTips", "Please select a vector layer.")
            return

        selected_items = self.active_actions_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Qgis MapTips", "Please select an action from the inventory list to test.")
            return

        act_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        feat = getattr(self, "_current_sample_feat", None)
        if not feat and isinstance(layer, QgsVectorLayer):
            sel = layer.selectedFeatures()
            feat = sel[0] if sel else None
        if not feat and isinstance(layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                for f in layer.getFeatures():
                    feat = f
                    break

        if not feat:
            QMessageBox.warning(self, "Qgis MapTips", "No feature available to run action on.")
            return

        act_name_lower = act_data.get("name", "").lower()
        cmd = act_data.get("command", "")
        act_type = str(act_data.get("type", ""))

        if "clipboard" in act_name_lower or "copy" in act_name_lower:
            self._copy_attributes_of_sample_feature()
        elif "report" in act_name_lower or "export" in act_name_lower:
            self._export_sample_card_report()
        elif "zoom" in act_name_lower or act_data.get("key") == "zoom_feature":
            self._zoom_to_sample_feature()
        elif "buffer" in act_name_lower or act_data.get("key") == "buffer_feature":
            self._buffer_sample_feature()
        elif "OpenUrl" in act_type or act_type == "0":
            ctx = QgsExpressionContext()
            ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
            ctx.setFeature(feat)
            expanded_url = QgsExpression.replaceExpressionText(cmd, ctx)
            QDesktopServices.openUrl(QUrl(expanded_url.strip()))
            if hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushSuccess(
                    "Qgis MapTips", f"Opened URL for '{act_data['name']}'."
                )
        else:
            with contextlib.suppress(Exception):
                layer.actions().doActionFeature(act_data["id"], feat)
            if hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushSuccess(
                    "Qgis MapTips", f"Executed '{act_data['name']}' on feature ID {feat.id()}."
                )

    def _on_activate_qgis_action_tool(self) -> None:
        if hasattr(self.iface, "actionFeatureAction") and self.iface.actionFeatureAction():
            self.iface.actionFeatureAction().trigger()
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushInfo(
                    "Qgis MapTips", "QGIS 'Run Feature Action' tool activated! Click any feature on the canvas."
                )
        else:
            QMessageBox.information(
                self, "Qgis MapTips", "Click the yellow gear 'Run Feature Action' icon in your QGIS toolbar."
            )

    def _on_clear_layer_actions(self) -> None:
        layer = self._resolve_target_layer()
        if not isinstance(layer, QgsVectorLayer):
            return
        count = remove_all_actions(layer)
        self._refresh_active_actions_list()
        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushInfo(
                "Qgis MapTips", f"Removed {count} actions from '{layer.name()}'."
            )

    def _toggle_canvas_cadastre_tool(self) -> None:
        if self.plugin and hasattr(self.plugin, "toggle_cadastre_tool"):
            self.plugin.toggle_cadastre_tool()
        elif self.canvas:
            from ..core.cadastre_tool import InteractiveCadastreTool
            if self._cadastre_tool is None:
                self._cadastre_tool = InteractiveCadastreTool(self.canvas, self.iface)
            if self.canvas.mapTool() == self._cadastre_tool:
                self.canvas.unsetMapTool(self._cadastre_tool)
                self.sync_cadastre_tool_state(False)
            else:
                self.canvas.setMapTool(self._cadastre_tool)
                self.sync_cadastre_tool_state(True)

    def sync_cadastre_tool_state(self, active: bool) -> None:
        if not hasattr(self, "btn_canvas_cadastre") or self.btn_canvas_cadastre is None:
            return
        if active:
            self.btn_canvas_cadastre.setText("🟢 Active (Click Map)")
            self.btn_canvas_cadastre.setStyleSheet(
                "QPushButton { background: #059669; color: #ffffff; font-weight: bold; border-radius: 3px; padding: 3px 8px; font-size: 8pt; }"
                "QPushButton:hover { background: #047857; }"
            )
        else:
            self.btn_canvas_cadastre.setText("⚡ Click Canvas to Download")
            self.btn_canvas_cadastre.setStyleSheet(
                "QPushButton { background: #d97706; color: #ffffff; font-weight: bold; border-radius: 3px; padding: 3px 8px; font-size: 8pt; }"
                "QPushButton:hover { background: #b45309; }"
            )

    def _on_preview_link_clicked(self, url: QUrl) -> None:
        url_str = url.toString()
        if url_str.startswith("action:copy_clipboard"):
            self._copy_attributes_of_sample_feature()
        elif url_str.startswith("action:export_card_report"):
            self._export_sample_card_report()
        elif url_str.startswith("action:zoom"):
            self._zoom_to_sample_feature()
        elif url_str.startswith("action:buffer"):
            self._buffer_sample_feature()
        elif url_str.startswith("action:tkgm") or url_str.startswith("action:parsel"):
            self._open_sample_tkgm_web()
        elif url_str.startswith("action:"):
            key = url_str.split(":", 1)[1]
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushInfo("Qgis MapTips", f"Action '{key}' clicked in preview.")
        else:
            QDesktopServices.openUrl(url)

    def _zoom_to_sample_feature(self) -> None:
        layer = self._resolve_target_layer()
        feat = getattr(self, "_current_sample_feat", None)
        if not feat and isinstance(layer, QgsVectorLayer):
            sel = layer.selectedFeatures()
            feat = sel[0] if sel else None
        if not feat and isinstance(layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                for f in layer.getFeatures():
                    feat = f
                    break
        canvas = self.canvas or (self.iface.mapCanvas() if self.iface else None)
        if feat and isinstance(layer, QgsVectorLayer) and canvas:
            zoom_to_feature(canvas, layer, feat, self.iface)
        elif hasattr(self.iface, "messageBar") and self.iface.messageBar():
            self.iface.messageBar().pushWarning("Qgis MapTips", "No feature available to zoom to.")

    def _buffer_sample_feature(self) -> None:
        layer = self._resolve_target_layer()
        feat = getattr(self, "_current_sample_feat", None)
        if not feat and isinstance(layer, QgsVectorLayer):
            sel = layer.selectedFeatures()
            feat = sel[0] if sel else None
        if not feat and isinstance(layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                for f in layer.getFeatures():
                    feat = f
                    break
        if feat and isinstance(layer, QgsVectorLayer):
            create_feature_buffer(layer, feat, 50.0, self.iface)
        elif hasattr(self.iface, "messageBar") and self.iface.messageBar():
            self.iface.messageBar().pushWarning("Qgis MapTips", "No feature available to buffer.")

    def _open_sample_tkgm_web(self) -> None:
        layer = self._resolve_target_layer()
        feat = getattr(self, "_current_sample_feat", None)
        if not feat and isinstance(layer, QgsVectorLayer):
            sel = layer.selectedFeatures()
            feat = sel[0] if sel else None
        if not feat and isinstance(layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                for f in layer.getFeatures():
                    feat = f
                    break
        if not feat or not feat.hasGeometry() or not isinstance(layer, QgsVectorLayer):
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning("TKGM Parsel Sorgu", "No feature with valid geometry found to open Parsel Sorgu.")
            return

        try:
            pos = feat.geometry().pointOnSurface() if not feat.geometry().pointOnSurface().isEmpty() else feat.geometry().centroid()
            pt = pos.asPoint()
            tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
            wgs = tr.transform(pt)
            lat, lon = round(wgs.y(), 6), round(wgs.x(), 6)
            url_str = f"https://parselsorgu.tkgm.gov.tr/#ara/cografi/{lat}/{lon}"
            QDesktopServices.openUrl(QUrl(url_str))
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushSuccess("TKGM Parsel Sorgu", f"Opened Parsel Sorgu in browser ({lat}, {lon}).")
        except Exception as exc:
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning("TKGM Parsel Sorgu", f"Could not open Parsel Sorgu: {exc}")

    def _copy_attributes_of_sample_feature(self) -> None:
        layer = self._resolve_target_layer()
        feat = getattr(self, "_current_sample_feat", None)
        if not feat and isinstance(layer, QgsVectorLayer):
            sel = layer.selectedFeatures()
            feat = sel[0] if sel else None
        if not feat and isinstance(layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                for f in layer.getFeatures():
                    feat = f
                    break
        if feat and isinstance(layer, QgsVectorLayer):
            lines = [f"{field.name()}: {feat[field.name()]}" for field in layer.fields()]
            QApplication.clipboard().setText("\n".join(lines))
            if hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushSuccess("Qgis MapTips", f"Copied {len(lines)} attributes to clipboard.")
            elif hasattr(self, "preview_status_lbl"):
                self.preview_status_lbl.setText("Attributes copied!")
        else:
            if hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushWarning("Qgis MapTips", "No feature available to copy attributes from.")

    def _export_sample_card_report(self) -> None:
        import os, tempfile
        layer = self._resolve_target_layer()
        feat = getattr(self, "_current_sample_feat", None)
        if not feat and isinstance(layer, QgsVectorLayer):
            sel = layer.selectedFeatures()
            feat = sel[0] if sel else None
        if not feat and isinstance(layer, QgsVectorLayer):
            with contextlib.suppress(Exception):
                for f in layer.getFeatures():
                    feat = f
                    break
        raw_html = getattr(self, "_current_raw_html", "")
        if not raw_html and isinstance(layer, QgsVectorLayer):
            raw_html = layer.mapTipTemplate() or compile_maptip_html(self._build_config_from_ui())
        if raw_html and feat and isinstance(layer, QgsVectorLayer):
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
            tmp = os.path.join(tempfile.gettempdir(), f"feature_card_report_{fid}.html")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(full_html)
            QDesktopServices.openUrl(QUrl.fromLocalFile(tmp))
            if hasattr(self.iface, "messageBar") and self.iface.messageBar():
                self.iface.messageBar().pushSuccess("Qgis MapTips", "Opened standalone HTML report in browser.")

    def _run_sample_instant_tkgm(self) -> None:
        layer = self._resolve_target_layer()
        feat = getattr(self, "_current_sample_feat", None)
        if not feat or not feat.hasGeometry() or not isinstance(layer, QgsVectorLayer):
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning("TKGM Cadastre", "No sample feature with valid geometry found in selected layer.")
            return

        try:
            pos = feat.geometry().pointOnSurface() if not feat.geometry().pointOnSurface().isEmpty() else feat.geometry().centroid()
            pt = pos.asPoint()
            tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
            wgs = tr.transform(pt)
            lat, lon = round(wgs.y(), 6), round(wgs.x(), 6)

            if not is_in_turkey_bounds(lat, lon):
                if hasattr(self.iface, "messageBar"):
                    self.iface.messageBar().pushWarning("TKGM Cadastre", f"Coordinates ({lat}, {lon}) fall outside Turkey bounds.")
                return

            success, data, err_msg = query_tkgm_megsis(lat, lon)
            if not success:
                if hasattr(self.iface, "messageBar"):
                    self.iface.messageBar().pushWarning("TKGM Cadastre", f"TKGM sorgusu başarısız: {err_msg}")
                return

            parcel_info = parse_tkgm_response(data)
            if not parcel_info:
                if hasattr(self.iface, "messageBar"):
                    self.iface.messageBar().pushWarning("TKGM Cadastre", "Belirtilen koordinatta resmi parsel bulunamadı.")
                return

            summary = (
                f"TKGM: {parcel_info['il']} / {parcel_info['ilce']} / {parcel_info['mahalle']} | "
                f"Ada: {parcel_info['ada_no']}, Parsel: {parcel_info['parsel_no']} | "
                f"Alan: {parcel_info['alan_m2']} m² | {parcel_info['nitelik']}"
            )
            QApplication.clipboard().setText(summary)

            cadastre_layer = get_or_create_cadastre_layer(QgsProject.instance())
            is_new, msg, _ = add_parcel_feature(cadastre_layer, parcel_info)

            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushInfo("TKGM Cadastre", f"🏛️ {summary} ({msg})")
        except Exception as exc:
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning("TKGM Cadastre", f"TKGM sorgu hatası: {exc}")

    def _on_preset_selected(self, index: int) -> None:
        preset_file = self.preset_combo.currentData()
        if not preset_file:
            return

        presets_dir = Path(__file__).resolve().parent.parent / "templates"
        preset_path = presets_dir / preset_file
        if preset_path.exists():
            cfg = TemplateConfig.load_json(preset_path)
            self._apply_config_to_ui(cfg)

    def _load_preset_by_file(self, filename: str) -> None:
        idx = self.preset_combo.findData(filename)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        else:
            presets_dir = Path(__file__).resolve().parent.parent / "templates"
            preset_path = presets_dir / filename
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

        if hasattr(cfg, "format_numbers"):
            self.cb_format_numbers.setChecked(cfg.format_numbers)
        if hasattr(cfg, "decimal_places"):
            self.spin_decimals.setValue(cfg.decimal_places)
        if hasattr(cfg, "null_text") and cfg.null_text:
            self.edit_null_text.setText(cfg.null_text)
        if hasattr(cfg, "media_fallback") and cfg.media_fallback:
            idx = self.combo_media_fallback.findData(cfg.media_fallback)
            if idx >= 0:
                self.combo_media_fallback.setCurrentIndex(idx)

        if hasattr(cfg, "show_action_buttons"):
            self.cb_card_actions.setChecked(cfg.show_action_buttons)
        if hasattr(cfg, "card_action_keys") and cfg.card_action_keys and hasattr(self, "action_checkboxes"):
            for k, cb in self.action_checkboxes.items():
                cb.setChecked(k in cfg.card_action_keys)

        # Retain preset donut and sparkline fields
        if hasattr(cfg, "donut_fields") and cfg.donut_fields:
            self._preset_donut_fields = cfg.donut_fields
            layer_fnames = self._current_layer.fields().names() if is_layer_alive(self._current_layer) else []
            matches_layer = any(fld in layer_fnames for fld, _, _ in cfg.donut_fields)
            if matches_layer or not is_layer_alive(self._current_layer):
                self._set_donut_slices_in_ui(cfg.donut_fields)
            else:
                self._auto_detect_donut_fields()
                if not self._donut_slice_rows:
                    self._set_donut_slices_in_ui(cfg.donut_fields)
        else:
            self._preset_donut_fields = None
            self._clear_donut_slice_rows()

        if hasattr(cfg, "sparkline_fields") and cfg.sparkline_fields:
            self._preset_sparkline_fields = cfg.sparkline_fields
        else:
            self._preset_sparkline_fields = None

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
        self._hud.set_hud_mode(checked)
        if not checked:
            self.hud_status_badge.setText("⚪ Inactive — Toggle switch to enable Canvas Inspector")
            self.hud_status_badge.setStyleSheet(
                "background-color: #1e293b; color: #64748b; font-size: 8pt; font-weight: bold; "
                "padding: 5px 8px; border-radius: 4px; border: 1px solid #334155;"
            )
        else:
            self.hud_status_badge.setText("⚪ Standby — Hover over map or click any feature to pin")
            self.hud_status_badge.setStyleSheet(
                "background-color: #1e293b; color: #94a3b8; font-size: 8pt; font-weight: bold; "
                "padding: 5px 8px; border-radius: 4px; border: 1px solid #334155;"
            )
        self._sync_cursor_state()

    def _sync_cursor_state(self) -> None:
        """Keep the canvas inspection reticle cursor active whenever MapTips or Inspector is active."""
        maptips_on = bool(hasattr(self, "maptips_switch") and self.maptips_switch.isChecked())
        hud_on = bool(hasattr(self, "hud_switch") and self.hud_switch.isChecked())
        current_tab = self.tabs.currentIndex() if hasattr(self, "tabs") else 0

        cursor_cb = getattr(self, "hud_cursor_cb", None)
        cursor_allowed = cursor_cb.isChecked() if cursor_cb is not None else True

        # Keep reticle cursor active whenever MapTips is ON (on Designer / Inspect tabs) or when Inspector is active
        want_cursor = cursor_allowed and (hud_on or (maptips_on and current_tab in (0, 2)))
        self._hud.set_cursor_mode(want_cursor)

    def _on_hud_cursor_toggled(self, checked: bool) -> None:
        self._hud.set_use_custom_cursor(checked)
        self._sync_cursor_state()

    def _on_hud_debounce_changed(self, val: int) -> None:
        self._hud.debounce_ms = val

    def _on_hud_feature_hovered(self, layer: Any, feat: Any, html_val: str) -> None:
        if not self._hud.is_pinned():
            layer_name = layer.name() if hasattr(layer, "name") else "Layer"
            fid = feat.id() if hasattr(feat, "id") else "?"
            self.hud_status_badge.setText(f"🟡 Hovering: {layer_name} (ID {fid})")
            self.hud_status_badge.setStyleSheet(
                "background-color: #1e293b; color: #38bdf8; font-size: 8pt; font-weight: bold; "
                "padding: 5px 8px; border-radius: 4px; border: 1px solid #0284c7;"
            )
            self.hud_live_browser.setHtml(html_val)
            self._populate_hud_attributes_table(layer, feat)

    def _on_hud_feature_pinned(self, layer: Any, feat: Any, html_val: str) -> None:
        layer_name = layer.name() if hasattr(layer, "name") else "Layer"
        fid = feat.id() if hasattr(feat, "id") else "?"
        self.hud_status_badge.setText(f"🟢 PINNED: {layer_name} (ID {fid})")
        self.hud_status_badge.setStyleSheet(
            "background-color: #1e293b; color: #f59e0b; font-size: 8pt; font-weight: bold; "
            "padding: 5px 8px; border-radius: 4px; border: 1px solid #f59e0b;"
        )
        self.btn_hud_pin.setText("✕ Unpin Card")
        self.hud_live_browser.setHtml(html_val)
        self._populate_hud_attributes_table(layer, feat)

    def _on_hud_pin_state_changed(self, pinned: bool) -> None:
        self.btn_hud_pin.setText("✕ Unpin Card" if pinned else "📌 Pin Card")
        if not pinned:
            self.hud_status_badge.setText("⚪ Standby — Hover over map or click any feature to pin")
            self.hud_status_badge.setStyleSheet(
                "background-color: #1e293b; color: #94a3b8; font-size: 8pt; font-weight: bold; "
                "padding: 5px 8px; border-radius: 4px; border: 1px solid #334155;"
            )

    def _on_hud_cleared(self) -> None:
        if not self._hud.is_pinned():
            self.hud_status_badge.setText("⚪ Standby — Hover over map or click any feature to pin")
            self.hud_status_badge.setStyleSheet(
                "background-color: #1e293b; color: #94a3b8; font-size: 8pt; font-weight: bold; "
                "padding: 5px 8px; border-radius: 4px; border: 1px solid #334155;"
            )

    def _on_hud_toggle_pin(self) -> None:
        self._hud.set_pinned(not self._hud.is_pinned())

    def _populate_hud_attributes_table(self, layer: Any, feat: Any) -> None:
        if not hasattr(layer, "fields") or not hasattr(feat, "attribute"):
            return
        fields = layer.fields()
        self.hud_attr_table.setRowCount(len(fields))
        for row, fld in enumerate(fields):
            val = feat.attribute(fld.name())
            val_str = "NULL" if val is None else str(val)
            item_k = QTableWidgetItem(fld.name())
            item_v = QTableWidgetItem(val_str)
            no_edit = getattr(Qt.ItemFlag, "ItemIsEditable", None)
            if no_edit is None:
                no_edit = getattr(Qt, "ItemIsEditable", 0)
            item_k.setFlags(item_k.flags() & ~no_edit)
            item_v.setFlags(item_v.flags() & ~no_edit)
            self.hud_attr_table.setItem(row, 0, item_k)
            self.hud_attr_table.setItem(row, 1, item_v)

    def _on_hud_zoom_feature(self) -> None:
        feat = getattr(self._hud, "_current_feature", None)
        layer = getattr(self._hud, "_current_layer", None)
        if not feat or not is_layer_alive(layer) or not feat.hasGeometry():
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushInfo("Qgis MapTips", "No feature currently inspected to zoom to.")
            return
        canvas = self.canvas or (self.iface.mapCanvas() if self.iface else None)
        zoom_to_feature(canvas, layer, feat, self.iface)

    def _on_hud_copy_feature(self) -> None:
        feat = getattr(self._hud, "_current_feature", None)
        layer = getattr(self._hud, "_current_layer", None)
        if not feat or not is_layer_alive(layer):
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning("Qgis MapTips", "No feature currently inspected to copy.")
            return
        lines = [f"{field.name()}: {feat[field.name()]}" for field in layer.fields()]
        QApplication.clipboard().setText("\n".join(lines))
        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushSuccess("Qgis MapTips", f"Copied {len(lines)} attributes to clipboard.")

    def _on_hud_export_feature(self) -> None:
        feat = getattr(self._hud, "_current_feature", None)
        layer = getattr(self._hud, "_current_layer", None)
        if not feat or not is_layer_alive(layer):
            if hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning("Qgis MapTips", "No feature currently inspected to export.")
            return
        import os, tempfile
        raw_html = layer.mapTipTemplate() or evaluate_vector_feature_maptip(layer, feat)
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
        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushSuccess("Qgis MapTips", "Opened feature card report in browser.")

    def _open_quick_manual(self) -> None:
        from .quick_manual import QuickManualDialog

        dlg = QuickManualDialog(self)
        dlg.exec()

    def _open_rate_plugin(self) -> None:
        import webbrowser

        webbrowser.open("https://plugins.qgis.org/plugins/qgis_maptips/")
        if hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushInfo(
                "Qgis MapTips", "⭐ Thank you for your support! Opening QGIS Plugin Hub review page."
            )

    def unload(self) -> None:
        """Clean up listeners and filters on plugin unload."""
        self._hud.stop()
        with contextlib.suppress(Exception):
            QgsProject.instance().layersWillBeRemoved.disconnect(self._on_layers_will_be_removed)
            QgsProject.instance().layersAdded.disconnect(self._refresh_layers)
            QgsProject.instance().layersRemoved.disconnect(self._refresh_layers)
            self.iface.currentLayerChanged.disconnect(self._on_qgis_active_layer_changed)
        with contextlib.suppress(Exception):
            if hasattr(self.iface, "actionMapTips") and self.iface.actionMapTips():
                self.iface.actionMapTips().toggled.disconnect(self._sync_maptip_action_state)
        with contextlib.suppress(Exception):
            if hasattr(self, "_current_layer") and is_layer_alive(self._current_layer) and isinstance(self._current_layer, QgsVectorLayer):
                self._current_layer.selectionChanged.disconnect(self._on_layer_selection_changed)
