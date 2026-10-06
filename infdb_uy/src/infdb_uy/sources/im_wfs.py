"""Intendencia de Montevideo GeoServer (WFS 2.0, GeoJSON).

Raw: every response page is stored unchanged under raw/im_wfs/<key>/.
Prepared: features are kept when they intersect the scope polygon. Geometries are
not cut; `scope_relation` and `scope_overlap_share` describe how they relate to it.
"""

from __future__ import annotations

import json
import logging

import geopandas as gpd
import pandas as pd

from ..core import Context, write_json
from ..scope import annotate_scope, load_scope

log = logging.getLogger(__name__)
SOURCE = "im_wfs"


def _params(ctx: Context, layer: str, bbox=None, cql=None) -> dict:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": layer,
        "srsName": ctx.crs,
    }
    if bbox is not None:
        params["bbox"] = ",".join(f"{v:.3f}" for v in bbox) + f",{ctx.crs}"
    if cql is not None:
        params["CQL_FILTER"] = cql
    return params


def _hits(ctx: Context, layer: str, bbox=None, cql=None) -> int:
    import re

    r = ctx.session.get(ctx.source(SOURCE)["endpoint"], params={**_params(ctx, layer, bbox, cql), "resultType": "hits"}, timeout=300)
    r.raise_for_status()
    m = re.search(r'numberMatched="(\d+)"', r.text)
    if not m:
        raise RuntimeError(f"Could not read numberMatched for {layer}: {r.text[:300]}")
    return int(m.group(1))


def _get_page(ctx: Context, layer: str, *, start: int | None, count: int, bbox=None, cql=None,
              sort_by: str | None = None) -> tuple[str, bytes]:
    cfg = ctx.source(SOURCE)
    params = {**_params(ctx, layer), "outputFormat": "application/json", "count": count}
    if start is not None:
        params["startIndex"] = start
    if sort_by:
        params["sortBy"] = sort_by
    if bbox is not None:
        params["bbox"] = ",".join(f"{v:.3f}" for v in bbox) + f",{ctx.crs}"
    if cql is not None:
        params["CQL_FILTER"] = cql
    r = ctx.session.get(cfg["endpoint"], params=params, timeout=600)
    r.raise_for_status()
    if not r.headers.get("Content-Type", "").startswith("application/json"):
        raise RuntimeError(f"WFS returned {r.headers.get('Content-Type')} for {layer}: {r.text[:300]}")
    return r.url, r.content


def fetch_layer(ctx: Context, key: str, *, bbox=None, cql=None) -> gpd.GeoDataFrame:
    """Download a layer (all pages) and return it as one GeoDataFrame."""
    cfg = ctx.source(SOURCE)
    layer = cfg["layers"][key]
    size = int(cfg.get("page_size", 5000))
    raw_dir = ctx.raw(SOURCE, key, "x").parent
    query = {"layer": layer, "bbox": list(bbox) if bbox is not None else None, "cql": cql, "page_size": size}
    query_file = raw_dir / "query.json"
    hits_file = raw_dir / "hits.json"
    cached = sorted(raw_dir.glob("page_*.geojson"))
    reuse = (cached and not ctx.refresh and hits_file.exists() and query_file.exists()
             and json.loads(query_file.read_text()) == query)
    if reuse:
        # compare cached pages with the count from the time they were downloaded; the live
        # layer keeps changing (e.g. new building permits)
        matched_total = json.loads(hits_file.read_text())["number_matched"]
    else:
        for f in [*cached, hits_file]:
            f.unlink(missing_ok=True)
        write_json(query_file, query)
        matched_total = _hits(ctx, layer, bbox, cql)
        write_json(hits_file, {"number_matched": matched_total})
    paged = matched_total > size
    sort_by = cfg.get("sort_by", "gid") if paged else None  # paging needs a stable order
    frames, start, page = [], 0, 0
    while True:
        page_file = raw_dir / f"page_{page:04d}.geojson"
        if reuse and page_file.exists():
            body = page_file.read_bytes()
        else:
            url, body = _get_page(ctx, layer, start=start if paged else None, count=size if paged else matched_total + 1,
                                  bbox=bbox, cql=cql, sort_by=sort_by)
            ctx.save_bytes(url, body, page_file, SOURCE)
        fc = json.loads(body)
        n = len(fc.get("features", []))
        if n:
            frames.append(gpd.GeoDataFrame.from_features(fc["features"], crs=ctx.crs))
        matched = fc.get("numberMatched")
        log.info("%s page %d: %d features (matched %s)", key, page, n, matched)
        start += n
        page += 1
        if not paged or n < size or (isinstance(matched, int) and start >= matched):
            break
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs=ctx.crs)
    gdf = pd.concat(frames, ignore_index=True)
    if len(gdf) != matched_total:
        raise RuntimeError(f"{key}: received {len(gdf)} features, server reported {matched_total}")
    if paged and sort_by in gdf and gdf[sort_by].duplicated().any():
        raise RuntimeError(f"{key}: sort key {sort_by!r} is not unique; paging could skip or repeat features")
    # GeoJSON feature ids are not carried by from_features; keep the order of the source.
    return gpd.GeoDataFrame(gdf, geometry="geometry", crs=ctx.crs)


def build_scope(ctx: Context) -> gpd.GeoDataFrame:
    """Fetch the scope polygon(s) exactly as published and store them."""
    sc = ctx.config["scope"]
    key = next(k for k, v in ctx.source(SOURCE)["layers"].items() if v == sc["layer"])
    values = ",".join(f"'{v}'" for v in sc["values"])
    gdf = fetch_layer(ctx, key, cql=f"{sc['field']} IN ({values})")
    found = set(gdf[sc["field"]]) if len(gdf) else set()
    missing = set(sc["values"]) - found
    if missing:
        raise RuntimeError(f"Scope values not found in {sc['layer']}: {sorted(missing)}")
    out = ctx.prepared("scope.gpkg")
    gdf.to_file(out, layer="scope", driver="GPKG")
    log.info("Scope: %s, %.1f ha", sorted(found), gdf.area.sum() / 1e4)
    return gdf


def run(ctx: Context) -> None:
    scope = load_scope(ctx)
    bbox = tuple(scope.total_bounds)
    cfg = ctx.source(SOURCE)
    summary = {}
    for key in cfg["layers"]:
        gdf = fetch_layer(ctx, key, bbox=bbox)
        n_bbox = len(gdf)
        gdf = annotate_scope(gdf, scope)
        gdf.to_file(ctx.prepared("im_wfs.gpkg"), layer=key, driver="GPKG")
        summary[key] = {
            "layer": cfg["layers"][key],
            "features_in_bbox": n_bbox,
            "features_intersecting_scope": len(gdf),
            "by_scope_relation": gdf["scope_relation"].value_counts().to_dict() if len(gdf) else {},
            "columns": [c for c in gdf.columns if c != "geometry"],
        }
        log.info("%s: %d intersecting scope", key, len(gdf))
    write_json(ctx.reports("im_wfs_summary.json"), summary)
