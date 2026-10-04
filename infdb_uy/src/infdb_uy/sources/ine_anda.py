"""INE ANDA (NADA catalogue): census 2023 weighted microdata, ECH, ...

Two stages:

1. `metadata`  – public API, fully automatic: study entry, data files, every variable
                 (label, format, categories, question text). Stored raw (JSON) and as tidy
                 parquet tables. Also writes data/raw/ine_anda/<idno>/files/README.txt.
2. `ingest`    – processes microdata files that the user downloaded from the catalogue
                 after accepting INE's terms and conditions, placed in
                 data/raw/ine_anda/<idno>/files/. Accepting the terms is deliberately left
                 to a person; this module never submits that form.

Ingest is lossless:
  * archives are unpacked to raw/ine_anda/<idno>/extracted/ (originals untouched);
  * text tables are stored as parquet with all columns as strings, exactly as in the file;
  * SPSS/Stata files keep their codes; value labels are written to a separate table;
  * columns are compared with the API variable list (report only);
  * a scope subset is written: records whose geography codes match INE census units
    (segment > section > department) that intersect the scope polygon.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from pathlib import Path

import geopandas as gpd
import libarchive
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from ..core import Context, write_json

log = logging.getLogger(__name__)
SOURCE = "ine_anda"
TABLE_EXT = {".csv", ".txt", ".tab", ".sav", ".zsav", ".dta", ".parquet"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".gz", ".tgz", ".tar", ".bz2", ".xz"}

README = """\
INE ANDA – {title}
IDNO: {idno}   catalogue id: {id}   data access type: {access}

How to obtain the microdata
---------------------------
1. Open {page}/{id}/get-microdata in a browser.
2. Read INE's terms and conditions. Downloading means accepting them on your own behalf.
   Key points: no redistribution without INE's written consent; scientific/statistical
   use only, results presented as aggregates; no re-identification; no linking of INE
   data with other data that could identify individuals or organisations; cite the
   dataset; send INE an electronic copy of publications based on the data.
3. Download the data files listed below (any format: CSV, SPSS, Stata, or archives).
4. Put them, unchanged, into this folder:
   {folder}
5. Run:  uv run infdb-uy anda-ingest

Data files described in the catalogue
-------------------------------------
{files}

This folder is inside data/ and excluded from version control. Do not commit or share it.
"""


# ---------------------------------------------------------------------- metadata
def _cached_json(ctx: Context, url: str, dest: Path) -> dict:
    if dest.exists() and not ctx.refresh:
        return json.loads(dest.read_text(encoding="utf-8"))
    r = ctx.session.get(url, timeout=120)
    r.raise_for_status()
    ctx.save_bytes(r.url, r.content, dest, SOURCE)
    time.sleep(0.1)  # be gentle with the INE server
    return r.json()


def _variable_rows(details: list[dict], files: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, cats = [], []
    for v in details:
        m = v.get("metadata") or {}
        fmt = m.get("var_format") or {}
        rows.append({
            "file_id": v.get("fid"),
            "file_name": files.get(v.get("fid")),
            "vid": v.get("vid"),
            "name": v.get("name"),
            "label": v.get("labl"),
            "format_type": fmt.get("type"),
            "interval": m.get("var_intrvl"),
            "width": m.get("loc_width"),
            "decimals": m.get("var_dcml"),
            "is_weight": m.get("var_is_wgt"),
            "universe": m.get("var_universe"),
            "question": m.get("var_qstn_qstnlit"),
            "definition": m.get("var_txt"),
            "n_categories": len(m.get("var_catgry") or []),
        })
        for c in m.get("var_catgry") or []:
            cats.append({"file_id": v.get("fid"), "name": v.get("name"), "code": c.get("value"), "label": c.get("labl")})
    return pd.DataFrame(rows), pd.DataFrame(cats, columns=["file_id", "name", "code", "label"])


def metadata(ctx: Context) -> dict:
    cfg = ctx.source(SOURCE)
    api = cfg["api"].rstrip("/")
    status = {}
    for st in cfg["studies"]:
        idno = st["idno"]
        mdir = ctx.raw(SOURCE, idno, "metadata", "x").parent
        cat = _cached_json(ctx, f"{api}/catalog/{idno}", mdir / "catalog.json")
        dataset = cat.get("dataset", cat)
        files = _cached_json(ctx, f"{api}/catalog/{idno}/data_files", mdir / "data_files.json").get("datafiles", [])
        var_list = _cached_json(ctx, f"{api}/catalog/{idno}/variables", mdir / "variables.json").get("variables", [])
        details = []
        for v in var_list:
            d = _cached_json(ctx, f"{api}/catalog/{idno}/variable/{v['vid']}", mdir / "variables" / f"{v['vid']}.json")
            details.append(d.get("variable", d))
        fmap = {f["file_id"]: f["file_name"] for f in files}
        variables, categories = _variable_rows(details, fmap)
        variables.to_parquet(ctx.prepared(SOURCE, idno, "api_variables.parquet"), index=False)
        categories.to_parquet(ctx.prepared(SOURCE, idno, "api_categories.parquet"), index=False)
        pd.DataFrame(files).to_parquet(ctx.prepared(SOURCE, idno, "api_data_files.parquet"), index=False)

        folder = ctx.raw(SOURCE, idno, "files", "README.txt")
        folder.write_text(README.format(
            title=dataset.get("title"), idno=idno, id=st["id"], access=dataset.get("data_access_type"),
            page=cfg["catalog_page"].rstrip("/"), folder=folder.parent,
            files="\n".join(f"  {f['file_id']}: {f['file_name']} ({f.get('var_count')} variables)" for f in files),
        ), encoding="utf-8")
        status[idno] = {
            "title": dataset.get("title"),
            "data_access_type": dataset.get("data_access_type"),
            "changed": dataset.get("changed"),
            "data_files": {f["file_id"]: f["file_name"] for f in files},
            "variables": len(variables),
            "variables_with_categories": int((variables["n_categories"] > 0).sum()),
            "drop_folder": str(folder.parent.relative_to(ctx.root)),
        }
        log.info("ANDA %s: %d files, %d variables", idno, len(files), len(variables))
    write_json(ctx.reports("ine_anda_metadata.json"), status)
    return status


# ------------------------------------------------------------------------ ingest
def _extract(archive: Path, target: Path) -> list[Path]:
    """Unpack with libarchive (zip, rar, 7z, tar, ...). Returns extracted files."""
    out = []
    target.mkdir(parents=True, exist_ok=True)
    with libarchive.file_reader(str(archive)) as arc:
        for entry in arc:
            if entry.isdir:
                continue
            rel = Path(*[p for p in Path(entry.pathname).parts if p not in ("..", "/")])
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as fh:
                for block in entry.get_blocks():
                    fh.write(block)
            out.append(dest)
    return out


def _sniff(path: Path) -> tuple[str, str]:
    head = path.open("rb").read(1 << 20)
    try:
        head.decode("utf-8")
        enc = "utf-8"
    except UnicodeDecodeError:
        enc = "latin-1"
    sample = head.decode(enc, errors="replace")
    try:
        delim = csv.Sniffer().sniff(sample[:65536], delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    return enc, delim


def _text_to_parquet(path: Path, out: Path) -> dict:
    enc, delim = _sniff(path)
    with path.open(encoding=enc, newline="") as fh:
        header = next(csv.reader(fh, delimiter=delim))
    header = [h.strip().lstrip("﻿") for h in header]
    reader = pacsv.open_csv(
        path,
        read_options=pacsv.ReadOptions(encoding=enc, column_names=header, skip_rows=1, block_size=1 << 26),
        parse_options=pacsv.ParseOptions(delimiter=delim),
        convert_options=pacsv.ConvertOptions(column_types={h: pa.string() for h in header},
                                             strings_can_be_null=False, quoted_strings_can_be_null=False),
    )
    rows = 0
    with pq.ParquetWriter(out, reader.schema) as w:
        for batch in reader:
            w.write_batch(batch)
            rows += batch.num_rows
    return {"format": "text", "encoding": enc, "delimiter": delim, "rows": rows, "columns": header}


def _stat_to_parquet(path: Path, out: Path, labels_out: Path) -> dict:
    import pyreadstat

    reader = pyreadstat.read_sav if path.suffix.lower() in {".sav", ".zsav"} else pyreadstat.read_dta
    writer, rows, meta = None, 0, None
    for chunk, meta in pyreadstat.read_file_in_chunks(reader, str(path), chunksize=200_000, apply_value_formats=False):
        table = pa.Table.from_pandas(chunk, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out, table.schema)
        writer.write_table(table.cast(writer.schema))
        rows += len(chunk)
    if writer:
        writer.close()
    labels = [{"name": col, "code": str(k), "label": v}
              for col, mapping in (meta.variable_value_labels or {}).items() for k, v in mapping.items()]
    pd.DataFrame(labels, columns=["name", "code", "label"]).to_parquet(labels_out, index=False)
    return {"format": path.suffix.lower().lstrip("."), "rows": rows, "columns": list(meta.column_names),
            "column_labels": meta.column_names_to_labels, "value_label_rows": len(labels)}


def _match_file(stem: str, columns: list[str], files: pd.DataFrame, variables: pd.DataFrame) -> dict:
    """Find the catalogue data file a table corresponds to.

    1. exact file name (case/punctuation-insensitive);
    2. otherwise the file whose variable list overlaps most with the table's columns
       (Jaccard, case-insensitive). The score is reported; below 0.5 no match is made.
    """
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    for _, f in files.iterrows():
        if norm(f["file_name"]) == norm(stem):
            return {"file_id": f["file_id"], "method": "file_name", "score": 1.0}
    cols = {c.lower() for c in columns}
    best = {"file_id": None, "method": "column_overlap", "score": 0.0}
    for fid, grp in variables.groupby("file_id"):
        names = {n.lower() for n in grp["name"]}
        score = len(cols & names) / len(cols | names) if cols | names else 0.0
        if score > best["score"]:
            best = {"file_id": fid, "method": "column_overlap", "score": round(score, 3)}
    if best["score"] < 0.5:
        best["file_id"] = None
    return best


def _scope_units(ctx: Context) -> dict[str, pd.DataFrame]:
    """INE census units intersecting the scope, keyed by integer code tuples."""
    gpkg = ctx.prepared("ine_cartografia.gpkg")
    if not gpkg.exists():
        raise FileNotFoundError("Run `infdb-uy ine` first (INE cartography is needed to select the scope).")
    seg = gpd.read_file(gpkg, layer="sg_23_pg", ignore_geometry=True)
    sec = gpd.read_file(gpkg, layer="sc_23_pg", ignore_geometry=True)
    to_int = lambda s: pd.to_numeric(s, errors="coerce").astype("Int64")
    seg = seg.assign(d=to_int(seg["DEPTO"]), s=to_int(seg["SECC"]), g=to_int(seg["SEG"]))
    sec = sec.assign(d=to_int(sec["DEPTO"]), s=to_int(sec["SECC"]))
    return {"segmento": seg, "seccion": sec}


def _scope_subset(ctx: Context, table: pa.Table, geo: dict, units: dict) -> tuple[pa.Table | None, dict]:
    cols = set(table.column_names)
    dep_col, sec_col, seg_col = geo.get("departamento"), geo.get("seccion"), geo.get("segmento")
    if not dep_col or dep_col not in cols:
        return None, {"scope_level": None, "reason": f"department column {dep_col!r} not in file"}
    to_int = lambda name: pd.to_numeric(pd.Series(table.column(name).to_pylist()), errors="coerce").astype("Int64")
    d = to_int(dep_col)
    dep_code = int(ctx.config["scope"]["ine_departamento"])
    info = {"rows_total": table.num_rows, "rows_in_departamento": int((d == dep_code).sum()),
            "rows_departamento_not_numeric": int(d.isna().sum())}

    if seg_col and seg_col in cols and sec_col and sec_col in cols:
        level, u = "segmento", units["segmento"]
        key = pd.DataFrame({"d": d, "s": to_int(sec_col), "g": to_int(seg_col)})
        on = ["d", "s", "g"]
    elif sec_col and sec_col in cols:
        level, u = "seccion", units["seccion"]
        key = pd.DataFrame({"d": d, "s": to_int(sec_col)})
        on = ["d", "s"]
    else:
        level, u, key, on = "departamento", None, pd.DataFrame({"d": d}), ["d"]

    if u is None:
        mask = (key["d"] == dep_code).to_numpy()
        extra = None
    else:
        ref = u[on + ["scope_relation", "scope_overlap_share"]].drop_duplicates(on)
        merged = key.reset_index().merge(ref, on=on, how="left").set_index("index").sort_index()
        mask = merged["scope_relation"].notna().to_numpy()
        extra = merged.loc[mask, ["scope_relation", "scope_overlap_share"]]
        in_dep = (key["d"] == dep_code)
        info["rows_in_departamento_with_unparseable_unit_code"] = int((in_dep & key[on].isna().any(axis=1)).sum())
    sub = table.filter(pa.array(mask))
    sub = sub.append_column("scope_level", pa.array([level] * sub.num_rows, pa.string()))
    if extra is not None:
        sub = sub.append_column("scope_relation", pa.array(extra["scope_relation"].tolist(), pa.string()))
        sub = sub.append_column("scope_overlap_share", pa.array(extra["scope_overlap_share"].astype(float).tolist(), pa.float64()))
    info.update({"scope_level": level, "rows_in_scope": sub.num_rows})
    return sub, info


def ingest(ctx: Context) -> dict:
    cfg = ctx.source(SOURCE)
    report = {}
    for st in cfg["studies"]:
        idno = st["idno"]
        files_dir = ctx.raw(SOURCE, idno, "files", "x").parent
        api_files_path = ctx.prepared(SOURCE, idno, "api_data_files.parquet")
        if not api_files_path.exists():
            metadata(ctx)
        api_files = pd.read_parquet(api_files_path)
        api_vars = pd.read_parquet(ctx.prepared(SOURCE, idno, "api_variables.parquet"))

        inputs = [p for p in sorted(files_dir.iterdir()) if p.is_file() and p.name != "README.txt"]
        if not inputs:
            report[idno] = {"status": "no files", "drop_folder": str(files_dir.relative_to(ctx.root))}
            log.warning("ANDA %s: no files in %s – see README.txt there", idno, files_dir)
            continue

        tables: list[Path] = []
        for p in inputs:
            if p.suffix.lower() in ARCHIVE_EXT:
                extracted = _extract(p, ctx.raw(SOURCE, idno, "extracted", p.name, "x").parent)
                tables += [e for e in extracted if e.suffix.lower() in TABLE_EXT]
            elif p.suffix.lower() in TABLE_EXT:
                tables.append(p)

        units = _scope_units(ctx)
        st_report = {"inputs": [p.name for p in inputs], "tables": {}}
        for t in tables:
            out = ctx.prepared(SOURCE, idno, f"{t.stem}.parquet")
            if t.suffix.lower() in {".sav", ".zsav", ".dta"}:
                info = _stat_to_parquet(t, out, ctx.prepared(SOURCE, idno, f"{t.stem}__value_labels.parquet"))
            elif t.suffix.lower() == ".parquet":
                pq.write_table(pq.read_table(t), out)
                info = {"format": "parquet", "rows": pq.read_metadata(out).num_rows, "columns": pq.read_schema(out).names}
            else:
                info = _text_to_parquet(t, out)

            match = _match_file(t.stem, info["columns"], api_files, api_vars)
            fid = match["file_id"]
            info["catalogue_match"] = match
            if fid:
                expected = set(api_vars.loc[api_vars["file_id"] == fid, "name"])
                got = set(info["columns"])
                info["columns_missing_vs_catalogue"] = sorted(expected - got)
                info["columns_extra_vs_catalogue"] = sorted(got - expected)
                low = {c.lower() for c in got}
                info["columns_missing_ignoring_case"] = sorted(c for c in expected if c.lower() not in low)

            table = pq.read_table(out)
            sub, sinfo = _scope_subset(ctx, table, st.get("geography", {}), units)
            if sub is not None:
                pq.write_table(sub, ctx.prepared(SOURCE, idno, "scope", f"{t.stem}.parquet"))
            info["scope"] = sinfo
            info.pop("columns", None)
            st_report["tables"][t.name] = info
            log.info("ANDA %s %s: %s rows, scope %s", idno, t.name, info.get("rows"), sinfo)
        report[idno] = st_report
    write_json(ctx.reports("ine_anda_ingest.json"), report)
    return report
