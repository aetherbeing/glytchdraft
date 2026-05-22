"""
run_block.py  [LA block pipeline — GlitchOS.io]

Process all 4 tiles of the LA 1836 block with process-level isolation
and rich progress bars.

Each tile runs in its own subprocess — a crash or failure in one tile
cannot corrupt outputs from other tiles.

Usage:
    python run_block.py                  # all 4 tiles, all stages
    python run_block.py --stages 00 01   # specific stages, all tiles
    python run_block.py --dry-run        # print what would run, don't execute

After all tiles finish, writes the combined block manifest.
Exit code 0 if all tiles pass, 1 if any tile fails.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "stages"))

from tile_config import TILES, TILE_ORDER, BLOCK_FOOTPRINTS_RAW
from stages import s05_manifest

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, MofNCompleteColumn,
)
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def _check_prerequisites() -> list[str]:
    errors = []
    for tid in TILE_ORDER:
        if not TILES[tid].laz_path.exists():
            errors.append(f"LAZ missing: {TILES[tid].laz_path}")
    if not BLOCK_FOOTPRINTS_RAW.exists():
        errors.append(
            f"Block footprints missing: {BLOCK_FOOTPRINTS_RAW}\n"
            "  Run: python 00_download_block_footprints.py"
        )
    return errors


def _run_tile_subprocess(tile_id: str, stages: list[str], python_exe: str) -> tuple[int, str]:
    cmd = [python_exe, str(Path(__file__).parent / "run_tile.py"), tile_id]
    if stages:
        cmd += ["--stages"] + stages
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    output = proc.stdout
    if proc.stderr:
        output += "\n" + proc.stderr
    return proc.returncode, output


def _load_tile_manifest(tile_id: str) -> dict:
    path = TILES[tile_id].tile_manifest
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main():
    args    = sys.argv[1:]
    stages  = []
    dry_run = False

    i = 0
    while i < len(args):
        if args[i] == "--stages":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                stages.append(args[i])
                i += 1
            continue
        elif args[i] == "--dry-run":
            dry_run = True
        elif args[i].startswith("--"):
            console.print(f"[red]Unknown flag: {args[i]}[/red]")
            sys.exit(1)
        i += 1

    python_exe = sys.executable

    console.print(Panel(
        f"[bold magenta]GlitchOS.io[/bold magenta] — LA 1836 block pipeline\n"
        f"Tiles: [cyan]{' '.join(TILE_ORDER)}[/cyan]   "
        f"Stages: [white]{' '.join(stages) if stages else 'all'}[/white]",
        box=box.ROUNDED,
    ))

    if dry_run:
        console.print("\n[cyan]DRY RUN — would execute:[/cyan]")
        for tid in TILE_ORDER:
            cmd_parts = ["python", "run_tile.py", tid]
            if stages:
                cmd_parts += ["--stages"] + stages
            console.print(f"  [dim]{' '.join(cmd_parts)}[/dim]")
        console.print(f"\n  [dim]write block manifest → {s05_manifest.BLOCK_MANIFEST_PATH}[/dim]" if hasattr(s05_manifest, 'BLOCK_MANIFEST_PATH') else "")
        return 0

    prereq_errors = _check_prerequisites()
    if prereq_errors:
        console.print("\n[red][ABORT] Prerequisites missing:[/red]")
        for e in prereq_errors:
            console.print(f"  [red]{e}[/red]")
        return 1

    tile_results    = {}
    tile_exit_codes = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=28),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        block_task = progress.add_task(
            "[magenta]la_1836 block", total=len(TILE_ORDER)
        )

        for tile_id in TILE_ORDER:
            tile_task = progress.add_task(
                f"  [cyan]{tile_id}[/cyan]", total=1
            )
            t0 = time.time()

            rc, output = _run_tile_subprocess(tile_id, stages, python_exe)
            elapsed = time.time() - t0

            # Echo subprocess output (dim, indented)
            for line in output.splitlines():
                stripped = line.strip()
                if stripped:
                    console.print(f"    [dim]{stripped}[/dim]")

            ok = rc == 0
            progress.update(
                tile_task,
                description=(
                    f"  [cyan]{tile_id}[/cyan] "
                    f"[{'green' if ok else 'red'}]{'OK' if ok else f'FAIL ({rc})'}[/] "
                    f"({elapsed/60:.1f} min)"
                ),
                completed=1,
            )
            progress.advance(block_task)

            tile_exit_codes[tile_id] = rc
            manifest = _load_tile_manifest(tile_id)
            tile_results[tile_id] = {
                "s00": {"bbox_2229":  manifest.get("bbox_2229"),
                        "bbox_32611": manifest.get("bbox_32611"),
                        "shift":      manifest.get("blender_shift")},
                "s01": {"count_32611": manifest.get("footprint_count")},
                "s02": {"ground_points": manifest.get("ground_points")},
                "s03": {"passed":   (manifest.get("crs_validation") or {}).get("passed"),
                        "failures": (manifest.get("crs_validation") or {}).get("failures", [])},
                "s04": {"lod0":    manifest.get("building_mass_lod0"),
                        "lod1":    manifest.get("building_mass_lod1"),
                        "quality": manifest.get("quality_breakdown")},
                "errors": manifest.get("errors", {}) if rc != 0 else {},
            }

    # Block manifest
    try:
        s05_manifest.write_block_manifest(tile_results)
    except Exception as e:
        console.print(f"[yellow]WARN: block manifest write failed: {e}[/yellow]")

    # Summary table
    n_ok   = sum(1 for rc in tile_exit_codes.values() if rc == 0)
    n_fail = len(TILE_ORDER) - n_ok

    tbl = Table(box=box.ROUNDED, header_style="bold cyan", show_lines=False)
    tbl.add_column("Tile", style="white")
    tbl.add_column("Status", justify="center")
    tbl.add_column("Footprints", justify="right")
    tbl.add_column("Ground pts", justify="right")
    tbl.add_column("LOD0 prisms", justify="right")
    tbl.add_column("CRS", justify="center")

    for tid in TILE_ORDER:
        r   = tile_results.get(tid, {})
        rc  = tile_exit_codes.get(tid, 1)
        ok_str = "[green]OK[/green]" if rc == 0 else "[red]FAIL[/red]"
        fp  = (r.get("s01") or {}).get("count_32611")  or "—"
        gp  = (r.get("s02") or {}).get("ground_points") or "—"
        lod = (r.get("s04") or {}).get("lod0")          or "—"
        crs_ok = (r.get("s03") or {}).get("passed")
        crs_str = "[green]PASS[/green]" if crs_ok else ("[red]FAIL[/red]" if crs_ok is False else "[dim]—[/dim]")
        tbl.add_row(tid, ok_str,
                    f"{fp:,}" if isinstance(fp, int) else str(fp),
                    f"{gp:,}" if isinstance(gp, int) else str(gp),
                    f"{lod:,}" if isinstance(lod, int) else str(lod),
                    crs_str)

    console.print()
    console.print(tbl)
    overall = "[green]ALL OK[/green]" if n_fail == 0 else f"[red]{n_fail} FAILED[/red]"
    console.print(f"\nBlock result: {n_ok}/{len(TILE_ORDER)} tiles OK   {overall}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
