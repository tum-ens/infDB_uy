# InfDB Uruguay

Preparing Uruguayan open data for the [InfDB](https://github.com/tum-ens/InfDB) pipeline (TUM-ENS). The pilot area is the barrio **Cordón** in Montevideo. The repository contains:

- a **data pipeline** that downloads cadastral, city GIS, census and LiDAR data and prepares it without modelling assumptions,
- a **web dashboard** to explore the prepared data,
- the **documentation**: sources, comparison with InfDB, required changes, pilot plan.

**Two-page summary for reviewers:** [English](docs/tldr.md) ([PDF](docs/InfDB-Uruguay-summary.pdf)) · [Deutsch](docs/tldr.de.md) ([PDF](docs/InfDB-Uruguay-Zusammenfassung.pdf)) · [Español](docs/tldr.es.md) ([PDF](docs/InfDB-Uruguay-resumen.pdf))

## Quick start

Requirements: [Docker](https://docs.docker.com/get-docker/) with Compose, about 5 GB of free disk space, and an internet connection.

```bash
git clone <repository-url> infdb_uy
cd infdb_uy
docker compose up --build
```

Then open **<http://localhost:8050>**.

The first start takes about 10 minutes. It builds the image and downloads about 1.5 GB (cadastre 200 MB, INE 60 MB, LiDAR 1.2 GB), then prepares the data. Progress shows in the terminal. Later starts reuse `./data` and are up within seconds. Stop with `Ctrl+C`. Remove everything with `docker compose down` and by deleting `data/` except `data/README.md`.

**Without Docker:** install [uv](https://docs.astral.sh/uv/) (and the system library `libarchive`, which is usually installed already), then run `./run.sh`.

## What you can look at

| Dashboard tab | Content |
|---|---|
| Overview | Area summary, data quality observations, provenance of every download |
| (all tabs) | Interface in English, German or Spanish (selector top right). Data values stay as published (Spanish). |
| Cadastre | 5,131 parcels on a map, coloured by construction year, floors, use, regime or value. Cross-filtering of 147,823 construction lines by use, year, category, condition, roof, floor level. Click a parcel for its full cadastral record. |
| Census | 2023 population and dwellings per census zone. Status and variable catalogue of the INE ANDA microdata. |
| LiDAR | The 8 LiDAR 2024 tiles, point counts per class, header information |
| Data | Every prepared table: schema, rows, search, CSV export |

The API behind the dashboard is documented at <http://localhost:8050/api/docs>.

## Data handling

- `data/raw/`: downloads exactly as received. `data/raw/manifest.jsonl` records URL, time, size and SHA-256 of each file.
- `data/prepared/`: lossless copies for the scope. Official column names, official code labels next to the codes, keys, EPSG:32721. No row dropped, corrected or imputed.
- `data/reports/qa.md`: what looks unusual (years 0, codes without labels, ...), described but not changed.

**INE ANDA microdata** (weighted census 2023, household survey) are only available after accepting INE's terms of use on their website. The pipeline prepares the metadata and a drop folder. To add the microdata:

1. Download the files after accepting the terms.
2. Put them into `data/raw/ine_anda/<idno>/files/`.
3. Restart.

See [docs/pipeline.md](docs/pipeline.md#ine-anda). These files must not be committed or shared.

## Commands

```bash
docker compose up --build                          # pipeline + dashboard
docker compose run --rm explorer infdb-uy all --force   # rerun every pipeline step
docker compose run --rm explorer infdb-uy all --refresh # re-query live sources (WFS, APIs)
```

Without Docker, use `uv run infdb-uy <step>`. Steps:

| Step | What it does |
|---|---|
| `scope` | Fetch the scope polygon |
| `im-wfs` | City GIS layers |
| `dnc` | Cadastre |
| `ine` | INE cartography and dictionary |
| `lidar` | LiDAR tiles |
| `anda-metadata` | INE ANDA metadata |
| `anda-ingest` | Process ANDA microdata from the drop folder |
| `qa` | QA report |
| `dashboard` | Build the dashboard layers |
| `all` | All steps above |
| `serve` | Run the dashboard |
| `start` | `all` + `serve` |

The area and the sources are configured in `config/pilot-cordon.yml`.

## Documentation

| Page | Content |
|---|---|
| [Summary (TL;DR)](docs/tldr.md) | Two pages: differences to InfDB, checked results, open decisions |
| [Overview](docs/index.md) | Purpose, key findings, recommended path |
| [Data sources](docs/data-sources.md) | Every source, with access status, format, keys and licence |
| [Comparison with InfDB](docs/infdb-comparison.md) | Stage-by-stage mapping between German and Uruguayan inputs |
| [Required changes](docs/required-changes.md) | What to change in InfDB, ordered along the pipeline |
| [Pilot – Cordón](docs/pilot-cordon.md) | Scope, area profile, step-by-step workflow and checks |
| [Pipeline](docs/pipeline.md) | How the data is downloaded and prepared, including INE ANDA |
| [Dashboard](docs/dashboard.md) | What the explorer shows and how it is built |
| [Reference – Catastro bulk schema](docs/reference-dnc-schema.md) | Column layout and code tables of the DNC monthly CSV release |

As a website: `uv run --with mkdocs-material mkdocs serve`.

## Status

Implemented:

- data download and preparation for the Cordón pilot
- the data explorer

Not implemented: the InfDB adaptation itself (building derivation from LiDAR, attribute assignment, population distribution). See [docs/required-changes.md](docs/required-changes.md).

## Licences of the data

- Catastro, INE cartography, IDE: *Licencia de Datos Abiertos del Gobierno de Uruguay*
- Intendencia de Montevideo: *dag-uy*
- Basemap: © OpenStreetMap contributors
- INE microdata: INE's terms of use

The data are downloaded at run time and are not part of this repository. Bundled library: MapLibre GL JS (BSD-3-Clause, `src/infdb_uy/dashboard/static/vendor/LICENSE.txt`).
