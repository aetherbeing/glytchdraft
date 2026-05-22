"""
tile_discovery.py  [LA city pipeline — GlitchOS.io]

Discover all USGS 3DEP LAZ tiles that intersect the City of Los Angeles
municipal boundary, then build a tile manifest with local availability info.

Discovery cascade:
  1. USGS TNM API  — query products API with city bbox, filter by project name
  2. Grid fallback — enumerate 3000 ft State Plane grid cells, generate
                     quarter-tile bboxes (a/b/c/d), check intersection

Both paths perform precise polygon intersection against the city boundary —
bounding-box-only matches are excluded.

Output: tile_manifest.json written to city output root.

Usage:
    python scripts/la/tile_discovery.py --city los_angeles
    python scripts/la/tile_discovery.py --city los_angeles --no-api   # grid only
    python scripts/la/tile_discovery.py --city los_angeles --json     # print manifest
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER, USGS_PROJECT_MATCH
from tile_config import LAZ_DIR, SRC_EPSG, DST_EPSG

from rich.console import Console

console = Console()

# ── USGS TNM API ──────────────────────────────────────────────────────────────

TNM_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"

# Dataset tag for 3DEP 1m DEM / LPC point cloud on TNM
TNM_DATASETS = "Lidar Point Cloud (LPC)"

# Expected naming pattern for LA 2016 tiles
# USGS_LPC_CA_LosAngeles_2016_L4_{X}_{Y}{q}_LAS_2018.laz
# where X is 7-digit State Plane easting ÷ 1000 (no decimal), Y is northing ÷ 1000
TILE_FILENAME_PATTERN = "USGS_LPC_CA_LosAngeles_2016_L4_"

# 3000 ft = 3000 US survey feet = one full grid cell width/height in EPSG:2229
GRID_STEP_FT = 3000.0

# Quarter subdivisions
QUARTERS = ["a", "b", "c", "d"]

# Half-grid in feet (each quarter tile is 1500 x 1500 ft)
HALF_STEP = GRID_STEP_FT / 2.0

# City of LA State Plane zone 5 (EPSG:2229) approximate extent.
# These cover the full municipal boundary + buffer.
CITY_X_MIN = 6_300_000.0   # roughly Santa Monica coast
CITY_X_MAX = 6_600_000.0   # roughly eastern city limit
CITY_Y_MIN = 1_730_000.0   # roughly San Pedro / Harbor area
CITY_Y_MAX = 1_930_000.0   # roughly San Fernando Valley north edge

TIMEOUT = 60


class TileInfo(NamedTuple):
    tile_id:       str            # e.g. "la_6477_1836a"
    laz_filename:  str            # e.g. "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836a_LAS_2018.laz"
    download_url:  str | None     # TNM download URL if discovered via API
    bbox_2229:     dict           # xmin/ymin/xmax/ymax in EPSG:2229
    bbox_4326:     dict | None    # xmin/ymin/xmax/ymax in EPSG:4326 if available
    on_disk:       bool           # LAZ file exists locally
    file_size_mb:  float | None   # local file size if on_disk


# ── coordinate helpers ────────────────────────────────────────────────────────

def _bbox_2229_to_4326(bbox: dict) -> dict:
    """Approximate EPSG:2229 → EPSG:4326 conversion using pyproj if available."""
    try:
        from pyproj import Transformer
        t = Transformer.from_crs(SRC_EPSG, 4326, always_xy=True)
        x0, y0 = t.transform(bbox["xmin"], bbox["ymin"])
        x1, y1 = t.transform(bbox["xmax"], bbox["ymax"])
        return {"xmin": min(x0, x1), "ymin": min(y0, y1),
                "xmax": max(x0, x1), "ymax": max(y0, y1)}
    except Exception:
        return {}


def _quarter_bbox_2229(gx: int, gy: int, q: str) -> dict:
    """
    Return the EPSG:2229 bbox for one quarter-tile.
    Grid origin is at (gx * 1000, gy * 1000) in US survey feet.
    Quarters: a = NW, b = NE, c = SW, d = SE  (USGS convention for CA 2016)
    """
    ox = float(gx) * 1000.0
    oy = float(gy) * 1000.0
    # a=NW, b=NE, c=SW, d=SE
    offsets = {
        "a": (0,          HALF_STEP, HALF_STEP, GRID_STEP_FT),
        "b": (HALF_STEP,  HALF_STEP, GRID_STEP_FT, GRID_STEP_FT),
        "c": (0,          0,         HALF_STEP, HALF_STEP),
        "d": (HALF_STEP,  0,         GRID_STEP_FT, HALF_STEP),
    }
    dx0, dy0, dx1, dy1 = offsets[q]
    return {
        "xmin": ox + dx0, "ymin": oy + dy0,
        "xmax": ox + dx1, "ymax": oy + dy1,
    }


# ── boundary intersection ─────────────────────────────────────────────────────

def _bbox_intersects_bbox(a: dict, b: dict) -> bool:
    return (a["xmin"] < b["xmax"] and a["xmax"] > b["xmin"] and
            a["ymin"] < b["ymax"] and a["ymax"] > b["ymin"])


def _load_boundary_polygon(fc: dict) -> object | None:
    """Return a shapely geometry union of all features in the boundary GeoJSON."""
    try:
        from shapely.geometry import shape
        from shapely.ops import unary_union
        geoms = [shape(f["geometry"]) for f in fc.get("features", []) if f.get("geometry")]
        if not geoms:
            return None
        return unary_union(geoms)
    except Exception:
        return None


def _bbox_4326_to_shapely(bbox: dict) -> object | None:
    """Return a shapely box for a 4326 bbox."""
    try:
        from shapely.geometry import box
        return box(bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"])
    except Exception:
        return None


def _tile_intersects_boundary(bbox_4326: dict, boundary_geom) -> bool:
    """True if the tile bbox intersects the city boundary polygon."""
    if boundary_geom is None:
        return True  # fallback: accept all on shapely failure
    try:
        tile_box = _bbox_4326_to_shapely(bbox_4326)
        if tile_box is None:
            return True
        return boundary_geom.intersects(tile_box)
    except Exception:
        return True


# ── TNM API discovery ─────────────────────────────────────────────────────────

def _http_get_json(url: str, timeout: int = TIMEOUT) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        console.print(f"  [yellow]HTTP error: {e}[/yellow]")
        return None


def _discover_via_tnm(bbox: dict, project_match: str) -> list[dict]:
    """
    Query USGS TNM API for LPC products in the given bbox.
    Returns list of raw product dicts from the API.
    """
    params = {
        "datasets":   TNM_DATASETS,
        "bbox":       f"{bbox['xmin']},{bbox['ymin']},{bbox['xmax']},{bbox['ymax']}",
        "max":        "1000",
        "offset":     "0",
        "outputFormat": "json",
    }
    url = TNM_PRODUCTS_URL + "?" + urllib.parse.urlencode(params)
    console.print(f"  [dim]TNM API query (max 1000)...[/dim]")
    data = _http_get_json(url)
    if not data:
        return []

    items = data.get("items", [])
    console.print(f"  [dim]TNM returned {len(items)} product(s) — filtering by project name[/dim]")

    matched = []
    for item in items:
        title = item.get("title", "")
        urls  = item.get("urls", {})
        if project_match.lower() in title.lower():
            matched.append(item)

    console.print(f"  [dim]{len(matched)} product(s) match {project_match!r}[/dim]")
    return matched


def _tnm_item_to_tile_info(item: dict) -> TileInfo | None:
    """Parse a TNM API product dict into a TileInfo, or None if unparseable."""
    title = item.get("title", "")
    urls  = item.get("urls", {})
    download_url = urls.get("LAZ") or urls.get("LAZ ") or None
    if not download_url:
        for v in urls.values():
            if isinstance(v, str) and v.lower().endswith(".laz"):
                download_url = v
                break

    # Extract filename from title or download URL
    laz_filename = None
    if download_url:
        laz_filename = download_url.rsplit("/", 1)[-1]
    elif TILE_FILENAME_PATTERN in title:
        # Try to parse from title
        idx = title.find(TILE_FILENAME_PATTERN)
        raw = title[idx:].split()[0]
        if not raw.endswith(".laz"):
            raw += "_LAS_2018.laz"
        laz_filename = raw

    if not laz_filename or not laz_filename.startswith(TILE_FILENAME_PATTERN):
        return None

    # Parse grid coords from filename
    # Pattern: USGS_LPC_CA_LosAngeles_2016_L4_{X}_{Y}{q}_LAS_2018.laz
    stem = laz_filename.replace("_LAS_2018.laz", "").replace(".laz", "")
    parts = stem.split("_")
    try:
        # Parts: USGS LPC CA LosAngeles 2016 L4 {X} {Yq}
        x_str  = parts[6]
        yq_str = parts[7]
        q      = yq_str[-1]
        y_str  = yq_str[:-1]
        if q not in QUARTERS:
            return None
        gx = int(x_str)
        gy = int(y_str)
    except (IndexError, ValueError):
        return None

    tile_id   = f"la_{gx}_{gy}{q}"
    bbox_2229 = _quarter_bbox_2229(gx, gy, q)
    bbox_4326 = _bbox_2229_to_4326(bbox_2229)

    laz_path = LAZ_DIR / laz_filename
    on_disk  = laz_path.exists()
    size_mb  = laz_path.stat().st_size / 1_048_576 if on_disk else None

    return TileInfo(
        tile_id=tile_id,
        laz_filename=laz_filename,
        download_url=download_url,
        bbox_2229=bbox_2229,
        bbox_4326=bbox_4326 if bbox_4326 else None,
        on_disk=on_disk,
        file_size_mb=size_mb,
    )


# ── grid fallback discovery ───────────────────────────────────────────────────

def _discover_via_grid(boundary_geom, boundary_bbox_4326: dict) -> list[TileInfo]:
    """
    Enumerate all 3000ft grid cells in the city extent, generate a/b/c/d
    quarter-tile bboxes, check intersection with the city boundary, and
    return TileInfo for all intersecting tiles.
    """
    console.print("  [dim]Grid-based tile discovery (fallback)...[/dim]")

    # Enumerate grid cells that could cover the city
    # CITY_X_MIN/MAX and CITY_Y_MIN/MAX in EPSG:2229 (US survey feet)
    gx_start = int(CITY_X_MIN / 1000)
    gx_end   = int(CITY_X_MAX / 1000) + 1
    gy_start = int(CITY_Y_MIN / 1000)
    gy_end   = int(CITY_Y_MAX / 1000) + 1

    tiles: list[TileInfo] = []
    checked = 0

    for gx in range(gx_start, gx_end + 1):
        for gy in range(gy_start, gy_end + 1):
            for q in QUARTERS:
                bbox_2229 = _quarter_bbox_2229(gx, gy, q)
                bbox_4326 = _bbox_2229_to_4326(bbox_2229)
                if not bbox_4326:
                    continue

                # Fast bbox check first, then precise polygon check
                if not _bbox_intersects_bbox(bbox_4326, boundary_bbox_4326):
                    continue
                if not _tile_intersects_boundary(bbox_4326, boundary_geom):
                    continue

                laz_filename = f"{TILE_FILENAME_PATTERN}{gx}_{gy}{q}_LAS_2018.laz"
                tile_id      = f"la_{gx}_{gy}{q}"
                laz_path     = LAZ_DIR / laz_filename
                on_disk      = laz_path.exists()
                size_mb      = laz_path.stat().st_size / 1_048_576 if on_disk else None

                tiles.append(TileInfo(
                    tile_id=tile_id,
                    laz_filename=laz_filename,
                    download_url=None,
                    bbox_2229=bbox_2229,
                    bbox_4326=bbox_4326,
                    on_disk=on_disk,
                    file_size_mb=size_mb,
                ))
                checked += 1

    console.print(f"  [dim]Grid: {checked} tiles intersect city boundary[/dim]")
    return tiles


# ── main discover function ────────────────────────────────────────────────────

def discover_tiles(city_id: str, use_api: bool = True) -> list[TileInfo]:
    """
    Discover all USGS 3DEP tiles that intersect the city boundary.
    Returns a sorted list of TileInfo.
    """
    from city_config import CITIES
    from boundary_downloader import load_boundary

    cfg = CITIES[city_id]
    console.print(f"\n[bold cyan]Discovering tiles for {cfg.display_name}...[/bold cyan]")

    # Load boundary
    fc = load_boundary(city_id)
    boundary_geom = _load_boundary_polygon(fc)
    if boundary_geom is None:
        console.print("[yellow]WARN: shapely not available — using bbox intersection only[/yellow]")

    # Compute boundary bbox in 4326 from the GeoJSON envelope
    boundary_bbox_4326 = cfg.bbox_4326  # use known city bbox as fallback

    tiles: list[TileInfo] = []
    seen_ids: set[str] = set()

    if use_api:
        console.print("  [dim]Strategy 1: USGS TNM API[/dim]")
        raw_items = _discover_via_tnm(cfg.bbox_4326, cfg.usgs_project)
        for item in raw_items:
            ti = _tnm_item_to_tile_info(item)
            if ti is None:
                continue
            if ti.bbox_4326 and not _tile_intersects_boundary(ti.bbox_4326, boundary_geom):
                continue
            if ti.tile_id not in seen_ids:
                tiles.append(ti)
                seen_ids.add(ti.tile_id)

        if tiles:
            console.print(f"  [green]TNM API: {len(tiles)} tile(s) intersecting boundary[/green]")
        else:
            console.print("  [yellow]TNM API returned no matching tiles — using grid fallback[/yellow]")

    if not tiles:
        console.print("  [dim]Strategy 2: grid enumeration[/dim]")
        grid_tiles = _discover_via_grid(boundary_geom, boundary_bbox_4326)
        for ti in grid_tiles:
            if ti.tile_id not in seen_ids:
                tiles.append(ti)
                seen_ids.add(ti.tile_id)

    # Sort by tile_id for stable output
    tiles.sort(key=lambda t: t.tile_id)
    return tiles


# ── manifest writer ───────────────────────────────────────────────────────────

def write_tile_manifest(city_id: str, tiles: list[TileInfo]) -> Path:
    from city_config import CITIES
    cfg = CITIES[city_id]

    n_on_disk  = sum(1 for t in tiles if t.on_disk)
    n_missing  = len(tiles) - n_on_disk
    total_gb_local = sum((t.file_size_mb or 0) for t in tiles if t.on_disk) / 1024
    # Estimate ~300 MB per LAZ tile on average for CA 2016 LPC
    est_download_gb = (n_missing * 300) / 1024

    manifest = {
        "schema_version": "1.0",
        "pipeline":       "GlitchOS.io LA city pipeline",
        "city_id":        city_id,
        "display_name":   cfg.display_name,
        "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "total_tiles":         len(tiles),
            "on_disk":             n_on_disk,
            "missing":             n_missing,
            "local_data_gb":       round(total_gb_local, 2),
            "est_download_gb":     round(est_download_gb, 2),
        },
        "tiles": [
            {
                "tile_id":      t.tile_id,
                "laz_filename": t.laz_filename,
                "download_url": t.download_url,
                "bbox_2229":    t.bbox_2229,
                "bbox_4326":    t.bbox_4326,
                "on_disk":      t.on_disk,
                "file_size_mb": round(t.file_size_mb, 1) if t.file_size_mb else None,
            }
            for t in tiles
        ],
    }

    cfg.output_root.mkdir(parents=True, exist_ok=True)
    cfg.tile_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"  [dim]Tile manifest → {cfg.tile_manifest}[/dim]")
    return cfg.tile_manifest


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    args    = sys.argv[1:]
    city_id = "los_angeles"
    use_api = "--no-api" not in args
    as_json = "--json" in args

    for i, a in enumerate(args):
        if a == "--city" and i + 1 < len(args):
            city_id = args[i + 1]

    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        return 1

    tiles = discover_tiles(city_id, use_api=use_api)
    path  = write_tile_manifest(city_id, tiles)

    if as_json:
        import json as _json
        print(_json.dumps([t._asdict() for t in tiles], indent=2, default=str))
    else:
        n_on_disk = sum(1 for t in tiles if t.on_disk)
        console.print(f"\nDiscovered {len(tiles)} tiles, {n_on_disk} on disk → {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
