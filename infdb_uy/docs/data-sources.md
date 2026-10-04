# Data sources

This is every source considered, grouped by provider, with the result of an access check run on 2–3 October 2026. **Status** means:

| Status | Meaning |
|---|---|
| ✅ Open | Downloaded or queried anonymously from a script. |
| ⚠️ Restricted | Reachable, but needs an account or login, or only partly checked. |
| ❌ Blocked | Not retrievable from a script. |

**Pilot role** says how the source is used in the [Cordón pilot](pilot-cordon.md):

- **Core**: required for the pilot.
- **Validation**: used to check results.
- **Later**: needed for national scale-up or downstream tools.
- **Not used**.

!!! warning "INE servers: TLS certificate chain"
    `www4.ine.gub.uy` and `www5.ine.gub.uy` send an incomplete certificate chain. Browsers work, but `curl`, Python `requests` and `urllib` fail with *unable to get local issuer certificate*. Importers must add the intermediate certificate to their trust store. Do not disable verification in production code.

## Overview

| # | Source | Provider | Status | Content | Pilot role |
|---|---|---|---|---|---|
| 1 | [Padrones urbanos y rurales](#1-padrones-urbanos-y-rurales-dnc) | DNC | ✅ | Parcels, units, construction lines, values (CSV, monthly) | Core |
| 2 | [Parcelario urbano / rural](#2-parcelario-shapefiles-dnc) | DNC | ✅ | Parcel polygons (SHP) | Core |
| 3 | [Cédula catastral web service](#3-cedula-catastral-web-service-dnc) | DNC | ✅ | Per-padrón PDF | Validation only |
| 4 | [IM GeoServer WFS](#4-intendencia-de-montevideo-geoserver-wfs) | Intendencia de Montevideo | ✅ | Parcels, door numbers, streets, census zones 2023, building permits, barrios, LiDAR index | Core |
| 5 | [LiDAR 2024](#5-lidar-2024-montevideo) | IM | ✅ | Classified point cloud (LAZ) | Core |
| 6 | [MDS 2024 (imNUBE)](#6-mds-2024-imnube) | IM | ⚠️ Login | Digital surface model | Not used (derive from LiDAR) |
| 7 | [Modelos 3D por zonas](#7-modelos-3d-por-zonas) | IM | ⚠️ Partly checked | Photorealistic meshes | Not used |
| 8 | [IM open data portal (CKAN)](#8-intendencia-de-montevideo-ckan) | IM | ✅ | Manzanas, historic population, settlements | Later |
| 9 | [IDE urban orthophotos / MDT / MDS 2017–18](#9-ide-urban-mdt-mds-201718) | IDE Uruguay | ✅ | 10 cm surface and terrain models, 86 towns | Later |
| 10 | [IDE national orthoimage / MDT](#10-ide-national-mdt) | IDE Uruguay | ✅ | 2.5 m terrain model, whole country | Later |
| 11 | [Google Open Buildings 2.5D Temporal](#11-google-open-buildings-25d-temporal) | Google Research | ✅ | Building presence and height rasters 2016–2023 | Later |
| 12 | [INE cartography 2023 (GeoPackage)](#12-ine-census-cartography-2023) | INE | ✅ | Census geographies with population and dwelling counts | Core |
| 13 | [INE census microdata 2023](#13-ine-census-microdata-2023) | INE | ✅ / ⚠️ Terms | Dwelling, household and person records | Core (distributions) |
| 14 | [INE census documentation](#14-ine-census-documentation-and-code-lists) | INE | ✅ | Questionnaire, definitions, code lists | Core (reference) |
| 15 | [Encuesta Continua de Hogares 2023](#15-encuesta-continua-de-hogares-2023) | INE | ⚠️ Terms | Household survey microdata | Later |
| 16 | [Asentamientos irregulares 2024](#16-asentamientos-irregulares-mvot) | MVOT | ✅ | Informal settlement polygons | Later |
| 17 | [MIEM energy statistics](#17-miem-energy-statistics) | MIEM | ✅ | National energy balance, residential end-use study | Later (calibration) |
| 18 | [Residential energy-efficiency study](#18-research-literature) | ResearchGate | ❌ 403 | Building typology research | Later (manual) |
| 19 | [Census zones 2011 (MGAP metadata)](#19-superseded-sources) | MGAP | ✅ | Metadata of old zones | Not used |

---

## 1. Padrones urbanos y rurales (DNC)

The most important dataset. It is the bulk equivalent of the cédula catastral, for the whole country.

| Property | Value |
|---|---|
| Catalogue | <https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-padrones-urbanos-y-rurales> |
| API | CKAN `package_show?id=direccion-nacional-de-catastro-padrones-urbanos-y-rurales` (188 resources, one zip per month since 09/2016) |
| Latest checked | `datosabiertosdnc2026-09.zip`, published 2026-09-17, 87,371,561 bytes |
| Format | Zip with 14 CSV files, **no header row**, comma-separated, quoted strings, Latin-1 for text tables |
| Licence | Licencia de Datos Abiertos del Gobierno de Uruguay (attribution) |
| Schema | `metadatos-dnc-1.0.pdf` in the same dataset (2023-06-14), reproduced in [Reference – Catastro bulk schema](reference-dnc-schema.md) |
| Spatial reference | None. Join to [source 2](#2-parcelario-shapefiles-dnc) by key. |
| Key | `(departamento, localidad, padrón)` for parcels, plus `(block, EP/SS, unidad)` for PH units |

Contents of the 2026-09 release:

| File | Rows | Content |
|---|---|---|
| `Padrones Urbanos.csv` | 1,473,575 | One row per urban parcel (régimen `CO`, 987,167) or unit (`PH` 474,575, `UH` 11,833). Land area, built area, land, improvement and total cadastral value, value for taxes, last DJCU date. |
| `Líneas de Construccion.csv` | 4,519,910 | One row per building part. Floor level, use (*destino*), construction category, conservation state, roof type, ceiling indicator, type of works, built area (m²), year of construction, original year. |
| `Histórico de Valores.CSV` | 1,668,889 | Cadastral and tax values for the previous four years |
| `Mutaciones Catastrales.CSV` | 1,941 | Parcel changes in the month: padrón, origin padrón, validity. This explains "padrón no vigente" (retired parcel numbers). |
| `Padrones Rurales.csv` | ≈ 8 MB | Rural parcels: section, area, values |
| Code tables | small | Departamentos, Localidades (498), Destinos (71), Categorías de Construcción, Estados de Conservación, Cubiertas, Cielorrasos, Tipos de Obra |

Verification against the cédulas: padrones `V-AA-1` and `V-AA-7` were compared line by line with the PDFs scraped earlier. These fields were identical:

- areas, values and the four-year value history
- floor levels and areas
- use, category, condition and year

Category code `3.0` corresponds to the cédula label *Mediana* (*Común* in the code table), and conservation `3.0` to *Regular*.

Data quality notes for import:

- The *Muros* (walls and fences), *Palier* (landings) and *Garage* uses are counted as built area. They must be excluded or flagged before computing heated or conditioned floor area.
- Some lines have implausible years (`0`, `180`, `1040`). In Cordón these cover about 10,800 m² of 4.8 million m². Treat them as missing.
- Lines with 0 m² exist (for example `V-AA-1`, use 13). Keep them for completeness, but ignore them in aggregates.
- PH properties have one row per unit in `Padrones Urbanos` and lines per unit in `Líneas de Construcción`. Common parts can be attached to a unit via *unidad uso exclusivo*.

## 2. Parcelario shapefiles (DNC)

| Property | Value |
|---|---|
| Catalogue | <https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-shapes-del-parcelario-rural-y-urbano> |
| Resources | `paisurbano_shp.zip` (109,802,401 bytes, updated 2026-09-09), `paisrural_shp.zip`, `paisseccat_shp.zip` (cadastral sections), `paislocalidades_shp.zip` |
| Format / CRS | ESRI Shapefile, UTF-8, WGS 84 / UTM 21S (EPSG:32721) |
| Licence | Licencia de Datos Abiertos del Gobierno de Uruguay |
| Fields (urban) | `NOMDEPTO, CODDEPTO, NOMLOCCAT, CODLOCCAT, PADRON, NUMCARCAT, NUMMANCAT, AREA, REGIMEN` |

The urban layer has 1,051,701 polygons and 1,048,633 distinct keys. Régimen values are `PC` (985,683), `PH` (61,458), `UH` (143) and empty (4,417).

Join coverage with [source 1](#1-padrones-urbanos-y-rurales-dnc) on `CODDEPTO + CODLOCCAT + PADRON`:

| Subset | Records | With polygon |
|---|---|---|
| All urban parcels | 1,048,670 | 99.7 % |
| Montevideo (`V`) | 200,105 | 99.9 % |
| Polygons with a cadastral record | 1,048,633 | 99.7 % |

672,170 parcels have at least one construction line. The others are vacant lots or carry no construction record.

## 3. Cédula catastral web service (DNC)

| Property | Value |
|---|---|
| URL | <http://sede.catastro.gub.uy/Sede/> → *Emisión de cédulas catastrales* |
| Access | GeneXus form. Choose ámbito, régimen, department, localidad and padrón, and the server generates `images/cedulas/{dep}-{loc}-{padrón}.pdf`. |
| Status | Works with browser automation. 100 PDFs were retrieved for `V-AA-1` … `V-AA-149`. |
| Use | **Validation only.** Everything in the PDF except street address and door number is in [source 1](#1-padrones-urbanos-y-rurales-dnc). Addresses come from [source 4](#4-intendencia-de-montevideo-geoserver-wfs). |

The 49 padrones that returned no PDF are retired ("no vigente", 43) or unknown ("no fue hallado", 6). They are not network errors.

## 4. Intendencia de Montevideo GeoServer (WFS)

| Property | Value |
|---|---|
| Endpoint | `https://montevideo.gub.uy/app/geoserver/ows` (WFS 1.0/2.0, `outputFormat=application/json`) |
| Capabilities | 200 feature types |
| CRS | EPSG:32721 |
| Licence | dag-uy (Montevideo open data licence, attribution) |
| Status | ✅ Anonymous queries succeeded. **Risk:** <https://sig.montevideo.gub.uy/geoservicios-ogc.html> states that geoservices are temporarily available to the intranet only. Mirror the layers you need into the database instead of querying live. |

Layers relevant to InfDB:

| Layer | Features | Geometry | Key attributes | Use |
|---|---|---|---|---|
| `mapstore-base:cb_v_mdg_parcelas_citim` | 208,611 | Polygon | `padron, areatot, areacat, ph, carpeta_ph` | Montevideo parcel geometry (cross-check with source 2) |
| `mapstore-base:cb_v_mdg_accesos_puerta` | 377,890 | Point | `padron, num_puerta, letra, cod_nombre_via, nom_calle, gid_tramo_via` | **Address per padrón and link to the street segment** |
| `mapstore-base:cb_v_sig_vias` | 33,502 | LineString | `gid, cod_nombre_via, nom_calle, tipo, cod_depto, cod_localidad` | Street centrelines (replaces basemap.de) |
| `mapstore-tematicas:icen_poblacion_23` / `icen_viviendas_23` | 13,648 | MultiPolygon | `CODCOMP` (zone code), `CODSEG`, `CODLOC`, `POB_TOT_23`, `POB_TOT_HO`, `POB_TOT_MU`, `VIV_TOT_23` | **Census 2023 population and dwellings per census zone** |
| `mapstore-tematicas:ic_v_ce_permisos_construccion_geom` | 43,893 | Point | `padron, fecha_aprob, dsc_destino, dsc_tipo_obra, dsc_categoria, area_edif` | Recent construction and refurbishment (validation, updates) |
| `mapstore-tematicas:fa_sig_lidar2024_v4` | 870 | MultiPolygon | `HOJA, enlace_lid` (direct LAZ link) | LiDAR tile index |
| `mapstore-tematicas:zon_v_sig_barrios` | 62 | Polygon | `barrio, nrobarrio, codba` | Barrios (pilot scope) |
| `mapstore-tematicas:zon_v_sig_municipios` | 8 | Polygon | `municipio` | Municipios |
| `mapstore-tematicas:ic_v_mdg_manzanas` | — | Polygon | | Cadastral blocks |
| `mapstore-tematicas:hyv_v_ai_asentamientos_sig` | — | Polygon | | Informal settlements (IM version) |
| `mapstore-base:cb_v_mdg_parcelas_log`, `cb_v_mdg_accesos_log` | — | | | Change logs for parcels and door numbers |

There is **no building-footprint layer** in the WFS.

## 5. LiDAR 2024 (Montevideo)

| Property | Value |
|---|---|
| Page | <https://sig.montevideo.gub.uy/lidar-2024.html> |
| Flight | November 2024, whole department |
| Tiles | 870 in the WFS index (the page says 871), named after the photo grid (for example `K-29-B-5-N-9`) |
| Download | Direct anonymous links: `https://imnube.montevideo.gub.uy/share/s/<id>/content/LIDAR_MVD_2024_<HOJA>.laz`. HTTP range requests work, so downloads can be resumed. |
| Format | LAS 1.4, LAZ-compressed, coordinate scale 0.01 m. The sample tile is 169,050,693 bytes. |
| Volume | ≈ 150 GB for the department, ≈ 1.4 GB for Cordón (8 tiles) |
| Classes | 1 unclassified, 2 ground, 3–5 vegetation (low, medium, high), **6 buildings**, 9 water |
| CRS (file header) | **EPSG:5382** (SIRGAS-ROU98 / UTM 21S), not EPSG:32721 like the vector data. The two datums differ at centimetre level, but the pipeline does not treat them as identical without a check. |
| Attributes per point (checked) | X/Y/Z (0.01 m resolution), classification, RGB colour (all points), intensity, return number and number of returns (up to 6), scan angle, scanner channel, GPS time. About 27 points/m² (tile K-29-D-6-P-4). Building points (class 6) in that tile range from 17 to 80 m elevation, ground from 25 to 35 m. |
| Undocumented classes | The 8 Cordón tiles also contain classes 11, 13, 15, 24, 105, 120 and 121 (about 75,000 of 164 million points). Their meaning is not on the IM page. Ask IM. |
| Guides | `Manual_de_descarga_de_archivos_de_imnube_lidar.pdf`, `guia_uso_lidar_qgis.pdf`, Potree desktop viewer |

Use it to derive building footprints (class 6), heights (class 6 minus a terrain model built from class 2), and later roof planes for LoD2 and PV potential.

## 6. MDS 2024 (imNUBE)

Digital surface model from the same flight. The download needs a gub.uy citizen login in imNUBE (`Repositorio/Documentos Públicos/Geomática/Vuelo_Noviembre_2024/MDS_2024`). The 2021 MDS is available on request by email (ufg@imm.gub.uy). It is not needed, because an equivalent surface model can be computed from [source 5](#5-lidar-2024-montevideo).

## 7. Modelos 3D por zonas

<https://sig.montevideo.gub.uy/modelos-3D.html> lists orthophotos, MDS and **photorealistic 3D models** by zone. The listing is rendered by JavaScript and was not inspected in depth. Photorealistic meshes carry no building semantics or parcel keys, so they are not useful as an InfDB input.

## 8. Intendencia de Montevideo CKAN

| Dataset | Resource | Note |
|---|---|---|
| [manzanas](https://ckan.montevideo.gub.uy/dataset/manzanas) | Shapefile via `generar_zip2.php?nom_tab=v_mdg_manzanas` | Cadastral blocks (also in WFS) |
| [poblacion-por-zona-censal-en-montevideo](https://ckan.montevideo.gub.uy/dataset/poblacion-por-zona-censal-en-montevideo) | `pobxzonas_2004.zip`, `pobxzonas_85-96.zip` | Censuses 1985, 1996 and 2004 only. Use the 2023 WFS layer instead. |
| [asentamientos-irregulares](https://ckan.montevideo.gub.uy/dataset/asentamientos-irregulares) | Shapefile | IM settlement layer (2024) |

The GeoNetwork record *Población por zona 2023* (`4066deb1-…`) describes the WFS layer `icen_poblacion_23`.

## 9. IDE urban MDT / MDS 2017–18

| Property | Value |
|---|---|
| Catalogue | <https://catalogodatos.gub.uy/dataset/ide-ortofotos-urbano> |
| Resources | GeoJSON tile grids with direct links to orthophotos, MDT and MDS |
| Coverage | 86 localities from the 2017–18 photogrammetric flight. The MDS grid has 2,753 tiles (Montevideo 477, Maldonado 298, Ciudad de la Costa 134, …). |
| Format | MDS as LAS and GeoTIFF at 10 cm resolution (sample GeoTIFF ≈ 11.9 MB), MDT likewise |
| Download | Direct, `https://visualizador.ide.uy/descargas/datos/CU_Remesa_XX/…` (range requests work) |
| Use | Building heights (MDS − MDT) in towns outside Montevideo, combined with footprints from source 11 or OSM |

## 10. IDE national MDT

<https://catalogodatos.gub.uy/dataset/ide-ortoimagen-mdt-de-cobertura-nacional> is a GeoJSON grid of 6,597 tiles with direct links to a 2.5 m terrain model (LAS and GeoTIFF) and orthoimages for the whole country, 2017–18. Use it as the terrain reference where no LiDAR exists.

## 11. Google Open Buildings 2.5D Temporal

| Property | Value |
|---|---|
| Pages | <https://sites.research.google/gr/open-buildings/temporal/>, [Earth Engine catalogue](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1) |
| Coverage | Africa, South and South-East Asia, **Latin America and the Caribbean** (includes Uruguay) |
| Time | Yearly, 2016–2023 |
| Content | Building presence (confidence), building height (0–100 m), fractional building count |
| Resolution | 4 m effective, rasters at 0.5 m |
| Licence | CC BY 4.0 or ODbL 1.0 (user's choice) |
| Access | Earth Engine (free registration), or direct download from Google Cloud Storage via the provided notebook |

This is the only national building-height source. Its accuracy has to be checked against the Montevideo LiDAR before relying on it elsewhere.

## 12. INE census cartography 2023

| Property | Value |
|---|---|
| Page | <https://www.gub.uy/instituto-nacional-estadistica/politicas-y-gestion/cartografia-estadistica> |
| Download | `https://www5.ine.gub.uy/documents/CENSO%202023/Cartografia/Mayo2026/gpck.zip` (58,498,142 bytes, see the TLS note above) |
| Format / CRS | GeoPackage, EPSG:4326 |
| Status note | INE states that weights and some territorial counts are under technical review (May 2026 update) |

| Layer | Features | Key | Attributes (all layers) |
|---|---|---|---|
| `depto_23_pg` | 20 | `DEPTO` | `VIV_OCUP_SP_23`, `VIV_DESOCUP_SP_23`, `TOT_VIV_SP_23`, `TOT_VIV_OCUP_POND_23`, `POB_TOT_23`, `POB_TOT_HOM_23`, `POB_TOT_MUJ_23`, area |
| `sc_23_pg` (secciones) | 236 | `CODSECC` | as above |
| `sg_23_pg` (segmentos) | 4,538 | `CODSEG`, `CODLOC` | as above |
| `loc_23_pg` / `loc_23_pt` | 652 | `CODLOC` | as above |
| `barrios_mvd_23_pg` | 63 | `CODBARRIOINE` | as above |
| `ccz_mvd_23_pg` | 18 | `CCZ` | as above |

The census-zone level (`CODCOMP`, finer than segments) is only published for Montevideo, through the IM WFS ([source 4](#4-intendencia-de-montevideo-geoserver-wfs)).

Related downloads on <https://www.gub.uy/instituto-nacional-estadistica/cartografia>:

- correspondence tables 1996–2004 and 2011–2023 (zone changes between censuses)
- code lists for departments, localidades 1963–2023 and Montevideo barrios
- `Definiciones.pdf`

## 13. INE census microdata 2023

| Version | Access | Files |
|---|---|---|
| Anonymised, version 2024 (superseded May 2026) | ✅ Direct download from `www5.ine.gub.uy/documents/CENSO%202023/Microdatos/` | `viviendas_ext_26_02.rar` (10,174,195 bytes), `hogares_…`, `personas_…`, `personas_ampliada_…`; `Diccionario de variables 2023.xlsx`; locality and department tables |
| Weighted ("ponderado"), version July 2026 (`URY-INE-CVPH-2023`, catalog 781; May 2026 version is catalog 780) | ⚠️ INE ANDA, access type *direct*: no account needed, but the download page requires **accepting INE's terms and conditions** (no redistribution, aggregate statistical use only, no re-identification, no linking that could identify individuals, citation). Metadata is public through the NADA API. | F1 `personas_ext_05_2026_extraccion` (147 variables), F2 `viviendas_ext_05_2026_extraccion` (15 variables) |

**Geography.**

- Anonymised version 2024: department, localidad (localities under 100 inhabitants are grouped as rural, code 900), municipio, region, urban or rural. No census section or segment.
- **Weighted version July 2026:** additionally `SECCION`, `SEGMENTO` (with `*_AGRUP` variants), `BARRIO85`, `CCZ` and `MUNICIPIO_136`, plus the weight `W`, `ESTRATO` and `TR`. Records can therefore be matched to the census segments of the INE cartography (`sg_23_pg`). Household attributes such as heating fuel become available per segment.

How the pipeline handles ANDA is described in [Pipeline](pipeline.md#ine-anda).

Variables relevant to energy modelling:

| Level | Variable | Code |
|---|---|---|
| Dwelling | Dwelling type (house; apartment in building with lift; without lift; single-storey building; …) | `VIVVO01` |
| Dwelling | Occupancy (occupied, temporary use, for rent or sale, under construction, ruinous, vacant) | `VIVVO02`, `VIVVO03` |
| Dwelling | Predominant material: exterior walls, roof, floor | `VIVDV01`, `VIVDV02`, `VIVDV03` |
| Household | Number of households in dwelling | `VIVHV01` |
| Household | Rooms, bedrooms | `HOGHD00`, `HOGHD01` |
| Household | Tenure | `HOGTE01`–`HOGTE03` |
| Household | **Main energy source for space heating** | `HOGCA01` |
| Household | **Main energy source for cooking** | `HOGSC02` |
| Household | Water heater (calefón, termofón, instantaneous) | `HOGCE27` |
| Household | **Solar collector** | `HOGCE26` |
| Household | **Air conditioning (yes, number of units)** | `HOGCE17`, `HOGCE17_1` |
| Household | Refrigerator, dryer, cars, … | `HOGCE03`, `HOGCE04`, `HOGCE13`, … |

## 14. INE census documentation and code lists

| Document | URL | Status |
|---|---|---|
| Census portal | <https://www.gub.uy/instituto-nacional-estadistica/censos2023pvh> | ✅ |
| Questionnaire with variable names | `www5.ine.gub.uy/documents/CENSO%202023/Cuestionario_Censo2023_variables.pdf` | ✅ (TLS note) |
| Microdata usage document (July 2026) | `…/Documento_para_uso_de_Microdatos_Censo_2023_090726.pdf` | ✅ (TLS note). The May 2026 version listed in the original research has been replaced. |
| Cartography definitions | `…/Cartografia/Definiciones.pdf` | ✅ (TLS note) |
| Methodology documents | `/politicas-y-gestion/documentos-metodologicos-censo-2023` | ✅ |
| Unoccupied dwellings report | `/comunicacion/noticias/censo-2023-caracterizacion-viviendas-desocupadas` | ✅ |

## 15. Encuesta Continua de Hogares 2023

INE ANDA [catalog 735](https://www4.ine.gub.uy/Anda5/index.php/catalog/735) (`URY-INE-ECH-2023-v01`), access type *direct* with terms and conditions as for the census. Files: `ECH_implantacion_2023` (517 variables), `ECH_seguimiento_2023` (132), `base_FIES_2023` (20). Geography variables: `dpto`, `secc`, `ccz`, `barrio`; weight `w`. The IM summary by municipio (`ECH_2023_Municipio.pdf`, 385 kB) downloads directly. Income and expenditure data are relevant later, for energy poverty and affordability.

## 16. Asentamientos irregulares (MVOT)

| Property | Value |
|---|---|
| Service | `https://sit.mvot.gub.uy/arcgis/rest/services/05_MVOT/HABITAT_Y_VIVIENDA/MapServer/2` (ArcGIS REST, capabilities Query, Map, Data) |
| Layer | *Asentamientos irregulares vigentes (2024)*, 667 polygons. `maxRecordCount` is 2000, so one query returns everything. |
| Fields | `Codigo_AI, Nombre_AI, Nombre_dep, Codigo_dep, Nombre_loc, Codigo_loc, Fecha_desd` |
| Documentation | RNAI 2024 methodology PDF (direct download), IDE GeoNetwork record `335f5f40-…` |

Informal settlements are mostly not in the cadastre as built parcels. The layer marks areas where cadastral building data is missing and has to be replaced by remote sensing.

## 17. MIEM energy statistics

| Item | Access | Content |
|---|---|---|
| [Datos abiertos MIEM](https://www.gub.uy/ministerio-industria-energia-mineria/datos-y-estadisticas/datos-abiertos) | ✅ 25 datasets on catalogodatos.gub.uy (CSV, XLSX, JSON, XML) | National energy balance (BEN): final consumption by sector (residential, commercial and services, industry, transport) and source |
| [Balance de Energía Útil residencial 2023](https://www.gub.uy/ministerio-industria-energia-mineria/datos-y-estadisticas/estadisticas/balance-energia-util-del-sector-residencial-datos-2023) | ✅ Report and interactive presentation (published 2026-08-21). No microdata found. | Useful-energy shares by end use (heating, hot water, cooking, …), region, income and household size |
| [Encuestas sobre energía](https://www.gub.uy/ministerio-industria-energia-mineria/datos-y-estadisticas/datos/encuestas-sobre-energia) | ✅ | Consumption surveys (industry 2024, …) |
| Mapas energéticos (content description PDF) | ✅ | Description of MIEM energy maps |

Use these for top-down calibration of the bottom-up building demand.

## 18. Research literature

*Eficiencia energética en el sector residencial en Uruguay* ([ResearchGate 374118462](https://www.researchgate.net/publication/374118462)) returns HTTP 403 to scripts and must be downloaded manually. It is a candidate basis for a Uruguayan building typology, which TABULA does not provide.

## 19. Superseded sources

- MGAP metadata for the 2011 census zones (`ine_zonas_11_metadatos.pdf`) is replaced by the 2023 cartography (sources 4 and 12).
- IM population by census zone 1985/1996/2004 is replaced by the 2023 layers.
- The anonymised census microdata version 2024 is replaced by the weighted May 2026 version. It is still useful as long as the weighted files have not been downloaded.
