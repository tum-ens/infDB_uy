"""Shared infrastructure: configuration, paths, HTTP with the INE certificate fix,
resumable downloads and the raw-file manifest."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import certifi
import requests
import yaml

log = logging.getLogger("infdb_uy")

USER_AGENT = "infdb-uy/0.1 (research; TUM)"


@dataclass
class Context:
    config: dict[str, Any]
    root: Path
    refresh: bool = False  # re-download live sources (WFS, APIs) even if raw copies exist

    @classmethod
    def load(cls, config_path: str | Path, *, data_dir: str | None = None, refresh: bool = False) -> "Context":
        config_path = Path(config_path).resolve()
        with open(config_path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        if data_dir:
            config["data_dir"] = str(Path(data_dir).resolve())
        # project root = folder containing config/ (relative data_dir is resolved against it)
        return cls(config=config, root=config_path.parent.parent, refresh=refresh)

    # ---------------------------------------------------------------- paths
    @property
    def data_dir(self) -> Path:
        return self.root / self.config.get("data_dir", "data")

    def raw(self, *parts: str) -> Path:
        p = self.data_dir.joinpath("raw", *parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def prepared(self, *parts: str) -> Path:
        p = self.data_dir.joinpath("prepared", *parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def reports(self, *parts: str) -> Path:
        p = self.data_dir.joinpath("reports", *parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def crs(self) -> str:
        return self.config["crs"]

    def source(self, name: str) -> dict[str, Any]:
        return self.config["sources"][name]

    def enabled(self, name: str) -> bool:
        return bool(self.config["sources"].get(name, {}).get("enabled", False))

    # ----------------------------------------------------------------- http
    _session: requests.Session | None = field(default=None, repr=False)

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            s = requests.Session()
            s.headers["User-Agent"] = USER_AGENT
            s.verify = str(self._ca_bundle())
            self._session = s
        return self._session

    def _ca_bundle(self) -> Path:
        """certifi bundle plus the intermediates INE does not send (see config `tls`)."""
        bundle = self.data_dir / "cache" / "ca-bundle.pem"
        if bundle.exists():
            return bundle
        bundle.parent.mkdir(parents=True, exist_ok=True)
        pem = Path(certifi.where()).read_text()
        for url in self.config.get("tls", {}).get("extra_intermediates", []):
            der = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT}).content
            pem += "\n" + ssl.DER_cert_to_PEM_cert(der)
            log.info("Added intermediate certificate from %s", url)
        bundle.write_text(pem)
        return bundle

    def get_json(self, url: str, **params: Any) -> Any:
        r = self.session.get(url, params=params or None, timeout=300)
        r.raise_for_status()
        return r.json()

    def download(self, url: str, dest: Path, source: str, *, force: bool = False) -> Path:
        """Download `url` to `dest` (resumable) and record it in the manifest.

        An existing complete file is kept unless `force`; files are never edited afterwards.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        if dest.exists() and not force:
            log.info("Keep existing %s", dest.relative_to(self.root))
            return dest

        meta: dict[str, Any] = {}
        for attempt in range(1, 6):
            offset = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            with self.session.get(url, headers=headers, stream=True, timeout=600) as r:
                if r.status_code == 416:  # already complete
                    break
                r.raise_for_status()
                if offset and r.status_code != 206:  # server ignored Range
                    offset = 0
                    part.unlink(missing_ok=True)
                total = r.headers.get("Content-Range", "").split("/")[-1] or r.headers.get("Content-Length")
                with open(part, "ab") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
                meta = {k: r.headers.get(k) for k in ("Last-Modified", "ETag", "Content-Type")}
            size = part.stat().st_size
            if total and total.isdigit() and size < int(total):
                log.warning("Incomplete download (%s/%s bytes), retry %d", size, total, attempt)
                continue
            break
        else:
            raise RuntimeError(f"Download did not complete: {url}")

        part.rename(dest)
        self._record(url, dest, source, meta)
        log.info("Downloaded %s (%.1f MB)", dest.relative_to(self.root), dest.stat().st_size / 1e6)
        return dest

    def save_bytes(self, url: str, content: bytes, dest: Path, source: str) -> Path:
        """Store a response body fetched elsewhere (e.g. paged WFS) as a raw file."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        self._record(url, dest, source, {})
        return dest

    def _record(self, url: str, path: Path, source: str, meta: dict[str, Any]) -> None:
        sha = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                sha.update(chunk)
        entry = {
            "source": source,
            "url": url,
            "path": str(path.relative_to(self.data_dir)),
            "bytes": path.stat().st_size,
            "sha256": sha.hexdigest(),
            "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            **{k.lower(): v for k, v in meta.items() if v},
        }
        manifest = self.data_dir / "raw" / "manifest.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
