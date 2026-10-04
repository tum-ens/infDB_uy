# Pipeline

The package in `src/infdb_uy` downloads and prepares the data for the [Cordón pilot](pilot-cordon.md). It covers the first two steps of the pilot workflow: Step 1 (administrative scope) and Step 2 (import). It also prepares the INE ANDA microdata.

It **makes no modelling assumptions**. It does not derive buildings, classify uses, distribute population or clean values. Those steps come later, each documented on its own.

## Rules

| Folder | Content | Allowed operations |
|---|---|---|
| `data/raw/` | Files exactly as downloaded, plus `manifest.jsonl` (URL, retrieval time, bytes, SHA-256, server headers) | None. Files are never edited. |
| `data/prepared/` | Analysis-ready copies | Lossless only: official column names, official code labels added next to raw codes, keys, reprojection, selection by scope |
| `data/reports/` | Summaries and QA | Descriptive only |

What this means in practice:

- **No row is dropped, corrected, imputed or reclassified.** Implausible values (year 0, area 0, codes without a label) stay as they are and are counted in the reports.
- **Scope selection never cuts geometry.** A feature is kept if it intersects the scope polygon. `scope_relation` (`within` / `crosses_boundary`) and `scope_overlap_share` (share of area or length inside) let later steps decide what to do with edge cases.
- **Codes stay codes.** Labels come only from the publisher's own code tables (DNC release, INE dictionary, ANDA metadata) and are added as `<column>_label`. Codes without an official label keep an empty label and are listed in the report. INE's generic codes (7777, 8888, 9898, 99/9999) are never converted to missing values.
- **Values that do not match their documented type** are kept in a `<column>_raw` column and counted in the report.
- `data/` is excluded from git. It contains INE microdata whose terms forbid redistribution.

## Running

Requirements: [uv](https://docs.astral.sh/uv/), and `libarchive` (system library, for RAR archives).

```bash
docker compose up --build    # pipeline + dashboard (see Dashboard)
# or, without Docker:
uv sync                      # creates .venv with Python 3.12
uv run infdb-uy all          # every step below, in order; finished steps are skipped
```

Single steps:

| Command | What it does | Main outputs |
|---|---|---|
| `infdb-uy scope` | Fetches the official IM barrio polygon(s) named in the config | `prepared/scope.gpkg` |
| `infdb-uy im-wfs` | Downloads the configured IM WFS layers within the scope bounding box and keeps features intersecting the scope | `raw/im_wfs/<layer>/page_*.geojson`, `prepared/im_wfs.gpkg` |
| `infdb-uy dnc` | Newest (or configured) monthly DNC release and the urban parcel shapefile. Selects all records of the parcels intersecting the scope. | `prepared/dnc.gpkg` (`parcelas_urbanas`), `prepared/dnc/*.parquet` |
| `infdb-uy ine` | INE census cartography 2023 (reprojected to EPSG:32721, units intersecting the scope) and the variable dictionary | `prepared/ine_cartografia.gpkg`, `prepared/ine/*.parquet` |
| `infdb-uy lidar` | LiDAR 2024 tiles intersecting the scope. Inventory only: header, point counts per class. | `raw/im_lidar/*.laz`, `prepared/lidar_tiles.gpkg`, `reports/lidar_inventory.json` |
| `infdb-uy anda-metadata` | INE ANDA metadata through the public API | `prepared/ine_anda/<idno>/api_*.parquet`, `raw/ine_anda/<idno>/files/README.txt` |
| `infdb-uy anda-ingest` | Processes ANDA microdata files placed in the drop folder (see below) | `prepared/ine_anda/<idno>/*.parquet`, `.../scope/*.parquet` |
| `infdb-uy qa` | Descriptive report across all sources | `reports/qa.md`, `reports/qa.json` |
| `infdb-uy dashboard` | Web layers and parcel attributes for the explorer | `dashboard/*.geojson`, `dashboard/parcel_attributes.parquet` |
| `infdb-uy serve` / `start` | Run the explorer / `all` + `serve` | <http://localhost:8050> |

Options:

| Option | Effect |
|---|---|
| `--config` | Default `config/pilot-cordon.yml` |
| `--data-dir` | Override the data folder |
| `--refresh` | Re-query live sources (WFS, APIs) instead of reusing raw copies |
| `--force` | Rerun steps that `all` would skip as already completed |
| `-v` | Debug logging |

## Configuration

Everything area- and source-specific is in `config/pilot-cordon.yml`. To run another area, copy the file and change `scope.values` (IM barrio names). Extending the scope beyond Montevideo also needs:

- the DNC department and localidad codes
- the INE department code
- a different scope layer (the IM barrios only cover Montevideo)

## Outputs

All geometries are in EPSG:32721. Keys:

- `parcel_key` = `<dep>-<loc>-<padrón>`, for example `V-AA-1`. It is the same in all DNC tables and the parcel layer. The IM layers carry `padron` (Montevideo only, `V-AA`).
- INE census units: `DEPTO`, `SECC`, `SEG` (and `CODSEG` / `CODSECC`) as published.

| File / layer | Rows (Cordón, Oct 2026) | Notes |
|---|---|---|
| `scope.gpkg/scope` | 1 | IM barrio *CORDON*, 227.8 ha |
| `dnc.gpkg/parcelas_urbanas` | 5,131 polygons, 5,130 keys | One padrón has two polygons. All 5,131 lie within the scope. |
| `dnc/padrones_urbanos.parquet` | 27,802 | Parcels and PH units |
| `dnc/lineas_de_construccion.parquet` | 147,823 | Building parts, with `*_label` columns |
| `dnc/historico_valores.parquet` | 26,272 | |
| `dnc/mutaciones_catastrales.parquet` | 5 | Changes in the release month |
| `dnc/cod_*.parquet` | | Code tables of the release |
| `im_wfs.gpkg/parcelas` | 5,131 | IM parcel layer |
| `im_wfs.gpkg/accesos_puerta` | 10,293 | Door numbers with padrón and street segment |
| `im_wfs.gpkg/vias` | 560 | Street centrelines (not cut at the boundary) |
| `im_wfs.gpkg/zonas_censales_2023` | 287 | Census zones with 2023 population and dwellings |
| `im_wfs.gpkg/permisos_construccion` | 2,064 | Building permits |
| `im_wfs.gpkg/manzanas`, `barrios`, `municipios`, `lidar_index` | 211 / 11 / 2 / 8 | Neighbouring units that only touch the boundary have an overlap share near 0 |
| `ine_cartografia.gpkg/sg_23_pg` | 58 segments (17 within, 41 crossing) | Also `sc_23_pg` (8), `barrios_mvd_23_pg` (10), `ccz_mvd_23_pg` (3), `loc_23_pg`, `depto_23_pg` |
| `ine/diccionario_*.parquet` | 161 variables, 434 categories | Parsed from INE's xlsx |
| `lidar_tiles.gpkg/tiles` | 8 tiles | Inventory in `reports/lidar_inventory.json` |

## What the QA report shows (Cordón, October 2026)

These are observations from `reports/qa.md`. **None of them has been acted on.**

| Topic | Observation |
|---|---|
| DNC units | 27,802: 24,522 PH, 3,280 common |
| Construction lines | 147,823. 581 have year 0, and 2 have a year between 1 and 1799. 22,301 have 0 m². 10,963 have an original year (reformed parts). |
| Type of works | 16,460 lines are *a construir* (code 40, not yet built) |
| Lines of two regimes | 917 parcels have lines of both CO and PH. 40,512 lines (1,111,199 m² on 878 parcels) belong to a régimen without a unit record on the parcel. Flag: `unit_regimen_exists`. |
| Built area | All lines 4.79 M m². Lines with `unit_regimen_exists` 3.68 M m². Units' `area_edificada_m2` 3.07 M m². No definition is chosen here. |
| Codes without official label | use 0 / 75 / 99 (98 lines), category 0.0 (254), condition 0.0 (941), roof 5 (6,252), ceiling 0 (147,820: the code table only defines 1) |
| Largest uses by area | dwelling 2.37 M m², walls 0.39 M m², garage 0.29 M m², office 0.24 M m², hall 0.23 M m², shop 0.23 M m² |
| Parcels | 5,130 DNC keys = 5,130 IM padrones. 8 differ in each direction. 60 parcels have no construction line. 12 have no door point. |
| Montevideo-wide | 133 DNC parcels have no polygon, and 207 polygons have no DNC record. These cannot be placed. |
| Census zones (IM) | 287 intersect Cordón: 186 within (35,591 people, 20,884 dwellings), 101 crossing (18,471 people, 10,322 dwellings) |
| Census segments (INE) | 58: 17 within, 41 crossing |
| LiDAR | 8 tiles, 164 million points, 1.23 GB. CRS EPSG:5382. Classes outside the documented list: 11, 13, 15, 24, 105, 120, 121. |

## Verification against cédulas (October 2026)

The 100 cédula PDFs scraped from Catastro's web service (padrones `V-AA-1` … `V-AA-149`, issued 30 Sep 2026) were compared with the prepared tables of the 2026-09 release:

| Item | Result |
|---|---|
| Land area, land value | 100 / 100 identical |
| Built area, improvement value, total value | 99 / 100 identical |
| Value history (4 years) | 400 / 400 identical |
| Construction lines (level, area, year, category, condition), CO lines | 99 / 100 identical |

- The one difference, `V-AA-137`, shows a 2015 reform on the cédula that is not in the bulk extract. The cédula is generated live, while the bulk file is a monthly snapshot.
- Use labels differ only in wording between the cédula and DNC's code table, for example *LOCAL COMERCIAL* ↔ *COMERCIO*, *S.S. H.H. INDEPENDIE…* ↔ *SS HH INDEPENDIENTES*, *PARRILLERO* ↔ *CHURRASQUERA*.
- Cédulas of régimen común show only the CO lines. The bulk line file may also contain PH lines for the same padrón (see `unit_regimen_exists`).

## INE ANDA {#ine-anda}

INE distributes the weighted census microdata (July 2026, `URY-INE-CVPH-2023`) and the ECH through its NADA catalogue *ANDA*. The catalogue states access type *direct*: no account is needed. But the download page shows INE's **terms and conditions**, and downloading means accepting them:

- no redistribution
- scientific and statistical use with aggregate results only
- no re-identification
- no linking of INE data with other data that could identify individuals
- citation, and sending publications to INE

Accepting is a decision for the person or team using the data. **The pipeline does not submit that form.**

### Workflow

1. `uv run infdb-uy anda-metadata`. Fully automatic, using the public API (`/index.php/api/catalog/<idno>`, `/data_files`, `/variables`, `/variable/<vid>`). It stores:
    - raw JSON for every call (`raw/ine_anda/<idno>/metadata/`)
    - `api_data_files.parquet`, `api_variables.parquet` (label, format, universe, question, definition) and `api_categories.parquet` (value labels where the catalogue has them)
    - a `README.txt` in the drop folder `data/raw/ine_anda/<idno>/files/` with the download link, the terms summary and the list of expected files
2. **Manual:** open the catalogue page, accept the terms, download the data files, and put them unchanged into the drop folder. CSV, SPSS (`.sav`), Stata (`.dta`), Parquet and archives (`.zip`, `.rar`, `.7z`, `.tar*`) are accepted.
3. `uv run infdb-uy anda-ingest`:
    - **Unpacks** archives into `raw/ine_anda/<idno>/extracted/` with libarchive. The originals stay untouched.
    - **Converts** each table to parquet:
        - Text files: encoding and delimiter are detected, and **all columns stay strings**, so codes with leading zeros survive.
        - SPSS/Stata files: values are kept as stored, without applying value formats. Their embedded value labels go to `<table>__value_labels.parquet`.
    - **Validates** columns against the catalogue's variable list for the matching data file (missing, extra, case differences) → report.
    - **Writes a scope subset** to `prepared/ine_anda/<idno>/scope/<table>.parquet`. Records are matched to INE census units intersecting the scope at the finest level present in the file:
        - segment (`departamento`, `seccion`, `segmento`)
        - otherwise section
        - otherwise department

      The column names per study are set under `geography` in the config:
        - census: `DEPARTAMENTO`, `SECCION`, `SEGMENTO`
        - ECH: `dpto`, `secc`

      Matching uses the integer values of the published unit codes. Each record carries `scope_level`, `scope_relation` and `scope_overlap_share` of its census unit. Records whose unit codes are not numeric are counted, not guessed.
    - Writes `reports/ine_anda_ingest.json`.

### What the catalogue says (October 2026)

| IDNO | Files | Geography in microdata | Weight |
|---|---|---|---|
| `URY-INE-CVPH-2023` (census, July 2026) | F1 `personas_ext_05_2026_extraccion` (147 vars), F2 `viviendas_ext_05_2026_extraccion` (15 vars) | `DEPARTAMENTO`, `LOCALIDAD`, `SECCION`, `SEGMENTO` (+ `_AGRUP`), `BARRIO85`, `CCZ`, `MUNICIPIO_136` | `W` (with `ESTRATO`, `TR`) |
| `URY-INE-ECH-2023-v01` (ECH 2023) | F3 `base_FIES_2023`, F5 `ECH_implantacion_2023`, F6 `ECH_seguimiento_2023` | `dpto`, `secc`, `ccz`, `barrio` | `w` |

The ingest was tested on fixtures in a separate data folder:

- a synthetic SPSS file in a zip (segment matching, value labels, bad codes)
- the public anonymised 2024 census dwelling file (RAR with CSV, 1.66 million rows, department fallback, no catalogue match because only 36 % of its columns overlap)
- a synthetic semicolon-separated ECH CSV (section matching, non-numeric code)

Points to clarify once the files are available:

- **The `*_AGRUP` variants.** They are probably aggregated units for confidentiality. Their meaning is not documented in the API. Check INE's usage document (*Documento para uso de microdatos*, July 2026) before using them.
- **`BARRIO85`.** It is not the same code list as `CODBARRIOINE` in the cartography. No mapping is assumed.
- **Department codes.** The scope uses `ine_departamento: "01"` (Montevideo in the INE cartography). The census dictionary confirms code 1 = Montevideo. For the ECH `dpto`, check the same against `nom_dpto` in the downloaded file.
- **Value labels.** The API lists categories for only some variables. The full labels are in INE's dictionary (`prepared/ine/diccionario_categorias.parquet`), which was written for the 2024 version. Compare it with the July 2026 files before relying on it.

## Not done here, by design

- Building footprints or heights from LiDAR (needs thresholds and cleaning choices)
- Use classification, conditioned floor area, removal of walls or landings from areas
- Treatment of implausible years or unlabelled codes
- Assignment of construction lines to buildings, population or households to buildings
- Decisions about features crossing the scope boundary

These are covered in [Required changes](required-changes.md) and the [pilot workflow](pilot-cordon.md#workflow) (Steps 3–9).
