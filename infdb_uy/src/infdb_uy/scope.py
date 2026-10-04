"""Scope polygon handling. The scope is used for selection only; geometries are never cut."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .core import Context


def load_scope(ctx: Context) -> gpd.GeoDataFrame:
    path = ctx.prepared("scope.gpkg")
    if not path.exists():
        raise FileNotFoundError("Scope not built yet – run `infdb-uy scope` first.")
    return gpd.read_file(path, layer="scope").to_crs(ctx.crs)


def annotate_scope(gdf: gpd.GeoDataFrame, scope: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep features intersecting the scope and describe the relation.

    scope_relation:      'within' | 'crosses_boundary'
    scope_overlap_share: share of the feature's area (polygons) or length (lines) inside
                         the scope; 1.0 / 0.0 for points; null for empty geometries.
    """
    if gdf.empty:
        out = gdf.copy()
        out["scope_relation"] = pd.Series(dtype="string")
        out["scope_overlap_share"] = pd.Series(dtype="float")
        return out
    gdf = gdf.to_crs(scope.crs)
    poly = scope.union_all()
    mask = gdf.intersects(poly)
    out = gdf.loc[mask].copy()
    within = out.within(poly)
    out["scope_relation"] = within.map({True: "within", False: "crosses_boundary"})

    gtype = out.geom_type.str.replace("Multi", "", regex=False)
    share = pd.Series(1.0, index=out.index)
    inter = out.intersection(poly)
    poly_mask = gtype == "Polygon"
    line_mask = gtype == "LineString"
    area = out.loc[poly_mask].area
    share.loc[poly_mask] = inter.loc[poly_mask].area / area.where(area > 0)
    length = out.loc[line_mask].length
    share.loc[line_mask] = inter.loc[line_mask].length / length.where(length > 0)
    out["scope_overlap_share"] = share.round(6)
    return out
