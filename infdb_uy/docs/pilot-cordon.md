# Pilot: Cordón (Montevideo)

The first implementation covers one barrio of Montevideo. The aim is to run the adapted pipeline end to end (import → buildings → population → streets → a first demand estimate) on a small area, before scaling to Montevideo and then the country.

## Why Cordón

| Criterion | Cordón |
|---|---|
| Data completeness | Everything needed is open and checked: DNC bulk data, parcels, IM door points, streets, 2023 census zones, LiDAR 2024 |
| Size | 228 ha, 8 LiDAR tiles (≈ 1.4 GB). Small enough to iterate quickly. |
| Building variety | Single-storey houses from the 1920s–40s next to 12+ storey apartment towers from the 2000s–2020s, plus offices, shops and garages |
| Existing validation | 135 of the padrones `V-AA-1` … `V-AA-149` lie in Cordón, including the 100 cédulas already checked against the bulk data |
| Mix of ownership regimes | 3,223 common parcels and 1,906 PH parcels, which tests both [assignment rules](required-changes.md#parcel-building-assignment) |

What Cordón does **not** cover: detached suburban housing (for example Carrasco or Punta Gorda), informal settlements (for example Casavalle) and peri-urban areas. Those are the next test areas (see [Extension](#extension)).

## Area profile

Computed from the DNC 2026-09 release, the DNC parcel shapefile, the IM barrio polygon and the 2023 census zones. Parcels and zones are assigned to the barrio by a point on their surface.

| Indicator | Value |
|---|---|
| Area | 228 ha |
| Parcels (shapefile) | 5,130: 3,223 common (`PC`), 1,906 PH, 2 without régimen |
| Cadastral units (`Padrones Urbanos`) | 27,802, of which 88 % are PH units |
| Construction lines | 147,823 |
| Built area (all uses) | 4.79 million m² |
| Of which *vivienda* (dwelling) | 2.37 million m² (≈ 50 %) |
| Other large uses | walls and fences 0.39, garage 0.29, office 0.24, hall 0.23, shop 0.23, storage 0.21, landings 0.16 million m² |
| Area-weighted mean construction year | 1976 |
| Census zones 2023 | 230 |
| Population 2023 | 44,219 |
| Dwellings 2023 (census) | 25,652 |
| LiDAR tiles | 8 |

Built area by construction period (DNC year of the line):

| Period | m² |
|---|---|
| before 1900 | 300 |
| 1900–1919 | 170,000 |
| 1920–1939 | 670,000 |
| 1940–1959 | 1,114,000 |
| 1960–1979 | 510,000 |
| 1980–1999 | 704,000 |
| 2000–2019 | 876,000 |
| 2020– | 735,000 |
| Missing or implausible year | ≈ 11,000 |

Parcels by number of storeys (highest DNC floor level + 1):

| Storeys | 1 | 2 | 3 | 4 | 5 | 6–9 | 10–11 | 12+ |
|---|---|---|---|---|---|---|---|---|
| Parcels | 1,682 | 1,454 | 1,061 | 646 | 247 | 319 | 121 | 457 |

## Scope definition

```yaml
infdb-import:
  name: "uy-mvd-cordon"
  scope:
    country: UY
    units: ["V-AA"]
    clip:
      layer: im_barrios        # mapstore-tematicas:zon_v_sig_barrios
      field: barrio
      values: ["CORDON"]
```

Barrio bounding box in EPSG:32721: `574283, 6136832, 576425, 6138479`. Use it with a 200 m buffer for WFS `BBOX` requests and LiDAR tile selection. Clip to the polygon afterwards.

## Workflow

Each step lists its inputs, outputs and a check that must pass before moving on.

### Step 0: Set up InfDB

- Run the InfDB stack (`infdb.sh`) with a new instance `uy-mvd-cordon`. Set `epsg: 32721`.
- Add the empty Uruguayan importer modules (see [Required changes §3](required-changes.md#3-new-importers-m-each)) and deactivate all German importers.

**Check:** the database is up. Schema `opendata` is empty.

### Step 1: Administrative scope

- **Inputs:** INE GeoPackage, IM barrios and municipios (WFS), DNC localidades.
- **Output:** `opendata.uy_scope` with `V-AA` and the Cordón clip polygon. The compatibility view for `fetch_scope_ags_from_db`.

**Check:** the scope polygon covers 228 ha. `fetch_scope_ags_from_db` returns `V-AA`.

### Step 2: Import open data

| Data | Source | Filter | Expected size |
|---|---|---|---|
| DNC bulk CSV (2026-09) | catalogodatos | `dep = V`, `loc = AA`, padrón in Cordón parcels | 27,802 units, 147,823 lines |
| DNC parcels | `paisurbano_shp.zip` | clip | 5,130 polygons |
| IM door points | WFS `cb_v_mdg_accesos_puerta` | BBOX + clip | — |
| IM streets | WFS `cb_v_sig_vias` | BBOX (+ 200 m) | — |
| Census zones 2023 | WFS `icen_poblacion_23` | BBOX + clip | 230 zones |
| Building permits | WFS `ic_v_ce_permisos_construccion_geom` | BBOX + clip | — |
| LiDAR 2024 | `fa_sig_lidar2024_v4` → LAZ | intersecting tiles | 8 tiles |
| Census microdata (weighted, ANDA) | INE `viviendas`, `personas` | census segments intersecting Cordón | — |
| Weather | Open-Meteo | scope centroid | hourly series |

**Check:** row counts match the expected sizes. The 100 scraped cédulas reproduce exactly from the imported tables (areas, values, lines).

### Step 3: Harmonise keys

- Build `padron_key = dep || '-' || loc || '-' || padron` on every DNC and IM table.
- Spatially join parcels → census zone, barrio and municipio (point on surface).
- Attach door points to parcels by `padron`. Keep the lowest door number as the main address (`es_minimo`).

**Check:** ≥ 99.5 % of DNC parcels have a polygon (Montevideo-wide value: 99.9 %). Every parcel has exactly one census zone. List parcels without a door point.

### Step 4: Derive buildings from LiDAR

- DTM from class 2, nDSM from class 6, footprints, split by parcels, heights (see [Required changes §4](required-changes.md#4-building-geometry-from-lidar-l)).
- Write the `building_view`-compatible table.

**Checks:**

- Visual check in QGIS against the 2024 orthophoto for 5 blocks.
- Sum of footprint areas vs DNC ground-floor areas, per parcel and in total.
- Share of parcels with lines but no footprint (`missing_geometry`), and footprints without lines (`uncadastred`).

### Step 5: Attach cadastral attributes

- Roll construction lines up to buildings using the [assignment rules](required-changes.md#parcel-building-assignment).
- Derive use, conditioned floor area (excluding walls, landings and open garages), floors, construction year (area-weighted, min, max), category, condition, roof type and number of units.

**Checks:**

- `floor_number` vs `height / 3 m`: flag more than ±2 storeys of difference.
- Construction years outside 1850–2026 are set to missing.
- Spot-check 20 buildings against the cédula PDFs.

### Step 6: Population and households

- Run the adapted SQL steps 06–08: census zones as units, residential m² as weight.
- Households from PH units and occupied dwellings. Household size and heating fuel shares from weighted microdata per census segment.

**Checks:**

- Σ occupants per zone = `POB_TOT_23`.
- Residential units from DNC vs census dwellings per zone. Report the ratio. The expected deviation comes from vacant, non-residential and unregistered units.
- Total population 44,219.

### Step 7: Building types

- Run the adapted steps 12–14: AB, MFH, SFH and TH from PH flag, unit count, floors and touching geometry.

**Check:** the type distribution against census dwelling types (`VIVVO01`: house vs apartment with or without lift) for the census segments in Cordón.

### Step 8: Streets and building-to-street

- `infdb-basedata-ways` on `im_vias`.
- Building → street via the door point's `gid_tramo_via`. Run the geometric nearest-street method as comparison.

**Check:** both methods agree on ≥ 95 % of buildings. Inspect the disagreements.

### Step 9: First downstream run

- Weather from Open-Meteo for the Cordón centroid.
- ro-heat with a **provisional** typology: a simple lookup by DNC category × construction period, marked as preliminary.
- Compare total residential demand per dwelling with the MIEM residential end-use study (Montevideo region).

**Check:** results are in a plausible range. Document the deviations as input for the typology work.

## Deliverables of the pilot

1. Importer modules: `uy_admin`, `dnc_padrones`, `dnc_parcelario`, `im_wfs`, `im_lidar`, `ine_census`.
2. LiDAR building tool (`uy-buildings-lidar`) producing the `building_view` table.
3. Adapted `infdb-basedata-buildings` SQL (steps 00, 02, 05–13) behind a `country: UY` switch.
4. `basedata.buildings` for Cordón, with quality flags.
5. A validation report covering every check above.
6. Updated documentation: lessons learned and changes needed for full Montevideo.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| IM geoservices switched to intranet-only | WFS import fails | Mirror all layers during step 2. Store the raw GeoJSON. |
| LiDAR blobs merge attached buildings | Wrong footprints | Split by parcel polygons (step 4). Flag parcels with odd ratios. |
| Census zone ≠ cadastral reality (vacant units, offices registered as dwellings) | Wrong occupant distribution | Weight by residential m². Report the ratio per zone. |
| INE TLS misconfiguration | Import fails | Bundle the intermediate certificate |
| DNC data quality (implausible years, 0 m² lines, walls counted as area) | Wrong attributes | Explicit cleaning rules in step 5 |

## Extension {#extension}

After Cordón, add one barrio per missing building pattern, then all of Montevideo:

| Barrio | Municipio | Parcels | PH share of units | Mean year | Census zones | LiDAR tiles | Tests |
|---|---|---|---|---|---|---|---|
| Cordón (pilot) | B | 5,130 | 0.88 | 1976 | 230 | 8 | Dense mixed, towers |
| Jacinto Vera | C | 1,760 | 0.65 | 1959 | 83 | 5 | Older low-rise housing |
| Carrasco | E | 3,983 | 0.44 | 1992 | 341 | 18 | Detached houses, large plots |
| Casavalle | D | 3,628 | 0.13 | 1976 | 399 | 19 | Social housing, informal settlements (uncadastred buildings) |

The whole of Montevideo has 200,105 cadastral parcels, 13,648 census zones and 870 LiDAR tiles (≈ 150 GB).
