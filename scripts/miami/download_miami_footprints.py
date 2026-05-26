"""
download_miami_footprints.py  [Project Bikini — GlitchOS.io]

Download Miami-Dade County building footprints from the public ArcGIS
FeatureServer and save as GeoJSON to T7.

Source: Miami-Dade County Open Data Hub
  https://gis-mdc.opendata.arcgis.com/datasets/building-footprint-2d
  ~2.5 M features, served in EPSG:4326

Output:
  /mnt/t7/miami/data_raw/geojson/miami_footprints_4326.geojson

Usage:
    python scripts/miami/download_miami_footprints.py          # full county
    python scripts/miami/download_miami_footprints.py --bbox   # Bikini bbox only (fast smoke test)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

BASE_URL   = "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer/0"
PAGE_SIZE  = 1000   # stay well under typical server maxRecordCount
RETRY_MAX  = 3
RETRY_WAIT = 5.0


def fetch_json(url: str) -> dict:
    for attempt in range(1, RETRY_MAX + 1):
        try:
            with urlopen(url, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except URLError as exc:
            if attempt == RETRY_MAX:
                raise
            print(f"    retry {attempt}/{RETRY_MAX}: {exc}")
            time.sleep(RETRY_WAIT)
    raise RuntimeError("unreachable")


def service_max_record_count() -> int:
    info = fetch_json(f"{BASE_URL}?f=json")
    return int(info.get("maxRecordCount", PAGE_SIZE))


def build_query_url(offset: int, page_size: int, bbox: dict | None) -> str:
    params: dict = {
        "where":             "1=1",
        "outFields":         "OBJECTID,UNIQUEID,SOURCE,YEARUPDATE,TYPE,HEIGHT,Shape__Area",
        "outSR":             "4326",
        "f":                 "geojson",
        "resultOffset":      offset,
        "resultRecordCount": page_size,
        "returnGeometry":    "true",
    }
    if bbox:
        params["geometry"]     = f"{bbox['xmin']},{bbox['ymin']},{bbox['xmax']},{bbox['ymax']}"
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"]         = "4326"
        params["spatialRel"]   = "esriSpatialRelIntersects"
    return f"{BASE_URL}/query?{urlencode(params)}"


def download(out_path: Path, bbox: dict | None = None) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    server_max = service_max_record_count()
    page_size  = min(PAGE_SIZE, server_max)
    bbox_label = "Bikini bbox" if bbox else "full county"
    print(f"Downloading Miami-Dade building footprints ({bbox_label})")
    print(f"  server maxRecordCount={server_max}  using page_size={page_size}")
    print(f"  -> {out_path}")

    total = 0
    offset = 0
    t0 = time.time()

    with out_path.open("w", encoding="utf-8") as f:
        f.write('{"type":"FeatureCollection","name":"miami_building_footprints_4326","features":[\n')
        first_feature = True

        while True:
            url = build_query_url(offset, page_size, bbox)
            page = fetch_json(url)

            features = page.get("features", [])
            if not features:
                break

            for feat in features:
                if not first_feature:
                    f.write(",\n")
                f.write(json.dumps(feat, separators=(",", ":")))
                first_feature = False

            total  += len(features)
            offset += len(features)
            elapsed = time.time() - t0
            rate = total / elapsed if elapsed > 0 else 0
            print(f"  {total:>8,} features  {elapsed/60:.1f} min  ({rate:.0f}/s)", end="\r")

            exceeded = page.get("properties", {}).get("exceededTransferLimit", False)
            if not exceeded and len(features) < page_size:
                break   # last page

        f.write("\n]}\n")

    elapsed = time.time() - t0
    size_mb = out_path.stat().st_size / 1_048_576
    print(f"\n  done: {total:,} features  {size_mb:.1f} MB  {elapsed/60:.1f} min")
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox", action="store_true",
                        help="clip to Bikini bbox only (fast smoke test)")
    args = parser.parse_args()

    bbox = CFG.BBOX_4326 if args.bbox else None
    n = download(CFG.COUNTY_FP_PATH, bbox=bbox)
    print(f"Saved {n:,} features -> {CFG.COUNTY_FP_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
