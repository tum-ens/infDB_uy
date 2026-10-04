# Required changes

This page lists what has to change in InfDB to run it on Uruguayan data. The changes are ordered along the pipeline. Each change carries a rough size:

| Size | Meaning |
|---|---|
| S | Configuration or a small function |
| M | A new importer or a rewritten SQL step |
| L | A new processing component |

The guiding principle is **adapt the inputs, keep the outputs**. Uruguayan data is loaded into the `opendata` schema and transformed so that `basedata.buildings` keeps the InfDB column contract. Downstream tools (pylovo, ro-heat, sunpot) then need as few changes as possible.

## 1. Configuration and CRS (S)

- New instance config `configs/config-infdb-import-uy.yml`, with all German sources set to `status: not-active`.
- Set `epsg: 32721` in the central `config-infdb.yml`. EPSG:3035 is a European projection and distorts lengths and areas in Uruguay. All Uruguayan sources except the INE GeoPackage (EPSG:4326) and the Google rasters are already in 32721.
- Replace the AGS scope with a Uruguayan scope definition, for example:

```yaml
infdb-import:
  name: "uy-mvd-cordon"
  scope:
    country: UY
    units:            # resolved against opendata.uy_scope
      - "V-AA"        # DNC departamento-localidad (Montevideo)
    clip:             # optional sub-localidad clip
      layer: im_barrios
      field: barrio
      values: ["CORDON"]
```

## 2. Scope and administrative units (M)

InfDB hard-wires BKG:

- `main.py` calls `bkg.load` before every other importer.
- `utils.fetch_scope_ags_from_db` and `utils.get_clip_geometry` query `opendata.bkg_vg5000_gem`.
- Many SQL steps filter on `gemeindeschluessel = '{ags}'`.

Changes:

1. New importer `uy_admin.py`, which loads:
    - the INE GeoPackage layers (department, localidad, segment, Montevideo barrios and CCZ), reprojected to 32721
    - the IM barrios and municipios
    - the DNC `Localidades.csv` and `paislocalidades_shp`
2. New table `opendata.uy_scope (scope_code, dnc_dep, dnc_loc, ine_codloc, name, geom)`. `scope_code` takes the role of the AGS. Montevideo is `V-AA` (INE `01` / `01020`).
3. **DNC↔INE crosswalk.** Match DNC localidades to INE localidades by name, then confirm by polygon overlap of `paislocalidades` with `loc_23_pg`. In Montevideo the mapping is trivial. Nationally it needs manual review for renamed or grouped localidades.
4. Generalise `fetch_scope_ags_from_db` / `get_clip_geometry` to read `uy_scope`, or provide a compatibility view `opendata.bkg_vg5000_gem (ags, geom)` on top of `uy_scope`. The view is the smaller change for a first run.
5. In `main.py`, call `uy_admin.load` instead of `bkg.load` when `country: UY`.

## 3. New importers (M each)

All importers follow the existing pattern in `services/infdb-import/src/*.py`: `load(infdb)`, an `if_active` guard, download into `opendata/`, import into schema `opendata` with a prefix.

| Importer | Source | Output tables (`opendata.`) | Notes |
|---|---|---|---|
| `dnc_padrones.py` | [DNC bulk CSV](data-sources.md#1-padrones-urbanos-y-rurales-dnc), monthly zip | `dnc_padrones_urbanos`, `dnc_lineas_construccion`, `dnc_historico_valores`, `dnc_mutaciones`, `dnc_padrones_rurales`, `dnc_cod_*` | Add column names from [the schema](reference-dnc-schema.md). Read text tables as Latin-1. Store the release month. Filter to the scope early: the line file has 4.5 million rows. |
| `dnc_parcelario.py` | [DNC shapefiles](data-sources.md#2-parcelario-shapefiles-dnc) | `dnc_parcelas_urbanas`, `dnc_parcelas_rurales`, `dnc_secciones`, `dnc_localidades` | Key `(coddepto, codloccat, padron)`. Clip to scope. |
| `im_wfs.py` | [IM GeoServer](data-sources.md#4-intendencia-de-montevideo-geoserver-wfs) | `im_accesos_puerta`, `im_vias`, `im_zonas_censales_2023`, `im_permisos_construccion`, `im_parcelas`, `im_barrios`, `im_municipios`, `im_lidar_index`, `im_manzanas` | Generic paged WFS 2.0 reader (`count`/`startIndex`), BBOX filter from scope, layer list in config. Mirror locally because of the intranet-only notice. |
| `im_lidar.py` | [LiDAR 2024](data-sources.md#5-lidar-2024-montevideo) | Files only (`opendata/lidar/*.laz`) | Select tiles from `im_lidar_index` that intersect the scope. Resumable range downloads. |
| `ine_census.py` | [INE GeoPackage](data-sources.md#12-ine-census-cartography-2023) and [microdata](data-sources.md#13-ine-census-microdata-2023) | `ine_segmentos_2023`, `ine_localidades_2023`, `ine_viviendas`, `ine_hogares`, `ine_personas`, `ine_dicc_*` | Fix the TLS chain. Unpack RAR (needs `unrar` or `py7zr`). Microdata are tables without geometry, keyed by localidad and municipio. |
| `mvot_asentamientos.py` | [MVOT ArcGIS REST](data-sources.md#16-asentamientos-irregulares-mvot) | `mvot_asentamientos_2024` | Single query, `f=geojson`. |
| `ide_elevation.py` *(later)* | [IDE MDT/MDS grids](data-sources.md#9-ide-urban-mdt-mds-201718) | Files + `ide_tiles` | Outside Montevideo only |
| `google_open_buildings.py` *(later)* | [Open Buildings 2.5D](data-sources.md#11-google-open-buildings-25d-temporal) | Raster files, `gob_buildings` | Outside Montevideo only |
| `openmeteo.py` | existing | existing | Only the scope lookup changes (centroid of `uy_scope` instead of the BKG grid) |

Importers not used for Uruguay: `bkg`, `lod2`, `basemap`, `plz`, `census2022`, `tabula`, `opendata_bavaria`, `kwp_*`, `nrw_opencloud`, `gebaeude_neuburg`, `waermeatlas_*`, `need`.

## 4. Building geometry from LiDAR (L)

This is the largest new component. It replaces `lod2.py` and the 3DCityDB `building_view` as the source of footprints and heights. Proposed tool: `tools/uy-buildings-lidar`.

1. **Terrain.** Ground points (class 2) → DTM raster, 0.5 m.
2. **Surface.** Building points (class 6) → nDSM = DSM − DTM.
3. **Footprints.** Rasterise class 6 → morphological clean-up → polygonise → simplify (for example 0.25 m tolerance) → drop parts under 10 m².
4. **Split by parcels.** Intersect footprints with the DNC parcel polygons. In dense blocks one LiDAR blob covers many attached buildings, and the parcel boundary is the best available split line. Pieces under a threshold (for example 5 m²) are merged into the neighbour.
5. **Heights.** Per footprint: median and 90th percentile of nDSM, and eave and ridge estimates for later LoD2.
6. **Output.** A table with the columns `infdb-basedata-buildings` expects from `building_view`:

    | Column | Value |
    |---|---|
    | `feature_id`, `objectid` | Stable ID, for example `UY-V-AA-<padrón>-<n>` |
    | `building_function_code` | DNC dominant use code |
    | `street`, `house_number` | IM door point |
    | `gemeindeschluessel` | `scope_code` |
    | `height` | nDSM median |
    | `groundsurface_flaeche` | Footprint area |
    | `geom`, `centroid` | Footprint and point on surface |

Option B, for later: generate CityGML LoD1/LoD2 from the same results and load it through the 3DCityDB importer. This keeps the 3D stack (API, viewers, sunpot roof surfaces) fully compatible. For the pilot, writing the `building_view` table directly is enough.

Tools: PDAL or `laspy` with `lazrs` for point clouds, `rasterio` and `shapely` for rasters and polygons. All run in the existing Python tool container.

## 5. Parcel–building assignment {#parcel-building-assignment}

The cadastre describes parcels and units, InfDB describes buildings. The rules are:

| Case | Rule |
|---|---|
| Common parcel (`CO`), one footprint | All construction lines → that building |
| Common parcel, several footprints (house + rear annex) | Lines are split by floor area: the largest footprint gets the lines with the highest floor levels. Remaining lines go proportionally by footprint area. |
| PH parcel (`PH`, all units share a padrón) | One building per footprint on the parcel. All unit lines are aggregated to it. The number of units gives the dwelling count. |
| Parcel with lines but no footprint | Flag `missing_geometry`. Use the parcel polygon as a proxy footprint, with height from floors × 3 m. |
| Footprint without lines | Flag `uncadastred`. Typical for informal settlements or sheds. Use is unknown. |
| `UH` (urbanización PH) | Treat each lot (manzana + unit) like a common parcel |

## 6. `infdb-basedata-buildings` SQL chain

| Step | File | Change | Size |
|---|---|---|---|
| 00 | `00_initalization.sql` | Replace `classify_building_use` (ALKIS codes) with a mapping from the 71 DNC use codes to InfDB classes (Residential, Commercial, Industrial, Public, …). Define which uses count as conditioned area (exclude walls, landings, open garages). | M |
| 01 | `01_create_temp_tables.sql` | Add columns: `padron_key`, `units`, `ph`, `dnc_category`, `dnc_condition`, `roof_type`, `ceiling`, `ac_share`, `heating_fuel` | S |
| 02 | `02_fill_id_object_id_building_use.sql` | Read from the LiDAR building table instead of `building_view`. Replace the ALKIS filter (`31001_%`, garages, water tanks) with DNC use rules. | S |
| 03 | `03_fill_height.sql` | Keep (height comes from the LiDAR table). Review the 3.5 m minimum: single-storey Uruguayan houses can be lower. | S |
| 04 | `04_fill_floor_area_geom.sql`, `04_a_fill_building_surface.sql` | Keep for footprint geometry. Wall and roof surfaces come from LoD1 extrusion until LoD2 exists. | S |
| 05 | `05_fill_floor_number.sql` | **Replace:** `floor_number = max(nivel) + 1` from DNC lines. Fall back to height ÷ 3 m. Flag disagreements over ±2 floors. | M |
| 06 | `06_prepare_grid.sql` | **Replace** the 100 m / 1 km grid with census zones (Montevideo) or segments (elsewhere) as `temp_census_units`. | M |
| 07 | `07_fill_occupants.sql` | Distribute `POB_TOT_23` of each census unit to residential buildings, weighted by **residential m²** from DNC (instead of volume). Nearest-unit fallback stays. | M |
| 08 | `08_fill_households.sql` | Households = occupied dwellings. For PH, use the number of residential units. For houses, use 1, or the census zone's occupied-dwelling count when larger. Household size distribution from microdata per municipio. | M |
| 09 | `09_fill_construction_year.sql` | **Replace** the random draw with the area-weighted mean year of the building's lines (also store min and max, and the original year of reformed parts). Census bands only as fallback. | S |
| 10 | `10_assign_postcode_to_buildings.sql` | Drop, or assign barrio and municipio instead | S |
| 11 | `11_create_building_to_grid.sql` | Becomes building → census unit | S |
| 12–13 | `12_*`, `13_a–d_*` | Building type: `AB` (apartment block) if PH with ≥ 4 residential units or ≥ 4 floors. `MFH` if PH or common parcel with 2–3 units. `SFH`/`TH` from touching-geometry rules as before. Check against census dwelling-type shares (`VIVVO01`) per municipio. | M |
| 14–15 | `14_*`, `15_*` | Keep | – |

## 7. Streets and building-to-street (M)

- `infdb-basedata-ways` reads basemap.de `verkehrslinie`. Point it at `opendata.im_vias` (Montevideo) and map `tipo` to InfDB road classes. Elsewhere use OSM.
- `buildings-to-street` can be **shortcut in Montevideo**: each IM door point carries `padron` and `gid_tramo_via` (street segment). Keep the geometric nearest-street method as fallback and for comparison.

## 8. Downstream tools

| Tool | Needed for Uruguay | Size |
|---|---|---|
| `openmeteo` / weather | Scope lookup only | S |
| `ro-heat` | A Uruguayan typology table that replaces TABULA: U-values and air change by DNC category × roof type × ceiling × construction period, plus census wall and roof material shares. Add **cooling demand**: Montevideo has mild winters and humid summers, and the census AC data allows calibration. Calibrate against the MIEM residential end-use study. | L |
| `pylovo-generation` | Needs Uruguayan low-voltage grid parameters (transformer sizes, cable types, consumer load profiles). None of the listed sources has them, so they need a UTE contact or literature values. | L |
| `sunpot` | Needs roof surfaces: LoD2 from LiDAR roof-plane segmentation (later). LoD1 flat roofs work as a first approximation. | M |
| `linear-heat-density` | Low priority: Uruguay has practically no district heating | – |
| `infdb-metadata` | Register the new sources and licences (DAG-UY, dag-uy, CC BY 4.0) | S |

## 9. Geometry outside Montevideo {#geometry-outside-montevideo}

Only Montevideo has a recent open LiDAR. For the national scale-up:

| Option | Footprint | Height | Pros and cons |
|---|---|---|---|
| A | Google Open Buildings polygons (v3) or OSM | Google 2.5D height raster | National and consistent. Height accuracy unknown, so validate on Montevideo LiDAR. |
| B | Same | IDE MDS − MDT 2017–18 (10 cm) | Accurate, but only 86 towns, and from 2017–18 |
| C | DNC parcel polygon | DNC floors × 3 m | Always available. No real footprint. Acceptable for rural areas and small towns. |

Recommendation: **A, with B where available, and C as fallback.** Compare all three on Cordón before choosing.

## 10. Open decisions

1. Footprint source outside Montevideo (section 9).
2. Accept INE's ANDA terms and conditions (weighted census microdata, ECH). This is a decision for the project team, see [Pipeline](pipeline.md#ine-anda). Request imNUBE access (MDS 2024), or derive the surface model from the public LiDAR.
3. Uruguayan typology: build it from the research literature and DNC categories, or start with a simplified TABULA mapping.
4. Contact UTE for grid data (pylovo).
5. Store DNC monthly releases as snapshots (history of parcels), or keep only the latest.
