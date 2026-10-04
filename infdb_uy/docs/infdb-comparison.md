# Comparison with InfDB

This page compares what InfDB consumes and produces for Germany with what the Uruguayan sources provide. The InfDB description is based on the [tum-ens/InfDB](https://github.com/tum-ens/InfDB) repository (main branch, October 2026).

## InfDB in brief

InfDB is a containerised PostgreSQL/PostGIS stack (with 3DCityDB 5.1 for 3D buildings) plus a set of tools that build a common *basedata* layer for energy-system models.

```
services/
  infdb-db        PostgreSQL + PostGIS + 3DCityDB 5.1
  infdb-import    downloads open data into schema "opendata"
  infdb-api       PostgREST, pygeoapi, FastAPI
  pgadmin, jupyter, infdb-qwc, infdb-lizmap, infdb-opencloud
tools/
  infdb-basedata-buildings   "opendata" -> "basedata" buildings (SQL chain 00-15)
  infdb-basedata-ways        street network
  buildings-to-street        building -> street assignment
  pylovo-generation          synthetic low-voltage grids
  ro-heat                    building heat demand
  linear-heat-density        district heating indicator
  sunpot                     PV potential
  infdb-metadata
```

How a run works:

- **Scope.** `config-infdb-import.yml` lists municipality keys (AGS, `LIKE` patterns allowed). `utils.fetch_scope_ags_from_db` resolves them against `opendata.bkg_vg5000_gem`. `main.py` always loads BKG first, then runs all other importers in parallel.
- **CRS.** Configured per instance. The template suggests EPSG:3035 (Europe). Importers reproject from EPSG:25832.

## Stage-by-stage mapping

| InfDB stage | German input (importer) | Uruguayan counterpart | Fit |
|---|---|---|---|
| Administrative scope | BKG VG5000 municipalities (`bkg.py`), AGS codes | INE GeoPackage (department, localidad, segment), IM barrios and municipios (WFS), DNC localidades. Codes: DNC letters (`V`/`AA`) and INE numbers (`01`/`01020`). | **Adapt.** Needs a scope table and a DNC↔INE crosswalk. |
| Statistical grid | BKG Geogitter 100 m / 1 km (`bkg.py`) | No grid. Irregular census polygons: 13,648 zones (Montevideo), 4,538 segments (country). | **Adapt.** Polygon joins instead of grid joins. |
| 3D buildings | LoD2 CityGML per federal state (`lod2.py`) into 3DCityDB, exposed as `building_view` | **None open.** Montevideo: LiDAR 2024 → derived LoD1. National: Google Open Buildings 2.5D, IDE MDS 2017–18, OSM footprints. | **Main gap.** New derivation step. |
| Building function | ALKIS code in LoD2 (`31001_xxxx`) | DNC use per construction line (71 *destinos*) | **Better.** Per floor, not per building. Needs a new classification function. |
| Address | LoD2 street and house number | IM door points (`padron`, `num_puerta`, `cod_nombre_via`, `gid_tramo_via`) | **Equal** in Montevideo. Gap elsewhere (OSM). |
| Height | LoD2 measured height | LiDAR nDSM (Montevideo), Google or IDE MDS elsewhere | Equal in Montevideo, weaker elsewhere |
| Floors | Estimated from height | DNC: highest floor level per building (observed) | **Better** |
| Floor area | Footprint × floors | DNC: built m² per line, by floor and use (observed) | **Better** |
| Construction year | Random draw from Zensus 2022 year bands per 100 m cell | DNC: year per construction line, plus the original year of reformed parts (observed) | **Much better** |
| Population | Zensus 100 m grid, distributed by building volume | Census 2023 per zone or segment, distributed by residential m² | Equal |
| Households | Zensus grid (household size, types) | Census dwellings per zone; household structure from weighted microdata per census segment | Slightly weaker in space |
| Building type SFH/TH/MFH/AB | Geometry (touching buildings) + Zensus building-type shares | DNC régimen (PH = apartments) + number of units + geometry; census dwelling type per municipio as reference | Equal or better |
| Heating system / fuel | Zensus heating type and energy source per grid cell | Census household heating fuel per census segment (weighted microdata) | Comparable (segments instead of grid cells) |
| Cooling | Not modelled | Census AC units per household | **New** (relevant in Uruguay) |
| Solar thermal | Not available | Census solar collector per household | **New** |
| Building typology | TABULA (`tabula.py`) | None. Must be built from DNC category, roof, ceiling and year plus census wall and roof materials. | **Gap** |
| Postcodes | PLZ GeoJSON (`plz.py`) | Not needed. Barrio and municipio serve the same purpose. | Drop |
| Streets | basemap.de traffic lines (`basemap.py`) | IM street centrelines (Montevideo), OSM elsewhere | Equal in Montevideo |
| Terrain | Bavaria DGM1 (`opendata_bavaria.py`) | LiDAR ground class (Montevideo), IDE MDT 2.5 m (country) | Equal |
| Weather | Open-Meteo (`openmeteo.py`), DWD | Open-Meteo works globally | **Reuse** |
| Grid data for pylovo | German reference grids and parameters | No UTE (utility) data among the sources | **Gap** |
| Calibration totals | – | MIEM energy balance, residential end-use study | New |

## Building attributes: where values come from

InfDB's `basedata.buildings` is filled by the SQL chain in `tools/infdb-basedata-buildings/sql/buildings_sql`. The table compares the origin of each attribute.

| Attribute | InfDB (Germany) | Uruguay (proposed) | Kind |
|---|---|---|---|
| `objectid`, `geom`, `centroid` | LoD2 ground surface | LiDAR-derived footprint (Montevideo) | Derived |
| `building_use` | `classify_building_use(ALKIS code)` | Area-weighted dominant DNC use per building | Observed |
| `street`, `house_number` | LoD2 | IM door point of the parcel | Observed |
| `height` | LoD2 | LiDAR nDSM (median of class 6 points minus ground) | Measured |
| `floor_area` | Footprint × floors | Sum of DNC line areas, excluding walls, landings and similar | Observed |
| `floor_number` | Height ÷ storey height | Highest DNC floor level + 1, checked against height | Observed |
| `occupants` | Zensus grid, weighted by volume | Census zone population, weighted by residential m² | Modelled |
| `households` | Zensus grid | Census zone dwellings (occupied), household size from microdata | Modelled |
| `construction_year` | Weighted random from Zensus bands | DNC year (area-weighted), original year for reforms | Observed |
| `postcode` | PLZ | Dropped (barrio and municipio instead) | – |
| `building_type` | Touching-geometry rules + Zensus | PH flag, unit count, use, touching geometry | Rule-based |

## Strengths and weaknesses of the Uruguayan data

**Strengths**

- **Observed building attributes.** InfDB estimates construction year, floors and floor area statistically. The Uruguayan cadastre records them per building part, nationally, and refreshes them monthly.
- **Clean keys.** Parcel geometry, cadastral records, door points and building permits all carry the padrón number.
- **Energy-related census variables**, including cooling and solar thermal, which the German Zensus lacks.
- **One CRS (EPSG:32721)** across almost all sources.

**Weaknesses**

- **No open building geometry.** Footprints and heights must be derived. This is straightforward from LiDAR in Montevideo and approximate elsewhere.
- **Coarse census geography outside Montevideo.** Segments are the finest published unit for both counts and weighted microdata. Census zones exist only for Montevideo.
- **No building typology or grid data.** These are needed by ro-heat and pylovo respectively.
- **Service availability.** The IM geoservices are announced as "intranet only", even though they currently answer. The INE TLS chain is broken.
- **Cadastre ≠ physical buildings.** A parcel can hold several buildings, and a PH building holds many units. Building-level aggregation must be designed (see [Required changes](required-changes.md#parcel-building-assignment)).
