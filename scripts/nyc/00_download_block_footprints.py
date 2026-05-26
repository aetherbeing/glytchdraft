"""
00_download_block_footprints.py  [NYC city pipeline - GlitchOS.io]

Download NYC building footprints to the city-wide footprint path consumed by
stages/s01_footprints.py.

Output:
  /mnt/t7/nyc/data_raw/geojson/nyc_footprints_4326.geojson

Primary source:
  NYC Open Data BUILDING dataset (5zhs-2jue), GeoJSON export.

The stage pipeline clips this city-wide GeoJSON per tile, then reprojects to
EPSG:32618. Keep this file in EPSG:4326 GeoJSON.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tile_config import BLOCK_FOOTPRINTS_RAW

DATASET_ID = "5zhs-2jue"
NYC_OPEN_DATA_PAGE = f"https://data.cityofnewyork.us/d/{DATASET_ID}"
NYC_OPEN_DATA_EXPORT = (
    f"https://data.cityofnewyork.us/resource/{DATASET_ID}.geojson"
)
NYC_OPEN_DATA_DOWNLOAD = (
    f"https://data.cityofnewyork.us/api/views/{DATASET_ID}/rows.geojson"
    "?accessType=DOWNLOAD"
)

OUT_DIR = BLOCK_FOOTPRINTS_RAW.parent
MIN_VALID_BYTES = 1024 * 1024


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "GlitchOS.io/1.0 NYC footprint downloader",
            "Accept": "application/geo+json, application/json",
        },
    )


def _download(url: str, out_path: Path) -> None:
    print(f"  downloading: {url}")
    with urllib.request.urlopen(_request(url), timeout=180) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
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
                        print(f"    {downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB")
                    else:
                        print(f"    {downloaded / 1_048_576:.1f} MB")
                    last_report = now


def _download_paged(out_path: Path, page_size: int = 50000) -> None:
    """
    Fallback through the SODA GeoJSON endpoint.

    Socrata can reject one-shot large exports in some environments. Paging keeps
    memory bounded and still writes a single FeatureCollection for GDAL.
    """
    print("  bulk export unavailable; falling back to paged SODA GeoJSON")
    total_features = 0
    offset = 0
    with out_path.open("w", encoding="utf-8") as out:
        out.write('{"type":"FeatureCollection","features":[\n')
        first = True
        while True:
            params = urllib.parse.urlencode({
                "$limit": page_size,
                "$offset": offset,
            })
            url = f"{NYC_OPEN_DATA_EXPORT}?{params}"
            print(f"    page offset={offset}")
            with urllib.request.urlopen(_request(url), timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            features = data.get("features") or []
            if not features:
                break
            for feature in features:
                if not first:
                    out.write(",\n")
                json.dump(feature, out, separators=(",", ":"))
                first = False
            total_features += len(features)
            if len(features) < page_size:
                break
            offset += page_size
        out.write("\n]}\n")
    print(f"  paged export wrote {total_features:,} features")


def _validate_geojson(path: Path) -> int:
    if not path.exists() or path.stat().st_size < MIN_VALID_BYTES:
        raise ValueError(f"download is too small to be the NYC footprint dataset: {path.stat().st_size if path.exists() else 0} bytes")

    with path.open("rb") as f:
        head = f.read(4096).lstrip()
    if not head.startswith(b"{"):
        raise ValueError("download is not JSON/GeoJSON")

    try:
        from osgeo import ogr

        ds = ogr.Open(str(path))
        if ds is None:
            raise ValueError("GDAL/OGR could not open GeoJSON")
        layer = ds.GetLayer(0)
        count = layer.GetFeatureCount()
        ds = None
        if count <= 0:
            raise ValueError("GeoJSON has no features")
        return count
    except ImportError:
        # Lightweight structural fallback for environments without GDAL.
        with path.open("r", encoding="utf-8") as f:
            prefix = f.read(65536)
        if '"FeatureCollection"' not in prefix or '"features"' not in prefix:
            raise ValueError("expected GeoJSON FeatureCollection")
        return -1


def main() -> int:
    force = "--force" in sys.argv[1:]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if BLOCK_FOOTPRINTS_RAW.exists() and BLOCK_FOOTPRINTS_RAW.stat().st_size > MIN_VALID_BYTES and not force:
        size_mb = BLOCK_FOOTPRINTS_RAW.stat().st_size / 1_048_576
        print(f"NYC footprints already exist ({size_mb:.1f} MB): {BLOCK_FOOTPRINTS_RAW}")
        print("Pass --force to refresh.")
        return 0

    print("GlitchOS.io - downloading NYC building footprints")
    print(f"Source: {NYC_OPEN_DATA_PAGE}")
    print(f"Output: {BLOCK_FOOTPRINTS_RAW}")

    with tempfile.TemporaryDirectory(prefix="nyc_footprints_", dir=OUT_DIR) as tmp_dir:
        tmp_path = Path(tmp_dir) / "nyc_footprints_4326.geojson"
        try:
            _download(NYC_OPEN_DATA_DOWNLOAD, tmp_path)
            feature_count = _validate_geojson(tmp_path)
        except Exception as first_error:
            print(f"  bulk export failed: {first_error}")
            try:
                _download_paged(tmp_path)
                feature_count = _validate_geojson(tmp_path)
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError, json.JSONDecodeError) as second_error:
                print("\nERROR: failed to download NYC building footprints.")
                print(f"  bulk export error: {first_error}")
                print(f"  paged export error: {second_error}")
                print("\nManual download:")
                print(f"  {NYC_OPEN_DATA_DOWNLOAD}")
                print(f"  Save to: {BLOCK_FOOTPRINTS_RAW}")
                return 1

        tmp_path.replace(BLOCK_FOOTPRINTS_RAW)

    size_mb = BLOCK_FOOTPRINTS_RAW.stat().st_size / 1_048_576
    print(f"\nwrote: {BLOCK_FOOTPRINTS_RAW}")
    if feature_count >= 0:
        print(f"  {feature_count:,} features, {size_mb:.1f} MB")
    else:
        print(f"  feature count not checked in this environment, {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
