"""Dirección Nacional de Catastro: monthly bulk CSV release and urban parcel shapefile.

Column names follow `metadatos-dnc-1.0.pdf` (catalogodatos.gub.uy). Where the observed
column order differs from that PDF it is noted below; both were checked against cédulas
(V-AA-1, V-AA-7) on the 2026-09 release.

Prepared tables contain every row of the selected parcels, unchanged. Codes keep their
raw value; official labels from the release's own code tables are added as `<col>_label`.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..core import Context, write_json
from ..scope import annotate_scope, load_scope

log = logging.getLogger(__name__)
SOURCE = "dnc_padrones"
ENCODING = "latin-1"
UNIT_KEY = ["regimen", "dep", "loc", "padron", "block", "ep_ss", "unidad"]

# --------------------------------------------------------------------------- schema
# (column, kind) with kind in {str, int, num, date}
SCHEMA: dict[str, list[tuple[str, str]]] = {
    "Padrones Urbanos": [
        ("regimen", "str"), ("dep", "str"), ("loc", "str"), ("padron", "int"),
        ("block", "str"), ("ep_ss", "str"), ("unidad", "int"),
        ("area_predio_m2", "int"), ("area_edificada_m2", "int"),
        ("valor_terreno", "int"), ("valor_mejoras", "int"), ("valor_total", "int"),
        ("valor_impuestos", "int"), ("fecha_djcu", "date"), ("vigencia_djcu", "date"),
    ],
    "Líneas de Construccion": [
        ("regimen", "str"), ("dep", "str"), ("loc", "str"), ("padron", "int"),
        ("block", "str"), ("ep_ss", "str"), ("unidad", "int"),
        ("nivel", "num"), ("destino", "int"), ("categoria", "num"), ("estado", "num"),
        ("cubierta", "int"), ("cielorraso", "int"), ("tipo_obra", "int"),
        ("area_m2", "int"), ("anio_construccion", "int"), ("anio_remanente", "int"),
        ("ep_ss_uso_exclusivo", "str"), ("unidad_uso_exclusivo", "int"),
    ],
    # Observed order: régimen, dep, loc, sección, padrón (PDF lists dep, sección, loc).
    "Histórico de Valores": [
        ("regimen", "str"), ("dep", "str"), ("loc", "str"), ("seccion", "int"), ("padron", "int"),
        ("block", "str"), ("ep_ss", "str"), ("unidad", "int"),
        ("valor_cat_y1", "int"), ("valor_imp_y1", "int"), ("valor_cat_y2", "int"), ("valor_imp_y2", "int"),
        ("valor_cat_y3", "int"), ("valor_imp_y3", "int"), ("valor_cat_y4", "int"), ("valor_imp_y4", "int"),
    ],
    "Mutaciones Catastrales": [
        ("regimen", "str"), ("dep", "str"), ("seccion", "int"), ("loc", "str"), ("padron", "int"),
        ("block", "str"), ("ep_ss", "str"), ("unidad", "int"),
        ("padron_origen", "int"), ("fecha_vigencia", "date"), ("vigencia_origen", "str"), ("referencia", "str"),
    ],
}
CODE_TABLES = {
    "Departamentos": ["dep", "label"],
    "Localidades": ["dep", "loc", "label"],
    "Destinos": ["code", "label"],
    "Categorías de Construcción": ["code", "label"],
    "Estados de Conservación": ["code", "label"],
    "Cubiertas": ["code", "label"],
    "Cielorrasos": ["code", "label"],
    "Tipos de Obra": ["code", "label"],
}
# column in Líneas de Construccion -> code table
LINE_LABELS = {
    "destino": "Destinos",
    "categoria": "Categorías de Construcción",
    "estado": "Estados de Conservación",
    "cubierta": "Cubiertas",
    "cielorraso": "Cielorrasos",
    "tipo_obra": "Tipos de Obra",
}


# ------------------------------------------------------------------------ download
def _release_resources(ctx: Context) -> tuple[str, dict, dict | None]:
    pkg = ctx.get_json(ctx.source(SOURCE)["ckan"])["result"]
    rx = re.compile(r"padrones urbanos y rurales\s+(\d{2})/(\d{4})", re.I)
    data, meta = {}, []
    for r in pkg["resources"]:
        name = (r.get("name") or "").lower()
        is_pdf = r["url"].lower().endswith(".pdf") or (r.get("format") or "").lower() == "pdf"
        if is_pdf and "metadatos" in name + r["url"].lower():
            meta.append(r)
            continue
        m = rx.search(name)
        if m and not is_pdf and "metadatos" not in name:
            data[f"{m.group(2)}-{m.group(1)}"] = r
    want = ctx.source(SOURCE).get("release") or max(data)
    if want not in data:
        raise KeyError(f"DNC release {want} not found; available: {sorted(data)[-6:]}")
    meta.sort(key=lambda r: r.get("created", ""))
    return want, data[want], (meta[-1] if meta else None)


def download(ctx: Context) -> Path:
    release, res, meta = _release_resources(ctx)
    zpath = ctx.download(res["url"], ctx.raw(SOURCE, release, Path(res["url"]).name), SOURCE)
    if meta:
        ctx.download(meta["url"], ctx.raw(SOURCE, "metadata", Path(meta["url"]).name), SOURCE)
    write_json(ctx.raw(SOURCE, release, "ckan_resource.json"), res)
    return zpath


# ------------------------------------------------------------------------- parsing
def _member(zf: zipfile.ZipFile, stem: str) -> str:
    for n in zf.namelist():
        if Path(n).stem.lower() == stem.lower():
            return n
    raise KeyError(f"{stem} not in {zf.filename}")


def _read_csv(zf: zipfile.ZipFile, stem: str, names: list[str], chunks: bool = False):
    raw = zf.open(_member(zf, stem))
    text = io.TextIOWrapper(raw, encoding=ENCODING, newline="")
    kw = dict(header=None, names=names, dtype=str, keep_default_na=False, na_values=[], quotechar='"')
    return pd.read_csv(text, chunksize=500_000, **kw) if chunks else pd.read_csv(text, **kw)


def _typed(df: pd.DataFrame, schema: list[tuple[str, str]], issues: dict) -> pd.DataFrame:
    """Convert columns to their documented type. Values that do not convert are kept
    in a `<col>_raw` column and counted in `issues`."""
    out = df.copy()
    for col, kind in schema:
        s = df[col]
        if kind == "str":
            continue
        if kind == "date":
            blank = s.str.strip().isin(["", "/  /"])
            parsed = pd.to_datetime(s.where(~blank), format="%d/%m/%Y", errors="coerce")
            bad = parsed.isna() & ~blank
            out[col] = parsed.dt.date
        else:
            parsed = pd.to_numeric(s.str.strip(), errors="coerce")
            bad = parsed.isna() & (s.str.strip() != "")
            out[col] = parsed.astype("Int64") if kind == "int" and not bad.any() and (parsed.dropna() % 1 == 0).all() else parsed
        if bad.any():
            out[f"{col}_raw"] = s.where(bad)
            issues[col] = int(bad.sum())
    return out


def _code_tables(zf: zipfile.ZipFile) -> dict[str, pd.DataFrame]:
    out = {}
    for stem, names in CODE_TABLES.items():
        df = _read_csv(zf, stem, names)
        if "code" in df:
            df["code_num"] = pd.to_numeric(df["code"], errors="coerce")
        out[stem] = df
    return out


def _add_labels(lines: pd.DataFrame, codes: dict[str, pd.DataFrame], issues: dict) -> pd.DataFrame:
    for col, table in LINE_LABELS.items():
        ct = codes[table].dropna(subset=["code_num"])
        mapping = dict(zip(ct["code_num"], ct["label"]))
        lab = lines[col].astype("float").map(mapping)
        lines[f"{col}_label"] = lab
        unmatched = lines.loc[lab.isna(), col].value_counts(dropna=False)
        if len(unmatched):
            issues[f"{col}_codes_without_label"] = {str(k): int(v) for k, v in unmatched.items()}
    return lines


# ----------------------------------------------------------------------- parcelario
def prepare_parcelario(ctx: Context) -> gpd.GeoDataFrame:
    cfg = ctx.config["sources"]["dnc_parcelario"]
    sc = ctx.config["scope"]
    zpath = ctx.download(cfg["url"], ctx.raw("dnc_parcelario", Path(cfg["url"]).name), "dnc_parcelario")
    with zipfile.ZipFile(zpath) as zf:
        shp = next(n for n in zf.namelist() if n.lower().endswith(".shp"))
    where = f"CODDEPTO = '{sc['dnc_departamento']}' AND CODLOCCAT = '{sc['dnc_localidad']}'"
    gdf = gpd.read_file(f"/vsizip/{zpath}/{shp}", where=where, engine="pyogrio")
    log.info("Parcelario %s: %d polygons in localidad", where, len(gdf))
    gdf = gdf.to_crs(ctx.crs)
    gdf = annotate_scope(gdf, load_scope(ctx))
    gdf.insert(0, "parcel_key", gdf["CODDEPTO"] + "-" + gdf["CODLOCCAT"] + "-" + gdf["PADRON"].astype("int64").astype(str))
    gdf.to_file(ctx.prepared("dnc.gpkg"), layer="parcelas_urbanas", driver="GPKG")
    log.info("Parcelario: %d polygons intersect the scope", len(gdf))
    return gdf


# -------------------------------------------------------------------------- tables
def prepare_tables(ctx: Context, zpath: Path, parcels: gpd.GeoDataFrame) -> tuple[dict, set[str]]:
    sc = ctx.config["scope"]
    dep, loc = sc["dnc_departamento"], sc["dnc_localidad"]
    keys = set(parcels["PADRON"].astype("int64").astype(str))
    out_dir = ctx.prepared("dnc", "x").parent
    report: dict = {"release_zip": zpath.name, "parcels_in_scope": len(keys), "tables": {}}

    with zipfile.ZipFile(zpath) as zf:
        report["zip_members"] = {i.filename: i.file_size for i in zf.infolist()}
        codes = _code_tables(zf)
        for stem, df in codes.items():
            df.to_parquet(out_dir / f"cod_{_slug(stem)}.parquet", index=False)

        for stem, schema in SCHEMA.items():
            names = [c for c, _ in schema]
            sel, n_total, n_loc = [], 0, 0
            for chunk in _read_csv(zf, stem, names, chunks=True):
                n_total += len(chunk)
                in_loc = (chunk["dep"] == dep) & (chunk["loc"] == loc)
                n_loc += int(in_loc.sum())
                hit = in_loc & chunk["padron"].str.strip().isin(keys)
                sel.append(chunk.loc[hit])
            df = pd.concat(sel, ignore_index=True)
            issues: dict = {}
            df = _typed(df, schema, issues)
            df.insert(0, "parcel_key", df["dep"] + "-" + df["loc"] + "-" + df["padron"].astype(str))
            if stem == "Padrones Urbanos":
                unit_regimes = set(zip(df["parcel_key"], df["regimen"]))
            if stem == "Líneas de Construccion":
                df = _add_labels(df, codes, issues)
                # Lossless flag: does the parcel have a unit record (Padrones Urbanos) of the
                # same régimen as this line? Lines of parcels changing régimen (e.g. CO -> PH)
                # can exist for both régimes; summing all lines then counts such buildings twice.
                df["unit_regimen_exists"] = [k in unit_regimes for k in zip(df["parcel_key"], df["regimen"])]
                issues["lines_without_unit_of_same_regimen"] = int((~df["unit_regimen_exists"]).sum())
            df.to_parquet(out_dir / f"{_slug(stem)}.parquet", index=False)
            report["tables"][stem] = {
                "rows_in_release": n_total,
                f"rows_in_{dep}-{loc}": n_loc,
                "rows_selected": len(df),
                "parcels_with_rows": int(df["parcel_key"].nunique()),
                "conversion_or_label_issues": issues,
            }
            log.info("%s: %d of %d rows selected", stem, len(df), n_total)

        # Parcels in the localidad present in the CSV but absent from the shapefile cannot
        # be placed spatially; count them so the gap is visible.
        urb_keys = set()
        for chunk in _read_csv(zf, "Padrones Urbanos", [c for c, _ in SCHEMA["Padrones Urbanos"]], chunks=True):
            m = (chunk["dep"] == dep) & (chunk["loc"] == loc)
            urb_keys.update(chunk.loc[m, "padron"].str.strip())
    return report, urb_keys


def _slug(s: str) -> str:
    s = s.lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def run(ctx: Context) -> None:
    zpath = download(ctx)
    parcels = prepare_parcelario(ctx)
    report, urb_keys = prepare_tables(ctx, zpath, parcels)

    # localidad-wide geometry coverage (independent of scope)
    sc = ctx.config["scope"]
    cfg = ctx.config["sources"]["dnc_parcelario"]
    zshp = ctx.raw("dnc_parcelario", Path(cfg["url"]).name)
    with zipfile.ZipFile(zshp) as zf:
        shp = next(n for n in zf.namelist() if n.lower().endswith(".shp"))
    allgeo = gpd.read_file(
        f"/vsizip/{zshp}/{shp}",
        where=f"CODDEPTO = '{sc['dnc_departamento']}' AND CODLOCCAT = '{sc['dnc_localidad']}'",
        columns=["PADRON", "CODDEPTO", "CODLOCCAT"], ignore_geometry=True, engine="pyogrio",
    )
    geo_keys = set(allgeo["PADRON"].astype("int64").astype(str))
    report["localidad_coverage"] = {
        "csv_parcels": len(urb_keys),
        "shapefile_parcels": len(geo_keys),
        "csv_parcels_without_polygon": len(urb_keys - geo_keys),
        "polygons_without_csv_record": len(geo_keys - urb_keys),
        "note": "CSV parcels without polygon cannot be assigned to the scope and are not in prepared tables.",
    }
    dup = parcels["parcel_key"].duplicated(keep=False)
    report["scope_parcel_polygons"] = {
        "polygons": len(parcels),
        "distinct_keys": int(parcels["parcel_key"].nunique()),
        "keys_with_multiple_polygons": int(parcels.loc[dup, "parcel_key"].nunique()),
        "by_scope_relation": parcels["scope_relation"].value_counts().to_dict(),
        "by_regimen": parcels["REGIMEN"].fillna("").value_counts().to_dict(),
    }
    write_json(ctx.reports("dnc_summary.json"), report)
