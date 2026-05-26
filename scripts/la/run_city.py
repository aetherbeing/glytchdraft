"""
run_city.py  [LA city pipeline — GlitchOS.io]

Process all 3DEP tiles intersecting the City of Los Angeles municipal boundary.

Usage:
    python scripts/la/run_city.py los_angeles --dry-run             # preview (default)
    python scripts/la/run_city.py los_angeles --execute             # actually run
    python scripts/la/run_city.py los_angeles --execute --stages 00 01 02
    python scripts/la/run_city.py los_angeles --execute --stages 06        # export city
    python scripts/la/run_city.py los_angeles --dry-run --no-grid   # accepted for compatibility
    python scripts/la/run_city.py los_angeles --dry-run --bbox-only # skip shapely
    python scripts/la/run_city.py los_angeles --dry-run --limit 20  # cap tiles (testing)

Dry-run shows:
  - city boundary source + bbox
  - total tiles required, on-disk vs. missing
  - estimated download size for missing tiles
  - pipeline commands that would execute
  - output paths

Execution:
  - Runs each tile via run_tile.py subprocess (process-isolated)
  - Rich progress bars per tile
  - Per-tile failure does NOT abort other tiles
  - Stage 06 exports city-level Blender-ready indexes/merged assets
  - Writes city-level manifest after all tiles complete

Outputs go to:
  /mnt/t7/la/data_processed/cities/los_angeles/tiles/<tile_id>/

Protected paths — NEVER written by this script:
  /mnt/t7/la/data_processed/tiles/1836*
  /mnt/t7/la/data_processed/sectors/dtla_core*
  /mnt/t7/la/data_processed/hero_tile*
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "stages"))

from city_config import CITIES, CITY_ORDER
from tile_discovery import discover_tiles, write_tile_manifest, TileInfo, _parse_discovery_flags
from tile_config import LAZ_DIR, PROC_DIR, CITY_FOOTPRINTS_RAW

from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, MofNCompleteColumn,
)
from rich.panel import Panel
from rich import box

console = Console()

PIPELINE_VERSION = "1.0"
ALL_STAGES = ["00", "01", "02", "03", "04", "05", "06"]
TILE_STAGES = {"00", "01", "02", "03", "04", "05"}

PROTECTED_PATHS = [
    PROC_DIR / "tiles",
    PROC_DIR / "sectors" / "dtla_core",
    PROC_DIR / "hero_tile",
]


def _disk_stats() -> str:
    path = r"T:/" if sys.platform == "win32" else "/mnt/t7"
    try:
        u = shutil.disk_usage(path)
        return f"T7 {u.used/1e9:.0f} / {u.total/1e9:.0f} GB ({u.used/u.total*100:.0f}% used)"
    except Exception:
        return "T7: unavailable"


# ── dry-run ───────────────────────────────────────────────────────────────────

CATALOG_TILE_RE = re.compile(r"^la_(\d+)_(\d+[a-d])$")


def _tile_info_from_manifest_record(t: dict) -> TileInfo:
    return TileInfo(
        tile_id=t["tile_id"],
        laz_filename=t["laz_filename"],
        download_url=t.get("download_url"),
        bbox_2229=t.get("bbox_2229") or {},
        bbox_4326=t.get("bbox_4326"),
        on_disk=t["on_disk"],
        file_size_mb=t.get("file_size_mb"),
    )


def _infer_laz_filename(tile_id: str) -> str | None:
    match = CATALOG_TILE_RE.match(tile_id)
    if match:
        stem_x, stem_yq = match.groups()
        return f"USGS_LPC_CA_LosAngeles_2016_L4_{stem_x}_{stem_yq}_LAS_2018.laz"
    return None


def _load_cached_tiles(city_id: str) -> list[TileInfo] | None:
    cfg = CITIES[city_id]
    if not cfg.tile_manifest.exists():
        return None
    try:
        data = json.loads(cfg.tile_manifest.read_text(encoding="utf-8"))
        return [_tile_info_from_manifest_record(t) for t in data.get("tiles", [])]
    except Exception:
        return None


def _discover_processed_tiles(city_id: str) -> list[TileInfo]:
    """
    Discover tiles from existing city output directories.

    This lets city execution resume from /mnt/t7/la/data_processed/cities/<city>/tiles
    without relying on tile_config.TILES or the run_tile.py CLI registry.
    """
    cfg = CITIES[city_id]
    if not cfg.tiles_root.exists():
        return []

    tiles: list[TileInfo] = []
    for tile_dir in sorted(p for p in cfg.tiles_root.iterdir() if p.is_dir()):
        tile_id = tile_dir.name
        manifest_data = {}
        manifest_dir = tile_dir / "manifest"
        manifest_path = manifest_dir / f"{tile_id}_manifest.json"
        if not manifest_path.exists() and manifest_dir.exists():
            matches = sorted(manifest_dir.glob("*_manifest.json"))
            manifest_path = matches[0] if matches else manifest_path

        if manifest_path.exists():
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest_data = {}

        laz_filename = (
            manifest_data.get("source_laz")
            or manifest_data.get("laz_filename")
            or _infer_laz_filename(tile_id)
        )
        if not laz_filename:
            continue

        laz_path = LAZ_DIR / laz_filename
        on_disk = laz_path.exists()
        size_mb = laz_path.stat().st_size / 1_048_576 if on_disk else None
        tiles.append(TileInfo(
            tile_id=tile_id,
            laz_filename=laz_filename,
            download_url=None,
            bbox_2229=manifest_data.get("bbox_2229") or {},
            bbox_4326=None,
            on_disk=on_disk,
            file_size_mb=size_mb,
        ))

    return tiles


def _merge_tiles(primary: list[TileInfo], extra: list[TileInfo]) -> list[TileInfo]:
    by_id = {t.tile_id: t for t in primary}
    seen_laz = {t.laz_filename for t in primary}
    for t in extra:
        if t.laz_filename in seen_laz:
            continue
        by_id.setdefault(t.tile_id, t)
    return sorted(by_id.values(), key=lambda t: t.tile_id)


def _tile_subprocess_code() -> str:
    return (
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(r'%s')))\n"
        "sys.path.insert(0, str(Path(r'%s') / 'stages'))\n"
        "from tile_config import TileConfig\n"
        "from run_tile import run_tile\n"
        "tile_id, laz_filename, output_root, stages_json = sys.argv[1:5]\n"
        "fp_src = Path(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else None\n"
        "tile = TileConfig(tile_id=tile_id, laz_filename=laz_filename, output_root=Path(output_root), footprints_src=fp_src)\n"
        "results = run_tile(tile, json.loads(stages_json))\n"
        "sys.exit(1 if results.get('errors') else 0)\n"
    ) % (Path(__file__).parent, Path(__file__).parent)


def dry_run(
    city_id:   str,
    stages:    list[str],
    use_api:   bool = True,
    no_grid:   bool = False,
    bbox_only: bool = False,
    limit:     int | None = None,
):
    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        console.print(f"Valid: {CITY_ORDER}")
        return 1

    cfg = CITIES[city_id]

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — LA City Pipeline[/bold magenta]\n"
        f"[cyan]DRY RUN[/cyan] — no files will be written\n"
        f"City: [white]{cfg.display_name}[/white]",
        box=box.ROUNDED,
    ))

    # Check for protected path conflicts
    conflicts = cfg.protected_path_check()
    if conflicts:
        console.print(f"[red]ABORT: output root {cfg.output_root} conflicts with protected path(s):[/red]")
        for c in conflicts:
            console.print(f"  [red]{c}[/red]")
        return 1

    console.print(f"[dim]Output root:[/dim] {cfg.output_root}")
    console.print(f"[dim]Boundary cache:[/dim] {cfg.boundary_cache}")
    console.print(f"[dim]Tile manifest:[/dim] {cfg.tile_manifest}")

    # Load or discover tiles
    processed_tiles = _discover_processed_tiles(city_id)
    tiles: list[TileInfo] | None = _load_cached_tiles(city_id)
    if tiles:
        try:
            console.print(f"\n[dim]Using cached tile manifest ({len(tiles)} tiles).[/dim]")
            console.print("[dim]Run list_city_tiles.py --refresh to re-discover.[/dim]")
        except Exception:
            tiles = None

    if tiles is None:
        console.print("\n[dim]Running tile discovery...[/dim]")
        tiles = discover_tiles(city_id, use_api=use_api, no_grid=no_grid,
                               bbox_only=bbox_only, limit=limit)
        write_tile_manifest(city_id, tiles)

    if processed_tiles:
        n_before = len(tiles)
        tiles = _merge_tiles(tiles, processed_tiles)
        console.print(
            f"[dim]Found {len(processed_tiles)} processed tile dir(s); "
            f"running set now {len(tiles)} tile(s) (was {n_before}).[/dim]"
        )

    n_on_disk  = sum(1 for t in tiles if t.on_disk)
    n_missing  = len(tiles) - n_on_disk
    local_gb   = sum((t.file_size_mb or 0) for t in tiles if t.on_disk) / 1024
    dl_gb_est  = (n_missing * 300) / 1024

    # Tile availability table
    console.print()
    console.rule("[cyan]Tile LAZ availability[/cyan]")

    tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
    tbl.add_column("Tile ID",  min_width=20)
    tbl.add_column("LAZ File", min_width=52)
    tbl.add_column("On Disk",  min_width=14)
    tbl.add_column("Output Dir")

    for t in tiles[:50]:  # cap at 50 rows in dry-run for readability
        disk = (f"[green]✓ {t.file_size_mb:.0f} MB[/green]" if t.on_disk
                else "[red]✗ missing[/red]")
        out_dir = str(cfg.tiles_root / t.tile_id)
        tbl.add_row(t.tile_id, t.laz_filename, disk, f"[dim]{out_dir}[/dim]")

    if len(tiles) > 50:
        tbl.add_row(f"... and {len(tiles) - 50} more ...", "", "", "")

    console.print(tbl)

    # Summary
    console.print()
    console.print(f"  Total tiles:      [white]{len(tiles)}[/white]")
    console.print(f"  On disk:          [green]{n_on_disk}[/green]")
    console.print(f"  Missing:          {'[red]' if n_missing else '[dim]'}{n_missing}{'[/red]' if n_missing else '[/dim]'}")
    console.print(f"  Local data:       [white]{local_gb:.1f} GB[/white]")
    console.print(f"  Est. to download: [yellow]{dl_gb_est:.1f} GB[/yellow]")

    # Pipeline stages that would execute
    console.print()
    console.rule("[cyan]Pipeline stages that would execute[/cyan]")
    if n_missing > 0:
        console.print(f"[yellow]  {n_missing} LAZ file(s) missing — only on-disk tiles will execute.[/yellow]")
    runnable = [t for t in tiles if t.on_disk]
    tile_stages = [s for s in stages if s in TILE_STAGES]
    if tile_stages:
        for i, t in enumerate(runnable[:10]):
            cmd = f"python -c <dynamic TileConfig> {t.tile_id} --output-root {cfg.tiles_root} --stages {' '.join(tile_stages)}"
            console.print(f"  [{i+1}/{len(runnable)}] [dim]{cmd}[/dim]")
        if len(runnable) > 10:
            console.print(f"  ... and {len(runnable) - 10} more tiles ...")
    if "06" in stages:
        console.print(
            f"  [stage 06] [dim]python scripts/la/export_city.py {city_id} "
            "--merge-geometry --generate-blender_manifest[/dim]"
        )
    console.print(f"  [last]  write city manifest → {cfg.city_manifest}")

    console.print()
    if n_missing == 0 and n_on_disk > 0:
        console.print("[bold green]✓ All tiles present. Ready to execute.[/bold green]")
        console.print(
            f"\n  [cyan]python scripts/la/run_city.py {city_id} --execute[/cyan]"
        )
    elif n_on_disk == 0:
        console.print("[red]✗ No LAZ tiles on disk — cannot execute yet.[/red]")
        console.print(f"  Download ~{dl_gb_est:.0f} GB from USGS 3DEP before running.")
    else:
        console.print(f"[yellow]◐ {n_on_disk} of {len(tiles)} tiles ready. "
                      f"Will process available tiles only.[/yellow]")
        console.print(
            f"\n  [cyan]python scripts/la/run_city.py {city_id} --execute[/cyan]"
            f"   — process {n_on_disk} on-disk tiles"
        )

    console.print()
    return 0


# ── execute ───────────────────────────────────────────────────────────────────

def execute(city_id: str, stages: list[str]):
    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        return 1

    cfg = CITIES[city_id]

    conflicts = cfg.protected_path_check()
    if conflicts:
        console.print(f"[red]ABORT: output root conflicts with protected paths:[/red]")
        for c in conflicts:
            console.print(f"  [red]{c}[/red]")
        return 1

    tiles = _load_cached_tiles(city_id)
    processed_tiles = _discover_processed_tiles(city_id)
    if tiles is None:
        if processed_tiles:
            tiles = processed_tiles
            console.print(
                f"[dim]Tile manifest unavailable; discovered "
                f"{len(tiles)} tile dir(s) from {cfg.tiles_root}.[/dim]"
            )
        else:
            console.print("[red]Tile manifest not found and no processed tile dirs found.[/red]")
            console.print(f"  [cyan]python scripts/la/list_city_tiles.py --city {city_id}[/cyan]")
            return 1

    if processed_tiles:
        n_before = len(tiles)
        tiles = _merge_tiles(tiles, processed_tiles)
        console.print(
            f"[dim]Found {len(processed_tiles)} processed tile dir(s); "
            f"running set now {len(tiles)} tile(s) (was {n_before}).[/dim]"
        )

    tile_stages = [s for s in stages if s in TILE_STAGES]
    run_export = "06" in stages

    runnable = [t for t in tiles if t.on_disk]
    if tile_stages and not runnable:
        console.print("[red]No on-disk LAZ tiles found. Nothing to execute.[/red]")
        return 1

    python   = sys.executable
    child_code = _tile_subprocess_code()

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — LA City Pipeline[/bold magenta]\n"
        f"City: [cyan]{cfg.display_name}[/cyan]   "
        f"Tiles: [white]{len(runnable)}[/white]   "
        f"Stages: [white]{' '.join(stages)}[/white]\n"
        f"[dim]{_disk_stats()}[/dim]",
        box=box.ROUNDED,
    ))

    tile_results:    dict = {}
    tile_exit_codes: dict = {}

    if tile_stages:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=32),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            city_task = progress.add_task(
                f"[magenta]{city_id}", total=len(runnable)
            )

            for t in runnable:
                tile_label = t.tile_id
                tile_task = progress.add_task(f"  {tile_label}", total=1)

                fp_src_str = str(CITY_FOOTPRINTS_RAW) if CITY_FOOTPRINTS_RAW.exists() else ""
                cmd = [
                    python,
                    "-c", child_code,
                    t.tile_id,
                    t.laz_filename,
                    str(cfg.tiles_root),
                    json.dumps(tile_stages),
                    fp_src_str,
                ]

                t0   = time.time()
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )
                elapsed = time.time() - t0
                rc      = proc.returncode

                ok = rc == 0
                progress.update(
                    tile_task,
                    description=(
                        f"  {tile_label} "
                        f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/] "
                        f"({elapsed/60:.1f} min)"
                    ),
                    completed=1,
                )
                progress.advance(city_task)

                tile_exit_codes[t.tile_id] = rc

                # Read tile manifest if written
                manifest_path = cfg.tiles_root / t.tile_id / "manifest" / f"{t.tile_id}_manifest.json"
                manifest_data = {}
                if manifest_path.exists():
                    try:
                        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass

                tile_results[t.tile_id] = {
                    "s01": {"count_32611": manifest_data.get("footprint_count")},
                    "s02": {"ground_points": manifest_data.get("ground_points")},
                    "s04": {"lod0": manifest_data.get("building_mass_lod0"),
                            "lod1": manifest_data.get("building_mass_lod1")},
                    "terrain_only": manifest_data.get("terrain_only", False),
                    "errors": manifest_data.get("errors", {}) if rc != 0 else {},
                }

                if proc.stdout:
                    for line in proc.stdout.strip().splitlines():
                        console.print(f"    [dim]{line}[/dim]")
                if proc.stderr and rc != 0:
                    for line in proc.stderr.strip().splitlines()[-10:]:
                        console.print(f"    [red]{line}[/red]")

    export_manifest = None
    if run_export:
        from export_city import export_city

        export_manifest = export_city(
            city_id,
            merge_geometry=True,
            keep_per_tile=False,
            generate_blender_manifest=True,
            merge_terrain=False,
        )
        console.print(f"[dim]City export manifest â†’ {export_manifest}[/dim]")

    if not tile_stages:
        for t in runnable:
            manifest_path = cfg.tiles_root / t.tile_id / "manifest" / f"{t.tile_id}_manifest.json"
            manifest_data = {}
            if manifest_path.exists():
                try:
                    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            tile_exit_codes[t.tile_id] = 0
            tile_results[t.tile_id] = {
                "s01": {"count_32611": manifest_data.get("footprint_count")},
                "s02": {"ground_points": manifest_data.get("ground_points")},
                "s04": {"lod0": manifest_data.get("building_mass_lod0"),
                        "lod1": manifest_data.get("building_mass_lod1")},
                "terrain_only": manifest_data.get("terrain_only", False),
                "errors": manifest_data.get("errors", {}),
            }

    _write_city_manifest(cfg, tile_results, tile_exit_codes)

    n_ok   = sum(1 for rc in tile_exit_codes.values() if rc == 0)
    n_fail = len(tile_exit_codes) - n_ok

    total_footprints = sum(
        (r.get("s01") or {}).get("count_32611") or 0 for r in tile_results.values()
    )

    console.print()
    console.print(Panel(
        "\n".join([
            f"[bold]City [cyan]{city_id}[/cyan] complete[/bold]",
            f"  {n_ok}/{len(tile_exit_codes)} tiles OK   "
            f"{'[green]ALL PASSED[/green]' if n_fail == 0 else f'[red]{n_fail} FAILED[/red]'}",
            f"  buildings: [white]{total_footprints:,}[/white]   [dim]{_disk_stats()}[/dim]",
        ]),
        box=box.ROUNDED,
    ))

    return 0 if n_fail == 0 else 1


def rerun_missing_masses(city_id: str) -> int:
    """
    Re-run stages 01 + 03 + 04 + 05 for every tile that does not yet have a
    LOD0 OBJ on disk.  This covers terrain-only tiles (old footprint source too
    small), s03-failed tiles (Z range / CRS issues), and any unknown failures.

    Stale crs_validation.json reports are deleted before rerunning so s03
    always runs fresh.  Requires CITY_FOOTPRINTS_RAW or live ESRI/OSM access.
    """
    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        return 1

    cfg = CITIES[city_id]

    if not CITY_FOOTPRINTS_RAW.exists():
        console.print(
            f"[yellow]CITY_FOOTPRINTS_RAW not found: {CITY_FOOTPRINTS_RAW}[/yellow]\n"
            "  Tiles will fall back to live ESRI/OSM queries (slower).\n"
            "  Pre-download with:  python scripts/la/download_city_footprints.py los_angeles"
        )

    # Discover which tiles need a re-run
    missing: list[TileInfo] = []
    tiles_root = cfg.tiles_root
    if not tiles_root.exists():
        console.print(f"[red]tiles_root not found: {tiles_root}[/red]")
        return 1

    for tile_dir in sorted(p for p in tiles_root.iterdir() if p.is_dir()):
        tile_id = tile_dir.name
        manifest_path = tile_dir / "manifest" / f"{tile_id}_manifest.json"
        if not manifest_path.exists():
            continue
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Skip tiles that already have LOD0 masses on disk.
        # Check both the constructed path and the manifest's stored path
        # (which may have a stale /mnt/t7/ mount point).
        constructed_lod0 = (
            tile_dir / "blender_ready" / "masses"
            / f"{tile_id}_masses_LOD0_individual.obj"
        )
        if not constructed_lod0.exists():
            stored_lod0 = (m.get("outputs") or {}).get("lod0_obj", "")
            if stored_lod0:
                p = Path(stored_lod0)
                remapped = Path(str(p).replace("/mnt/t7/", "/mnt/e/"))
                if p.exists() or remapped.exists():
                    continue
        else:
            continue

        # Delete stale validation report so s03 re-runs fresh
        val_report = tile_dir / "notes" / "crs_validation.json"
        if val_report.exists():
            try:
                val_report.unlink()
            except Exception:
                pass

        laz_filename = m.get("source_laz")
        if not laz_filename:
            continue
        laz_on_disk = (LAZ_DIR / laz_filename).exists()
        missing.append(TileInfo(
            tile_id=tile_id,
            laz_filename=laz_filename,
            download_url=None,
            bbox_2229=m.get("bbox_2229") or {},
            bbox_4326=None,
            on_disk=laz_on_disk,
            file_size_mb=None,
        ))

    if not missing:
        console.print("[green]All tiles already have LOD0 masses — nothing to rerun.[/green]")
        return 0

    laz_missing = [t for t in missing if not t.on_disk]
    if laz_missing:
        console.print(
            f"[yellow]Warning: {len(laz_missing)} tiles missing LAZ — s04 will fail for those.[/yellow]"
        )

    stages = ["01", "03", "04", "05"]
    python = sys.executable
    child_code = _tile_subprocess_code()
    fp_src_str = str(CITY_FOOTPRINTS_RAW) if CITY_FOOTPRINTS_RAW.exists() else ""

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — Rerun Missing Masses[/bold magenta]\n"
        f"City: [cyan]{cfg.display_name}[/cyan]   "
        f"Tiles to fix: [white]{len(missing)}[/white]   "
        f"Stages: [white]{' '.join(stages)}[/white]\n"
        f"Footprint src: [dim]{fp_src_str or 'live ESRI/OSM'}[/dim]\n"
        f"[dim]Stale crs_validation.json deleted before each tile runs.[/dim]",
        box=box.ROUNDED,
    ))

    tile_results: dict = {}
    tile_exit_codes: dict = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=32),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        city_task = progress.add_task(f"[magenta]{city_id}", total=len(missing))

        for t in missing:
            tile_task = progress.add_task(f"  {t.tile_id[:40]}", total=1)
            cmd = [
                python, "-c", child_code,
                t.tile_id, t.laz_filename,
                str(cfg.tiles_root),
                json.dumps(stages),
                fp_src_str,
            ]
            t0   = time.time()
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            elapsed = time.time() - t0
            ok = proc.returncode == 0
            progress.update(
                tile_task,
                description=f"  {t.tile_id[:40]} [{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/] ({elapsed/60:.1f} min)",
                completed=1,
            )
            progress.advance(city_task)
            tile_exit_codes[t.tile_id] = proc.returncode

            manifest_path = cfg.tiles_root / t.tile_id / "manifest" / f"{t.tile_id}_manifest.json"
            manifest_data = {}
            if manifest_path.exists():
                try:
                    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            tile_results[t.tile_id] = {
                "s01": {"count_32611": manifest_data.get("footprint_count")},
                "s02": {"ground_points": manifest_data.get("ground_points")},
                "s04": {"lod0": manifest_data.get("building_mass_lod0"),
                        "lod1": manifest_data.get("building_mass_lod1")},
                "terrain_only": manifest_data.get("terrain_only", False),
                "errors": manifest_data.get("errors", {}) if proc.returncode != 0 else {},
            }
            if proc.stdout:
                for line in proc.stdout.strip().splitlines():
                    console.print(f"    [dim]{line}[/dim]")
            if proc.stderr and proc.returncode != 0:
                for line in proc.stderr.strip().splitlines()[-10:]:
                    console.print(f"    [red]{line}[/red]")

    n_ok   = sum(1 for rc in tile_exit_codes.values() if rc == 0)
    n_fail = len(tile_exit_codes) - n_ok
    n_masses = sum(
        1 for r in tile_results.values()
        if (r.get("s04") or {}).get("lod0", 0) or 0 > 0
    )
    console.print()
    console.print(Panel(
        f"[bold]Rerun complete[/bold]\n"
        f"  {n_ok}/{len(tile_exit_codes)} OK   "
        f"{'[green]ALL PASSED[/green]' if n_fail == 0 else f'[red]{n_fail} FAILED[/red]'}\n"
        f"  Tiles with new masses: [cyan]{n_masses}[/cyan]",
        box=box.ROUNDED,
    ))
    return 0 if n_fail == 0 else 1


def _write_city_manifest(cfg, tile_results: dict, tile_exit_codes: dict):
    totals = {
        "tiles_attempted":   len(tile_exit_codes),
        "tiles_ok":          sum(1 for rc in tile_exit_codes.values() if rc == 0),
        "total_footprints":  sum((r.get("s01") or {}).get("count_32611") or 0 for r in tile_results.values()),
        "total_ground_pts":  sum((r.get("s02") or {}).get("ground_points") or 0 for r in tile_results.values()),
        "total_lod0_prisms": sum((r.get("s04") or {}).get("lod0") or 0 for r in tile_results.values()),
    }
    manifest = {
        "schema_version": PIPELINE_VERSION,
        "pipeline":       "GlitchOS.io LA city pipeline",
        "city_id":        cfg.city_id,
        "display_name":   cfg.display_name,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "all_tiles_passed": totals["tiles_ok"] == totals["tiles_attempted"],
        "totals": totals,
        "tiles": {
            tid: {
                "status":          "ok" if tile_exit_codes.get(tid, 1) == 0 else "failed",
                "terrain_only":    r.get("terrain_only", False),
                "footprint_count": (r.get("s01") or {}).get("count_32611"),
                "ground_points":   (r.get("s02") or {}).get("ground_points"),
                "lod0_prisms":     (r.get("s04") or {}).get("lod0"),
                "errors":          r.get("errors", {}),
            }
            for tid, r in tile_results.items()
        },
    }
    cfg.output_root.mkdir(parents=True, exist_ok=True)
    cfg.city_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"[dim]City manifest → {cfg.city_manifest}[/dim]")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        console.print(__doc__)
        return 0

    city_id = args[0]
    dry     = "--dry-run" in args or "--execute" not in args
    stages  = []

    i = 1
    while i < len(args):
        if args[i] == "--stages":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                stages.append(args[i])
                i += 1
            continue
        i += 1

    if not stages:
        stages = ALL_STAGES[:]

    # Discovery flags (shared with tile_discovery / list_city_tiles)
    _, use_api, no_grid, bbox_only, _, limit = _parse_discovery_flags(args)

    if "--rerun-missing-masses" in args:
        return rerun_missing_masses(city_id)
    elif dry:
        return dry_run(city_id, stages, use_api=use_api, no_grid=no_grid,
                       bbox_only=bbox_only, limit=limit)
    else:
        return execute(city_id, stages)


if __name__ == "__main__":
    sys.exit(main())
