"""
tile_discovery.py  [LA city pipeline — GlitchOS.io]

Discover all USGS 3DEP LAZ tiles that intersect the City of Los Angeles
municipal boundary, then build a tile manifest with local availability info.

Discovery cascade:
  1. USGS TNM API  — query products API with city bbox, filter by project name
  2. Grid fallback — enumerate 3000 ft State Plane grid cells, generate
                     quarter-tile bboxes (a/b/c/d), check intersection

Both paths perform precise polygon intersection against the city boundary.
--bbox-only skips shapely and uses bbox intersection only.

Output: tile_manifest.json written to city output root.

Usage:
    python scripts/la/tile_discovery.py --city los_angeles
    python scripts/la/tile_discovery.py --city los_angeles --no-api     # grid only
    python scripts/la/tile_discovery.py --city los_angeles --no-grid    # API only
    python scripts/la/tile_discovery.py --city los_angeles --bbox-only  # no shapely
    python scripts/la/tile_discovery.py --city los_angeles --limit 20   # cap for testing
    python scripts/la/tile_discovery.py --city los_angeles --json       # print manifest
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER, USGS_PROJECT_MATCH
from tile_config import LAZ_DIR, SRC_EPSG, DST_EPSG

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, MofNCompleteColumn,
)

console = Console()

# ── USGS TNM API ──────────────────────────────────────────────────────────────

TNM_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
TNM_DATASETS     = "Lidar Point Cloud (LPC)"

TILE_FILENAME_PATTERN = "USGS_LPC_CA_LosAngeles_2016_L4_"

GRID_STEP_FT = 3000.0
QUARTERS     = ["a", "b", "c", "d"]
HALF_STEP    = GRID_STEP_FT / 2.0

TNM_TIMEOUT      = 60   # seconds for TNM API
OVERPASS_TIMEOUT = 90   # seconds for OSM Overpass (slower)


class TileInfo(NamedTuple):
    tile_id:       str
    laz_filename:  str
    download_url:  str | None
    bbox_2229:     dict
    bbox_4326:     dict | None
    on_disk:       bool
    file_size_mb:  float | None


# ── coordinate helpers ────────────────────────────────────────────────────────

_transformer_2229_to_4326 = None
_transformer_4326_to_2229 = None


def _get_transformer_2229_to_4326():
    global _transformer_2229_to_4326
    if _transformer_2229_to_4326 is None:
        from pyproj import Transformer
        _transformer_2229_to_4326 = Transformer.from_crs(SRC_EPSG, 4326, always_xy=True)
    return _transformer_2229_to_4326


def _get_transformer_4326_to_2229():
    global _transformer_4326_to_2229
    if _transformer_4326_to_2229 is None:
        from pyproj import Transformer
        _transformer_4326_to_2229 = Transformer.from_crs(4326, SRC_EPSG, always_xy=True)
    return _transformer_4326_to_2229


def _bbox_2229_to_4326(bbox: dict) -> dict:
    try:
        t = _get_transformer_2229_to_4326()
        x0, y0 = t.transform(bbox["xmin"], bbox["ymin"])
        x1, y1 = t.transform(bbox["xmax"], bbox["ymax"])
        return {"xmin": min(x0, x1), "ymin": min(y0, y1),
                "xmax": max(x0, x1), "ymax": max(y0, y1)}
    except Exception:
        return {}


def _bbox_4326_to_2229_approx(bbox: dict) -> dict:
    """Project a 4326 bbox to approx EPSG:2229 by transforming all four corners."""
    try:
        t = _get_transformer_4326_to_2229()
        corners = [
            t.transform(bbox["xmin"], bbox["ymin"]),
            t.transform(bbox["xmax"], bbox["ymin"]),
            t.transform(bbox["xmin"], bbox["ymax"]),
            t.transform(bbox["xmax"], bbox["ymax"]),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        return {"xmin": min(xs), "ymin": min(ys), "xmax": max(xs), "ymax": max(ys)}
    except Exception:
        # Fallback to hardcoded city extent if pyproj fails
        return {"xmin": 6_290_000.0, "ymin": 1_720_000.0,
                "xmax": 6_630_000.0, "ymax": 1_960_000.0}


def _quarter_bbox_2229(gx: int, gy: int, q: str) -> dict:
    ox = float(gx) * 1000.0
    oy = float(gy) * 1000.0
    offsets = {
        "a": (0,         HALF_STEP,  HALF_STEP,    GRID_STEP_FT),
        "b": (HALF_STEP, HALF_STEP,  GRID_STEP_FT, GRID_STEP_FT),
        "c": (0,         0,          HALF_STEP,    HALF_STEP),
        "d": (HALF_STEP, 0,          GRID_STEP_FT, HALF_STEP),
    }
    dx0, dy0, dx1, dy1 = offsets[q]
    return {"xmin": ox + dx0, "ymin": oy + dy0,
            "xmax": ox + dx1, "ymax": oy + dy1}


# ── boundary intersection ─────────────────────────────────────────────────────

def _bbox_intersects_bbox(a: dict, b: dict) -> bool:
    return (a["xmin"] < b["xmax"] and a["xmax"] > b["xmin"] and
            a["ymin"] < b["ymax"] and a["ymax"] > b["ymin"])


def _load_boundary_polygon(fc: dict) -> object | None:
    try:
        from shapely.geometry import shape
        from shapely.ops import unary_union
        geoms = [shape(f["geometry"]) for f in fc.get("features", []) if f.get("geometry")]
        if not geoms:
            return None
        return unary_union(geoms)
    except ImportError:
        console.print(
            "[yellow]WARN: shapely not installed — using bbox intersection only.[/yellow]\n"
            "  Install with:\n"
            "    [cyan]conda install -n pdal_env -c conda-forge shapely[/cyan]"
        )
        return None
    except Exception as e:
        console.print(f"[yellow]WARN: could not load boundary polygon: {e}[/yellow]")
        return None


def _bbox_4326_to_shapely(bbox: dict) -> object | None:
    try:
        from shapely.geometry import box
        return box(bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"])
    except Exception:
        return None


def _tile_intersects_boundary(bbox_4326: dict, boundary_geom) -> bool:
    if boundary_geom is None:
        return True
    try:
        tile_box = _bbox_4326_to_shapely(bbox_4326)
        if tile_box is None:
            return True
        return boundary_geom.intersects(tile_box)
    except Exception:
        return True


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_get_json(url: str, timeout: int = TNM_TIMEOUT) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if "timed out" in str(reason).lower():
            console.print(f"  [yellow]Request timed out after {timeout}s: {url[:80]}[/yellow]")
        else:
            console.print(f"  [yellow]HTTP error: {reason}[/yellow]")
        return None
    except Exception as e:
        console.print(f"  [yellow]HTTP error: {e}[/yellow]")
        return None


# ── TNM API discovery ─────────────────────────────────────────────────────────

def _discover_via_tnm(bbox: dict, project_match: str) -> list[dict]:
    params = {
        "datasets":     TNM_DATASETS,
        "bbox":         f"{bbox['xmin']},{bbox['ymin']},{bbox['xmax']},{bbox['ymax']}",
        "max":          "1000",
        "offset":       "0",
        "outputFormat": "json",
    }
    url = TNM_PRODUCTS_URL + "?" + urllib.parse.urlencode(params)
    console.print(f"  [dim]TNM API query (timeout {TNM_TIMEOUT}s, max 1000)...[/dim]")
    t0   = time.time()
    data = _http_get_json(url, timeout=TNM_TIMEOUT)
    elapsed = time.time() - t0
    if not data:
        return []

    items = data.get("items", [])
    console.print(f"  [dim]TNM: {len(items)} product(s) in {elapsed:.1f}s — "
                  f"filtering by {project_match!r}[/dim]")

    matched = [
        item for item in items
        if project_match.lower() in item.get("title", "").lower()
    ]
    console.print(f"  [dim]{len(matched)} product(s) match[/dim]")
    return matched


def _tnm_item_to_tile_info(item: dict) -> TileInfo | None:
    title = item.get("title", "")
    urls  = item.get("urls", {})
    download_url = urls.get("LAZ") or urls.get("LAZ ") or None
    if not download_url:
        for v in urls.values():
            if isinstance(v, str) and v.lower().endswith(".laz"):
                download_url = v
                break

    laz_filename = None
    if download_url:
        laz_filename = download_url.rsplit("/", 1)[-1]
    elif TILE_FILENAME_PATTERN in title:
        idx = title.find(TILE_FILENAME_PATTERN)
        raw = title[idx:].split()[0]
        if not raw.endswith(".laz"):
            raw += "_LAS_2018.laz"
        laz_filename = raw

    if not laz_filename or not laz_filename.startswith(TILE_FILENAME_PATTERN):
        return None

    stem  = laz_filename.replace("_LAS_2018.laz", "").replace(".laz", "")
    parts = stem.split("_")
    try:
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

def _discover_via_grid(
    boundary_geom,
    boundary_bbox_4326: dict,
    bbox_only: bool = False,
    limit: int | None = None,
) -> list[TileInfo]:
    """
    Enumerate 3000ft grid cells covering the city boundary, generate a/b/c/d
    quarter-tile bboxes, check intersection, return matching TileInfos.

    Shows a Rich progress bar — never silent.
    """
    # Project city 4326 bbox → EPSG:2229 to tighten the search range.
    city_2229 = _bbox_4326_to_2229_approx(boundary_bbox_4326)

    # Grid coords are in thousands of feet (i.e. gx=6477 → ox=6,477,000 ft)
    # Add 1-cell buffer on each side.
    gx_start = int(city_2229["xmin"] / 1000) - 1
    gx_end   = int(city_2229["xmax"] / 1000) + 1
    gy_start = int(city_2229["ymin"] / 1000) - 1
    gy_end   = int(city_2229["ymax"] / 1000) + 1

    n_gx             = gx_end - gx_start + 1
    n_gy             = gy_end - gy_start + 1
    total_candidates = n_gx * n_gy * 4

    console.print(
        f"  City bbox (4326): "
        f"lon [{boundary_bbox_4326['xmin']:.3f}, {boundary_bbox_4326['xmax']:.3f}]  "
        f"lat [{boundary_bbox_4326['ymin']:.3f}, {boundary_bbox_4326['ymax']:.3f}]"
    )
    console.print(
        f"  City bbox (2229): "
        f"x [{city_2229['xmin']:.0f}, {city_2229['xmax']:.0f}]  "
        f"y [{city_2229['ymin']:.0f}, {city_2229['ymax']:.0f}]"
    )
    console.print(f"  Grid x range:     {gx_start}–{gx_end}  ({n_gx} cells)")
    console.print(f"  Grid y range:     {gy_start}–{gy_end}  ({n_gy} cells)")
    console.print(f"  Total candidates: {n_gx} × {n_gy} × 4 = {total_candidates:,}")
    if bbox_only:
        console.print("  [yellow]bbox-only mode — shapely polygon check skipped[/yellow]")
    if limit is not None:
        console.print(f"  [yellow]limit: {limit} tiles (testing mode)[/yellow]")

    tiles: list[TileInfo] = []
    t0 = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=28),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        scan_task = progress.add_task(
            f"  Scanning grid x={gx_start}", total=n_gx
        )

        done = False
        for gx in range(gx_start, gx_end + 1):
            if done:
                break
            progress.update(
                scan_task,
                description=f"  x={gx}  found=[green]{len(tiles)}[/green]",
            )
            for gy in range(gy_start, gy_end + 1):
                if done:
                    break
                for q in QUARTERS:
                    bbox_2229 = _quarter_bbox_2229(gx, gy, q)
                    bbox_4326 = _bbox_2229_to_4326(bbox_2229)
                    if not bbox_4326:
                        continue

                    if not _bbox_intersects_bbox(bbox_4326, boundary_bbox_4326):
                        continue

                    if not bbox_only and not _tile_intersects_boundary(bbox_4326, boundary_geom):
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

                    elapsed = time.time() - t0
                    progress.update(
                        scan_task,
                        description=(
                            f"  x={gx} y={gy}{q}  "
                            f"found=[green]{len(tiles)}[/green]  "
                            f"{elapsed:.0f}s"
                        ),
                    )

                    if limit is not None and len(tiles) >= limit:
                        console.print(f"  [yellow]Limit reached ({limit}). Stopping.[/yellow]")
                        done = True
                        break

            progress.advance(scan_task)

        # Force bar to 100% if limit stopped us early
        progress.update(scan_task, completed=n_gx,
                        description=f"  Grid done  found=[green]{len(tiles)}[/green]  "
                                    f"{time.time() - t0:.1f}s")

    elapsed = time.time() - t0
    console.print(f"  [dim]Grid complete: {len(tiles)} tile(s) in {elapsed:.1f}s[/dim]")
    return tiles


# ── main discover function ────────────────────────────────────────────────────

def discover_tiles(
    city_id:  str,
    use_api:  bool = True,
    no_grid:  bool = False,
    bbox_only: bool = False,
    limit:    int | None = None,
) -> list[TileInfo]:
    """
    Discover all USGS 3DEP tiles that intersect the city boundary.

    use_api   — query USGS TNM API first (default True)
    no_grid   — skip grid fallback even if API returns nothing
    bbox_only — use bounding-box intersection only, skip shapely polygon check
    limit     — stop after N tiles (for testing)
    """
    from city_config import CITIES
    from boundary_downloader import load_boundary

    cfg = CITIES[city_id]
    console.print(f"\n[bold cyan]Discovering tiles for {cfg.display_name}...[/bold cyan]")

    # Boundary: uses cache if already downloaded
    fc = load_boundary(city_id)
    boundary_geom = None if bbox_only else _load_boundary_polygon(fc)
    if not bbox_only and boundary_geom is None:
        console.print("[yellow]Falling back to bbox intersection (shapely unavailable).[/yellow]")

    boundary_bbox_4326 = cfg.bbox_4326

    tiles: list[TileInfo] = []
    seen_ids: set[str] = set()

    if use_api:
        console.print("  [dim]Strategy 1: USGS TNM API[/dim]")
        raw_items = _discover_via_tnm(cfg.bbox_4326, cfg.usgs_project)
        for item in raw_items:
            ti = _tnm_item_to_tile_info(item)
            if ti is None:
                continue
            if ti.bbox_4326 and not bbox_only and not _tile_intersects_boundary(ti.bbox_4326, boundary_geom):
                continue
            if ti.tile_id not in seen_ids:
                tiles.append(ti)
                seen_ids.add(ti.tile_id)
            if limit is not None and len(tiles) >= limit:
                break

        if tiles:
            console.print(f"  [green]TNM API: {len(tiles)} tile(s) intersecting boundary[/green]")
        else:
            console.print("  [yellow]TNM API returned no matching tiles.[/yellow]")

    if not tiles and not no_grid:
        console.print("  Strategy 2: grid enumeration")
        grid_tiles = _discover_via_grid(
            boundary_geom, boundary_bbox_4326,
            bbox_only=bbox_only, limit=limit,
        )
        for ti in grid_tiles:
            if ti.tile_id not in seen_ids:
                tiles.append(ti)
                seen_ids.add(ti.tile_id)
    elif not tiles and no_grid:
        console.print("  [yellow]--no-grid set and API returned nothing — no tiles found.[/yellow]")

    tiles.sort(key=lambda t: t.tile_id)
    return tiles


# ── manifest writer ───────────────────────────────────────────────────────────

def write_tile_manifest(city_id: str, tiles: list[TileInfo]) -> Path:
    from city_config import CITIES
    cfg = CITIES[city_id]

    n_on_disk       = sum(1 for t in tiles if t.on_disk)
    n_missing       = len(tiles) - n_on_disk
    total_gb_local  = sum((t.file_size_mb or 0) for t in tiles if t.on_disk) / 1024
    est_download_gb = (n_missing * 300) / 1024

    manifest = {
        "schema_version": "1.0",
        "pipeline":       "GlitchOS.io LA city pipeline",
        "city_id":        city_id,
        "display_name":   cfg.display_name,
        "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "total_tiles":     len(tiles),
            "on_disk":         n_on_disk,
            "missing":         n_missing,
            "local_data_gb":   round(total_gb_local, 2),
            "est_download_gb": round(est_download_gb, 2),
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

def _parse_discovery_flags(args: list[str]) -> tuple[str, bool, bool, bool, bool, int | None]:
    """Returns (city_id, use_api, no_grid, bbox_only, as_json, limit)."""
    city_id  = "los_angeles"
    use_api  = "--no-api"   not in args
    no_grid  = "--no-grid"  in args
    bbox_only = "--bbox-only" in args
    as_json  = "--json"     in args
    limit    = None

    for i, a in enumerate(args):
        if a == "--city" and i + 1 < len(args):
            city_id = args[i + 1]
        if a == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                pass

    return city_id, use_api, no_grid, bbox_only, as_json, limit


def main():
    args = sys.argv[1:]
    city_id, use_api, no_grid, bbox_only, as_json, limit = _parse_discovery_flags(args)

    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        return 1

    tiles = discover_tiles(city_id, use_api=use_api, no_grid=no_grid,
                           bbox_only=bbox_only, limit=limit)
    path  = write_tile_manifest(city_id, tiles)

    if as_json:
        print(json.dumps([t._asdict() for t in tiles], indent=2, default=str))
    else:
        n_on_disk = sum(1 for t in tiles if t.on_disk)
        console.print(f"\nDiscovered {len(tiles)} tiles, {n_on_disk} on disk → {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
