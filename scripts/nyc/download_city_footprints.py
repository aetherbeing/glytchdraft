"""
download_city_footprints.py  [NYC city pipeline - GlitchOS.io]

Downloads building footprints for New York City.

Source:
  NYC Open Data geospatial export
  https://data.cityofnewyork.us/api/geospatial/qb5r-6dgf?method=export&type=GeoJSON

Output:
  /mnt/t7/nyc/data_raw/geojson/nyc_footprints_4326.geojson

Usage:
    python scripts/nyc/download_city_footprints.py new_york_city
    python scripts/nyc/download_city_footprints.py new_york_city --force
"""

from __future__ import annotations

import sys
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER
from tile_config import BLOCK_FOOTPRINTS_RAW

try:
    from rich.console import Console
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        DownloadColumn,
        TransferSpeedColumn,
        TimeElapsedColumn,
    )

    _RICH = True
    console = Console()

    def _print(msg: str):
        console.print(msg)

except ImportError:
    _RICH = False

    def _print(msg: str):
        print(msg)


SOURCE_URL = "https://data.cityofnewyork.us/api/geospatial/qb5r-6dgf?method=export&type=GeoJSON"
USER_AGENT = "GlytchDraft/1.0 (spatial pipeline; contact charleshopeart@gmail.com)"
MIN_VALID_BYTES = 1024 * 1024


def _resolve_local_path(path: Path) -> Path:
    """
    Map the pipeline's WSL-style /mnt/t7 path to the local Windows T7 drive.

    On this machine the T7 data root is E:\\nyc, while WSL paths use
    /mnt/t7/nyc. Environment variables can override the drive mapping:
    NYC_T7_ROOT or GLYTCH_T7_ROOT.
    """
    if os.name != "nt":
        return path

    normalized = str(path).replace("\\", "/")
    if not normalized.startswith("/mnt/t7/"):
        return path

    rel = normalized[len("/mnt/t7/"):]
    for env_name in ("NYC_T7_ROOT", "GLYTCH_T7_ROOT", "T7_ROOT"):
        root = os.environ.get(env_name)
        if root:
            return Path(root) / rel

    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        drive_root = Path(f"{letter}:/")
        if not drive_root.exists():
            continue
        if (drive_root / "nyc" / "data_raw").exists():
            return drive_root / rel

    return path


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _urlopen(req: urllib.request.Request, timeout: int = 180):
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            _print("[yellow]Windows certificate verification failed; retrying this download without certificate verification.[/yellow]" if _RICH else "Windows certificate verification failed; retrying this download without certificate verification.")
            return urllib.request.urlopen(
                req,
                timeout=timeout,
                context=ssl._create_unverified_context(),
            )
        raise


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/geo+json, application/json",
        },
    )


def _download(url: str, out_path: Path) -> None:
    req = _request(url)
    with _urlopen(req, timeout=180) as resp:
        total = int(resp.headers.get("Content-Length") or 0)

        if _RICH:
            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]{task.description}"),
                BarColumn(bar_width=28),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=False,
            ) as progress:
                task = progress.add_task("downloading NYC footprints", total=total or None)
                with out_path.open("wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
            return

        downloaded = 0
        last_report = time.time()
        with out_path.open("wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last_report > 5:
                    if total:
                        print(f"  {downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB")
                    else:
                        print(f"  {downloaded / 1_048_576:.1f} MB")
                    last_report = now


def _validate_geojson(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"download did not create {path}")
    if path.stat().st_size < MIN_VALID_BYTES:
        raise RuntimeError(f"download is too small: {path.stat().st_size} bytes")
    with path.open("rb") as f:
        head = f.read(4096).lstrip()
    if not head.startswith(b"{") or b"FeatureCollection" not in head[:4096]:
        raise RuntimeError("download does not look like GeoJSON FeatureCollection")


def download(city_id: str, force: bool = False) -> int:
    if city_id not in CITIES:
        _print(f"Unknown city: {city_id!r}  valid: {CITY_ORDER}")
        return 1

    logical_path = BLOCK_FOOTPRINTS_RAW
    out_path = _resolve_local_path(logical_path)
    if out_path.exists() and not force:
        size_mb = out_path.stat().st_size / 1_048_576
        _print(f"Already exists: {out_path}  ({size_mb:.1f} MB)\n  Use --force to re-download.")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)

    _print(f"City: {CITIES[city_id].display_name}")
    _print(f"Source: {SOURCE_URL}")
    if out_path != logical_path:
        _print(f"Pipeline path: {logical_path}")
    _print(f"Output: {out_path}")
    _print("")

    with tempfile.TemporaryDirectory(prefix="nyc_footprints_", dir=out_path.parent) as tmp_dir:
        tmp_path = Path(tmp_dir) / out_path.name
        _download(SOURCE_URL, tmp_path)
        _validate_geojson(tmp_path)
        tmp_path.replace(out_path)

    size_mb = out_path.stat().st_size / 1_048_576
    _print(f"Wrote: {out_path}  ({size_mb:.1f} MB)")
    return 0


def main() -> int:
    args = sys.argv[1:]
    city_id = next((a for a in args if not a.startswith("--")), "new_york_city")
    force = "--force" in args
    return download(city_id, force=force)


if __name__ == "__main__":
    sys.exit(main())
