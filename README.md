# infDB_uy – InfDB for Uruguay (proof of concept)

This repository is **proof-of-concept work**. It explores whether the [InfDB](https://github.com/tum-ens/InfDB) pipeline (TUM-ENS) can be applied to Uruguay, using one pilot barrio of Montevideo (**Cordón**, 228 ha).

Implemented so far:

- an inventory of Uruguayan open data and its mapping to InfDB's inputs
- a pipeline that downloads and prepares that data without modelling assumptions
- a web dashboard to inspect the data

The InfDB adaptation itself is **not** implemented yet.

| Where | What |
|---|---|
| [`infdb_uy/`](infdb_uy/) | Code, configuration, Docker setup and documentation |
| [`infdb_uy/docs/tldr.md`](infdb_uy/docs/tldr.md) | Two-page summary, also in [German](infdb_uy/docs/tldr.de.md) and [Spanish](infdb_uy/docs/tldr.es.md), with PDFs |
| [`infdb_uy/README.md`](infdb_uy/README.md) | Detailed usage |

## Start

```bash
git clone git@github.com:tum-ens/infDB_uy.git
cd infDB_uy/infdb_uy
docker compose up --build      # first run ≈ 10 min, downloads ≈ 1.5 GB
```

Then open <http://localhost:8050>. The interface is available in English, German and Spanish.

## Key points

- **Cadastre.** The bulk cadastral data (DNC) records observed building attributes per floor: use, category, condition, roof, area, year. It matches 99 of 100 official cédulas exactly.
- **Building geometry.** There is no open building geometry. Footprints and heights must be derived from the open LiDAR 2024 survey of Montevideo.
- **LiDAR.** The raw LiDAR data contains detailed, measured building information: centimetre-precise heights, about 27 points/m², classification, colour and multiple returns. It has been downloaded and inventoried but not processed yet.
- **3D view.** The dashboard's 3D view uses an **assumed** storey height, for visualization only.
- **Not resolved.** Data-quality findings, for example construction lines of two ownership regimes on one parcel (≈ 23 % of line area), are flagged but not fixed. See the summary.

## TODO

**Modelling (InfDB adaptation)**

- [ ] Derive buildings from LiDAR: DTM, nDSM, footprints split by parcel, measured heights. Replace the illustrative 3D view with them.
- [ ] Decide rules for:
    - lines of two regimes (CO/PH) on one parcel
    - which built-area definition feeds `floor_area` (lines 4.79 M m² / lines of existing regimes 3.68 M m² / units 3.07 M m²)
    - census zones crossing the scope boundary
- [ ] Adapt InfDB:
    - Uruguayan scope/admin importer, DNC↔INE code crosswalk, EPSG:32721
    - `infdb-basedata-buildings` SQL steps 00, 02, 05–13 behind a country switch
    - streets from IM street axes
    - building→street link via door points
- [ ] Building typology for ro-heat, including cooling demand. Calibrate against the MIEM residential end-use balance.
- [ ] Low-voltage grid parameters for pylovo (contact UTE). Roof surfaces (LoD2) for sunpot.

**Data**

- [ ] Accept INE's ANDA terms and download the weighted census 2023 microdata (and ECH). The ingest pipeline is ready. Then clarify the `*_AGRUP` variables and `BARRIO85` codes.
- [ ] Ask the Intendencia de Montevideo about:
    - the LiDAR CRS (EPSG:5382 vs. 32721)
    - the undocumented point classes (11, 13, 15, 24, 105, 120, 121)
    - the long-term availability of the WFS (announced as intranet-only)
- [ ] Ask DNC about roof code 5 and the other codes without labels.
- [ ] Extend the pilot to Carrasco (detached houses) and Casavalle (informal settlements), then to all of Montevideo. Choose the building-geometry source outside Montevideo (Google Open Buildings / IDE / OSM).

**Project**

- [ ] Tests and CI for the pipeline and API
- [ ] Translate the detailed docs (currently English only, summary in EN/DE/ES)
- [ ] Use a self-hosted or keyed basemap for heavier use (currently the public OSM tile server)
