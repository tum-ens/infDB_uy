"""Build the dashboard bundle (data/dashboard/) from data/prepared/.

Web layers are written as GeoJSON in EPSG:4326, coordinates rounded to 7 decimals (~1 cm),
for display only. Parcel attributes are descriptive aggregates of the cadastral records;
every attribute name says exactly what it counts. Nothing is inferred or modelled.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd

from ..core import Context, write_json

log = logging.getLogger(__name__)

# (output name, gpkg, layer, columns to keep or None for all)
LAYERS = [
    ("scope", "scope.gpkg", "scope", None),
    ("zonas_censales_2023", "im_wfs.gpkg", "zonas_censales_2023", None),
    ("segmentos_2023", "ine_cartografia.gpkg", "sg_23_pg", None),
    ("vias", "im_wfs.gpkg", "vias", None),
    ("accesos_puerta", "im_wfs.gpkg", "accesos_puerta", None),
    ("permisos_construccion", "im_wfs.gpkg", "permisos_construccion", None),
    ("manzanas", "im_wfs.gpkg", "manzanas", None),
    ("barrios", "im_wfs.gpkg", "barrios", None),
    ("lidar_tiles", "lidar_tiles.gpkg", "tiles", None),
]

PARCEL_SQL = """
WITH l AS (SELECT * FROM read_parquet('{lines}')),
u AS (SELECT * FROM read_parquet('{units}')),
use_area AS (
    SELECT parcel_key, coalesce(destino_label, 'código ' || CAST(destino AS VARCHAR)) AS use, sum(area_m2) AS a
    FROM l GROUP BY 1, 2
),
dominant AS (
    SELECT parcel_key, arg_max(use, a) AS use_largest_area FROM use_area GROUP BY 1
),
la AS (
    SELECT parcel_key,
           count(*)                                         AS n_lines,
           sum(area_m2)                                     AS lines_area_m2,
           sum(area_m2) FILTER (WHERE destino = 1)          AS lines_area_vivienda_m2,
           max(nivel)                                       AS nivel_max,
           max(nivel) FILTER (WHERE nivel >= 0)             AS nivel_max_aboveground,
           min(nivel)                                       AS nivel_min,
           count(DISTINCT nivel)                            AS n_niveles,
           min(anio_construccion) FILTER (WHERE anio_construccion > 0)    AS year_min_nonzero,
           max(anio_construccion) FILTER (WHERE anio_construccion > 0)    AS year_max_nonzero,
           median(anio_construccion) FILTER (WHERE anio_construccion > 0) AS year_median_nonzero,
           count(*) FILTER (WHERE anio_construccion = 0)    AS n_lines_year_0,
           count(*) FILTER (WHERE anio_remanente > 0)       AS n_lines_reformed,
           count(*) FILTER (WHERE tipo_obra = 40)           AS n_lines_a_construir,
           count(*) FILTER (WHERE NOT unit_regimen_exists)  AS n_lines_regimen_without_unit,
           sum(area_m2) FILTER (WHERE unit_regimen_exists)  AS lines_area_unit_regimen_m2
    FROM l GROUP BY 1
),
ua AS (
    SELECT parcel_key,
           count(*)                                   AS n_units,
           string_agg(DISTINCT regimen, '/' ORDER BY regimen) AS regimen_units,
           sum(valor_total)                           AS valor_total_sum,
           sum(area_edificada_m2)                     AS area_edificada_sum_m2,
           max(area_predio_m2)                        AS area_predio_max_m2
    FROM u GROUP BY 1
)
SELECT ua.*, la.* EXCLUDE (parcel_key), dominant.use_largest_area
FROM ua
LEFT JOIN la USING (parcel_key)
LEFT JOIN dominant USING (parcel_key)
"""


def _to_geojson(gdf: gpd.GeoDataFrame, path: Path) -> int:
    gdf = gdf.to_crs("EPSG:4326")
    for c in gdf.columns:
        if c != "geometry" and not pd.api.types.is_numeric_dtype(gdf[c]) and not pd.api.types.is_bool_dtype(gdf[c]):
            gdf[c] = gdf[c].astype("string")
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GeoJSON", COORDINATE_PRECISION=7)
    return len(gdf)


def run(ctx: Context) -> dict:
    P = ctx.prepared
    out = ctx.data_dir / "dashboard"
    out.mkdir(parents=True, exist_ok=True)
    built: dict = {"layers": {}}

    for name, gpkg, layer, cols in LAYERS:
        src = P(gpkg)
        if not src.exists():
            log.warning("Dashboard: %s missing, layer %s skipped", gpkg, name)
            continue
        gdf = gpd.read_file(src, layer=layer)
        if cols:
            gdf = gdf[cols + ["geometry"]]
        built["layers"][name] = _to_geojson(gdf, out / f"{name}.geojson")

    # parcels with descriptive cadastral attributes
    dnc = P("dnc", "x").parent
    parcels = gpd.read_file(P("dnc.gpkg"), layer="parcelas_urbanas")
    attrs = duckdb.sql(PARCEL_SQL.format(lines=dnc / "lineas_de_construccion.parquet",
                                         units=dnc / "padrones_urbanos.parquet")).df()
    attrs.to_parquet(out / "parcel_attributes.parquet", index=False)

    doors = gpd.read_file(P("im_wfs.gpkg"), layer="accesos_puerta", ignore_geometry=True)
    doors = doors.sort_values(["padron", "num_puerta"])
    first = doors.drop_duplicates("padron")[["padron", "nom_calle", "num_puerta"]]
    first["address_lowest_door"] = first["nom_calle"].str.strip() + " " + first["num_puerta"].astype("Int64").astype(str)
    first["padron"] = first["padron"].astype("int64")

    g = parcels[["parcel_key", "PADRON", "REGIMEN", "AREA", "scope_relation", "scope_overlap_share", "geometry"]].copy()
    g["PADRON"] = g["PADRON"].astype("int64")
    g = g.merge(attrs, on="parcel_key", how="left").merge(first[["padron", "address_lowest_door"]],
                                                          left_on="PADRON", right_on="padron", how="left")
    g = g.drop(columns=["padron"])
    # Illustration only (not data): extrusion height for the explorer's 3D view.
    storey = float(ctx.config.get("dashboard", {}).get("visual_storey_height_m", 3.0))
    g["vis_floors"] = (g["nivel_max_aboveground"] // 1 + 1).astype("Int64")
    g["vis_height_m"] = (g["vis_floors"].astype("float") * storey).round(1)
    built["visual_storey_height_m"] = storey
    built["layers"]["parcelas"] = _to_geojson(gpd.GeoDataFrame(g, geometry="geometry", crs=parcels.crs),
                                             out / "parcelas.geojson")
    write_json(out / "build.json", built)
    log.info("Dashboard bundle: %s", built["layers"])
    return built
