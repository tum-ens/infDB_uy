"""IM LiDAR 2024: download the tiles that intersect the scope and inventory them.

No derived products (DTM, nDSM, footprints) are made here; those involve modelling
choices and belong to a later processing step.
"""

from __future__ import annotations

import logging
from collections import Counter

import geopandas as gpd
import laspy
import pandas as pd

from ..core import Context, write_json

log = logging.getLogger(__name__)
SOURCE = "im_lidar"


def _inventory(path) -> dict:
    with laspy.open(path) as fh:
        h = fh.header
        classes: Counter = Counter()
        returns: Counter = Counter()
        for pts in fh.chunk_iterator(5_000_000):
            classes.update(_counts(pts.classification))
            returns.update(_counts(pts.return_number))
        crs = h.parse_crs()
        return {
            "las_version": f"{h.version.major}.{h.version.minor}",
            "point_format": h.point_format.id,
            "point_count": int(h.point_count),
            "scales": list(map(float, h.scales)),
            "offsets": list(map(float, h.offsets)),
            "mins": list(map(float, h.mins)),
            "maxs": list(map(float, h.maxs)),
            "crs": crs.to_string() if crs else None,
            "creation_date": str(h.creation_date) if h.creation_date else None,
            "system_identifier": h.system_identifier,
            "generating_software": h.generating_software,
            "classification_counts": {int(k): int(v) for k, v in sorted(classes.items())},
            "return_number_counts": {int(k): int(v) for k, v in sorted(returns.items())},
        }


def _counts(arr) -> Counter:
    import numpy as np

    vals, cnt = np.unique(np.asarray(arr), return_counts=True)
    return Counter(dict(zip(vals.tolist(), cnt.tolist())))


def run(ctx: Context) -> None:
    cfg = ctx.source(SOURCE)
    index = gpd.read_file(ctx.prepared("im_wfs.gpkg"), layer=cfg["index_layer"])
    log.info("LiDAR: %d tiles intersect the scope", len(index))
    rows = []
    for _, t in index.iterrows():
        sheet, url = t[cfg["sheet_field"]], t[cfg["url_field"]]
        dest = ctx.raw(SOURCE, f"LIDAR_MVD_2024_{sheet}.laz")
        ctx.download(url, dest, SOURCE)
        inv = _inventory(dest)
        rows.append({"sheet": sheet, "file": dest.name, "bytes": dest.stat().st_size,
                     "scope_relation": t["scope_relation"], "scope_overlap_share": t["scope_overlap_share"], **inv})
        log.info("%s: %d points, classes %s", sheet, inv["point_count"], inv["classification_counts"])
    write_json(ctx.reports("lidar_inventory.json"), rows)
    tiles = index.merge(pd.DataFrame(rows)[["sheet", "file", "bytes", "point_count", "las_version", "crs"]],
                        left_on=cfg["sheet_field"], right_on="sheet", how="left")
    tiles.to_file(ctx.prepared("lidar_tiles.gpkg"), layer="tiles", driver="GPKG")
