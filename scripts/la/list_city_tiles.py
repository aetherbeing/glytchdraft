"""
list_city_tiles.py  [LA city pipeline — GlitchOS.io]

Show all 3DEP tiles required to process a city boundary, their local
LAZ availability, estimated download size, and output paths.

Usage:
    python scripts/la/list_city_tiles.py --city los_angeles
    python scripts/la/list_city_tiles.py --city los_angeles --no-api      # grid only
    python scripts/la/list_city_tiles.py --city los_angeles --no-grid     # API only
    python scripts/la/list_city_tiles.py --city los_angeles --bbox-only   # skip shapely
    python scripts/la/list_city_tiles.py --city los_angeles --limit 20    # cap for testing
    python scripts/la/list_city_tiles.py --city los_angeles --refresh     # re-discover
    python scripts/la/list_city_tiles.py --city los_angeles --json        # machine-readable
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER
from tile_discovery import (
    discover_tiles, write_tile_manifest, TileInfo, _parse_discovery_flags,
)

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def _load_cached_manifest(city_id: str) -> list[TileInfo] | None:
    cfg = CITIES[city_id]
    if not cfg.tile_manifest.exists():
        return None
    try:
        data = json.loads(cfg.tile_manifest.read_text(encoding="utf-8"))
        return [
            TileInfo(
                tile_id=t["tile_id"],
                laz_filename=t["laz_filename"],
                download_url=t.get("download_url"),
                bbox_2229=t.get("bbox_2229") or {},
                bbox_4326=t.get("bbox_4326"),
                on_disk=t["on_disk"],
                file_size_mb=t.get("file_size_mb"),
            )
            for t in data.get("tiles", [])
        ]
    except Exception:
        return None


def _print_tile_table(tiles: list[TileInfo], city_id: str):
    cfg = CITIES[city_id]

    n_on_disk = sum(1 for t in tiles if t.on_disk)
    n_missing = len(tiles) - n_on_disk
    local_gb  = sum((t.file_size_mb or 0) for t in tiles if t.on_disk) / 1024
    dl_gb_est = (n_missing * 300) / 1024

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — City Tile Registry[/bold magenta]\n"
        f"City: [cyan]{cfg.display_name}[/cyan]   "
        f"Tiles: [white]{len(tiles)}[/white]   "
        f"On disk: [green]{n_on_disk}[/green]   "
        f"Missing: {'[red]' if n_missing else '[dim]'}{n_missing}{'[/red]' if n_missing else '[/dim]'}   "
        f"Local: [white]{local_gb:.1f} GB[/white]   "
        f"Est. download: [yellow]{dl_gb_est:.1f} GB[/yellow]",
        box=box.ROUNDED,
    ))

    tbl = Table(
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
        title=f"[bold]{cfg.display_name} — 3DEP Tile Manifest[/bold]",
    )
    tbl.add_column("Tile ID",   style="white", min_width=18)
    tbl.add_column("LAZ File",  style="dim",   min_width=52)
    tbl.add_column("On Disk",   justify="center", min_width=14)
    tbl.add_column("Size",      justify="right",  min_width=8)
    tbl.add_column("Source",    style="dim",   min_width=8)

    for t in tiles:
        disk_str = "[green]✓[/green]" if t.on_disk else "[red]✗ missing[/red]"
        size_str = f"{t.file_size_mb:.0f} MB" if t.file_size_mb else "—"
        src_str  = "API" if t.download_url else "grid"
        tbl.add_row(t.tile_id, t.laz_filename, disk_str, size_str, src_str)

    console.print(tbl)
    console.print()

    if n_missing == 0:
        console.print(f"[bold green]✓ All {len(tiles)} LAZ tiles present on disk.[/bold green]")
        console.print(
            f"\nReady to execute:\n"
            f"  [cyan]python scripts/la/run_city.py {city_id} --execute[/cyan]"
        )
    else:
        console.print(
            f"[yellow]{n_missing} LAZ tile(s) missing — "
            f"estimated {dl_gb_est:.1f} GB to download.[/yellow]"
        )
        console.print(
            f"\nTo download missing tiles, use the USGS TNM downloader or\n"
            f"  usgs-lidar-fetch --project CA_LosAngeles_2016 \\\n"
            f"    --output {cfg.output_root.parent.parent / 'data_raw' / 'laz'}"
        )

    console.print()
    console.print("[dim]Commands[/dim]")
    console.print(
        f"  [cyan]python scripts/la/list_city_tiles.py --city {city_id} --refresh[/cyan]"
        "   — re-run tile discovery"
    )
    console.print(
        f"  [cyan]python scripts/la/run_city.py {city_id} --dry-run[/cyan]"
        "   — preview pipeline run"
    )


def main():
    args    = sys.argv[1:]
    refresh = "--refresh" in args

    city_id, use_api, no_grid, bbox_only, as_json, limit = _parse_discovery_flags(args)

    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        console.print(f"Valid: {CITY_ORDER}")
        return 1

    # Use cached manifest unless --refresh (or --limit, which implies a test run)
    tiles = None
    if not refresh and limit is None:
        tiles = _load_cached_manifest(city_id)
        if tiles:
            cfg = CITIES[city_id]
            console.print(
                f"[dim]Using cached manifest ({len(tiles)} tiles): {cfg.tile_manifest}[/dim]"
            )
            console.print("[dim]Pass --refresh to re-run discovery.[/dim]")

    if tiles is None:
        tiles = discover_tiles(
            city_id, use_api=use_api, no_grid=no_grid,
            bbox_only=bbox_only, limit=limit,
        )
        write_tile_manifest(city_id, tiles)

    if as_json:
        print(json.dumps([t._asdict() for t in tiles], indent=2, default=str))
        return 0

    _print_tile_table(tiles, city_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
