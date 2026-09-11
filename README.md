# 02Maptips: Advanced Map Tips and Actions

**02Maptips** (zero2maptips) is an advanced, theme-aware QGIS 3.28+ and QGIS 4 plugin for designing rich, responsive HTML/CSS Map Tips and configuring 1-click feature actions for any vector or raster layer.

---

## Key Features

- **Dockable Studio:** Automatically adapts to QGIS light and dark themes using Qt palette derivation.
- **Universal Layout Archetypes:**
  - *KPI & Metric Card:* Large metric banner, status badge, structured key-value summary.
  - *Comparison Progress Bar:* Dynamic horizontal bars showing percentage of range or target.
  - *Multi-Metric Donut:* Inline SVG donut chart evaluating category distributions.
  - *Photo & Document Card:* Safe thumbnail preview of local files or remote URLs.
  - *Raster Cell HUD:* Live floating inspector for elevation, slope, and multi-band rasters.
- **Zero External Dependencies:** Every chart is generated using nested HTML tables or pure SVG data-URIs, ensuring instant render inside Qt's QTextDocument engine.
- **1-Click Action Library:**
  - Dynamic WGS84 web actions (Google Maps, Street View, Yandex, TKGM Cadastre).
  - Open local document/photo in default desktop viewer.
  - Copy feature summary to clipboard (Plain Text or Markdown).
- **Native Persistence:** Injected map tips and actions write directly to the layer style and QgsActionManager, functioning normally even on machines without the plugin installed.

---

## Installation

Clone or extract to your QGIS plugins folder:
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\zero2maptips

---

## Author & License

Developed by **Yusuf Eminoğlu**.
Licensed under **GPL-3.0-or-later**.
