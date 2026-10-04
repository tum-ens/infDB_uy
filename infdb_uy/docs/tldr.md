# InfDB Uruguay – summary

*Status October 2026 · English · [Deutsch](tldr.de.md) · [Español](tldr.es.md) · Start: `docker compose up --build`, then <http://localhost:8050>.*

## Goal and status

**Goal.** Run the InfDB pipeline on Uruguay, starting with **Cordón**, a 228 ha barrio of Montevideo.

**Done:**

- inventory of Uruguayan open data and its mapping to InfDB's inputs
- a pipeline that downloads and prepares the Cordón data without modelling assumptions
- a web explorer for that data

**Not done:** the InfDB adaptation itself (buildings from LiDAR, attribute assignment, population distribution).

## How Uruguay differs from the German InfDB inputs

| InfDB input (DE) | Uruguay | Verdict |
|---|---|---|
| LoD2 CityGML buildings | **No open building geometry.** Montevideo has an open LiDAR 2024 survey (classified, building class 6). Elsewhere: Google Open Buildings 2.5D, IDE surface models 2017–18, OSM. | Main gap. Footprints and heights must be derived. |
| Construction year, floors, floor area estimated from Zensus grid and geometry | **Observed in the cadastre.** DNC publishes every *línea de construcción* monthly, nationwide: floor, use, category, condition, roof type, m², year, original year of reformed parts. | Better. InfDB SQL steps 05 and 09 become lookups. |
| Zensus 100 m grid | Census 2023 per census zone (13,648 polygons, Montevideo only) or segment (national). Weighted microdata with heating fuel, AC and solar water heaters per segment, after accepting INE's terms. | Polygons instead of grid. Energy variables InfDB lacks. |
| BKG admin units / AGS | INE and DNC codes, which differ (`01`/`01020` vs `V`/`AA`), so a crosswalk is needed. | Adapt |
| basemap.de streets, PLZ | IM street axes plus door points carrying the padrón and the street segment (a ready building→street link). PLZ not needed. | Equal in Montevideo |
| TABULA typology | None. Build from DNC category × roof × year plus census materials. | Gap |
| pylovo grid parameters | No UTE (utility) data | Gap |
| CRS 3035 | EPSG:32721 (UTM 21S) everywhere. The LiDAR uses EPSG:5382 (SIRGAS-ROU98). | Config |

**In short:** Uruguay has better building *attributes* than Germany, but no building *geometry*. InfDB's estimation steps shrink, and a LiDAR building-derivation step has to be added. Details: [comparison](infdb-comparison.md), [required changes](required-changes.md).

## Pilot Cordón: checked results

**Data volumes:**

- 5,130 parcels and 27,802 cadastral units
- 147,823 construction lines
- 287 census zones touching the barrio (186 fully inside, 35,591 inhabitants)
- 8 LiDAR tiles (164 million points, 1.2 GB)

**Bulk cadastre vs. official cédula PDFs.** Compared against 100 cédulas scraped from Catastro's web service:

- 99 match exactly, on every floor line, area, year, category, condition, value and the 4-year value history.
- The one difference (V-AA-137) is a 2015 reform that appears on the cédula, which is generated live, but not in the September bulk extract.
- PDF scraping is therefore unnecessary.

**Joins.** 99.9 % of Montevideo's cadastral parcels have a polygon. Parcel and door-point keys agree for all but 8 parcels in Cordón.

**Reproducibility.** A clean `docker compose up --build` downloads everything (≈ 1.5 GB) and serves the dashboard in about 9 minutes. Raw files carry SHA-256 hashes in a manifest.

## Findings that need a decision before modelling

1. **Lines of two regimes on one parcel.** 917 parcels carry construction lines under both *común* (CO) and *propiedad horizontal* (PH), typically during a conversion. 40,512 lines (1.1 M m², 23 % of line area) belong to a regime without a unit record. Summing all lines double-counts these buildings.
2. **Three "built areas" disagree.** All lines give 4.79 M m², lines of existing regimes 3.68 M m², and the units' own built area 3.07 M m². Lines include walls, landings and open areas. Which definition feeds InfDB's `floor_area`?
3. **Data quality.** 581 lines have year 0, 22,301 have 0 m², and 16,460 are *a construir* (not yet built). Some codes have no label in DNC's code table (e.g. roof code 5 on 6,252 lines).
4. **LiDAR.** The tiles are in EPSG:5382 and contain classes (11, 13, 15, 24, 105, 120, 121) that the city's documentation doesn't describe.
5. **Census zones** crossing the barrio edge hold 18,471 more inhabitants. How they are attributed is a modelling choice.

All of these are reported, flagged and filterable in the dashboard, but **not resolved**. Following the pipeline's rule, raw data is kept unchanged.

## Next steps (proposed)

1. Derive building footprints and heights from the LiDAR (DTM, nDSM, footprints split by parcel).
2. Decide the rules for findings 1, 2 and 5, then adapt InfDB SQL steps 00, 02, 05–13 behind a country switch.
3. Accept INE's ANDA terms (weighted census microdata). The ingest pipeline is ready and tested on sample files.
4. Draft a Uruguayan building typology for ro-heat. Ask UTE about grid data for pylovo.
5. Extend from Cordón to barrios with detached houses (Carrasco) and informal settlements (Casavalle), then to all of Montevideo.
