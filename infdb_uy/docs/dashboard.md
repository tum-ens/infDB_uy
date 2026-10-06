# Dashboard

The data explorer runs at <http://localhost:8050> after `docker compose up --build` (or `./run.sh`). It reads the prepared data and shows only **descriptive** figures: counts, sums and distributions. Nothing is modelled, imputed or reclassified.

## Languages

The interface is available in English, German and Spanish. The selector is in the header. The choice is stored in the browser; otherwise the browser language decides.

- **Data values** (DNC and INE codes and labels, street names) are shown exactly as published, in Spanish.
- **Numbers** are formatted for the chosen language (1,234.5 / 1.234,5).
- **Translations** live in `static/i18n.js`. A missing key falls back to English.

## Tabs

| Tab | What it shows | Source tables |
|---|---|---|
| Overview | Area summary, data quality observations, provenance per source (files, size, host, retrieval time), ANDA status | `reports/qa.json`, `reports/dnc_summary.json`, `raw/manifest.jsonl` |
| Cadastre | Parcel map with colour options. Charts of construction lines by use, construction year, category, conservation state, roof type, floor level, type of works and regime. Parcel record on click. | `prepared/dnc/*.parquet`, `prepared/dnc.gpkg`, `prepared/im_wfs.gpkg` |
| Census | 2023 population and dwellings per census zone (choropleth and table), scope relation per zone. ANDA: drop-folder status, variable catalogue and, once microdata are ingested, distributions of any variable (optionally weighted, optionally per census unit). | `prepared/im_wfs.gpkg#zonas_censales_2023`, `prepared/ine_anda/...` |
| LiDAR | Tile footprints, points per class (with documented meaning or "not documented"), header information | `reports/lidar_inventory.json`, `prepared/lidar_tiles.gpkg` |
| Data | Every prepared table and GeoPackage layer: schema, paged rows, search, CSV export | `prepared/**` |

## How the figures are defined

- **Cadastre charts** sum the built area (`area_m2`) of construction lines. Each chart is filtered by the other charts but not by itself, so the alternatives stay visible.
  - Clicking a bar adds a filter.
  - Clicking a decade sets a year range; shift-click extends it.
  - *Include lines with year 0* controls whether lines with construction year 0 pass a year filter. With no year filter, the toggle excludes them altogether when unchecked.
- **Parcel colours** use attributes computed in `infdb-uy dashboard` (`data/dashboard/parcel_attributes.parquet`). Their names state what they count:

  | Attribute | Definition |
  |---|---|
  | `year_median_nonzero` | Median construction year of the parcel's lines, ignoring year 0 |
  | `nivel_max` | Highest floor level of the parcel's lines |
  | `lines_area_m2` | Sum of the line areas, including walls, landings and garages |
  | `use_largest_area` | The use code whose lines have the largest summed area |
  | `regimen_units` | Régimen codes of the parcel's units |
  | `n_units` | Number of unit records in `padrones_urbanos` |
  | `valor_total_sum` | Sum of `valor_total` over units |
  | `n_lines_year_0` | Lines with construction year 0 |

  Parcels without construction lines appear in the "no construction lines" colour.
- **Parcel record**: all unit records, construction lines (codes with official labels; unlabelled codes shown in italics), value history (the four previous years, relative to the release), door numbers and building permits of the padrón, and changes from the monthly mutation file.
- **3D view (Cadastre tab).** The assumption applies **only to this visualization**. The raw LiDAR 2024 data already contains detailed, measured building information: centimetre-precise height of every point (≈ 27 points/m²), building classification, RGB colour, intensity and multiple returns. Measured heights, footprints and roof shapes will be derived from it in the planned LiDAR step and will replace the illustration.
- **3D view, how it is drawn:** parcel polygons extruded to (highest above-ground floor level + 1) × an **assumed** storey height. The height is set in `config/pilot-cordon.yml` → `dashboard.visual_storey_height_m`, default 3 m. A banner marks it as an assumption.
  - Parcels are not building footprints, so yards are extruded too.
  - LiDAR heights are not used.
  - The illustrative height is stored as `vis_floors` and `vis_height_m` in `data/dashboard/parcelas.geojson` only. It is not part of the prepared data.
  - It will be replaced by LiDAR-derived footprints and heights once that step exists (see [Required changes §4](required-changes.md#4-building-geometry-from-lidar-l)).
- **Census zones crossing the scope** are shown and counted whole. The overlap share is an area share, not a population share, and no attribution to the scope is made.
- **ANDA panel.** One collapsible box per study. Variable and weight are chosen from searchable lists of the columns of the selected table (type a name or label to filter); *Show* is enabled only for a valid column. Likely weight columns (`W…`, `peso`, labels "expansor"/"ponderador") are listed first, because INE does not flag weights in its catalogue. Clicking a row of the variable catalogue selects it.
- **ANDA distributions** count records per code. *Weighted* sums the chosen weight column. Labels come from the ANDA catalogue, otherwise from INE's 2023 dictionary. The table states which source was used.

## Architecture

```
infdb-uy dashboard   prepared/ → data/dashboard/  (GeoJSON EPSG:4326, parcel attributes)
infdb-uy serve       FastAPI + DuckDB  →  /api/*  +  static single-page app
```

| File | Role |
|---|---|
| `src/infdb_uy/dashboard/build.py` | Builds the web layers and parcel attributes |
| `src/infdb_uy/dashboard/app.py` | API. Endpoints: `/api/meta`, `/api/geo/{layer}`, `/api/cadastre/summary`, `/api/cadastre/parcel/{key}`, `/api/lidar`, `/api/anda*` (incl. `/api/anda/{idno}/columns`), `/api/network`, `/api/datasets*`. OpenAPI at `/api/docs`. |
| `src/infdb_uy/dashboard/static/` | `index.html`, `app.js`, `style.css`, `i18n.js` (interface texts EN/DE/ES). MapLibre GL JS is bundled in `vendor/`, so no CDN is needed for the map library. |

The basemap uses the public OpenStreetMap tile server, drawn in greyscale. Without internet the data layers still display, but the basemap does not. The OSM tile policy allows light interactive use like this. For heavier use, configure another tile source in `app.js` (`baseStyle`).

## Single-command start

`docker compose up --build` builds the image (Python 3.12, uv, libarchive) and runs `infdb-uy start`:

1. It runs every pipeline step. Steps that already completed with the same configuration are skipped (markers in `data/state/`).
2. It serves the dashboard on port 8050.

**Network access.** The port is published on all network interfaces of the host, so other devices in the same network can open the dashboard. A container cannot see the host's network address, so the compose file first runs a one-off service `netinfo` in the host's network (`network_mode: host`). It writes the host's address to `data/state/host_network.json` and always exits successfully. The address is printed at startup ("From another device in the same network: http://…:8050") and shown in the header as a button "Network: …" that copies it. Only the address of the default-route interface is shown; Docker's own networks are skipped. On Docker Desktop (macOS, Windows) the host network is a VM, so no address is shown there.

- Another port: `PORT=8080 docker compose up --build`
- This computer only, not the network: `PORT=127.0.0.1:8050 docker compose up --build`

Anyone in the network can then see everything the dashboard shows, including ingested ANDA microdata through the Data tab and the API. Use the local-only setting on untrusted networks; INE's terms do not allow sharing the microdata.

`./data` and `./config` are mounted from the host, so data persists across restarts and the config can be edited without rebuilding. To add INE ANDA microdata later, drop the files into `data/raw/ine_anda/<idno>/files/` and restart (file list per study: [Data downloads](data-downloads.md)). `anda-ingest`, `qa` and `dashboard` always run.
