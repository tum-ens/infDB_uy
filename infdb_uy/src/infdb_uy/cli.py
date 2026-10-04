"""Command line: `uv run infdb-uy <step>`.

`all` runs every pipeline step in order and skips steps that already completed with the
same configuration (marker files in data/state/). Use --force to rerun them.
`start` = `all` followed by `serve` – the single command used by Docker.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging

from . import qa
from .core import Context
from .sources import dnc, im_lidar, im_wfs, ine, ine_anda

log = logging.getLogger("infdb_uy")


def _dashboard(ctx: Context) -> None:
    from .dashboard import build

    build.run(ctx)


STEPS = {
    "scope": lambda ctx: im_wfs.build_scope(ctx),
    "im-wfs": im_wfs.run,
    "dnc": dnc.run,
    "ine": ine.run,
    "lidar": im_lidar.run,
    "anda-metadata": ine_anda.metadata,
    "anda-ingest": ine_anda.ingest,
    "qa": qa.run,
    "dashboard": _dashboard,
}
ALL = ["scope", "im-wfs", "dnc", "ine", "lidar", "anda-metadata", "anda-ingest", "qa", "dashboard"]
# Steps that always run in `all`: cheap, and their input can change between runs
# (files dropped into the ANDA folders).
ALWAYS = {"anda-ingest", "qa", "dashboard"}


def _config_hash(ctx: Context) -> str:
    # data_dir and dashboard settings do not change pipeline outputs
    cfg = {k: v for k, v in ctx.config.items() if k not in ("data_dir", "dashboard")}
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _marker(ctx: Context, step: str):
    p = ctx.data_dir / "state" / f"{step}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_pipeline(ctx: Context, steps: list[str], *, force: bool, skip_done: bool) -> None:
    chash = _config_hash(ctx)
    for step in steps:
        marker = _marker(ctx, step)
        if skip_done and not force and step not in ALWAYS and marker.exists():
            done = json.loads(marker.read_text())
            if done.get("config_hash") == chash:
                log.info("=== %s – already done %s, skipped (use --force to rerun)", step, done.get("finished_at"))
                continue
        log.info("=== %s", step)
        STEPS[step](ctx)
        marker.write_text(json.dumps({"config_hash": chash,
                                      "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}))


def serve(ctx: Context, host: str, port: int) -> None:
    import uvicorn

    from .dashboard.app import create_app

    if not (ctx.data_dir / "dashboard" / "build.json").exists():
        log.info("Dashboard bundle missing – building it")
        _dashboard(ctx)
    log.info("Dashboard on http://%s:%d  (Ctrl+C to stop)", "localhost" if host in ("0.0.0.0", "127.0.0.1") else host, port)
    uvicorn.run(create_app(ctx), host=host, port=port, log_level="warning")


def main() -> None:
    ap = argparse.ArgumentParser(prog="infdb-uy", description="Download and prepare Uruguayan data for InfDB, and explore it.")
    ap.add_argument("step", choices=[*STEPS, "all", "serve", "start"])
    ap.add_argument("--config", default="config/pilot-cordon.yml")
    ap.add_argument("--data-dir", default=None, help="override data_dir from the config")
    ap.add_argument("--refresh", action="store_true", help="re-query live sources (WFS, APIs) even if cached")
    ap.add_argument("--force", action="store_true", help="rerun steps that are marked as done")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for noisy in ("pyogrio", "fiona", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    ctx = Context.load(args.config, data_dir=args.data_dir, refresh=args.refresh)

    if args.step in ("all", "start"):
        run_pipeline(ctx, ALL, force=args.force or args.refresh, skip_done=True)
    elif args.step != "serve":
        run_pipeline(ctx, [args.step], force=True, skip_done=False)
    if args.step in ("serve", "start"):
        serve(ctx, args.host, args.port)


if __name__ == "__main__":
    main()
