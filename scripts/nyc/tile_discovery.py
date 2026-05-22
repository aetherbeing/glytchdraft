"""
tile_discovery.py  [NYC city pipeline - GlitchOS.io]

MVP discovery reads the real NOAA 9306 LAZ catalog and emits all real NYC
downloadable/local tiles. Borough geometry filtering will be added after the
city-wide manifest is stable.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

from build_nyc_catalog import CATALOG_PATH, build_catalog
from city_config import CITIES, CITY_ORDER
from tile_config import LAZ_DIR

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


def _load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        return build_catalog(force=False)
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _to_tile_info(record: dict) -> TileInfo:
    filename = record.get("laz_filename") or record["filename"]
    path = LAZ_DIR / filename
    on_disk = path.exists()
    return TileInfo(
        tile_id=record.get("tile_id") or Path(filename).stem,
        laz_filename=filename,
        download_url=record.get("download_url"),
        bbox_2229=record.get("bbox_source") or {},
        bbox_4326=record.get("bbox_4326"),
        on_disk=on_disk,
        file_size_mb=path.stat().st_size / 1_048_576 if on_disk else None,
    )


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
    catalog = _load_catalog()
    records = catalog.get("tiles", [])
    if limit is not None:
        records = records[:limit]
    tiles = [_to_tile_info(r) for r in records]
    tiles.sort(key=lambda t: t.tile_id)
    console.print(
        f"  [green]{len(tiles)} real NOAA LAZ tile(s)[/green] "
        f"({sum(1 for t in tiles if t.on_disk)} on disk)"
    )
    return tiles


def write_tile_manifest(city_id: str, tiles: list[TileInfo]) -> Path:
    cfg = CITIES[city_id]
    n_on_disk = sum(1 for t in tiles if t.on_disk)
    total_gb_local = sum((t.file_size_mb or 0) for t in tiles) / 1024
    manifest = {
        "schema_version": "1.0",
        "pipeline": "GlitchOS.io NYC city pipeline",
        "city_id": city_id,
        "display_name": cfg.display_name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "discovery_source": "noaa_9306_catalog",
        "catalog_path": str(CATALOG_PATH),
        "summary": {
            "total_tiles": len(tiles),
            "on_disk": n_on_disk,
            "missing": len(tiles) - n_on_disk,
            "local_data_gb": round(total_gb_local, 2),
        },
        "tiles": [
            {
                "tile_id": t.tile_id,
                "laz_filename": t.laz_filename,
                "download_url": t.download_url,
                "bbox_source": t.bbox_2229,
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
