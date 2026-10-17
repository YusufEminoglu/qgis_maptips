"""Processing algorithm to export an entire layer of MapTip cards as an interactive HTML report."""
from __future__ import annotations

import html
from typing import Any, Dict

from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
)

from ..core.template_engine import Archetype, TemplateConfig, compile_maptip_html


class ExportLayerCardsReportAlgorithm(QgsProcessingAlgorithm):
    """Batch renders MapTip cards for all features of a layer into a standalone HTML portfolio/report."""

    PARAM_INPUT = "INPUT"
    PARAM_PALETTE = "PALETTE"
    PARAM_COLUMNS = "COLUMNS"
    PARAM_OUTPUT = "OUTPUT"

    PALETTES = ["emerald", "blue", "slate", "crimson", "purple", "amber"]
    PALETTE_NAMES = ["Emerald Studio", "Classic Blue", "Dark Slate", "Crimson Alert", "Modern Purple", "Cadastral Amber"]

    def name(self) -> str:
        return "export_layer_cards_report"

    def displayName(self) -> str:
        return "Export Layer Cards as Interactive HTML Portfolio Report"

    def group(self) -> str:
        return "Reporting"

    def groupId(self) -> str:
        return "reporting"

    def shortHelpString(self) -> str:
        return (
            "Renders the active MapTip card for every feature in the selected vector layer "
            "into a publication-grade HTML catalog/atlas report. Features can be filtered, "
            "searched, and printed to PDF with clean print page-breaks."
        )

    def createInstance(self) -> ExportLayerCardsReportAlgorithm:
        return ExportLayerCardsReportAlgorithm()

    def initAlgorithm(self, config: Dict[str, Any] = None) -> None:
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.PARAM_INPUT,
                "Input Vector Layer",
                types=[QgsProcessing.SourceType.TypeVectorAnyGeometry],
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PARAM_PALETTE,
                "Color Theme Palette",
                options=self.PALETTE_NAMES,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PARAM_COLUMNS,
                "Grid Columns (1 to 4)",
                type=QgsProcessingParameterNumber.Type.Integer,
                defaultValue=3,
                minValue=1,
                maxValue=4,
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.PARAM_OUTPUT,
                "Output HTML Report",
                fileFilter="HTML Files (*.html)",
            )
        )

    def processAlgorithm(
        self,
        parameters: Dict[str, Any],
        context: Any,
        feedback: Any,
    ) -> Dict[str, Any]:
        layer = self.parameterAsVectorLayer(parameters, self.PARAM_INPUT, context)
        if not layer or not layer.isValid():
            raise QgsProcessingException("Invalid input vector layer.")

        palette_idx = self.parameterAsEnum(parameters, self.PARAM_PALETTE, context)
        palette_key = self.PALETTES[palette_idx] if 0 <= palette_idx < len(self.PALETTES) else "emerald"
        columns = self.parameterAsInt(parameters, self.PARAM_COLUMNS, context)
        output_path = self.parameterAsFileOutput(parameters, self.PARAM_OUTPUT, context)

        # Get or generate MapTip template
        maptip_template = layer.mapTipTemplate().strip()
        if not maptip_template:
            # Auto-compile default card
            fields = [f.name() for f in layer.fields()]
            title_fld = fields[0] if fields else ""
            attrs = [(f, f) for f in fields[1:7]]
            cfg = TemplateConfig(
                archetype=Archetype.KPI_CARD,
                palette_key=palette_key,
                card_width=320,
                title_field=title_fld,
                attribute_fields=attrs,
                footer_text=f"Layer: {layer.name()}",
            )
            maptip_template = compile_maptip_html(cfg)

        ctx = QgsExpressionContext()
        ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))

        cards_html = []
        total = layer.featureCount()
        for idx, feat in enumerate(layer.getFeatures()):
            if feedback.isCanceled():
                break

            if total > 0 and idx % 20 == 0:
                feedback.setProgress(int(100 * (idx / total)))

            ctx.setFeature(feat)
            card_rendered = QgsExpression.replaceExpressionText(maptip_template, ctx)
            cards_html.append(
                f'<div class="report-card" data-idx="{idx}">{card_rendered}</div>'
            )

        grid_cols_css = f"repeat({columns}, minmax(280px, 1fr))"

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(layer.name())} — Feature Cards Portfolio</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #f1f5f9;
      margin: 0;
      padding: 0;
      color: #0f172a;
    }}
    header {{
      background: linear-gradient(135deg, #0f766e 0%, #047857 100%);
      color: white;
      padding: 24px 32px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .header-content {{
      max-width: 1400px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}
    h1 {{ margin: 0; font-size: 20px; }}
    .meta-pill {{
      background: rgba(255,255,255,0.2);
      border-radius: 20px;
      padding: 4px 12px;
      font-size: 12px;
      font-weight: 600;
    }}
    .search-box {{
      padding: 8px 16px;
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.4);
      background: rgba(255,255,255,0.9);
      font-size: 14px;
      width: 260px;
      outline: none;
    }}
    .container {{
      max-width: 1400px;
      margin: 32px auto;
      padding: 0 24px;
    }}
    .cards-grid {{
      display: grid;
      grid-template-columns: {grid_cols_css};
      gap: 20px;
      align-items: start;
    }}
    .report-card {{
      background: white;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
      border: 1px solid #e2e8f0;
      overflow: hidden;
      display: flex;
      justify-content: center;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
      break-inside: avoid;
    }}
    .report-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(0,0,0,0.1);
    }}
    @media print {{
      header {{ position: static; box-shadow: none; }}
      .search-box {{ display: none; }}
      .cards-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .report-card {{ break-inside: avoid; page-break-inside: avoid; box-shadow: none; border: 1px solid #ccc; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <div>
        <h1>{html.escape(layer.name())}</h1>
        <div style="font-size:12px; opacity:0.85; margin-top:4px;">Qgis Advanced Map Tips&Actions &bull; Feature Catalog Report</div>
      </div>
      <div style="display:flex; align-items:center; gap:12px;">
        <span class="meta-pill">{len(cards_html):,} Features</span>
        <input type="text" class="search-box" id="searchInput" placeholder="Search features..." onkeyup="filterCards()">
      </div>
    </div>
  </header>
  <div class="container">
    <div class="cards-grid" id="cardsGrid">
      {"".join(cards_html)}
    </div>
  </div>
  <script>
    function filterCards() {{
      const query = document.getElementById('searchInput').value.toLowerCase();
      const cards = document.querySelectorAll('.report-card');
      cards.forEach(card => {{
        const text = card.textContent.toLowerCase();
        card.style.display = text.includes(query) ? 'flex' : 'none';
      }});
    }}
  </script>
</body>
</html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        feedback.setProgress(100)
        feedback.pushInfo(f"HTML report successfully written to: {output_path}")
        return {"OUTPUT": output_path, "FEATURE_COUNT": len(cards_html)}
