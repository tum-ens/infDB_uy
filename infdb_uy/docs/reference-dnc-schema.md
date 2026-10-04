# Reference: Catastro bulk schema

The CSV files in the DNC monthly release (`datosabiertosdnc<YYYY-MM>.zip`) have **no header row**. The column order below comes from `metadatos-dnc-1.0.pdf` (catalogodatos.gub.uy, 2023-06-14) and was confirmed against the 2026-09 release by matching padrones `V-AA-1` and `V-AA-7` with their cédulas.

The suggested column names are for the `opendata.dnc_*` tables.

## Padrones Urbanos.csv

| # | Column | Description | Type | Example (`V-AA-1`) |
|---|---|---|---|---|
| 1 | `regimen` | `CO` common, `PH` horizontal property, `UH` urbanización PH | char(2) | `CO` |
| 2 | `dep` | Department letter (see Departamentos) | char(1) | `V` |
| 3 | `loc` | Localidad code (see Localidades) | char(2) | `AA` |
| 4 | `padron` | Padrón number, unique within the localidad | int | `1` |
| 5 | `block` | Block (PH) or manzana (UH) | char(2) | `""` |
| 6 | `ep_ss` | Entrepiso / subsuelo | char(2) | `""` |
| 7 | `unidad` | Unit | int | `0` |
| 8 | `area_predio_m2` | Land area | int | `412` |
| 9 | `area_edificada_m2` | Built area | int | `436` |
| 10 | `valor_terreno` | Cadastral land value (UYU) | int | `1508595` |
| 11 | `valor_mejoras` | Cadastral improvement value (UYU) | int | `3888301` |
| 12 | `valor_total` | Total cadastral value (UYU) | int | `5396896` |
| 13 | `valor_impuestos` | Value for taxes (UYU) | int | `5396895` |
| 14 | `fecha_djcu` | Date of the last urban characterisation declaration (DJCU), `dd/mm/yyyy` or `/  /` | date | `/  /` |
| 15 | `vigencia_djcu` | Validity of the last DJCU | date | `/  /` |

## Líneas de Construccion.csv

| # | Column | Description | Type | Example (`V-AA-1`, 3rd line) |
|---|---|---|---|---|
| 1–7 | `regimen` … `unidad` | Same key as above | | `CO, V, AA, 1, "", "", 0` |
| 8 | `nivel` | Floor level (1 decimal, signed; negative = basement) | numeric | `1.0` |
| 9 | `destino` | Use code (see Destinos) | int | `1` (vivienda) |
| 10 | `categoria` | Construction category 1.0–5.0 (see below) | numeric | `3.0` |
| 11 | `estado` | Conservation state 1.0–5.0 (see below) | numeric | `3.0` |
| 12 | `cubierta` | Roof type (see Cubiertas) | int | `0` |
| 13 | `cielorraso` | Ceiling indicator (see Cielorrasos) | int | `0` |
| 14 | `tipo_obra` | Type of works (see Tipos de Obra) | int | `0` |
| 15 | `area_m2` | Built area of the line | int | `24` |
| 16 | `anio_construccion` | Year of construction | int | `1950` |
| 17 | `anio_remanente` | Original year of construction (for reformed parts) | int | `0` |
| 18 | `ep_ss_uso_exclusivo` | EP/SS of the unit with exclusive use | char(2) | `""` |
| 19 | `unidad_uso_exclusivo` | Unit with exclusive use | int | `0` |

## Histórico de Valores.CSV

| # | Column | Description |
|---|---|---|
| 1 | `regimen` | `CO`, `PH`, `UH`, `RU` (rural) |
| 2 | `dep` | Department |
| 3 | `seccion` | Cadastral section (rural only, else 0) |
| 4 | `loc` | Localidad |
| 5 | `padron` | Padrón |
| 6–8 | `block`, `ep_ss`, `unidad` | Unit key |
| 9, 10 | `valor_cat_y1`, `valor_imp_y1` | Cadastral and tax value, previous year |
| 11, 12 | `valor_cat_y2`, `valor_imp_y2` | Two years before |
| 13, 14 | `valor_cat_y3`, `valor_imp_y3` | Three years before |
| 15, 16 | `valor_cat_y4`, `valor_imp_y4` | Four years before |

!!! note "Column order differs from Padrones Urbanos"
    In the 2026-09 file the rows read `"CO","V","AA",0,1,…`: régimen, department, localidad, **section**, padrón. That is not the order printed in the metadata PDF (department, section, localidad). Map by observed position, and verify again on new releases.

## Mutaciones Catastrales.CSV

| # | Column | Description |
|---|---|---|
| 1 | `regimen` | `CO`, `PH`, `UH`, `RU` |
| 2 | `dep` | Department |
| 3 | `seccion` | Cadastral section (rural) |
| 4 | `loc` | Localidad |
| 5 | `padron` | Padrón |
| 6–8 | `block`, `ep_ss`, `unidad` | Unit key |
| 9 | `padron_origen` | Origin padrón |
| 10 | `fecha_vigencia` | Effective date |
| 11 | `vigencia_origen` | Origin padrón still valid (`S`/`N`) |
| 12 | `referencia` | Reference (if any) |

!!! note "Observed order"
    The 2026-09 rows read `"CO","A",0,"NR",174,"","",0,39968,31/08/2026," ",""`. Here column 9 is the origin padrón and column 10 the date, consistent with the table above.

## Padrones Rurales.csv

| # | Column | Description |
|---|---|---|
| 1 | `dep` | Department |
| 2 | `padron` | Padrón (unique within the department) |
| 3 | `seccion` | Cadastral section |
| 4 | `area_m2` | Parcel area |
| 5 | `valor_total` | Total cadastral value |
| 6 | `valor_impuestos` | Value for taxes |

## Code tables

**Departamentos**: letter → name. Montevideo is `V`.

**Localidades**: `(dep, loc)` → name, 498 rows. Montevideo has a single localidad, `V-AA`.

**Categorías de Construcción**

| Code | Label | Cédula label |
|---|---|---|
| 1.0 | Muy confortable | Muy buena |
| 1.5 | (intermediate) | |
| 2.0 | Confortable | Buena |
| 2.5 | (intermediate) | |
| 3.0 | Común | Mediana |
| 3.5 | (intermediate) | Mediana-económica |
| 4.0 | Económica | Económica |
| 4.5 | (intermediate) | |
| 5.0 | Muy económica | Muy económica |

The cédula labels were matched against 307 construction lines of the 100 scraped cédulas (matched by area and year), for codes 1.0, 2.0, 3.0, 3.5, 4.0 and 5.0. Code `0.0` appears as *No ingresado* (not recorded).

**Estados de Conservación**

The code table and the cédula use different labels for the same codes:

| Code | Code-table label | Cédula label |
|---|---|---|
| 0.0 | – | No tiene (not recorded) |
| 1.0 | Excelente | Muy bueno |
| 1.5 | Excelente/Bueno | Exc/Bue |
| 2.0 | Bueno | Bueno |
| 2.5 | Bueno/Regular | Bue/Reg |
| 3.0 | Regular | Regular |
| 3.5 | Regular/Malo | Reg/Mal |
| 4.0 | Malo | Malo |
| 4.5 | Malo/Muy malo | M/Muy M |
| 5.0 | Muy malo | Muy malo |

**Tipos de Obra**: 0 Original, 11–17 Reforma, 21–28 Paralizada (more than 1 year), 31–38 Habilitada sin terminar, 40 A construir, 50 A demoler. Nationally, 92 % of lines have 0 and 177,081 lines have 40 (*a construir*).

!!! warning "Reforms are encoded in the years, not in `tipo_obra`"
    On the cédula, a line is shown as *Reforma* when `anio_remanente > 0`. Then `anio_construccion` is the year of the reform and `anio_remanente` the original construction year. All 69 reform lines among the scraped cédulas follow this rule and have `tipo_obra = 0`. Use `anio_remanente` as the age of the structure (envelope) and `anio_construccion` as the age of the last refurbishment. 235,610 lines nationally (5 %) have an original year.

    Exclude lines with `tipo_obra` 40 (*a construir*) and 50 (*a demoler*) from the existing building stock.

**Destinos**: 71 use codes, including:

- 1 Vivienda
- 2 Escritorio / estudio / oficina
- 3 Consultorio
- 4 Comercio
- garage, depósito, salón, muros, palier, …

See `Destinos.csv` for the full list. The InfDB use mapping ([Required changes §6, step 00](required-changes.md#6-infdb-basedata-buildings-sql-chain)) has to cover all 71 codes.

**Cubiertas** (roof type) with the national line counts:

| Code | Label | Lines |
|---|---|---|
| 0 | Losa o bovedilla (concrete slab or vault) | 3,251,286 |
| 1 | Liviana sin cielorraso (light roof, no ceiling) | 665,123 |
| 2 | Liviana con cielorraso (light roof with ceiling) | 452,730 |
| 3 | Quincho sin cielorraso (thatch, no ceiling) | 25,446 |
| 4 | Quincho con cielorraso (thatch with ceiling) | 10,533 |
| 5 | *Not in code table* | 114,792 |

Code 5 occurs but is undocumented. Ask DNC, or treat it as unknown.

**Cielorrasos**: `1` *Con cielorraso* (149,584 lines). All other lines have `0` (no ceiling, or not applicable).

Roof type and ceiling are the most direct envelope information in the cadastre and key inputs for the thermal typology.
