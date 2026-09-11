"""Qgis Advanced Map Tips&Actions plugin."""
from __future__ import annotations

from typing import Any


def classFactory(iface: Any):
    """Load QgisMapTipsPlugin class from main_plugin."""
    from .main_plugin import QgisMapTipsPlugin

    return QgisMapTipsPlugin(iface)
