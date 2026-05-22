"""
run_tile.py  [LA block/sector pipeline — GlitchOS.io]

Run the full pipeline for one or more tiles, with rich progress bars.

Usage:
    python run_tile.py 1836b                          # one tile
    python run_tile.py 1836a 1836c                    # two tiles
    python run_tile.py --all                          # all four 1836 tiles
    python run_tile.py 1836b --stages 00 01 02        # specific stages only
    python run_tile.py 1836b --output-root /path/to   # sector pipeline override

Stages:
    00  compute extent + Blender shift
    01  clip footprints to tile bbox
    02  extract ground point cloud
    03  CRS validation gate (must pass before 04)
    04  footprint-driven building masses
    05  write tile manifest

--output-root: overrides the default /mnt/t7/la/data_processed/tiles/<tile_id>/
               Used by run_sector.py to write to sectors/<sector_id>/tiles/<tile_id>/
               without touching the existing tiles/ tree.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "stages"))

from tile_config import TILES, TILE_ORDER, TileConfig
from stages import s00_extent, s01_footprints, s02_pointcloud, s03_validate, s04_masses, s05_manifest

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, MofNCompleteColumn,
)
from rich.panel import Panel
from rich import box

console = Console()

ALL_STAGES = ["00", "01", "02", "03", "04", "05"]

STAGE_FNS = {
    "00": ("extent",     s00_extent.run),
    "01": ("footprints", s01_footprints.run),
    "02": ("pointcloud", s02_pointcloud.run),
    "03": ("validate",   s03_validate.run),
    "04": ("masses",     s04_masses.run),
}

STAGE_LABELS = {
    "00": "Compute extent + shift",
    "01": "Clip footprints",
    "02": "Extract ground PC",
    "03": "CRS validation gate",
    "04": "Building masses",
    "05": "Write manifest",
}


def run_tile(tile: TileConfig, stages: list[str], progress=None, tile_task=None) -> dict:
    """
    Run requested stages for one tile. Returns stage_results dict.
    Never raises — exceptions are caught and stored in results["errors"].
    """
    stage_results: dict = {"errors": {}}
    tile.ensure_dirs()

    runnable = [s for s in stages if s in STAGE_FNS]

    for stage_id in stages:
        if stage_id == "05":
            continue
        if stage_id not in STAGE_FNS:
            continue

        label, fn = STAGE_FNS[stage_id]

        if progress and tile_task is not None:
            progress.update(tile_task, description=f"  [cyan]{tile.tile_id}[/cyan] → {label}")

        t0 = time.time()
        try:
            result = fn(tile)
            stage_results[f"s{stage_id}"] = result
            elapsed = time.time() - t0
            console.print(f"    [dim]s{stage_id} {label}: done in {elapsed:.1f}s[/dim]")
        except Exception as e:
            msg = str(e)
            stage_results["errors"][f"s{stage_id}"] = msg
            console.print(f"    [red]s{stage_id} FAILED: {msg}[/red]")
            if stage_id == "03":
                console.print(f"    [yellow]Skipping stages 04+ — CRS validation failed.[/yellow]")
                break

        if progress and tile_task is not None:
            progress.advance(tile_task)

    if "05" in stages:
        try:
            s05_manifest.write_tile_manifest(tile, stage_results)
            if progress and tile_task is not None:
                progress.advance(tile_task)
        except Exception as e:
            console.print(f"    [yellow]WARN: manifest write failed: {e}[/yellow]")

    return stage_results


def _parse_args(argv: list[str]) -> tuple[list[str], list[str], Path | None]:
    """Returns (tile_ids, stages, output_root)."""
    tile_ids    = []
    stages      = list(ALL_STAGES)
    output_root = None
    run_all     = False

    # Import SECTOR_TILES so --output-root works for sector tiles too
    try:
        from sector_config import SECTOR_TILES
        known_tiles = {**TILES, **SECTOR_TILES}
    except ImportError:
        known_tiles = TILES

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--all":
            run_all = True
        elif arg == "--stages":
            stages = []
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                stages.append(argv[i])
                i += 1
            continue
        elif arg == "--output-root":
            i += 1
            if i < len(argv):
                output_root = Path(argv[i])
        elif arg.startswith("--"):
            console.print(f"[red]Unknown flag: {arg}[/red]")
            sys.exit(1)
        elif arg in known_tiles:
            tile_ids.append(arg)
        else:
            console.print(f"[red]Unknown tile ID: {arg!r}[/red]")
            console.print(f"Valid: {TILE_ORDER}")
            sys.exit(1)
        i += 1

    if run_all:
        tile_ids = TILE_ORDER[:]
    if not tile_ids:
        console.print("Usage: python run_tile.py <tile_id> [--all] [--stages 00 01 ...] [--output-root /path]")
        console.print(f"Valid tiles: {TILE_ORDER}")
        sys.exit(1)

    return tile_ids, stages, output_root


def main():
    tile_ids, stages, output_root = _parse_args(sys.argv[1:])

    # Resolve tile configs (SECTOR_TILES takes precedence when output-root given)
    try:
        from sector_config import SECTOR_TILES
        known_tiles = {**TILES, **SECTOR_TILES}
    except ImportError:
        known_tiles = TILES

    # Apply output_root override if supplied
    tile_configs = []
    for tid in tile_ids:
        base = known_tiles.get(tid)
        if base is None:
            console.print(f"[red]Unknown tile {tid!r}[/red]")
            sys.exit(1)
        if output_root is not None:
            from dataclasses import replace
            base = TileConfig(
                tile_id=base.tile_id,
                laz_filename=base.laz_filename,
                x_range=base.x_range,
                y_range=base.y_range,
                output_root=output_root,
            )
        tile_configs.append(base)

    # Pre-flight
    missing = [tc for tc in tile_configs if not tc.laz_path.exists()]
    if missing:
        for tc in missing:
            console.print(f"[red]LAZ not found: {tc.laz_path}[/red]")
        sys.exit(1)

    n_active = len([s for s in stages if s in STAGE_FNS])
    overall_t0 = time.time()
    any_failed = False

    console.print(Panel(
        f"[bold magenta]GlitchOS.io[/bold magenta] — LA pipeline\n"
        f"Tiles: [cyan]{' '.join(tile_ids)}[/cyan]   Stages: [white]{' '.join(stages)}[/white]",
        box=box.ROUNDED,
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=28),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        overall_task = progress.add_task(
            "[magenta]overall", total=len(tile_configs)
        )

        for tc in tile_configs:
            tile_task = progress.add_task(
                f"  [cyan]{tc.tile_id}[/cyan]",
                total=n_active + (1 if "05" in stages else 0),
            )
            tile_t0 = time.time()
            results = run_tile(tc, stages, progress=progress, tile_task=tile_task)
            elapsed = time.time() - tile_t0

            ok = not results["errors"]
            progress.update(
                tile_task,
                description=(
                    f"  [cyan]{tc.tile_id}[/cyan] "
                    f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/] "
                    f"({elapsed/60:.1f} min)"
                ),
            )
            progress.advance(overall_task)

            if not ok:
                any_failed = True
                for k, v in results["errors"].items():
                    console.print(f"  [red]  {k}: {v}[/red]")

    total = time.time() - overall_t0
    status_str = "[red]SOME FAILURES[/red]" if any_failed else "[green]ALL OK[/green]"
    console.print(f"\nTotal: {total/60:.1f} min  {status_str}")

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
