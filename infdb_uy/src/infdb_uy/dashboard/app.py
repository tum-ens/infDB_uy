"""Dashboard web server: FastAPI + DuckDB over data/prepared and data/dashboard.

Read-only. All analysis is descriptive (counts, sums, distributions) on the prepared data.
"""

from __future__ import annotations

import io
import json
import os
import threading
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..core import Context

STATIC = Path(__file__).parent / "static"

# facet -> (column in lines, label column)
FACETS = {
    "destino": ("destino", "destino_label"),
    "categoria": ("categoria", "categoria_label"),
    "estado": ("estado", "estado_label"),
    "cubierta": ("cubierta", "cubierta_label"),
    "tipo_obra": ("tipo_obra", "tipo_obra_label"),
    "regimen": ("regimen", None),
    "unit_regimen_exists": ("unit_regimen_exists", None),
}


def network_urls(ctx: Context, port: int | None = None) -> dict:
    """LAN URLs of the dashboard. In Docker the host's address comes from the netinfo service
    (data/state/host_network.json); outside Docker it is determined directly."""
    from ..netinfo import lan_ips

    published = os.environ.get("PUBLISHED_PORT", "")  # "8050" or "127.0.0.1:8050"
    port = int(published.rsplit(":", 1)[-1] or port or 8050)
    in_docker = Path("/.dockerenv").exists()
    if published.count(":") and not published.startswith("0.0.0.0:"):  # bound to one address only
        return {"port": port, "in_docker": in_docker, "hostname": None, "urls": []}
    f = ctx.data_dir / "state" / "host_network.json"
    info = json.loads(f.read_text()) if in_docker and f.exists() else None
    ips = (info or {}).get("ips", []) if in_docker else lan_ips()
    return {"port": port, "in_docker": in_docker, "hostname": (info or {}).get("hostname"),
            "urls": [f"http://{ip}:{port}" for ip in ips]}


def _clean(obj):
    """JSON-safe values (NaN -> None, numpy -> python)."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    if hasattr(obj, "item"):
        return _clean(obj.item())
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj


def _records(df: pd.DataFrame) -> list[dict]:
    return _clean(json.loads(df.to_json(orient="records", date_format="iso")))


def create_app(ctx: Context) -> FastAPI:
    P = ctx.prepared
    D = ctx.data_dir / "dashboard"
    R = ctx.reports
    lines_pq = P("dnc", "lineas_de_construccion.parquet")
    lock = threading.Lock()
    con = duckdb.connect()
    con.execute(f"CREATE VIEW lines AS SELECT * FROM read_parquet('{lines_pq}')")
    app = FastAPI(title="InfDB Uruguay – data dashboard", docs_url="/api/docs")

    def q(sql: str, params: list | None = None) -> pd.DataFrame:
        with lock:
            return con.execute(sql, params or []).df()

    @lru_cache(maxsize=32)
    def layer_df(gpkg: str, layer: str) -> pd.DataFrame:
        return gpd.read_file(P(gpkg), layer=layer, ignore_geometry=True)

    def read_json(path: Path):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # ------------------------------------------------------------------ meta
    @app.get("/api/network")
    def network():
        return _clean(network_urls(ctx))

    @app.get("/api/meta")
    def meta():
        manifest = ctx.data_dir / "raw" / "manifest.jsonl"
        sources: dict = defaultdict(lambda: {"files": set(), "bytes": 0, "first": None, "last": None, "hosts": set()})
        latest: dict = {}
        if manifest.exists():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                latest[e["path"]] = e
        for e in latest.values():
            s = sources[e["source"]]
            s["files"].add(e["path"])
            s["bytes"] += e["bytes"]
            s["first"] = min(filter(None, [s["first"], e["retrieved_at"]]))
            s["last"] = max(filter(None, [s["last"], e["retrieved_at"]]))
            s["hosts"].add(e["url"].split("/")[2])
        src = [{"source": k, "files": len(v["files"]), "bytes": v["bytes"], "first_retrieved": v["first"],
                "last_retrieved": v["last"], "hosts": sorted(v["hosts"])} for k, v in sorted(sources.items())]
        scope = ctx.config["scope"]
        return _clean({
            "name": ctx.config.get("name"),
            "scope": {"layer": scope["layer"], "values": scope["values"], "crs": ctx.crs},
            "build": read_json(D / "build.json"),
            "dnc": read_json(R("dnc_summary.json")),
            "qa": read_json(R("qa.json")),
            "sources": src,
        })

    # ------------------------------------------------------------------ layers
    @app.get("/api/geo/{name}")
    def geo(name: str):
        path = D / f"{name}.geojson"
        if not path.exists() or path.parent != D:
            raise HTTPException(404, f"layer {name} not built")
        return FileResponse(path, media_type="application/geo+json")

    # --------------------------------------------------------------- cadastre
    def _where(f: dict, skip: str | None = None) -> tuple[str, list]:
        clauses, params = [], []
        for facet, (col, _) in FACETS.items():
            vals = f.get(facet)
            if facet == skip or not vals:
                continue
            clauses.append(f"CAST({col} AS VARCHAR) IN ({','.join('?' * len(vals))})")
            params += vals
        if skip != "decade":
            if f.get("year_from") is not None or f.get("year_to") is not None:
                yf = f.get("year_from") if f.get("year_from") is not None else -1
                yt = f.get("year_to") if f.get("year_to") is not None else 99999
                cond = "(anio_construccion BETWEEN ? AND ?)"
                params += [yf, yt]
                if f.get("include_year0"):
                    cond = f"({cond} OR anio_construccion = 0)"
                clauses.append(cond)
            elif f.get("include_year0") is False:
                clauses.append("anio_construccion <> 0")
        if skip != "nivel" and (f.get("nivel_from") is not None or f.get("nivel_to") is not None):
            clauses.append("nivel BETWEEN ? AND ?")
            params += [f.get("nivel_from") if f.get("nivel_from") is not None else -99,
                       f.get("nivel_to") if f.get("nivel_to") is not None else 999]
        if f.get("parcel"):
            clauses.append("parcel_key = ?")
            params.append(f["parcel"])
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _filters(destino, categoria, estado, cubierta, tipo_obra, regimen, year_from, year_to,
                 include_year0, nivel_from, nivel_to, unit_regimen_exists="") -> dict:
        split = lambda s: [v for v in s.split(",") if v != ""] if s else []
        return {"destino": split(destino), "categoria": split(categoria), "estado": split(estado),
                "cubierta": split(cubierta), "tipo_obra": split(tipo_obra), "regimen": split(regimen),
                "year_from": year_from, "year_to": year_to, "include_year0": include_year0,
                "nivel_from": nivel_from, "nivel_to": nivel_to, "unit_regimen_exists": split(unit_regimen_exists)}

    @app.get("/api/cadastre/summary")
    def cadastre_summary(destino: str = "", categoria: str = "", estado: str = "", cubierta: str = "",
                         tipo_obra: str = "", regimen: str = "", year_from: int | None = None,
                         year_to: int | None = None, include_year0: bool = True,
                         nivel_from: float | None = None, nivel_to: float | None = None,
                         unit_regimen_exists: str = ""):
        f = _filters(destino, categoria, estado, cubierta, tipo_obra, regimen, year_from, year_to,
                     include_year0, nivel_from, nivel_to, unit_regimen_exists)
        w, p = _where(f)
        k = q(f"""SELECT count(*) AS lines, count(DISTINCT parcel_key) AS parcels,
                         count(DISTINCT (parcel_key, regimen, block, ep_ss, unidad)) AS units,
                         coalesce(sum(area_m2),0) AS area_m2,
                         coalesce(sum(area_m2) FILTER (WHERE destino = 1),0) AS area_vivienda_m2,
                         count(*) FILTER (WHERE anio_construccion = 0) AS lines_year_0,
                         count(*) FILTER (WHERE area_m2 = 0) AS lines_area_0
                  FROM lines {w}""", p).iloc[0].to_dict()
        by = {}
        for facet, (col, lab) in FACETS.items():
            w2, p2 = _where(f, skip=facet)
            label = f"any_value({lab})" if lab else f"CAST({col} AS VARCHAR)"
            by[facet] = _records(q(f"""SELECT CAST({col} AS VARCHAR) AS code, {label} AS label,
                                              count(*) AS lines, sum(area_m2) AS area_m2
                                       FROM lines {w2} GROUP BY 1 ORDER BY area_m2 DESC NULLS LAST""", p2))
        w2, p2 = _where(f, skip="decade")
        by["decade"] = _records(q(f"""SELECT CAST(floor(anio_construccion/10)*10 AS INTEGER) AS decade,
                                             count(*) AS lines, sum(area_m2) AS area_m2
                                      FROM lines {w2} GROUP BY 1 ORDER BY 1""", p2))
        w2, p2 = _where(f, skip="nivel")
        by["nivel"] = _records(q(f"""SELECT nivel, count(*) AS lines, sum(area_m2) AS area_m2
                                     FROM lines {w2} GROUP BY 1 ORDER BY 1""", p2))
        parcels = q(f"SELECT DISTINCT parcel_key FROM lines {w}", p)["parcel_key"].tolist()
        return _clean({"kpis": k, "by": by, "parcels": parcels})

    @app.get("/api/cadastre/parcel/{key}")
    def parcel(key: str):
        dnc = P("dnc", "x").parent
        get = lambda name: q(f"SELECT * FROM read_parquet('{dnc / name}') WHERE parcel_key = ?", [key])
        lines = get("lineas_de_construccion.parquet")
        if lines.empty and get("padrones_urbanos.parquet").empty:
            raise HTTPException(404, f"parcel {key} not in prepared data")
        padron = int(key.split("-")[-1])
        doors = layer_df("im_wfs.gpkg", "accesos_puerta")
        permits = layer_df("im_wfs.gpkg", "permisos_construccion")
        par = layer_df("dnc.gpkg", "parcelas_urbanas")
        return _clean({
            "parcel_key": key,
            "parcel": _records(par[par["parcel_key"] == key]),
            "units": _records(get("padrones_urbanos.parquet")),
            "lines": _records(lines.sort_values(["regimen", "block", "ep_ss", "unidad", "nivel"])),
            "values": _records(get("historico_de_valores.parquet")),
            "mutations": _records(get("mutaciones_catastrales.parquet")),
            "doors": _records(doors[pd.to_numeric(doors["padron"], errors="coerce") == padron]),
            "permits": _records(permits[pd.to_numeric(permits["padron"], errors="coerce") == padron]
                                .sort_values("fecha_aprob", ascending=False)),
        })

    # ------------------------------------------------------------------ lidar
    @app.get("/api/lidar")
    def lidar():
        return _clean(read_json(R("lidar_inventory.json")) or [])

    # ------------------------------------------------------------------- ANDA
    def _anda_studies():
        return ctx.source("ine_anda").get("studies", []) if "ine_anda" in ctx.config["sources"] else []

    @app.get("/api/anda")
    def anda():
        meta_rep = read_json(R("ine_anda_metadata.json")) or {}
        ingest_rep = read_json(R("ine_anda_ingest.json")) or {}
        out = []
        for st in _anda_studies():
            idno = st["idno"]
            base = P("ine_anda", idno, "x").parent
            scope_dir = base / "scope"
            tables = sorted(p.stem for p in scope_dir.glob("*.parquet")) if scope_dir.exists() else []
            files_dir = ctx.data_dir / "raw" / "ine_anda" / idno / "files"
            out.append({
                "idno": idno, "id": st.get("id"), "geography": st.get("geography"),
                "metadata": meta_rep.get(idno), "ingest": ingest_rep.get(idno),
                "drop_folder": str(files_dir.relative_to(ctx.root)) if files_dir.is_relative_to(ctx.root) else str(files_dir),
                "files_present": sorted(p.name for p in files_dir.glob("*") if p.name != "README.txt") if files_dir.exists() else [],
                "scope_tables": tables,
                "download_page": f"{ctx.source('ine_anda')['catalog_page'].rstrip('/')}/{st.get('id')}/get-microdata",
            })
        return _clean(out)

    @app.get("/api/anda/{idno}/variables")
    def anda_variables(idno: str):
        path = P("ine_anda", idno, "api_variables.parquet")
        if not path.exists():
            raise HTTPException(404, "metadata not downloaded – run `infdb-uy anda-metadata`")
        return _records(pd.read_parquet(path))

    @app.get("/api/anda/{idno}/columns")
    def anda_columns(idno: str, table: str):
        """Columns of an ingested scope table, with catalogue labels where the name matches."""
        if idno not in {s["idno"] for s in _anda_studies()}:
            raise HTTPException(404, "unknown study")
        path = P("ine_anda", idno, "scope", f"{table}.parquet")
        if not path.exists() or path.parent.name != "scope":
            raise HTTPException(404, "table not ingested")
        cols = q(f"DESCRIBE SELECT * FROM read_parquet('{path}')")["column_name"].tolist()
        # catalogue file matched at ingest time (by file name or column overlap)
        tables = ((read_json(R("ine_anda_ingest.json")) or {}).get(idno) or {}).get("tables", {})
        fid = next((v.get("catalogue_match", {}).get("file_id") for k, v in tables.items() if Path(k).stem == table), None)
        labels, weights = {}, set()
        vpath = P("ine_anda", idno, "api_variables.parquet")
        if vpath.exists():
            v = pd.read_parquet(vpath)
            v = pd.concat([v[v["file_id"] == fid], v[v["file_id"] != fid]])  # matched file first
            for r in v.itertuples():
                key = str(r.name).lower()
                labels.setdefault(key, r.label)
                if str(getattr(r, "is_weight", "") or "").lower() in ("1", "true", "y", "yes"):
                    weights.add(key)
        return _clean([{"name": c, "label": labels.get(c.lower()), "is_weight": c.lower() in weights} for c in cols])

    @app.get("/api/anda/{idno}/distribution")
    def anda_distribution(idno: str, table: str, variable: str, weight: str = "", by_unit: bool = False):
        if idno not in {s["idno"] for s in _anda_studies()}:
            raise HTTPException(404, "unknown study")
        path = P("ine_anda", idno, "scope", f"{table}.parquet")
        if not path.exists() or path.parent.name != "scope":
            raise HTTPException(404, "table not ingested")
        cols = q(f"DESCRIBE SELECT * FROM read_parquet('{path}')")["column_name"].tolist()
        if variable not in cols or (weight and weight not in cols):
            raise HTTPException(400, f"column not in table; available: {cols}")
        geo = next(s for s in _anda_studies() if s["idno"] == idno).get("geography", {})
        unit_cols = [geo[k] for k in ("departamento", "seccion", "segmento") if geo.get(k) in cols]
        unit = " || '-' || ".join(f'CAST("{c}" AS VARCHAR)' for c in unit_cols) if by_unit and unit_cols else "'scope'"
        wexpr = f'sum(TRY_CAST(replace(CAST("{weight}" AS VARCHAR), \',\', \'.\') AS DOUBLE))' if weight else "NULL"
        df = q(f"""SELECT {unit} AS unit, CAST("{variable}" AS VARCHAR) AS code, count(*) AS records,
                          {wexpr} AS weighted
                   FROM read_parquet('{path}') GROUP BY 1, 2 ORDER BY 1, 2""")
        labels = {}
        api_cat = P("ine_anda", idno, "api_categories.parquet")
        if api_cat.exists():
            c = pd.read_parquet(api_cat)
            labels.update({str(r.code): (r.label, "ANDA catalogue") for r in c[c["name"] == variable].itertuples()})
        dic = P("ine", "diccionario_categorias.parquet")
        if dic.exists():
            c = pd.read_parquet(dic)
            for r in c[c["name"] == variable].itertuples():
                labels.setdefault(str(r.code), (r.label, "INE dictionary 2023"))

        def norm(code):  # SPSS stores numbers as floats; label tables use integers
            try:
                return str(int(float(code))) if float(code).is_integer() else str(code)
            except (TypeError, ValueError):
                return str(code)

        df["label"] = [labels.get(norm(c), (None, None))[0] for c in df["code"]]
        df["label_source"] = [labels.get(norm(c), (None, None))[1] for c in df["code"]]
        return _records(df)

    # --------------------------------------------------------------- datasets
    def _datasets() -> dict[str, dict]:
        out = {}
        for pq in sorted(ctx.data_dir.joinpath("prepared").rglob("*.parquet")):
            rel = pq.relative_to(ctx.data_dir).as_posix()
            out[rel] = {"id": rel, "kind": "parquet", "path": pq}
        for gp in sorted(ctx.data_dir.joinpath("prepared").glob("*.gpkg")):
            for layer in gpd.list_layers(gp)["name"]:
                rel = f"{gp.relative_to(ctx.data_dir).as_posix()}#{layer}"
                out[rel] = {"id": rel, "kind": "gpkg", "path": gp, "layer": layer}
        return out

    def _dataset_df(d: dict) -> pd.DataFrame:
        if d["kind"] == "parquet":
            return pd.read_parquet(d["path"])
        return layer_df(d["path"].name, d["layer"]).copy()

    @app.get("/api/datasets")
    def datasets():
        res = []
        for d in _datasets().values():
            if d["kind"] == "parquet":
                info = q(f"SELECT count(*) AS n FROM read_parquet('{d['path']}')").iloc[0]["n"]
                cols = q(f"DESCRIBE SELECT * FROM read_parquet('{d['path']}')")[["column_name", "column_type"]]
                res.append({"id": d["id"], "rows": int(info), "columns": _records(cols)})
            else:
                df = _dataset_df(d)
                res.append({"id": d["id"], "rows": len(df),
                            "columns": [{"column_name": c, "column_type": str(t)} for c, t in df.dtypes.items()]})
        return res

    @app.get("/api/datasets/rows")
    def dataset_rows(id: str, offset: int = 0, limit: int = Query(100, le=1000), search: str = ""):
        d = _datasets().get(id)
        if not d:
            raise HTTPException(404, "unknown dataset")
        df = _dataset_df(d)
        if search:
            mask = df.astype(str).apply(lambda c: c.str.contains(search, case=False, regex=False)).any(axis=1)
            df = df[mask]
        return {"total": len(df), "rows": _records(df.iloc[offset:offset + limit])}

    @app.get("/api/datasets/download")
    def dataset_download(id: str):
        d = _datasets().get(id)
        if not d:
            raise HTTPException(404, "unknown dataset")
        buf = io.StringIO()
        _dataset_df(d).to_csv(buf, index=False)
        name = id.replace("/", "_").replace("#", "__").replace(".parquet", "").replace(".gpkg", "") + ".csv"
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ----------------------------------------------------------------- static
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.exception_handler(FileNotFoundError)
    def missing(_, exc):
        return JSONResponse({"detail": f"{exc} – run the pipeline first"}, status_code=503)

    return app
