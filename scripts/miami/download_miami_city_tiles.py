"""
download_miami_city_tiles.py  [GlitchOS city pipeline — Miami]

Download FL_MiamiDade_D23 LAZ tiles for the City of Miami to:
  /mnt/t7/miami/data_raw/laz/   (shared with Project Bikini)

Reads: /mnt/t7/miami/data_raw/miami_d23_catalog.json
       (built by build_miami_catalog.py)

Resume support: tiles already on disk are skipped.
Atomic writes:  each tile downloads to <name>.laz.tmp then renames on success.

Usage:
    python scripts/miami/download_miami_city_tiles.py
    python scripts/miami/download_miami_city_tiles.py --dry-run
    python scripts/miami/download_miami_city_tiles.py --workers 4
    python scripts/miami/download_miami_city_tiles.py --limit 10
    python scripts/miami/download_miami_city_tiles.py --force-catalog

Exit codes:
    0  all targets on disk
    1  one or more downloads failed
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import miami_city_config as CFG
from build_miami_catalog import build_catalog

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn, DownloadColumn, MofNCompleteColumn, Progress,
        SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn,
        TransferSpeedColumn,
    )
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None

HTTP_TIMEOUT = 180
CHUNK_SIZE   = 1 << 17   # 128 KB

# City of Miami bbox — only download tiles that intersect these limits
_CITY_BB = CFG.CITY_BBOX_4326


def _bbox_intersects(a: dict, b: dict) -> bool:
    return (
        a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"]
        and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]
    )


# ── tile selection ─────────────────────────────────────────────────────────────

def select_tiles(force_catalog: bool = False) -> list[dict]:
    catalog = build_catalog(force=force_catalog)
    all_tiles = catalog.get("tiles", [])

    city_tiles = []
    for t in all_tiles:
        bb = t.get("bbox_4326")
        if bb and not _bbox_intersects(bb, _CITY_BB):
            continue
        if not t.get("download_url"):
            continue
        city_tiles.append(t)

    return city_tiles


# ── download ───────────────────────────────────────────────────────────────────

def _download_one(
    tile: dict,
    laz_dir: Path,
    progress: "Progress | None" = None,
    overall_task=None,
) -> tuple[bool, str]:
    filename = tile["laz_filename"]
    url      = tile["download_url"]
    dest     = laz_dir / filename

    if dest.exists():
        if progress and overall_task is not None:
            progress.advance(overall_task)
        return True, f"skip:{filename}"

    tmp = dest.with_suffix(".laz.tmp")
    dest.parent.mkdir(parents=True, exist_ok=True)

    size_b   = int((tile.get("size_mb") or 0) * 1_048_576) or None
    file_task = None
    if progress:
        file_task = progress.add_task(
            f"  [cyan]{filename[-45:]}", total=size_b
        )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp, \
             open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                fh.write(chunk)
                if progress and file_task is not None:
                    progress.advance(file_task, len(chunk))

        tmp.rename(dest)
        if progress:
            if file_task is not None:
                progress.remove_task(file_task)
            if overall_task is not None:
                progress.advance(overall_task)
        return True, filename

    except Exception as exc:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        if progress and file_task is not None:
            try:
                progress.remove_task(file_task)
            except Exception:
                pass
        return False, f"FAIL:{filename} — {exc}"


def download_tiles(
    tiles: list[dict],
    laz_dir: Path,
    dry_run: bool = False,
    workers: int = 2,
    limit: int | None = None,
) -> int:
    on_disk = [t for t in tiles if (laz_dir / t["laz_filename"]).exists()]
    missing = [t for t in tiles if not (laz_dir / t["laz_filename"]).exists()]
    if limit is not None:
        missing = missing[:limit]

    total_mb_on_disk = sum(t.get("size_mb") or 0 for t in on_disk)
    total_mb_missing = sum(t.get("size_mb") or 0 for t in missing)
    total_mb_all     = total_mb_on_disk + total_mb_missing

    if console:
        console.print()
        console.print(Panel(
            "[bold magenta]GlitchOS — Miami City LAZ Downloader[/bold magenta]\n"
            f"  Project:  [white]{CFG.USGS_PROJECT_FULL}[/white]\n"
            f"  LAZ dir:  [white]{laz_dir}[/white]\n"
            f"  City tiles: [white]{len(tiles)}[/white]  "
            f"([green]{len(on_disk)} on disk[/green], "
            f"[{'red' if missing else 'dim'}]{len(missing)} to download[/{'red' if missing else 'dim'}])\n"
            f"  Need:     [yellow]{total_mb_missing/1024:.1f} GB[/yellow]  "
            f"  Total:    [dim]{total_mb_all/1024:.1f} GB[/dim]"
            + ("\n  [yellow]DRY RUN — no files will be written[/yellow]" if dry_run else ""),
            box=box.ROUNDED,
        ))
    else:
        print(f"Miami city downloader: {len(missing)} tiles to download ({total_mb_missing/1024:.1f} GB)")

    if dry_run:
        if console:
            tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
            tbl.add_column("Filename",  min_width=52)
            tbl.add_column("Status",    min_width=12)
            tbl.add_column("Size MB",   min_width=8, justify="right")
            for t in tiles:
                disk   = "[green]ON DISK[/green]" if (laz_dir / t["laz_filename"]).exists() else "[red]DOWNLOAD[/red]"
                sz     = str(t.get("size_mb","?"))
                tbl.add_row(t["laz_filename"], disk, sz)
            console.print(tbl)
        else:
            for t in tiles:
                status = "ON DISK " if (laz_dir / t["laz_filename"]).exists() else "DOWNLOAD"
                print(f"  [{status}] {t['laz_filename']}  {t.get('size_mb','?')} MB")
        return 0

    if not missing:
        if console:
            console.print("[bold green]All city tiles already on disk.[/bold green]")
        else:
            print("All city tiles already on disk.")
        return 0

    laz_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    if console:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            MofNCompleteColumn(),
            console=console,
            transient=False,
        ) as progress:
            overall = progress.add_task(
                f"  [bold white]Miami tiles  ({len(missing)} missing)", total=len(missing)
            )
            if workers <= 1:
                for tile in missing:
                    ok, msg = _download_one(tile, laz_dir, progress, overall)
                    if not ok:
                        failures.append(msg)
                        console.print(f"  [red]{msg}[/red]")
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futs = {
                        pool.submit(_download_one, t, laz_dir, progress, overall): t
                        for t in missing
                    }
                    for fut in as_completed(futs):
                        ok, msg = fut.result()
                        if not ok:
                            failures.append(msg)
                            console.print(f"  [red]{msg}[/red]")

        n_ok = len(missing) - len(failures)
        console.print(Panel(
            f"[bold]Download complete[/bold]\n"
            f"  Downloaded: [green]{n_ok}[/green]\n"
            f"  Skipped (on disk): [dim]{len(on_disk)}[/dim]\n"
            f"  Failed:  {'[red]' if failures else '[green]'}"
            f"{len(failures)}{'[/red]' if failures else '[/green]'}\n"
            f"  On disk now: {len(on_disk) + n_ok} / {len(tiles)}",
            box=box.ROUNDED,
        ))
        for msg in failures:
            console.print(f"  [red]FAIL: {msg}[/red]")
    else:
        for i, tile in enumerate(missing, 1):
            print(f"[{i}/{len(missing)}] {tile['laz_filename']} …", end=" ", flush=True)
            ok, msg = _download_one(tile, laz_dir)
            print("ok" if ok else f"FAILED: {msg}")
            if not ok:
                failures.append(msg)

    if failures:
        if console:
            console.print(f"\n[red]{len(failures)} tile(s) failed. Re-run to retry.[/red]")
        return 1
    return 0


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    args          = sys.argv[1:]
    dry_run       = "--dry-run"       in args
    force_catalog = "--force-catalog" in args
    workers = 2
    limit   = None

    i = 0
    while i < len(args):
        if args[i] == "--workers" and i + 1 < len(args):
            workers = int(args[i + 1]); i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        else:
            i += 1

    tiles = select_tiles(force_catalog=force_catalog)
    if not tiles:
        if console:
            console.print("[red]No city tiles found in catalog. Run build_miami_catalog.py first.[/red]")
        else:
            print("No city tiles found. Run build_miami_catalog.py first.")
        return 1

    return download_tiles(
        tiles,
        laz_dir=CFG.LAZ_DIR,
        dry_run=dry_run,
        workers=workers,
        limit=limit,
    )


if __name__ == "__main__":
    sys.exit(main())
