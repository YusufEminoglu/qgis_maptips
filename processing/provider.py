"""Processing provider for qgis_maptips."""
from __future__ import annotations

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .enhance_all_layers import EnhanceAllLayersAlgorithm
from .export_layer_cards_report import ExportLayerCardsReportAlgorithm


class QgisMapTipsProvider(QgsProcessingProvider):
    """Exposes Qgis Advanced Map Tips&Actions algorithms to the QGIS Processing Toolbox."""

    PROVIDER_ID = "qgis_maptips"

    def id(self) -> str:
        return self.PROVIDER_ID

    def name(self) -> str:
        return "Qgis Advanced Map Tips&Actions"

    def icon(self) -> QIcon:
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "icon.png")
        return QIcon(icon_path)

    def loadAlgorithms(self) -> None:
        self.addAlgorithm(EnhanceAllLayersAlgorithm())
        self.addAlgorithm(ExportLayerCardsReportAlgorithm())
