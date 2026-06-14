"""
download_detroit_footprints.py  [GlitchOS city pipeline — Detroit]

Download City of Detroit building footprints from the ArcGIS FeatureServer
and write GeoJSON to T7.

Source:
  City of Detroit Open Data — BaseUnitFeatures FeatureServer, Layer 2 (buildings)
  https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/BaseUnitFeatures/FeatureServer/2
  ArcGIS item: 2b9ab7687289457c9793a4a92d7c4eb9  owner: topsoil.integration_detroitmi  access: public
  ~364,210 features  EPSG:4326

  NOTE: production_allowed is false in detroit.json pending manual license/terms
  confirmation from data.detroitmi.gov.

Output:
  /mnt/t7/detroit/data_raw/footprints/detroit_buildings.geojson

Usage:
    python3 scripts/detroit/download_detroit_footprints.py
    python3 scripts/detroit/download_detroit_footprints.py --dry-run
    python3 scripts/detroit/download_detroit_footprints.py --force
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL  = "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/BaseUnitFeatures/FeatureServer/2"
OUT_PATH  = Path("/mnt/t7/detroit/data_raw/footprints/detroit_buildings.geojson")
PAGE_SIZE = 2000
RETRY_MAX = 3

try:
    from rich.console import Console
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None


def _pr(msg: str) -> None:
    if console:
        console.print(msg)
    else:
        print(msg)


def _service_info() -> tuple[int, int]:
    """Return (total_count, max_record_count) from the FeatureServer layer."""
    info_url = f"{BASE_URL}?f=json"
    req = urllib.request.Request(info_url, headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        info = json.loads(resp.read())
    max_rc = int(info.get("maxRecordCount", PAGE_SIZE))

    count_params = urllib.parse.urlencode({"where": "1=1", "returnCountOnly": "true", "f": "json"})
    req2 = urllib.request.Request(f"{BASE_URL}/query?{count_params}", headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req2, timeout=30) as resp2:
        count_data = json.loads(resp2.read())
    total = int(count_data.get("count", 0))
    return total, max_rc


def _fetch_page(offset: int, page_size: int) -> tuple[list, bool]:
    """Fetch one page of GeoJSON features. Returns (features, exceeded_transfer_limit)."""
    params = urllib.parse.urlencode({
        "where": "1=1",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "returnGeometry": "true",
    })
    url = f"{BASE_URL}/query?{params}"
    for attempt in range(1, RETRY_MAX + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                page = json.loads(resp.read())
            features = page.get("features", [])
            exceeded = bool(page.get("properties", {}).get("exceededTransferLimit"))
            return features, exceeded
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == RETRY_MAX:
                raise
            wait = 5 * attempt
            _pr(f"  page offset={offset} attempt {attempt}/{RETRY_MAX} failed: {exc} — retry in {wait}s")
            time.sleep(wait)
    return [], False


def download(out_path: Path, force: bool = False, dry_run: bool = False) -> int:
    if out_path.exists() and not force and not dry_run:
        size_mb = out_path.stat().st_size / 1e6
        _pr(f"Already exists: {out_path}  ({size_mb:.1f} MB) — use --force to re-download")
        return 0

    _pr(f"Querying FeatureServer: {BASE_URL}")
    total, max_rc = _service_info()
    page_size = min(PAGE_SIZE, max_rc)
    pages = (total + page_size - 1) // page_size

    _pr(f"  Total features : {total:,}")
    _pr(f"  Page size      : {page_size}  (~{pages} pages)")
    _pr(f"  Output         : {out_path}")

    if dry_run:
        _pr("  dry-run — no files written")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    written = 0
    offset = 0

    with out_path.open("w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","name":"detroit_buildings","features":[\n')
        first = True

        if HAS_RICH:
            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]{task.description}"),
                BarColumn(bar_width=30),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=False,
            ) as progress:
                task = progress.add_task("downloading", total=pages)
                page_num = 0
                while True:
                    features, exceeded = _fetch_page(offset, page_size)
                    if not features:
                        break
                    for feat in features:
                        if not first:
                            fh.write(",\n")
                        fh.write(json.dumps(feat, separators=(",", ":")))
                        first = False
                    written += len(features)
                    offset  += len(features)
                    page_num += 1
                    progress.update(task, advance=1,
                                    description=f"page {page_num}/{pages}  n={written:,}")
                    if not exceeded and len(features) < page_size:
                        break
        else:
            while True:
                features, exceeded = _fetch_page(offset, page_size)
                if not features:
                    break
                for feat in features:
                    if not first:
                        fh.write(",\n")
                    fh.write(json.dumps(feat, separators=(",", ":")))
                    first = False
                written += len(features)
                offset  += len(features)
                elapsed = time.time() - t0
                rate = written / elapsed if elapsed > 0 else 0
                print(f"  {written:>7,} / {total:,}  {elapsed/60:.1f} min  ({rate:.0f}/s)", end="\r")
                if not exceeded and len(features) < page_size:
                    break

        fh.write("\n]}\n")

    elapsed = time.time() - t0
    size_mb = out_path.stat().st_size / 1e6
    _pr(f"\nDone: {written:,} features  {size_mb:.1f} MB  {elapsed/60:.1f} min  → {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Detroit building footprints from ArcGIS FeatureServer to T7.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scripts/detroit/download_detroit_footprints.py\n"
            "  python3 scripts/detroit/download_detroit_footprints.py --dry-run\n"
            "  python3 scripts/detroit/download_detroit_footprints.py --force\n"
            "  python3 scripts/detroit/download_detroit_footprints.py --output /custom/path.geojson\n"
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan only; do not download")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if output file already exists")
    parser.add_argument("--output", type=Path, default=OUT_PATH,
                        help=f"Override output path (default: {OUT_PATH})")
    args = parser.parse_args()

    return download(args.output, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
