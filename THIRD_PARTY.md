# Third-Party Services, Quotas & Acknowledgments

This document outlines the external web services, APIs, data sources, and terms of service utilized by **Qgis Advanced Map Tips&Actions** (`qgis_maptips`), alongside fair-use quota warnings, legal disclaimers, and acknowledgments.

---

## 1. Tapu ve Kadastro Genel Müdürlüğü (TKGM) — MEGSİS Web API

### Service Overview
- **Service Name:** Mekânsal Gayrimenkul Sistemi (MEGSİS) Web API
- **Provider:** Republic of Turkey Ministry of Environment, Urbanisation and Climate Change — General Directorate of Land Registry and Cadastre (*T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı, Tapu ve Kadastro Genel Müdürlüğü*).
- **Public Query Endpoint:** `https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api/parsel/{lat}/{lon}/`
- **Official Web Portal:** [https://parselsorgu.tkgm.gov.tr/](https://parselsorgu.tkgm.gov.tr/)

### Fair Use & Daily Quota Notice
- **Daily Request Limits:** TKGM MEGSİS API implements fair-use security controls, rate limiting, and daily IP query quotas (typically ~100 queries per day per IP address).
- **HTTP 403 Forbidden Response:** When this threshold is reached, the TKGM server responds with HTTP 403 Forbidden. The plugin detects this status code and informs the user directly. Daily quotas typically reset at midnight (Turkey Time, UTC+3).
- **Fair-Use Practice:** This plugin queries parcel information strictly on-demand in response to direct user clicks or single-feature action executions. Automated mass web scraping, concurrent bot crawling, or excessive loop queries are not supported and will result in temporary IP throttling or blocking by TKGM security firewalls.
- **Geographical Scope:** MEGSİS data covers cadastral parcels located within the sovereign borders of the Republic of Turkey.

### Legal Status & Disclaimer
> **IMPORTANT NOTICE:** Cadastral geometry, parcel areas, and attribute data retrieved via the MEGSİS API are provided for **informational, spatial planning, and preliminary geographic analysis purposes only**.
> They do **not** constitute an official Land Registry Title Deed (*Tapu Senedi*) or a legally certified boundary survey. For official real estate transactions, legal boundary determinations, or disputes, legally binding documentation must be obtained directly from the relevant Land Registry and Cadastre Directorates (*Tapu ve Kadastro Müdürlükleri*).

---

## 2. Google Maps & Google Street View

- **Provider:** Google LLC (Alphabet Inc.)
- **Endpoints Utilized:**
  - Google Maps Satellite View: `https://www.google.com/maps/search/?api=1&query={lat},{lon}&basemap=satellite`
  - Google Street View Panorama: `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}`
- **Terms of Service:** Governed by the [Google Maps Platform Terms of Service](https://cloud.google.com/maps-platform/terms) and [Google Terms of Service](https://policies.google.com/terms).
- **Functionality:** Features dynamic WGS84 coordinate calculation (`point_on_surface($geometry)`) for instantaneous cross-referencing of satellite imagery and street-level photographic context.

---

## 3. OpenStreetMap (OSM)

- **Provider:** OpenStreetMap Foundation (OSMF)
- **Endpoint Utilized:** `https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}`
- **Copyright & License:** OpenStreetMap data is © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).
- **Tile Usage:** Tile requests adhere to the [OSMF Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/).

---

## 4. Yandex Maps

- **Provider:** Yandex LLC
- **Endpoint Utilized:** `https://yandex.com/maps/?ll={lon}%2C{lat}&z=18&l=sat%2Cskl`
- **Terms of Service:** Governed by the [Yandex Maps Terms of Use](https://yandex.com/legal/maps_termsofuse/).

---

## 5. Acknowledgments & Special Thanks

### Special Thanks to `geographyclub`
We extend our warmest appreciation and sincere thanks to **[geographyclub](https://github.com/geographyclub)** for outstanding creative inspiration regarding:
- Publication-grade HTML formatting and styling patterns within QGIS map layouts and MapTip popup cards.
- Elegant, compact micro-card compositions that render natively inside Qt's `QTextDocument` engine.
- Sophisticated QGIS attribute expressions and dynamic layout variables.

### Special Thanks to Okan Şafak (`qgistkgmplugin`)
We extend our sincere thanks to **[Okan Şafak](https://github.com/okansafak)** for pioneering work and creative inspiration regarding:
- The 1-click interactive map canvas click mode for direct cadastral parcel querying and layer acquisition from TKGM MEGSİS services, as demonstrated in the [**`qgistkgmplugin`**](https://github.com/okansafak/qgistkgmplugin) project.
- Real-world community experience on Turkish cadastral integration and daily fair-use rate limit management.

Their innovative work in the geospatial cartography community served as a valuable aesthetic benchmark during the design of this plugin.

---

## 6. Implementation & Architecture Integrity

All Python source code, architecture patterns, custom canvas map tools (`InteractiveCadastreTool`), responsive HTML template engines, live raster HUD sampling algorithms, and Processing algorithms in this repository are **clean-room, original implementations** developed by **Geophilo**.
