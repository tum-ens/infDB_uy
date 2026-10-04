# InfDB Uruguay

This documentation describes how the [InfDB](https://github.com/tum-ens/InfDB) pipeline (TUM-ENS) can be applied to Uruguay. It covers:

- which Uruguayan open data can replace the German inputs of InfDB ([Data sources](data-sources.md)),
- how each InfDB stage maps to those sources ([Comparison with InfDB](infdb-comparison.md)),
- what has to change in InfDB to make it work ([Required changes](required-changes.md)),
- a first, deliberately small pilot in Montevideo ([Pilot – Cordón](pilot-cordon.md)),
- the data pipeline that downloads and prepares the pilot data ([Pipeline](pipeline.md)),
- the web dashboard to explore it ([Dashboard](dashboard.md)).

Implemented so far: download and preparation of the data for the Cordón pilot, without modelling assumptions ([Pipeline](pipeline.md)), and a data explorer ([Dashboard](dashboard.md)). Start both with `docker compose up --build`. Nothing of the InfDB adaptation itself (building derivation, attribute assignment) is implemented yet. Access checks and figures are from 2–3 October 2026.

## Key findings

1. **The cadastre is the strongest dataset, and it is fully open in bulk.** The Dirección Nacional de Catastro (DNC) publishes a monthly CSV release with every urban padrón (cadastral parcel or unit) and every *línea de construcción* (one row per building part: floor, use, construction category, condition, roof type, built area, year of construction). That is the same content as the per-property PDF *cédula catastral*. The September 2026 release matched 100 scraped cédulas field for field. **PDF scraping is not needed.**
2. **Cadastral records join to geometry almost perfectly.** The national urban parcel shapefile uses the same key (department letter + localidad code + padrón number). 99.7 % of the cadastral parcels have a polygon (99.9 % in Montevideo).
3. **What Uruguay lacks is building geometry.** There is no open LoD1/LoD2 building dataset comparable to the German CityGML. In Montevideo, the 2024 LiDAR survey (open, classified, building class 6) lets us derive footprints and heights. Outside Montevideo the options are the 2017–18 IDE surface models (86 towns), Google Open Buildings 2.5D (national) and OpenStreetMap.
4. **Census data is coarser in space than the German Zensus grid, but richer in energy content.** INE publishes 2023 population and dwelling counts per census zone (13,648 zones in Montevideo) and per segment nationally. The weighted household microdata (heating fuel, cooking fuel, air conditioning, solar water heaters, building materials) carries census section and segment codes. It is available after accepting INE's terms of use.
5. **InfDB's statistical estimation steps can partly be replaced by observed values.** Construction year, number of floors and floor area are estimated in Germany. In Uruguay they come directly from the cadastre. Population and households still have to be distributed from census units onto buildings.

## Recommended path

Start with **Cordón** (Municipio B, Montevideo):

- 228 ha
- 5,130 parcels and 27,802 cadastral units
- buildings from 1 to 12+ floors, built between 1900 and today
- 8 LiDAR tiles
- 230 census zones

Cordón also contains the 100 cédulas already validated against the bulk data. Once the pilot works end to end, extend to the whole of Montevideo, then to the rest of the country, where the building-geometry source has to change (see [Required changes](required-changes.md#geometry-outside-montevideo)).

## Document conventions

- **Padrón**: cadastral parcel number, unique within a *localidad catastral*. Properties under horizontal ownership (PH) carry additional keys *block*, *entrepiso/subsuelo* and *unidad*.
- **Key notation**: `V-AA-1` means department `V` (Montevideo), localidad `AA` (Montevideo), padrón `1`. The DNC uses this lettered system. INE uses a numeric one (`01` / `01020`).
- **CRS**: unless stated otherwise, EPSG:32721 (WGS 84 / UTM zone 21S), which almost every Uruguayan source uses natively.
