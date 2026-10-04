"""QA report: describes the prepared data and cross-source consistency.

Nothing here modifies data. The report states facts (counts, distributions, mismatches);
deciding what to do about them is left to later, documented processing steps.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .core import Context, write_json


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _dist(s: pd.Series) -> dict:
    s = pd.to_numeric(s, errors="coerce")
    q = s.quantile([0, 0.01, 0.25, 0.5, 0.75, 0.99, 1]).round(2)
    return {"n": int(s.notna().sum()), "missing": int(s.isna().sum()), "zeros": int((s == 0).sum()),
            "quantiles": {str(k): float(v) for k, v in q.items()}}


def run(ctx: Context) -> dict:
    P = ctx.prepared
    qa: dict = {"scope": {}, "dnc": {}, "cross_source": {}, "census": {}, "lidar": None}

    scope = gpd.read_file(P("scope.gpkg"), layer="scope")
    qa["scope"] = {"features": len(scope), "area_ha": round(float(scope.area.sum()) / 1e4, 2), "crs": ctx.crs}

    # ------------------------------------------------------------------ DNC
    dnc_dir = P("dnc", "x").parent
    if (dnc_dir / "lineas_de_construccion.parquet").exists():
        lines = pd.read_parquet(dnc_dir / "lineas_de_construccion.parquet")
        urb = pd.read_parquet(dnc_dir / "padrones_urbanos.parquet")
        qa["dnc"] = {
            "units_by_regimen": urb["regimen"].value_counts().to_dict(),
            "lines": len(lines),
            "lines_by_regimen": lines["regimen"].value_counts().to_dict(),
            "anio_construccion": _dist(lines["anio_construccion"]),
            "anio_construccion_below_1800": int((pd.to_numeric(lines["anio_construccion"]) .between(1, 1799)).sum()),
            "anio_construccion_after_current_year": int((pd.to_numeric(lines["anio_construccion"]) > pd.Timestamp.now().year).sum()),
            "anio_remanente_gt_0": int((pd.to_numeric(lines["anio_remanente"]) > 0).sum()),
            "area_m2": _dist(lines["area_m2"]),
            "nivel": _dist(lines["nivel"]),
            "tipo_obra_counts": lines["tipo_obra"].astype(str).value_counts().to_dict(),
            "lines_without_unit_of_same_regimen": {
                "lines": int((~lines["unit_regimen_exists"]).sum()),
                "area_m2": int(lines.loc[~lines["unit_regimen_exists"], "area_m2"].sum()),
                "parcels": int(lines.loc[~lines["unit_regimen_exists"], "parcel_key"].nunique()),
                "by_regimen": lines.loc[~lines["unit_regimen_exists"], "regimen"].value_counts().to_dict(),
            } if "unit_regimen_exists" in lines else None,
            "parcels_with_lines_of_several_regimes": int((lines.groupby("parcel_key")["regimen"].nunique() > 1).sum()),
            "destino_top20_by_area": (lines.groupby("destino_label", dropna=False)["area_m2"].sum()
                                      .sort_values(ascending=False).head(20).astype(int)
                                      .rename(index=lambda x: x if isinstance(x, str) else "<no label>").to_dict()),
            "summary": _load_json(ctx.reports("dnc_summary.json")),
        }

    # ------------------------------------------------------- cross-source
    gpkg = P("im_wfs.gpkg")
    parcels_dnc = gpd.read_file(P("dnc.gpkg"), layer="parcelas_urbanas") if P("dnc.gpkg").exists() else None
    if gpkg.exists() and parcels_dnc is not None:
        im_par = gpd.read_file(gpkg, layer="parcelas", ignore_geometry=True)
        doors = gpd.read_file(gpkg, layer="accesos_puerta", ignore_geometry=True)
        k_dnc = set(parcels_dnc["PADRON"].astype("int64"))
        k_im = set(pd.to_numeric(im_par["padron"], errors="coerce").dropna().astype("int64"))
        k_door = set(pd.to_numeric(doors["padron"], errors="coerce").dropna().astype("int64"))
        lines_keys = set(pd.read_parquet(dnc_dir / "lineas_de_construccion.parquet", columns=["padron"])["padron"].astype("int64")) \
            if (dnc_dir / "lineas_de_construccion.parquet").exists() else set()
        qa["cross_source"] = {
            "dnc_polygons_in_scope": len(k_dnc),
            "im_parcel_polygons_in_scope": len(k_im),
            "padron_in_dnc_not_im": len(k_dnc - k_im),
            "padron_in_im_not_dnc": len(k_im - k_dnc),
            "door_points_in_scope": len(doors),
            "door_padron_not_in_dnc_polygons": len(k_door - k_dnc),
            "dnc_polygons_without_door_point": len(k_dnc - k_door),
            "dnc_polygons_with_construction_lines": len(k_dnc & lines_keys),
            "dnc_polygons_without_construction_lines": len(k_dnc - lines_keys),
            "note": "Padrón comparison within Montevideo (DNC V-AA); features crossing the scope boundary are included.",
        }

    # -------------------------------------------------------------- census
    if gpkg.exists():
        z = gpd.read_file(gpkg, layer="zonas_censales_2023", ignore_geometry=True)
        qa["census"]["im_zonas_2023"] = {
            "zones": len(z),
            "by_scope_relation": z["scope_relation"].value_counts().to_dict(),
            "POB_TOT_23_within": int(z.loc[z["scope_relation"] == "within", "POB_TOT_23"].sum()),
            "POB_TOT_23_crossing": int(z.loc[z["scope_relation"] != "within", "POB_TOT_23"].sum()),
            "VIV_TOT_23_within": int(z.loc[z["scope_relation"] == "within", "VIV_TOT_23"].sum()),
            "VIV_TOT_23_crossing": int(z.loc[z["scope_relation"] != "within", "VIV_TOT_23"].sum()),
        }
    qa["census"]["ine_cartografia"] = _load_json(ctx.reports("ine_cartografia_summary.json"))
    qa["census"]["anda_metadata"] = _load_json(ctx.reports("ine_anda_metadata.json"))
    qa["census"]["anda_ingest"] = _load_json(ctx.reports("ine_anda_ingest.json"))
    inv = _load_json(ctx.reports("lidar_inventory.json"))
    if inv:
        total = {}
        for t in inv:
            for k, v in t["classification_counts"].items():
                total[k] = total.get(k, 0) + v
        qa["lidar"] = {"tiles": len(inv), "points": sum(t["point_count"] for t in inv),
                       "bytes": sum(t["bytes"] for t in inv), "classification_counts": total,
                       "crs": sorted({str(t["crs"]) for t in inv}), "las_versions": sorted({t["las_version"] for t in inv})}
    qa["im_wfs"] = _load_json(ctx.reports("im_wfs_summary.json"))

    write_json(ctx.reports("qa.json"), qa)
    ctx.reports("qa.md").write_text(_markdown(qa), encoding="utf-8")
    return qa


def _markdown(qa: dict) -> str:
    def block(title, obj):
        return f"## {title}\n\n```json\n{json.dumps(obj, ensure_ascii=False, indent=2, default=str)}\n```\n"

    parts = ["# QA report\n", "Descriptive only – no data was changed.\n"]
    for k in ("scope", "dnc", "cross_source", "census", "lidar", "im_wfs"):
        parts.append(block(k, qa.get(k)))
    return "\n".join(parts)
