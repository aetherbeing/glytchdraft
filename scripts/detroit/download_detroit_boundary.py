"""
download_detroit_boundary.py  [GlitchOS city pipeline — Detroit]

Download the official City of Detroit municipal boundary from Census TIGER
and write it as GeoJSON to the expected pipeline path on T7.

Primary source:
  Census TIGER/Line 2023 — Michigan Incorporated Places
  https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_26_place.zip
  Filter: GEOID = 2622000  (State FIPS 26 + Place FIPS 22000 = Detroit)
  Input CRS: EPSG:4269 (NAD83) → reprojected to EPSG:4326

Fallback source (if TIGER download fails):
  OSM Overpass API — relation 134591 (wikidata Q12439, Detroit MI)

Output:
  /mnt/t7/detroit/data_raw/geojson/detroit_city_boundary.geojson

Usage:
    # Requires geopandas (available in pdal_env):
    conda run -n pdal_env python3 scripts/detroit/download_detroit_boundary.py
    python3 scripts/detroit/download_detroit_boundary.py  # if pdal_env is active

    python3 scripts/detroit/download_detroit_boundary.py --dry-run
    python3 scripts/detroit/download_detroit_boundary.py --force
    python3 scripts/detroit/download_detroit_boundary.py --fallback-osm
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

# ── dependency check ──────────────────────────────────────────────────────────

try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

# ── constants ─────────────────────────────────────────────────────────────────

DETROIT_GEOID = "2622000"   # Michigan (26) + Detroit place (22000)
TIGER_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_26_place.zip"

OSM_RELATION_ID = 134591    # wikidata Q12439 — confirmed Detroit MI (pop 632k)
OSM_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OUTPUT_PATH = Path("/mnt/t7/detroit/data_raw/geojson/detroit_city_boundary.geojson")
HTTP_TIMEOUT = 120

try:
    from rich.console import Console
    from rich.panel import Panel
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


# ── TIGER source ──────────────────────────────────────────────────────────────

def _download_tiger(tmp_dir: Path) -> Path:
    """Download TIGER Michigan places zip to tmp_dir. Returns zip path."""
    dest = tmp_dir / "tl_2023_26_place.zip"
    if dest.exists():
        return dest
    _pr(f"  Downloading TIGER Michigan places: {TIGER_URL}")
    req = urllib.request.Request(TIGER_URL, headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        t0 = time.time()
        with dest.open("wb") as fh:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
    elapsed = time.time() - t0
    _pr(f"  Downloaded {downloaded / 1e6:.1f} MB in {elapsed:.1f}s")
    return dest


def _read_tiger(zip_path: Path) -> dict:
    """
    Read Michigan places from TIGER zip, filter to Detroit, return GeoJSON dict.
    Requires geopandas.
    """
    if not HAS_GEOPANDAS:
        raise RuntimeError(
            "geopandas is required to read TIGER shapefiles.\n"
            "Run with pdal_env: conda run -n pdal_env python3 scripts/detroit/download_detroit_boundary.py"
        )

    _pr("  Reading TIGER shapefile...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gdf = gpd.read_file(zip_path)

    _pr(f"  Michigan places loaded: {len(gdf)} features  CRS: {gdf.crs}")

    detroit = gdf[gdf["GEOID"] == DETROIT_GEOID].copy()
    if detroit.empty:
        raise RuntimeError(
            f"GEOID={DETROIT_GEOID} not found in TIGER shapefile.\n"
            f"Available GEOIDs (first 10): {list(gdf['GEOID'][:10])}"
        )

    _pr(f"  Detroit found: NAME={detroit.iloc[0]['NAME']}  GEOID={DETROIT_GEOID}")

    # Reproject EPSG:4269 (NAD83) → EPSG:4326 — difference is sub-meter
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        detroit = detroit.to_crs("EPSG:4326")

    geojson = json.loads(detroit.to_json())

    # Annotate with provenance metadata
    for feat in geojson.get("features", []):
        feat.setdefault("properties", {}).update({
            "_source": "census_tiger_2023",
            "_tiger_url": TIGER_URL,
            "_geoid": DETROIT_GEOID,
            "_downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    return geojson


def from_tiger(dry_run: bool = False) -> dict | None:
    """Download and parse TIGER boundary. Returns GeoJSON dict or None on failure."""
    _pr("\n[bold cyan]Source: Census TIGER 2023[/bold cyan]" if HAS_RICH else "\nSource: Census TIGER 2023")
    try:
        with tempfile.TemporaryDirectory(prefix="detroit_tiger_") as tmp:
            zip_path = _download_tiger(Path(tmp))
            return _read_tiger(zip_path)
    except Exception as exc:
        _pr(
            f"  [yellow]TIGER failed: {exc}[/yellow]" if HAS_RICH
            else f"  TIGER failed: {exc}"
        )
        return None


# ── OSM fallback ──────────────────────────────────────────────────────────────

def _osm_relation_to_geojson(elements: list) -> dict | None:
    """Convert OSM relation elements (with geom) to a GeoJSON FeatureCollection."""
    for el in elements:
        if el.get("type") != "relation" or el.get("id") != OSM_RELATION_ID:
            continue
        members = el.get("members", [])
        outer_rings: list[list] = []
        for m in members:
            if m.get("role") == "outer" and m.get("type") == "way":
                coords = [[n["lon"], n["lat"]] for n in m.get("geometry", [])]
                if len(coords) >= 4:
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    outer_rings.append(coords)

        if not outer_rings:
            return None

        if len(outer_rings) == 1:
            geometry = {"type": "Polygon", "coordinates": outer_rings}
        else:
            geometry = {"type": "MultiPolygon", "coordinates": [[r] for r in outer_rings]}

        tags = el.get("tags", {})
        feature = {
            "type": "Feature",
            "properties": {
                "NAME": tags.get("name", "Detroit"),
                "GEOID": DETROIT_GEOID,
                "osm_id": str(OSM_RELATION_ID),
                "wikidata": tags.get("wikidata", "Q12439"),
                "population": tags.get("population"),
                "_source": "osm_overpass",
                "_osm_relation": OSM_RELATION_ID,
                "_downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            "geometry": geometry,
        }
        return {"type": "FeatureCollection", "features": [feature]}

    return None


def from_osm(dry_run: bool = False) -> dict | None:
    """Fetch Detroit boundary from OSM Overpass. Returns GeoJSON dict or None."""
    _pr("\n[bold cyan]Source: OSM Overpass (fallback)[/bold cyan]" if HAS_RICH else "\nSource: OSM Overpass (fallback)")
    query = f"[out:json][timeout:60];relation({OSM_RELATION_ID});out geom;"
    payload = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        OSM_OVERPASS_URL, data=payload, headers={"User-Agent": "GlitchOS/1.0"}
    )
    for attempt in range(1, 4):
        try:
            _pr(f"  OSM Overpass query (attempt {attempt}/3)...")
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())
            fc = _osm_relation_to_geojson(result.get("elements", []))
            if fc:
                _pr(f"  OSM returned {len(fc['features'])} feature(s)")
                return fc
            _pr("  OSM response contained no usable geometry")
            return None
        except urllib.error.HTTPError as exc:
            if exc.code == 504 and attempt < 3:
                _pr(f"  Overpass 504 — retry in 15s...")
                time.sleep(15)
                continue
            _pr(f"  OSM failed: HTTP {exc.code}")
            return None
        except Exception as exc:
            _pr(f"  OSM failed: {exc}")
            return None
    return None


# ── write + report ────────────────────────────────────────────────────────────

def _bounds(geojson: dict) -> tuple[float, float, float, float] | None:
    """Return (xmin, ymin, xmax, ymax) across all features."""
    lons: list[float] = []
    lats: list[float] = []

    def _collect(coords):
        for item in coords:
            if isinstance(item[0], (int, float)):
                lons.append(item[0])
                lats.append(item[1])
            else:
                _collect(item)

    for feat in geojson.get("features", []):
        geom = feat.get("geometry") or {}
        _collect(geom.get("coordinates", []))

    if not lons:
        return None
    return min(lons), min(lats), max(lons), max(lats)


def write_and_report(geojson: dict, out_path: Path, source: str, dry_run: bool) -> None:
    n = len(geojson.get("features", []))
    bounds = _bounds(geojson)

    _pr("")
    if HAS_RICH:
        console.print(Panel("[bold green]Detroit Boundary[/bold green]", expand=False))
    _pr(f"  Source        : {source}")
    _pr(f"  Features      : {n}")
    if bounds:
        _pr(f"  Bounds (4326) : xmin={bounds[0]:.6f}  ymin={bounds[1]:.6f}  xmax={bounds[2]:.6f}  ymax={bounds[3]:.6f}")
    _pr(f"  Output        : {out_path}")

    if dry_run:
        _pr("  [dim]dry-run — no file written[/dim]" if HAS_RICH else "  dry-run — no file written")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(geojson, separators=(",", ":")), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    _pr(
        f"  [green]Written: {out_path}  ({size_kb:.0f} KB)[/green]" if HAS_RICH
        else f"  Written: {out_path}  ({size_kb:.0f} KB)"
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Detroit city boundary (Census TIGER 2023, GEOID=2622000) to T7.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  conda run -n pdal_env python3 scripts/detroit/download_detroit_boundary.py\n"
            "  conda run -n pdal_env python3 scripts/detroit/download_detroit_boundary.py --dry-run\n"
            "  conda run -n pdal_env python3 scripts/detroit/download_detroit_boundary.py --force\n"
            "  conda run -n pdal_env python3 scripts/detroit/download_detroit_boundary.py --fallback-osm\n"
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print report only; do not write file")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if output file already exists")
    parser.add_argument("--fallback-osm", action="store_true",
                        help="Skip TIGER and use OSM Overpass directly")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH,
                        help=f"Override output path (default: {OUTPUT_PATH})")
    args = parser.parse_args()

    out_path = args.output

    if out_path.exists() and not args.force and not args.dry_run:
        size_kb = out_path.stat().st_size / 1024
        _pr(f"Already exists: {out_path}  ({size_kb:.0f} KB) — use --force to re-download")
        return 0

    # Source cascade
    geojson = None
    source = ""

    if not args.fallback_osm:
        geojson = from_tiger(dry_run=args.dry_run)
        if geojson:
            source = "census_tiger_2023"

    if geojson is None:
        _pr("  Falling back to OSM Overpass..." if not args.fallback_osm else "")
        geojson = from_osm(dry_run=args.dry_run)
        if geojson:
            source = "osm_overpass"

    if geojson is None:
        _pr(
            "[red]ERROR: Both TIGER and OSM sources failed. Check network connectivity.[/red]"
            if HAS_RICH else
            "ERROR: Both TIGER and OSM sources failed. Check network connectivity."
        )
        return 1

    n = len(geojson.get("features", []))
    if n == 0:
        _pr(
            "[red]ERROR: Source returned 0 features for Detroit (GEOID=2622000).[/red]"
            if HAS_RICH else
            "ERROR: Source returned 0 features for Detroit (GEOID=2622000)."
        )
        return 1

    write_and_report(geojson, out_path, source, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
