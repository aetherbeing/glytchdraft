"""
run_sector.py  [LA sector pipeline — GlitchOS.io]

Process one named sector through the full pipeline.

Usage:
    python scripts/la/run_sector.py dtla_core --dry-run     # preview (default safe mode)
    python scripts/la/run_sector.py dtla_core --execute     # actually run
    python scripts/la/run_sector.py dtla_core --execute --stages 00 01

Dry-run shows:
  - sector config (tiles, bbox, output root)
  - per-tile LAZ availability
  - what commands would execute
  - estimated output paths

Execution:
  - Runs each tile via run_tile.py subprocess (process-isolated)
  - Rich progress bars per stage and per tile
  - Per-tile failure does NOT abort other tiles
  - Writes sector-level manifest after all tiles complete

Outputs go to:
  /mnt/t7/la/data_processed/sectors/<sector_id>/tiles/<tile_id>/

The following paths are NEVER written by this script:
  /mnt/t7/la/data_processed/tiles/1836*
  /mnt/t7/la/data_processed/hero_tile*
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "stages"))

from sector_config import SECTORS, SECTOR_ORDER, SECTOR_TILES, SECTORS_ROOT
from tile_config import LAZ_DIR
from stages import s05_manifest

from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, MofNCompleteColumn, TaskProgressColumn,
)
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

PIPELINE_VERSION = "1.1"

ALL_STAGES = ["00", "01", "02", "03", "04", "05"]

STATUS_ICON = {
    "ready":          "[green]●[/green]",
    "scaffold":       "[yellow]◐[/yellow]",
    "optional_later": "[dim]○[/dim]",
}


# ── dry-run display ────────────────────────────────────────────────────────────

def dry_run(sector_id: str, stages: list[str]):
    if sector_id not in SECTORS:
        console.print(f"[red]Unknown sector: {sector_id!r}[/red]")
        console.print(f"Valid sectors: {SECTOR_ORDER}")
        return 1

    s = SECTORS[sector_id]

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — LA Sector Pipeline[/bold magenta]\n"
        f"[cyan]DRY RUN[/cyan] — no files will be written",
        box=box.ROUNDED,
    ))

    # Sector summary
    tbl = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    tbl.add_column(style="dim", min_width=18)
    tbl.add_column(style="white")
    tbl.add_row("Sector ID",     s.sector_id)
    tbl.add_row("Name",          s.display_name)
    tbl.add_row("Status",        f"{STATUS_ICON[s.status]} {s.status}")
    tbl.add_row("Description",   s.description)
    tbl.add_row("Tiles",         str(len(s.tile_ids)))
    tbl.add_row("Output root",   str(s.output_root))
    tbl.add_row("Sector manifest", str(s.sector_manifest))
    tbl.add_row("Footprints src", str(s.footprints_raw))
    tbl.add_row("Stages",        " ".join(stages))
    bbox = s.bbox_4326
    if bbox:
        tbl.add_row("Bbox (4326)",
                    f"lon [{bbox['xmin']:.4f}, {bbox['xmax']:.4f}]  "
                    f"lat [{bbox['ymin']:.4f}, {bbox['ymax']:.4f}]")
    console.print(tbl)

    # Notes
    if s.notes:
        console.print(f"\n[yellow]Note:[/yellow] {s.notes}")

    # Per-tile availability
    console.print()
    console.rule("[cyan]Tile LAZ availability[/cyan]")
    tile_tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
    tile_tbl.add_column("Tile ID", min_width=18)
    tile_tbl.add_column("LAZ File", min_width=52)
    tile_tbl.add_column("On Disk", min_width=12)
    tile_tbl.add_column("Output Dir")

    all_laz_ok = True
    for tid in s.tile_ids:
        tc = SECTOR_TILES.get(tid)
        if not tc:
            tile_tbl.add_row(tid, "[red]not in SECTOR_TILES[/red]", "[red]✗[/red]", "—")
            all_laz_ok = False
            continue
        exists = tc.laz_path.exists()
        if exists:
            size_mb = tc.laz_path.stat().st_size / 1_048_576
            disk = f"[green]✓ {size_mb:.0f} MB[/green]"
        else:
            disk = "[red]✗ missing[/red]"
            all_laz_ok = False
        out_dir = str(s.tiles_root / tid)
        tile_tbl.add_row(tid, tc.laz_filename, disk, f"[dim]{out_dir}[/dim]")

    console.print(tile_tbl)

    # Runnable verdict
    console.print()
    if s.status == "ready" and all_laz_ok:
        console.print("[bold green]✓ Sector is ready to execute.[/bold green]")
        console.print(
            f"\n  [cyan]python scripts/la/run_sector.py {sector_id} --execute[/cyan]"
        )
        if stages != ALL_STAGES:
            console.print(
                f"  [cyan]python scripts/la/run_sector.py {sector_id} --execute "
                f"--stages {' '.join(stages)}[/cyan]"
            )
    elif s.status == "scaffold":
        console.print("[yellow]◐ Sector is a scaffold — LAZ files not yet downloaded.[/yellow]")
        console.print("\nTo prepare:")
        console.print("  1. Verify tile grid IDs via https://apps.nationalmap.gov/lidar-explorer/")
        console.print("  2. Download LAZ tiles to /mnt/t7/la/data_raw/laz/")
        console.print("  3. Update sector_config.py laz_filename entries if grid IDs differ")
        console.print("  4. Set status='ready' in sector_config.py")
        console.print(f"  5. python scripts/la/run_sector.py {sector_id} --dry-run  (verify again)")
    elif s.status == "optional_later":
        console.print("[dim]○ Sector is deferred — not planned for immediate processing.[/dim]")
    elif not all_laz_ok:
        console.print("[red]✗ Some LAZ files are missing — sector cannot run.[/red]")

    # What would execute
    if s.status == "ready":
        console.print()
        console.rule("[cyan]Pipeline stages that would execute[/cyan]")
        python = sys.executable
        for i, tid in enumerate(s.tile_ids):
            cmd = f"python run_tile.py {tid} --stages {' '.join(stages)}"
            console.print(f"  [{i+1}/{len(s.tile_ids)}] [dim]{cmd}[/dim]")
        console.print(f"  [last]  write sector manifest → {s.sector_manifest}")

    console.print()
    return 0


# ── execution (subprocess-isolated) ───────────────────────────────────────────

def execute(sector_id: str, stages: list[str]):
    if sector_id not in SECTORS:
        console.print(f"[red]Unknown sector: {sector_id!r}[/red]")
        return 1

    s = SECTORS[sector_id]

    if not s.is_runnable():
        console.print(f"[red]Sector {sector_id!r} is not runnable (status={s.status!r}, "
                      f"or LAZ files missing).[/red]")
        console.print("Run with --dry-run to see what's missing.")
        return 1

    # Safety check: confirm outputs won't touch protected paths
    protected = [
        Path("/mnt/t7/la/data_processed/tiles"),
        Path("/mnt/t7/la/data_processed/hero_tile"),
    ]
    for p in protected:
        if str(s.output_root).startswith(str(p)):
            console.print(f"[red]ABORT: output root {s.output_root} would write into "
                          f"protected path {p}[/red]")
            return 1

    tile_configs = s.get_tile_configs()
    python       = sys.executable
    run_tile     = str(Path(__file__).parent / "run_tile.py")

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — LA Sector Pipeline[/bold magenta]\n"
        f"Sector: [cyan]{sector_id}[/cyan]   Tiles: [white]{len(tile_configs)}[/white]   "
        f"Stages: [white]{' '.join(stages)}[/white]",
        box=box.ROUNDED,
    ))

    tile_results  = {}
    tile_exit_codes = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=32),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        block_task = progress.add_task(
            f"[magenta]{sector_id}", total=len(tile_configs)
        )

        for tc in tile_configs:
            tile_task = progress.add_task(
                f"  {tc.tile_id}", total=len([s for s in stages if s != "05"])
            )

            # Build command — pass output_root via env or config
            # run_tile.py accepts tile_id; the output_root is baked into
            # the TileConfig returned by sector_config.get_tile_configs().
            # We pass it as a JSON fragment via --sector flag.
            cmd = [
                python, run_tile,
                tc.tile_id,
                "--output-root", str(tc.output_root),
            ]
            if stages:
                cmd += ["--stages"] + stages

            t0   = time.time()
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            elapsed = time.time() - t0
            rc      = proc.returncode

            progress.advance(tile_task, len([s for s in stages if s != "05"]))
            progress.update(tile_task,
                            description=f"  {tc.tile_id} "
                                        f"[{'green' if rc == 0 else 'red'}]"
                                        f"{'OK' if rc == 0 else 'FAIL'}[/]")
            progress.advance(block_task)

            # Store output for manifest
            manifest_path = tc.manifest_dir / f"{tc.tile_id}_manifest.json"
            manifest_data = {}
            if manifest_path.exists():
                try:
                    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            tile_exit_codes[tc.tile_id] = rc
            tile_results[tc.tile_id] = {
                "s00": {"bbox_2229":  manifest_data.get("bbox_2229"),
                        "bbox_32611": manifest_data.get("bbox_32611"),
                        "shift":      manifest_data.get("blender_shift")},
                "s01": {"count_32611": manifest_data.get("footprint_count")},
                "s02": {"ground_points": manifest_data.get("ground_points")},
                "s03": {"passed": (manifest_data.get("crs_validation") or {}).get("passed"),
                        "failures": (manifest_data.get("crs_validation") or {}).get("failures", [])},
                "s04": {"lod0": manifest_data.get("building_mass_lod0"),
                        "lod1": manifest_data.get("building_mass_lod1"),
                        "quality": manifest_data.get("quality_breakdown")},
                "errors": manifest_data.get("errors", {}) if rc != 0 else {},
            }

            # Echo subprocess output
            if proc.stdout:
                for line in proc.stdout.strip().splitlines():
                    console.print(f"    [dim]{line}[/dim]")
            if proc.stderr and rc != 0:
                for line in proc.stderr.strip().splitlines()[-10:]:
                    console.print(f"    [red]{line}[/red]")

    # Write sector manifest
    _write_sector_manifest(s, tile_results)

    # Summary
    n_ok   = sum(1 for rc in tile_exit_codes.values() if rc == 0)
    n_fail = len(tile_configs) - n_ok
    console.print()
    console.print(Panel(
        "\n".join(
            [f"[bold]Sector [cyan]{sector_id}[/cyan] complete[/bold]",
             f"  {n_ok}/{len(tile_configs)} tiles OK   "
             f"{'[green]ALL PASSED[/green]' if n_fail == 0 else f'[red]{n_fail} FAILED[/red]'}"]
            + [f"  {'[green]OK[/green]' if tile_exit_codes[tc.tile_id] == 0 else '[red]FAIL[/red]'}  {tc.tile_id}"
               for tc in tile_configs]
        ),
        box=box.ROUNDED,
    ))

    return 0 if n_fail == 0 else 1


def _write_sector_manifest(s, tile_results: dict):
    s.output_root.mkdir(parents=True, exist_ok=True)
    totals = {
        "tiles":             len(s.tile_ids),
        "tiles_ok":          sum(1 for r in tile_results.values() if not r.get("errors")),
        "total_footprints":  sum((r.get("s01") or {}).get("count_32611") or 0 for r in tile_results.values()),
        "total_ground_pts":  sum((r.get("s02") or {}).get("ground_points") or 0 for r in tile_results.values()),
        "total_lod0_prisms": sum((r.get("s04") or {}).get("lod0") or 0 for r in tile_results.values()),
    }
    manifest = {
        "schema_version":   PIPELINE_VERSION,
        "pipeline":         "GlitchOS.io LA sector pipeline",
        "sector_id":        s.sector_id,
        "display_name":     s.display_name,
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "all_tiles_passed": totals["tiles_ok"] == totals["tiles"],
        "totals":           totals,
        "tiles":            {
            tid: {
                "status": "ok" if not r.get("errors") else "failed",
                "footprint_count": (r.get("s01") or {}).get("count_32611"),
                "ground_points":   (r.get("s02") or {}).get("ground_points"),
                "lod0_prisms":     (r.get("s04") or {}).get("lod0"),
                "quality":         (r.get("s04") or {}).get("quality"),
                "errors":          r.get("errors", {}),
            }
            for tid, r in tile_results.items()
        },
    }
    s.sector_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"[dim]Sector manifest → {s.sector_manifest}[/dim]")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        console.print(__doc__)
        return 0

    sector_id = args[0]
    dry       = "--dry-run"  in args or "--execute" not in args
    stages    = []

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

    if dry:
        return dry_run(sector_id, stages)
    else:
        return execute(sector_id, stages)


if __name__ == "__main__":
    sys.exit(main())
