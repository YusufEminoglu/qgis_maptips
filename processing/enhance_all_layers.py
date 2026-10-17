"""Processing algorithm to batch enhance all project vector layers with MapTips and Actions."""
from __future__ import annotations

from typing import Any, Dict

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProject,
    QgsVectorLayer,
)

from ..core.action_builder import apply_actions_to_layer
from ..core.template_engine import Archetype, TemplateConfig, compile_maptip_html


class EnhanceAllLayersAlgorithm(QgsProcessingAlgorithm):
    """Batch injects responsive HTML MapTips and dynamic Web Actions across project vector layers."""

    PARAM_PALETTE = "PALETTE"
    PARAM_ACTIONS = "INCLUDE_ACTIONS"
    PARAM_OVERWRITE = "OVERWRITE_EXISTING"

    PALETTES = ["emerald", "blue", "slate", "crimson", "purple", "amber"]
    PALETTE_NAMES = ["Emerald Studio", "Classic Blue", "Dark Slate", "Crimson Alert", "Modern Purple", "Cadastral Amber"]

    def name(self) -> str:
        return "enhance_all_layers"

    def displayName(self) -> str:
        return "Batch Enhance All Project Vector Layers with MapTips & Actions"

    def group(self) -> str:
        return "Batch Tools"

    def groupId(self) -> str:
        return "batch_tools"

    def shortHelpString(self) -> str:
        return (
            "Scans all vector layers in the current QGIS project, automatically detects "
            "title and metric attributes, and injects Qt-compliant HTML MapTips and "
            "1-click web navigation actions without manual configuration."
        )

    def createInstance(self) -> EnhanceAllLayersAlgorithm:
        return EnhanceAllLayersAlgorithm()

    def initAlgorithm(self, config: Dict[str, Any] = None) -> None:
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PARAM_PALETTE,
                "Color Theme Palette",
                options=self.PALETTE_NAMES,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PARAM_ACTIONS,
                "Inject Universal Web & Clipboard Actions (Google Sat, Street View, Copy)",
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PARAM_OVERWRITE,
                "Overwrite Existing MapTips",
                defaultValue=False,
            )
        )

    def processAlgorithm(
        self,
        parameters: Dict[str, Any],
        context: Any,
        feedback: Any,
    ) -> Dict[str, Any]:
        palette_idx = self.parameterAsEnum(parameters, self.PARAM_PALETTE, context)
        include_actions = self.parameterAsBoolean(parameters, self.PARAM_ACTIONS, context)
        overwrite = self.parameterAsBoolean(parameters, self.PARAM_OVERWRITE, context)

        palette_key = self.PALETTES[palette_idx] if 0 <= palette_idx < len(self.PALETTES) else "emerald"

        project = QgsProject.instance()
        vector_layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]

        if not vector_layers:
            feedback.pushInfo("No vector layers found in the current project.")
            return {"ENHANCED_LAYERS_COUNT": 0}

        enhanced_count = 0
        total = len(vector_layers)

        for i, layer in enumerate(vector_layers):
            if feedback.isCanceled():
                break

            feedback.setProgress(int(100 * (i / total)))
            if not layer.isValid():
                continue

            existing_tip = layer.mapTipTemplate().strip()
            if existing_tip and not overwrite:
                feedback.pushInfo(f"Skipping '{layer.name()}': already has a MapTip.")
                continue

            fields = layer.fields()
            if fields.isEmpty():
                continue

            # Auto-detect title and attribute fields
            field_names = [f.name() for f in fields]
            title_fld = field_names[0]
            for fn in field_names:
                if any(k in fn.lower() for k in ("name", "ad", "title", "id", "label")):
                    title_fld = fn
                    break

            # Select up to 6 attribute fields
            attrs = [(fn, fn) for fn in field_names if fn != title_fld][:6]

            cfg = TemplateConfig(
                archetype=Archetype.KPI_CARD if len(field_names) > 2 else Archetype.CLEAN_TABLE,
                palette_key=palette_key,
                card_width=320,
                title_field=title_fld,
                attribute_fields=attrs,
                footer_text=f"Layer: {layer.name()}",
            )

            html_tip = compile_maptip_html(cfg)
            layer.setMapTipTemplate(html_tip)

            if include_actions:
                apply_actions_to_layer(layer, ["google_satellite", "google_streetview", "copy_clipboard"])

            enhanced_count += 1
            feedback.pushInfo(f"Enhanced '{layer.name()}' with MapTip and Actions.")

        feedback.setProgress(100)
        feedback.pushInfo(f"Successfully enhanced {enhanced_count} vector layer(s).")
        return {"ENHANCED_LAYERS_COUNT": enhanced_count}
