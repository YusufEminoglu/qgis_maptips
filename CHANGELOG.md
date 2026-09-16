# Changelog

## [0.1.1] - 2026-09-17

- Upgraded official plugin icon to high-end tactile 3D brand identity (isometric 45°, slim teal pedestal, full bleed transparent canvas).
- Synchronized documentation, repository and issue tracker endpoints to GeoPhilo and GitLab.

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-11

### Added
- Initial release of Qgis Advanced Map Tips&Actions (`qgis_maptips`).
- Theme-aware dockable studio supporting light, dark, and high-contrast QGIS themes with palette tokenization.
- Six universal layout archetypes: KPI Metric Card, Comparison Progress Bar, Multi-metric Donut Chart, Mini Sparkline Trend, Photo/Media Preview Card, and Raster HUD Card.
- Zero-dependency micro-chart engine producing Qt-compatible nested HTML tables and pure SVG data-URIs.
- 1-click action builder generating dynamic CRS-aware web actions (Google Maps, Street View, Yandex Maps, TKGM Cadastre), local document/photo viewers, and clipboard exports.
- Live Canvas HUD inspector for passive raster pixel sampling and multi-layer hover tips with configurable debouncing.
- Interactive HTML Portfolio Report processing algorithm to batch render layer cards into standalone searchable web catalogs.
- Batch Processing algorithm to inject publication-grade MapTips and actions across all vector layers in a project.
- Real-time expression inspection tab and 1-click "Copy HTML / Expression" clipboard integration.
- Interactive Canvas Cadastre Picker (`InteractiveCadastreTool`): 1-click tool querying official TKGM MEGSİS API directly from map canvas coordinates without requiring any layer selection (Turkey Only).
- Automated memory layer management for `"TKGM Parselleri (TR)"` with Turkish schema (`il`, `ilce`, `mahalle`, `ada_no`, `parsel_no`, `alan_m2`, `nitelik`, `mevkii`, `ozet`, `sorgu_tarihi`), amber boundary styling, and Turkish MapTip KPI card.
- Default inside-polygon centered labeling (`Ada No / Parsel No`) with subtle 0.7mm white halo text buffer.
- Transparent daily query counting and user-friendly error handling for TKGM fair-use rate limits (HTTP 403 Forbidden).
- Ultra-compact, sleek dock bar with `🇹🇷 TR` micro-badge and zero extra toolbar icon clutter.
- Added comprehensive `THIRD_PARTY.md` detailing TKGM MEGSİS daily quotas, fair-use rate limits, legal disclaimers, and terms for Google Maps, OpenStreetMap, and Yandex Maps.
- Added dedicated Acknowledgments & Special Thanks to `geographyclub` (https://github.com/geographyclub) and `Okan Şafak` (https://github.com/okansafak/qgistkgmplugin) in `README.md`, `THIRD_PARTY.md`, and the plugin About dialog.
- Fully isolated unit tests and QGIS dual-runtime (3.28+ LTR and QGIS 4.x) test suites.

### Fixed
- Fixed SVG donut chart single-color rendering glitch: expressions now wrap percentage calculations in `coalesce(..., 0.0)` and `try(to_real(...), 0.0)`, preventing division-by-zero or non-existent attribute lookups from collapsing into invalid `stroke-dasharray=" "` fallback that caused the Qt SVG engine to paint a solid 100% single-color circle.
- Added dedicated "🍩 Donut Chart Slices" collapsible configuration section in the dock panel with per-slice color picker (`QColorDialog`), layer attribute combo, editable slice labels, and dynamic slice addition/removal.
- Added smart numeric field auto-discovery (`_auto_detect_donut_fields`) when switching to Donut Chart or loading presets onto custom layers, ensuring proportional multi-color slicing out of the box.
- Redesigned plugin icon (`icons/icon.png`): sculpted into a unified, monolithic 3D locator pin where the squircle balloon head blends a rounded rectangle with a spherical volume, seamlessly tapering into a metallic pin needle tip while keeping the rich MapTip card dashboard embedded inside.
