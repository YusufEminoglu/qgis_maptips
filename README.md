# Qgis Advanced Map Tips&Actions

**Qgis Advanced Map Tips&Actions** (`qgis_maptips`) is an advanced, theme-aware QGIS 3.28+ LTR and QGIS 4.x plugin for visually designing publication-grade, responsive HTML/CSS MapTips, embedding zero-dependency micro-charts, evaluating real-time spatial aggregations, and configuring 1-click feature actions for any vector or raster layer.

---

## Highlights & Capabilities

- **Interactive Dockable Studio:** Automatically inherits and adapts to QGIS light, dark, and high-contrast themes via live Qt palette tokenization.
- **Six Universal MapTip Archetypes:**
  1. **KPI Metric Card:** High-impact metric highlight with unit, dynamic subtitle, key-value attributes, and conditional status badge.
  2. **Comparison Progress Bar:** Nested HTML table progress bar displaying capacity, completion percentage, or relative score.
  3. **Multi-Metric Donut Chart:** Pure SVG data-URI ring chart showing categorical distributions and percentage breakdowns.
  4. **Mini Sparkline Trend:** Compact SVG bar chart visualizing multi-period temporal trends or attribute sequences.
  5. **Photo & Media Preview:** Safe thumbnail rendering for local image paths or remote web URLs with fallback placeholders.
  6. **Clean Attribute Table:** Minimalist key-value tabular layout with alternate row shading.
- **Real-Time Spatial Aggregations:** Inject cross-layer metrics (e.g., counting intersecting points, summing areas, or finding nearest neighbor) using optimized QGIS expressions.
- **Dynamic Conditional Status Badges:** Configure color-coded status pills based on numerical or string attribute thresholds (`>=`, `<=`, `=`, `!=`).
- **1-Click Universal Action Hub:**
  - **Dynamic Web Mapping:** Google Satellite, Google Street View, OpenStreetMap, Yandex Maps, and TKGM Cadastre, automatically transforming coordinates from `@layer_crs` to WGS84 using `point_on_surface($geometry)`.
  - **Feature Card HTML Report:** 1-click browser report viewing the active MapTip card.
  - **Clipboard Export:** Instant copy of formatted attribute values to the system clipboard.
  - **Local Media Launcher:** Open linked PDF plans, drawings, or photos in the user's default OS viewer.
  - **Cross-Layer Spatial Selection:** 1-click selection of intersecting features in any other loaded vector layer.
- **Canvas Hover HUD:** Non-blocking raster pixel sampling and composite vector/raster hover inspector with configurable debouncing.
- **Batch Processing Algorithms:**
  - **Enhance All Layers:** Apply theme-matched MapTips and web actions across every vector layer in the project with a single run.
  - **Export Layer Cards as Interactive HTML Portfolio Report:** Render every feature into a standalone, searchable HTML catalog with responsive grid cards and print-ready CSS.
- **Zero External Dependencies:** Every chart and component is rendered using pure nested HTML tables or inline SVG data-URIs, guaranteeing full compatibility with Qt's `QTextDocument` engine without WebKit/Chromium overhead.
- **Native Persistence & Portability:** MapTips and actions are stored directly in the standard QGIS layer style and `QgsActionManager`. Projects shared with colleagues work natively without requiring the plugin to be installed.
- **Instant Canvas Cadastre Picker (Turkey Only):** Query and download official cadastral parcel boundaries directly from the QGIS map canvas without selecting any vector layer. Works over any satellite imagery (Google, Bing, XYZ) or blank canvas:
  - Custom high-visibility reticle cursor with visual flash feedback on the clicked parcel.
  - Automatically creates a styled `"TKGM Parselleri (TR)"` memory layer with Turkish attributes (`il`, `ilce`, `mahalle`, `ada_no`, `parsel_no`, `alan_m2`, `nitelik`, `mevkii`, `ozet`, `sorgu_tarihi`) and amber boundary symbology.
  - Default inside-polygon centered labeling (`Ada No / Parsel No`) with a subtle white halo buffer.
  - Automatically configures an Amber MapTip KPI Card and 1-click web navigation actions (Google Sat, Street View, clipboard copy) on the newly downloaded parcels.
  - Transparent daily quota tracking and user-friendly warnings for TKGM fair-use rate limits (HTTP 403).

---

## Built-In Card Presets

The plugin includes pre-configured, production-tested templates in the `templates/` directory:

| Preset | Archetype | Palette | Purpose |
|--------|-----------|---------|---------|
| `kpi_real_estate.json` | KPI Card | Emerald | Real estate valuation, unit pricing, conditional potential badges |
| `progress_capacity.json` | Progress Bar | Classic Blue | Infrastructure load, zoning capacity, and occupancy rates |
| `donut_shares.json` | Donut Chart | Dark Slate | Land use distribution, demographic shares, zoning breakdowns |
| `sparkline_timeline.json` | Sparkline | Modern Purple | Multi-year historical progression and sequential indicators |

Users can also customize any configuration in the studio and save/load their own JSON preset files.

---

## Processing Toolbox Algorithms

Under the **Qgis Advanced Map Tips&Actions** processing provider group:

1. **Enhance All Layers in Project:**
   - Evaluates every vector layer, detects title and numeric fields automatically, and injects consistent MapTip cards and selected actions across the entire workspace.
2. **Export Layer Cards as Interactive HTML Portfolio Report:**
   - Iterates over all features in a vector layer, evaluates the active MapTip expression, and produces a single self-contained HTML catalog featuring a live text search bar, responsive grid layout, and print page-break optimizations.

---

## Third-Party Services, Fair-Use Quotas & Terms

External web mapping services and APIs integrated into the plugin actions and tools are subject to the respective provider's terms of service and usage policies:
- **TKGM MEGSİS Web API:** Informational cadastral parcel service for the Republic of Turkey. Subject to fair-use rate limits and daily query quotas (~100 queries/day/IP). Not an official legal title deed certificate.
- **Google Maps & Google Street View:** Governed by Google Maps Platform terms.
- **OpenStreetMap:** © OpenStreetMap contributors, ODbL.
- **Yandex Maps:** Governed by Yandex Maps service terms.

Detailed service terms, rate limiting guidelines, and legal disclaimers are documented in [**`THIRD_PARTY.md`**](THIRD_PARTY.md).

---

## Acknowledgments & Special Thanks

We would like to express our sincere gratitude and special thanks to:
- **[geographyclub](https://github.com/geographyclub)** for outstanding creative inspiration on responsive, publication-grade HTML layout formatting in QGIS map layouts, compact micro-card aesthetics, and advanced attribute expressions.
- **[Okan Şafak](https://github.com/okansafak)** for pioneering creative inspiration on the 1-click interactive map canvas click mode for direct cadastral parcel querying and vector layer downloading from TKGM MEGSİS services ([`qgistkgmplugin`](https://github.com/okansafak/qgistkgmplugin)).

---

## Installation & Requirements

- **Supported QGIS Versions:** QGIS 3.28 LTR through 3.44 LTR, and QGIS 4.x (Qt5 & Qt6 compatible).
- **Dependencies:** 100% pure PyQGIS (`qgis.core`, `qgis.gui`, `qgis.PyQt`). No external Python libraries required.
- **Installation:** Extract the plugin into your QGIS plugins directory:
  `QGIS_PLUGINPATH` or `<QGIS_PROFILE_DIR>/python/plugins/qgis_maptips`.

---

## Author & License

Developed by **Geophilo** (`yusuf.eminoglu@deu.edu.tr`).  
Repository: [https://gitlab.com/geophilo1/qgis_maptips](https://gitlab.com/geophilo1/qgis_maptips) (GitLab)  
Issue Tracker: [https://gitlab.com/geophilo1/qgis_maptips/-/issues](https://gitlab.com/geophilo1/qgis_maptips/-/issues)  
Distributed under the **GNU General Public License v3.0 or later** (GPL-3.0-or-later).
