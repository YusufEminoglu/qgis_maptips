# Changelog

## [0.2.2] - 2026-10-27

- Hub listing text rewritten; author Geophilo; university affiliation removed; documentation links use the standard geophilo.com pages (manual.html, guide/); manual HTML no longer ships in the plugin package.

## [0.2.1] - 2026-10-26

### Fixed

- **Cross-layer counts never worked.** "Spatial Intersects (Count)" and
  "Spatial Contains (Count)" called `overlay_intersects(layer)` without an
  expression, which returns true/false rather than a list, so the card showed
  the raw `[% ... %]` expression instead of a number. Counts now come from
  `overlay_*(layer, $id)`; sum, mean, median, min and max use the field's
  numeric value.
- **Attribute values were pasted into the card as HTML.** A name such as
  `Plot <A> & B` lost `<A>` (read as a tag) and could break the card layout.
  Titles, subtitles, attribute rows and nearest-neighbour values are now
  escaped.
- **The "No Photo Available" placeholder broke the photo card.** Its SVG sat
  unencoded inside the `src="..."` attribute, so the attribute ended at the
  first quote and SVG text leaked into the card. The placeholder is now
  percent-encoded.
- **The designer's sample feature had no geometry on file layers.** It was
  fetched without geometry, so on GeoPackage or Shapefile layers the zoom,
  buffer, TKGM and Action Studio test-run buttons did nothing, and coordinates
  in the preview's action links were empty.
- **The hover HUD repeated its "click to pin" footer** inside every nested
  table of a card (badges, bars, action buttons). It is now added once.
- The HUD's 5-pixel hover tolerance was wrong when the map and the layer use
  different CRSs (it only handled a geographic layer on a projected map).
- An `action:` link with an empty key raised `AttributeError`
  (`QUrl.Authority()` does not exist).
- Re-applying actions with replacement requested added a second copy of each
  action; it now replaces the same-named action, and the dock uses that, so
  re-applying after a plugin update refreshes stale action commands.
- The nearest-neighbour metric always read a field called `id`, which is NULL
  on most layers; it now shows the target layer's name-like field.
- Batch "Enhance All Project Vector Layers" picked titles by substring, so
  `fid` (contains "id") or `road` (contains "ad") won over `name`, and it
  edited project layers from a Processing worker thread. It now chooses a
  name-like field and runs on the main thread. The HTML report's default card
  uses the same title choice.
- Field names containing double quotes, conditional-badge labels with quotes
  or markup, and unknown comparison operators no longer produce invalid
  expressions.

## [0.2.0] - 2026-10-17

### Added
- **Interactive Action Studio Tab (`🛠️ Action Studio`)**: Full-featured action generator, template browser, and code/URL customizer allowing users to inspect, revise, test-run, and inject custom QGIS actions onto any vector layer.
- **22 Ready-to-Use QGIS Action Templates across 5 Categories**:
  - *Web & Street Navigation (8)*: Google Maps (Satellite), Google Street View, Google Driving Directions, OpenStreetMap Inspector, OpenStreetMap iD Web Editor, Yandex Maps & Panorama, Microsoft Bing Aerial View, Mapillary Street Imagery.
  - *Geometry & Spatial Analysis (6)*: Smart Zoom & Center (Adaptive CRS Padding), Pan & Flash Highlight, Custom-Distance Metric Buffer Layer, Select Nearby Features Within Radius, Extract Feature to Scratch Layer, Ellipsoidal Geometry & Coordinate Audit (Area/Perimeter/Length/Vertices).
  - *Attribute, Export & Clipboard (4)*: Copy Attributes (Key-Value), Copy Feature as RFC 7946 GeoJSON (WGS84), Copy WKT Geometry & Coordinates, Export Feature Card to Standalone HTML Report.
  - *Cadastral & Urban Planning (2)*: Open in TKGM Parsel Sorgu Web Portal, Download Official TKGM Parcel Polygon at Feature (Turkey).
  - *External Portals & Forms (2)*: Open Native QGIS Feature Attribute Form Dialog, Wikimedia GeoHack Coordinate Intelligence Portal.
- **Dynamic Field & Spatial Token Inserter**: 1-click insertion of active layer attribute fields (`[% "field" %]`) and 12 CRS-safe spatial tokens (WGS84 Lat/Lon, `$id`, `@layer_id`, `$area`, `$perimeter`, `$length`, WKT) at the editor cursor.
- **Quick Numeric Parameter Adjuster & Live Expression Preview**: 1-click adjustment of buffer distances, proximity search radii, or web map zoom levels, paired with real-time evaluation of `[% ... %]` expressions against the current sample feature.
- **Portable JSON Action Packs**: Export customized actions to `.json` and import them into any layer or project.

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
