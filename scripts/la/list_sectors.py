"""
list_sectors.py  [LA sector pipeline — GlitchOS.io]

Print a summary of all configured LA sectors: status, tile count,
LAZ availability, and output paths.

Usage:
    python scripts/la/list_sectors.py
    python scripts/la/list_sectors.py --tiles        # also show per-tile detail
    python scripts/la/list_sectors.py --json         # machine-readable output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sector_config import SECTORS, SECTOR_ORDER, SECTOR_TILES, SECTORS_ROOT
from tile_config import LAZ_DIR

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

console = Console()

STATUS_STYLE = {
    "ready":          "bold green",
    "scaffold":       "yellow",
    "optional_later": "dim",
}

STATUS_ICON = {
    "ready":          "[green]●[/green]",
    "scaffold":       "[yellow]◐[/yellow]",
    "optional_later": "[dim]○[/dim]",
}


def laz_status(laz_path: Path) -> tuple[str, str]:
    """Returns (icon, style) for LAZ file availability."""
    if laz_path.exists():
        size_mb = laz_path.stat().st_size / 1_048_576
        return f"[green]✓[/green] {size_mb:.0f} MB", "green"
    return "[red]✗ missing[/red]", "red"


def sector_table() -> Table:
    t = Table(
        title="[bold magenta]GlitchOS.io — LA Sector Registry[/bold magenta]",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold cyan",
    )
    t.add_column("Sector", style="bold white", min_width=14)
    t.add_column("Display Name", min_width=22)
    t.add_column("Status", min_width=14)
    t.add_column("Tiles", justify="center", min_width=6)
    t.add_column("LAZ Ready", justify="center", min_width=10)
    t.add_column("Output Root")
    return t


def tile_detail_table(sector_id: str) -> Table:
    t = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="dim cyan",
        pad_edge=False,
    )
    t.add_column("  Tile ID", style="white", min_width=18)
    t.add_column("LAZ File", min_width=32)
    t.add_column("On Disk", min_width=14)
    t.add_column("Output Dir")
    return t


def main():
    show_tiles = "--tiles" in sys.argv
    as_json    = "--json"  in sys.argv

    if as_json:
        out = {}
        for sid in SECTOR_ORDER:
            s = SECTORS[sid]
            tiles_info = []
            for tid in s.tile_ids:
                tc = SECTOR_TILES.get(tid)
                tiles_info.append({
                    "tile_id":     tid,
                    "laz_file":    tc.laz_filename if tc else None,
                    "laz_exists":  tc.laz_path.exists() if tc else False,
                    "output_dir":  str(s.tiles_root / tid),
                })
            laz_ready = sum(1 for ti in tiles_info if ti["laz_exists"])
            out[sid] = {
                "sector_id":    sid,
                "display_name": s.display_name,
                "status":       s.status,
                "tile_count":   len(s.tile_ids),
                "laz_ready":    laz_ready,
                "runnable":     s.is_runnable(),
                "output_root":  str(s.output_root),
                "sector_manifest": str(s.sector_manifest),
                "bbox_4326":    s.bbox_4326,
                "notes":        s.notes,
                "tiles":        tiles_info,
            }
        print(json.dumps(out, indent=2))
        return 0

    # Rich table output
    tbl = sector_table()

    for sid in SECTOR_ORDER:
        s = SECTORS[sid]
        laz_ready = sum(
            1 for tid in s.tile_ids
            if tid in SECTOR_TILES and SECTOR_TILES[tid].laz_path.exists()
        )
        laz_cell = (
            f"[green]{laz_ready}/{len(s.tile_ids)}[/green]"
            if laz_ready == len(s.tile_ids)
            else f"[yellow]{laz_ready}[/yellow][dim]/{len(s.tile_ids)}[/dim]"
            if laz_ready > 0
            else f"[red]0/{len(s.tile_ids)}[/red]"
        )
        runnable = s.is_runnable()
        tbl.add_row(
            f"{STATUS_ICON[s.status]} {sid}",
            s.display_name,
            f"[{STATUS_STYLE[s.status]}]{s.status}[/{STATUS_STYLE[s.status]}]",
            str(len(s.tile_ids)),
            laz_cell,
            f"[dim]{s.output_root}[/dim]",
        )

    console.print()
    console.print(tbl)

    # Notes for non-ready sectors
    any_notes = False
    for sid in SECTOR_ORDER:
        s = SECTORS[sid]
        if s.notes:
            if not any_notes:
                console.print()
                console.print("[bold]Notes[/bold]")
                any_notes = True
            console.print(f"  [yellow]{sid}[/yellow]: {s.notes}")

    # Per-tile detail
    if show_tiles:
        for sid in SECTOR_ORDER:
            s = SECTORS[sid]
            console.print()
            console.rule(f"[cyan]{sid}[/cyan] — tiles")
            dtbl = tile_detail_table(sid)
            for tid in s.tile_ids:
                tc = SECTOR_TILES.get(tid)
                if tc:
                    disk_str, _ = laz_status(tc.laz_path)
                    out_dir = str(s.tiles_root / tid)
                else:
                    disk_str = "[red]not in registry[/red]"
                    out_dir  = "—"
                dtbl.add_row(
                    f"  {tid}",
                    tc.laz_filename if tc else "—",
                    disk_str,
                    f"[dim]{out_dir}[/dim]",
                )
            console.print(dtbl)

    # Quick command reference
    console.print()
    console.print("[bold]Commands[/bold]")
    console.print("  [cyan]python scripts/la/list_sectors.py --tiles[/cyan]   — per-tile LAZ detail")
    console.print("  [cyan]python scripts/la/run_sector.py dtla_core --dry-run[/cyan]   — preview run")
    console.print("  [cyan]python scripts/la/run_sector.py dtla_core[/cyan]   — execute (requires --execute)")
    console.print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
