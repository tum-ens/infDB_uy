# Data downloads: links, file names, destinations

This page lists every file the pilot uses: where it comes from, what the file is called, and
where it ends up. All paths are relative to `infdb_uy/`. Background on each source is in
[Data sources](data-sources.md).

There are two kinds of sources:

- **Automatic.** The pipeline downloads these itself (`docker compose up` or `infdb-uy all`).
  Nothing to do by hand. Every download is recorded in `data/raw/manifest.jsonl` with URL,
  time, size and SHA-256.
- **Manual.** INE ANDA microdata. INE only releases them after you accept its terms of use in
  the browser, so you download them yourself and copy them into a drop folder. The pipeline
  never accepts the terms on your behalf.

Files in `data/` are never committed. ANDA microdata in particular must not be shared
(INE's terms forbid redistribution).

## 1. Automatic downloads

| Source | Link | File name(s) | Destination |
|---|---|---|---|
| DNC Padrones urbanos y rurales (bulk cadastre, monthly) | Dataset: <https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-padrones-urbanos-y-rurales>. The newest monthly release is found through the CKAN API: <https://catalogodatos.gub.uy/api/3/action/package_show?id=direccion-nacional-de-catastro-padrones-urbanos-y-rurales> | `datosabiertosdnc<YYYY-MM>.zip` (e.g. `datosabiertosdnc2026-10.zip`), plus `ckan_resource.json` (the catalogue entry) | `data/raw/dnc_padrones/<YYYY-MM>/` |
| DNC field descriptions | Same dataset | `metadatos-dnc-1.0.pdf` | `data/raw/dnc_padrones/metadata/` |
| DNC urban parcel shapefile | <https://catalogodatos.gub.uy/dataset/9e0dc092-a669-4697-b3ba-88808165c902/resource/3d211675-14a6-4e69-bc0b-6cc549060633/download/paisurbano_shp.zip> | `paisurbano_shp.zip` | `data/raw/dnc_parcelario/` |
| IM GeoServer WFS (9 layers: parcels, door numbers, streets, census zones 2023, building permits, blocks, barrios, municipios, LiDAR index) | <https://montevideo.gub.uy/app/geoserver/ows> – layer names in `config/pilot-cordon.yml` | `page_0000.geojson`, `page_0001.geojson`, … (one file per page of 5,000 features), `query.json` (the request), `hits.json` (feature count reported by the server at download time) | `data/raw/im_wfs/<layer>/`, e.g. `data/raw/im_wfs/parcelas/` |
| IM LiDAR 2024 (point clouds) | Info: <https://sig.montevideo.gub.uy/lidar-2024.html>. Tiles are selected through the WFS layer `mapstore-tematicas:fa_sig_lidar2024_v4` (field `enlace_lid` holds the direct link of each tile) | `LIDAR_MVD_2024_<HOJA>.laz`, one per tile. Cordón: 8 tiles `K-29-D-6-N-7`, `-N-8`, `-P-1` … `-P-6`, about 1.4 GB in total | `data/raw/im_lidar/` |
| INE census cartography 2023 (GeoPackage) | <https://www5.ine.gub.uy/documents/CENSO%202023/Cartografia/Mayo2026/gpck.zip> | `gpck.zip` | `data/raw/ine_cartografia/` |
| INE census variable dictionary 2023 | <https://www5.ine.gub.uy/documents/CENSO%202023/Microdatos/Diccionario%20de%20variables%202023.xlsx> | `Diccionario de variables 2023.xlsx` | `data/raw/ine_diccionario/` |
| INE ANDA catalogue metadata (all studies below) | API: `https://www4.ine.gub.uy/Anda5/index.php/api/catalog/<idno>` | `catalog.json`, `data_files.json`, `variables.json`, `variables/<vid>.json`, and a `README.txt` in the drop folder | `data/raw/ine_anda/<idno>/metadata/` |

The INE servers do not send their intermediate TLS certificate. The pipeline fetches it from
<http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt> and adds it to the
certificate bundle (setting `tls.extra_intermediates` in the config).

## 2. Manual downloads (INE ANDA microdata)

For each study:

1. Open the download page and accept INE's terms of use. Downloading means accepting them
   on your own behalf. No login is needed: all studies below are "direct access".
2. Download the files listed under "Download".
3. Copy them **unchanged** (do not unpack or rename archives) into the destination folder.
4. Restart (`docker compose up`) or run `uv run infdb-uy anda-ingest`.

The destination folders are created by the pipeline (step `anda-metadata`). Some INE study
IDs end with a dot, and so do their folder names.

| Study | Download page | Download | Not needed | Destination |
|---|---|---|---|---|
| Census 2023, weighted (Censos 2023, July 2026 version) | <https://www4.ine.gub.uy/Anda5/index.php/catalog/781/get-microdata> | `personas_ext_07_2026.csv` (RAR, 129 MB), `viviendas_ext_05_2026.csv.rar` (8 MB) | the `_rdata` versions (R format, not read) | `data/raw/ine_anda/URY-INE-CVPH-2023/files/` |
| Encuesta Continua de Hogares 2025 | <https://www4.ine.gub.uy/Anda5/index.php/catalog/779/get-microdata> | **Microdatos ECH 2025 Implantación** → `ECH_2025_implantacion.csv` (65 MB). Optional: the monthly follow-up files `ECH_01_2025.csv` … `ECH_12_2025.csv` | replicate weights (`Pesos replicados …`), `ECH_VICTIMIZACION_2025`, `FIES_2025` | `data/raw/ine_anda/INE-ECH-2025/files/` |
| Encuesta Nacional de Gastos e Ingresos de los Hogares 2016–17 | <https://www4.ine.gub.uy/Anda5/index.php/catalog/718/get-microdata> | all 4 (SAV): `ENGIH 2016 Base de Datos Gastos.sav`, `… Hogares.sav`, `… Personas.sav`, `ENGIH 2016 UPM y Estratos.sav` | – | `data/raw/ine_anda/URY-INE-ENGIH-2016-v04/files/` |
| Census 2011 (optional, for comparison) | <https://www4.ine.gub.uy/Anda5/index.php/catalog/243/get-microdata> | SPSS versions: `Hogares_spss_8_2013.rar`, `Viviendas_spss_8_2013.rar`, `Personas_spss_8_2013.zip`, `Censo Entorno Urbanistico 2011 (formato SPSS).rar`. Optional: `Base_unificada_Viv_Hog_Pers_spss_8_2013.zip` (the three tables already joined) | DBF versions (`*_dbf_*`, `Base Personas Censos 2011.rar`, `… (formato DBF).rar`): same tables, not read by the ingest | `data/raw/ine_anda/URY-INE-CPHV-2011-v02./files/` |
| Business register 2025 (Directorio de empresas) | <https://www4.ine.gub.uy/Anda5/index.php/catalog/782/get-microdata> | `Mpymes_2025.xlsx` | – | `data/raw/ine_anda/DM2025./files/` |
| Encuesta Continua de Hogares 2023 (optional, same year as the census) | <https://www4.ine.gub.uy/Anda5/index.php/catalog/735/get-microdata> | the CSV files | R versions | `data/raw/ine_anda/URY-INE-ECH-2023-v01/files/` |

What the ingest does with these files:

- It unpacks archives (ZIP, RAR, 7z) into `data/raw/ine_anda/<idno>/extracted/`. It only
  unpacks formats it reads (CSV, SPSS, Stata, Excel, Parquet), and nothing twice.
- It converts each table to Parquet in `data/prepared/ine_anda/<idno>/`, and writes the
  records in scope to `…/scope/`. The scope is selected by census segment or section where
  the study has those codes, otherwise by department (Montevideo). See
  [Pipeline](pipeline.md#ine-anda).
- It reports matches with the catalogue in `data/reports/ine_anda_ingest.json`.

Geography of each study in this pilot:

| Study | Finest geography used | Note |
|---|---|---|
| Census 2023 | census segment | Cordón's segments (68,695 persons) |
| ECH 2025 annual | census section | Sections are much larger than Cordón; check `scope_overlap_share`. The `barrio` column would be more precise but has no code list in the catalogue yet. |
| ECH 2025 monthly, ENGIH, business register | department | Montevideo |
| Census 2011 | department | Its section/segment codes refer to the 2011 census map, not the 2023 one used for the scope. |
| Business register | department | Its `Sección` column is the economic-activity section (CIIU), not a census section. |

## 3. Not downloaded (documented only)

Sources checked but not used yet, such as the IM surface model (gub.uy login), IM 3D models,
IDE terrain models, Google Open Buildings and MIEM energy statistics, are described in
[Data sources](data-sources.md).
