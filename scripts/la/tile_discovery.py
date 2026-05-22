"""
tile_discovery.py  [LA city pipeline - GlitchOS.io]

Discover all real USGS 3DEP LAZ tiles that intersect the City of Los Angeles
municipal boundary by filtering the authoritative LA 2016 LAZ catalog.

No grid enumeration is performed here. Every returned tile comes from
la_2016_laz_catalog.json, which is built by build_la_catalog.py from S3/TNM
product listings.

Output: tile_manifest.json written to city output root.

Usage:
    python scripts/la/build_la_catalog.py
    python scripts/la/tile_discovery.py --city los_angeles
    python scripts/la/tile_discovery.py --city los_angeles --bbox-only
    python scripts/la/tile_discovery.py --city los_angeles --limit 20
    python scripts/la/tile_discovery.py --city los_angeles --json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER
from tile_config import LAZ_DIR

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, MofNCompleteColumn,
)

console = Console()

CATALOG_PATH = LAZ_DIR.parent / "la_2016_laz_catalog.json"


class TileInfo(NamedTuple):
    tile_id:       str
    laz_filename:  str
    download_url:  str | None
    bbox_2229:     dict
    bbox_4326:     dict | None
    on_disk:       bool
    file_size_mb:  float | None


def _bbox_intersects_bbox(a: dict, b: dict) -> bool:
    return (
        a["xmin"] < b["xmax"] and a["xmax"] > b["xmin"] and
        a["ymin"] < b["ymax"] and a["ymax"] > b["ymin"]
    )


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
            "[yellow]WARN: shapely not installed - using bbox intersection only.[/yellow]\n"
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


def _catalog_tile_id(tile: dict) -> str:
    return f"la_{tile['stem_x']}_{tile['stem_y']}{tile['quarter']}"


def _tile_info_from_catalog(tile: dict) -> TileInfo:
    filename = tile["filename"]
    laz_path = LAZ_DIR / filename
    on_disk = laz_path.exists()
    size_mb = laz_path.stat().st_size / 1_048_576 if on_disk else None

    return TileInfo(
        tile_id=_catalog_tile_id(tile),
        laz_filename=filename,
        download_url=tile.get("download_url"),
        bbox_2229=tile.get("bbox_2229") or {},
        bbox_4326=tile.get("bbox_4326"),
        on_disk=on_disk,
        file_size_mb=size_mb,
    )


def _load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(CATALOG_PATH)
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    tiles = data.get("tiles")
    if not isinstance(tiles, list):
        raise ValueError(f"Catalog is missing a tiles list: {CATALOG_PATH}")
    return data


def _filter_catalog_tiles(
    catalog_tiles: list[dict],
    boundary_geom,
    boundary_bbox_4326: dict,
    bbox_only: bool = False,
    limit: int | None = None,
) -> list[TileInfo]:
    tiles: list[TileInfo] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=28),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("  Filtering catalog", total=len(catalog_tiles))

        for entry in catalog_tiles:
            bbox_4326 = entry.get("bbox_4326")
            if not bbox_4326:
                progress.advance(task)
                continue

            if not _bbox_intersects_bbox(bbox_4326, boundary_bbox_4326):
                progress.advance(task)
                continue

            if not bbox_only and not _tile_intersects_boundary(bbox_4326, boundary_geom):
                progress.advance(task)
                continue

            tiles.append(_tile_info_from_catalog(entry))
            progress.update(
                task,
                description=f"  Filtering catalog  found=[green]{len(tiles)}[/green]",
            )
            progress.advance(task)

            if limit is not None and len(tiles) >= limit:
                console.print(f"  [yellow]Limit reached ({limit}). Stopping.[/yellow]")
                break

        progress.update(
            task,
            completed=len(catalog_tiles),
            description=f"  Catalog done  found=[green]{len(tiles)}[/green]",
        )

    return tiles


def discover_tiles(
    city_id: str,
    use_api: bool = True,
    no_grid: bool = False,
    bbox_only: bool = False,
    limit: int | None = None,
) -> list[TileInfo]:
    """
    Discover real USGS 3DEP tiles that intersect the city boundary.

    use_api and no_grid are accepted for backward CLI compatibility, but the
    catalog is now the only discovery source.
    """
    from boundary_downloader import load_boundary

    cfg = CITIES[city_id]
    console.print(f"\n[bold cyan]Discovering tiles for {cfg.display_name}...[/bold cyan]")

    if not use_api:
        console.print("  [dim]--no-api ignored: discovery uses the local catalog.[/dim]")
    if no_grid:
        console.print("  [dim]--no-grid ignored: grid enumeration has been removed.[/dim]")

    try:
        catalog = _load_catalog()
    except FileNotFoundError:
        console.print(f"[red]Catalog not found: {CATALOG_PATH}[/red]")
        console.print("Run first:")
        console.print("  [cyan]python scripts/la/build_la_catalog.py[/cyan]")
        raise

    catalog_tiles = catalog.get("tiles", [])
    console.print(
        f"  [dim]Catalog: {len(catalog_tiles)} real tile(s) "
        f"source={catalog.get('source', 'unknown')}[/dim]"
    )

    # Boundary: uses cache if already downloaded.
    fc = load_boundary(city_id)
    boundary_geom = None if bbox_only else _load_boundary_polygon(fc)
    if bbox_only:
        console.print("  [yellow]bbox-only mode - shapely polygon check skipped[/yellow]")
    elif boundary_geom is None:
        console.print("[yellow]Falling back to bbox intersection (shapely unavailable).[/yellow]")

    t0 = time.time()
    tiles = _filter_catalog_tiles(
        catalog_tiles,
        boundary_geom,
        cfg.bbox_4326,
        bbox_only=bbox_only,
        limit=limit,
    )

    tiles.sort(key=lambda t: t.tile_id)
    console.print(
        f"  [green]Catalog filter: {len(tiles)} tile(s) intersecting boundary "
        f"in {time.time() - t0:.1f}s[/green]"
    )
    return tiles


def write_tile_manifest(city_id: str, tiles: list[TileInfo]) -> Path:
    cfg = CITIES[city_id]

    n_on_disk = sum(1 for t in tiles if t.on_disk)
    n_missing = len(tiles) - n_on_disk
    total_gb_local = sum((t.file_size_mb or 0) for t in tiles if t.on_disk) / 1024
    est_download_gb = (n_missing * 300) / 1024

    manifest = {
        "schema_version": "1.0",
        "pipeline": "GlitchOS.io LA city pipeline",
        "city_id": city_id,
        "display_name": cfg.display_name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "discovery_source": "la_2016_laz_catalog",
        "catalog_path": str(CATALOG_PATH),
        "summary": {
            "total_tiles": len(tiles),
            "on_disk": n_on_disk,
            "missing": n_missing,
            "local_data_gb": round(total_gb_local, 2),
            "est_download_gb": round(est_download_gb, 2),
        },
        "tiles": [
            {
                "tile_id": t.tile_id,
                "laz_filename": t.laz_filename,
                "download_url": t.download_url,
                "bbox_2229": t.bbox_2229,
                "bbox_4326": t.bbox_4326,
                "on_disk": t.on_disk,
                "file_size_mb": round(t.file_size_mb, 1) if t.file_size_mb else None,
            }
            for t in tiles
        ],
    }

    cfg.output_root.mkdir(parents=True, exist_ok=True)
    cfg.tile_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"  [dim]Tile manifest -> {cfg.tile_manifest}[/dim]")
    return cfg.tile_manifest


def _parse_discovery_flags(args: list[str]) -> tuple[str, bool, bool, bool, bool, int | None]:
    """Returns (city_id, use_api, no_grid, bbox_only, as_json, limit)."""
    city_id = "los_angeles"
    use_api = "--no-api" not in args
    no_grid = "--no-grid" in args
    bbox_only = "--bbox-only" in args
    as_json = "--json" in args
    limit = None

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
        console.print(f"Valid: {CITY_ORDER}")
        return 1

    try:
        tiles = discover_tiles(
            city_id,
            use_api=use_api,
            no_grid=no_grid,
            bbox_only=bbox_only,
            limit=limit,
        )
    except FileNotFoundError:
        return 1

    path = write_tile_manifest(city_id, tiles)

    if as_json:
        print(json.dumps([t._asdict() for t in tiles], indent=2, default=str))
    else:
        n_on_disk = sum(1 for t in tiles if t.on_disk)
        console.print(f"\nDiscovered {len(tiles)} tiles, {n_on_disk} on disk -> {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
