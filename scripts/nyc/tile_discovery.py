"""
tile_discovery.py  [NYC city pipeline - GlitchOS.io]

Disk-first tile discovery: scan LAZ_DIR for on-disk .laz files,
enrich with bbox/borough data from the NOAA catalog if available.
No network access is required when tiles are already downloaded.

Borough assignment uses coarse 4326 bboxes from city_config.BOROUGH_BBOXES_4326.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

from build_nyc_catalog import CATALOG_PATH, build_catalog
from city_config import CITIES, CITY_ORDER, BOROUGH_BBOXES_4326
from tile_config import LAZ_DIR, SRC_EPSG

from rich.console import Console

console = Console()


class TileInfo(NamedTuple):
    tile_id: str
    laz_filename: str
    download_url: str | None
    bbox_2229: dict
    bbox_4326: dict | None
    on_disk: bool
    file_size_mb: float | None
    boroughs: tuple[str, ...] = ()


# ── borough helpers ────────────────────────────────────────────────────────────

def _bbox_intersects(a: dict, b: dict) -> bool:
    return (
        a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"]
        and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]
    )


def _boroughs_for_bbox(bbox_4326: dict | None) -> tuple[str, ...]:
    if not bbox_4326:
        return ()
    return tuple(
        name for name, bb in BOROUGH_BBOXES_4326.items()
        if _bbox_intersects(bbox_4326, bb)
    )


def _src_bbox_to_4326(bbox_src: dict) -> dict | None:
    """Reproject a source-CRS (EPSG:SRC_EPSG) bbox dict to EPSG:4326."""
    try:
        import pyproj
        transformer = pyproj.Transformer.from_crs(SRC_EPSG, 4326, always_xy=True)
        minx = bbox_src["minx"]; miny = bbox_src["miny"]
        maxx = bbox_src["maxx"]; maxy = bbox_src["maxy"]
        xs, ys = [], []
        for cx, cy in [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]:
            lon, lat = transformer.transform(cx, cy)
            xs.append(lon); ys.append(lat)
        return {"xmin": min(xs), "ymin": min(ys), "xmax": max(xs), "ymax": max(ys)}
    except Exception:
        return None


# ── disk-first discovery ───────────────────────────────────────────────────────

def _tile_id_from_filename(filename: str) -> str:
    return Path(filename).name.replace(".copc.laz", "").replace(".laz", "")


def _discover_from_disk() -> list[TileInfo]:
    """Scan LAZ_DIR for all .laz files — no network required."""
    if not LAZ_DIR.exists():
        return []
    tiles = []
    for path in sorted(LAZ_DIR.glob("*.laz")):
        filename = path.name
        size_mb = path.stat().st_size / 1_048_576
        tiles.append(TileInfo(
            tile_id=_tile_id_from_filename(filename),
            laz_filename=filename,
            download_url=None,
            bbox_2229={},
            bbox_4326=None,
            on_disk=True,
            file_size_mb=size_mb,
        ))
    return tiles


def _enrich_from_catalog(tiles: list[TileInfo]) -> list[TileInfo]:
    """Add bbox + borough data from the NOAA catalog if it exists on disk."""
    if not CATALOG_PATH.exists():
        return tiles
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        by_name: dict[str, dict] = {
            (r.get("laz_filename") or r.get("filename")): r
            for r in data.get("tiles", [])
        }
    except Exception:
        return tiles

    enriched = []
    for t in tiles:
        rec = by_name.get(t.laz_filename)
        if not rec:
            enriched.append(t)
            continue
        bbox_src = rec.get("bbox_source")
        bbox_4326 = rec.get("bbox_4326")
        if bbox_src and not bbox_4326:
            bbox_4326 = _src_bbox_to_4326(bbox_src)
        boroughs = _boroughs_for_bbox(bbox_4326)
        enriched.append(TileInfo(
            tile_id=t.tile_id,
            laz_filename=t.laz_filename,
            download_url=rec.get("download_url"),
            bbox_2229=bbox_src or {},
            bbox_4326=bbox_4326,
            on_disk=t.on_disk,
            file_size_mb=t.file_size_mb,
            boroughs=boroughs,
        ))
    return enriched


# ── catalog fallback (no tiles on disk) ───────────────────────────────────────

def _to_tile_info(record: dict) -> TileInfo:
    filename = record.get("laz_filename") or record["filename"]
    path = LAZ_DIR / filename
    on_disk = path.exists()
    bbox_src = record.get("bbox_source")
    bbox_4326 = record.get("bbox_4326")
    if bbox_src and not bbox_4326:
        bbox_4326 = _src_bbox_to_4326(bbox_src)
    boroughs = _boroughs_for_bbox(bbox_4326)
    return TileInfo(
        tile_id=record.get("tile_id") or _tile_id_from_filename(filename),
        laz_filename=filename,
        download_url=record.get("download_url"),
        bbox_2229=bbox_src or {},
        bbox_4326=bbox_4326,
        on_disk=on_disk,
        file_size_mb=path.stat().st_size / 1_048_576 if on_disk else None,
        boroughs=boroughs,
    )


def _load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        return build_catalog(force=False)
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


# ── public API ─────────────────────────────────────────────────────────────────

def discover_tiles(
    city_id: str,
    use_api: bool = True,
    no_grid: bool = False,
    bbox_only: bool = False,
    limit: int | None = None,
) -> list[TileInfo]:
    if city_id not in CITIES:
        raise KeyError(city_id)
    cfg = CITIES[city_id]
    console.print(f"\n[bold cyan]Discovering NYC tiles for {cfg.display_name}...[/bold cyan]")

    # ── Primary: scan LAZ_DIR directly ────────────────────────────────────
    disk_tiles = _discover_from_disk()
    if disk_tiles:
        if limit is not None:
            disk_tiles = disk_tiles[:limit]
        tiles = _enrich_from_catalog(disk_tiles)
        tiles.sort(key=lambda t: t.tile_id)

        n_with_borough = sum(1 for t in tiles if t.boroughs)
        console.print(
            f"  [green]{len(tiles)} LAZ files on disk[/green]"
            + (f"  ({n_with_borough} with borough assignment)" if n_with_borough else
               "  [dim](run build_nyc_catalog.py to add borough assignment)[/dim]")
        )
        if n_with_borough:
            from collections import Counter
            counts: Counter = Counter(b for t in tiles for b in t.boroughs)
            for borough, n in sorted(counts.items()):
                console.print(f"    [dim]{borough}: ~{n} tile(s)[/dim]")
        return tiles

    # ── Fallback: build from NOAA catalog (network) ───────────────────────
    console.print("  [dim]No LAZ files on disk; loading catalog (may fetch from NOAA)...[/dim]")
    catalog = _load_catalog()
    records = catalog.get("tiles", [])
    if limit is not None:
        records = records[:limit]
    tiles = [_to_tile_info(r) for r in records]
    tiles.sort(key=lambda t: t.tile_id)
    console.print(
        f"  [yellow]{len(tiles)} catalog tiles[/yellow] "
        f"({sum(1 for t in tiles if t.on_disk)} on disk)"
    )
    return tiles


def write_tile_manifest(city_id: str, tiles: list[TileInfo]) -> Path:
    cfg = CITIES[city_id]
    n_on_disk = sum(1 for t in tiles if t.on_disk)
    total_gb_local = sum((t.file_size_mb or 0) for t in tiles) / 1024

    from collections import Counter
    borough_counts: dict = {}
    if any(t.boroughs for t in tiles):
        borough_counts = dict(Counter(b for t in tiles for b in t.boroughs))

    manifest = {
        "schema_version": "1.0",
        "pipeline": "GlitchOS.io NYC city pipeline",
        "city_id": city_id,
        "display_name": cfg.display_name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "discovery_source": "disk_scan",
        "laz_dir": str(LAZ_DIR),
        "summary": {
            "total_tiles": len(tiles),
            "on_disk": n_on_disk,
            "missing": len(tiles) - n_on_disk,
            "local_data_gb": round(total_gb_local, 2),
            "borough_tile_counts": borough_counts,
        },
        "tiles": [
            {
                "tile_id": t.tile_id,
                "laz_filename": t.laz_filename,
                "download_url": t.download_url,
                "bbox_source": t.bbox_2229,
                "bbox_4326": t.bbox_4326,
                "boroughs": list(t.boroughs),
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
    city_id = "new_york_city"
    use_api = "--no-api" not in args
    no_grid = "--no-grid" in args
    bbox_only = "--bbox-only" in args
    as_json = "--json" in args
    limit = None
    for i, arg in enumerate(args):
        if arg == "--city" and i + 1 < len(args):
            city_id = args[i + 1]
        elif arg == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                pass
    return city_id, use_api, no_grid, bbox_only, as_json, limit


def main():
    city_id, use_api, no_grid, bbox_only, as_json, limit = _parse_discovery_flags(sys.argv[1:])
    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        console.print(f"Valid: {CITY_ORDER}")
        return 1
    tiles = discover_tiles(city_id, use_api=use_api, no_grid=no_grid, bbox_only=bbox_only, limit=limit)
    path = write_tile_manifest(city_id, tiles)
    if as_json:
        print(json.dumps([t._asdict() for t in tiles], indent=2, default=str))
    else:
        console.print(f"\nDiscovered {len(tiles)} tiles -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
