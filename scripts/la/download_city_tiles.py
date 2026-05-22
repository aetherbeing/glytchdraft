"""
download_city_tiles.py  [LA city pipeline — GlitchOS.io]

Download missing LAZ tiles listed in the city tile manifest.

Reads:
  /mnt/t7/la/data_processed/cities/<city_id>/tile_manifest.json

Downloads to:
  /mnt/t7/la/data_raw/laz/

Skips files that are already present on disk.
Shows per-file byte progress and overall tile count progress.

Usage:
    python scripts/la/download_city_tiles.py
    python scripts/la/download_city_tiles.py --city los_angeles
    python scripts/la/download_city_tiles.py --dry-run       # show what would download
    python scripts/la/download_city_tiles.py --limit 3       # first N missing only
    python scripts/la/download_city_tiles.py --workers 2     # parallel downloads (default 1)

Exit code:
    0  all tiles now on disk (nothing to download, or all downloads succeeded)
    1  one or more downloads failed
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from tile_config import LAZ_DIR

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    DownloadColumn, TransferSpeedColumn, TimeElapsedColumn,
    TimeRemainingColumn, MofNCompleteColumn, TaskID,
)
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# ── USGS download URL patterns for CA_LosAngeles_2016 ─────────────────────────
# Tried in order until one returns HTTP 200.

USGS_URL_TEMPLATES = [
    # AWS S3 staged products (most reliable for 3DEP LPC)
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/LPC/Projects/"
    "CA_LosAngeles_2016_D16/CA_LosAngeles_2016/LAZ/{filename}",
    # USGS RockyWeb mirror
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/"
    "CA_LosAngeles_2016_D16/CA_LosAngeles_2016/LAZ/{filename}",
]

CHUNK_SIZE  = 1 << 20   # 1 MiB chunks
TIMEOUT_S   = 120       # per-request connect+read timeout


# ── manifest loading ──────────────────────────────────────────────────────────

def _load_manifest(city_id: str) -> list[dict]:
    from city_config import CITIES
    cfg = CITIES[city_id]
    if not cfg.tile_manifest.exists():
        console.print(f"[red]Tile manifest not found: {cfg.tile_manifest}[/red]")
        console.print(
            f"Run first:\n"
            f"  [cyan]python scripts/la/list_city_tiles.py --city {city_id}[/cyan]"
        )
        raise FileNotFoundError(cfg.tile_manifest)
    data = json.loads(cfg.tile_manifest.read_text(encoding="utf-8"))
    return data.get("tiles", [])


# ── URL resolution ─────────────────────────────────────────────────────────────

def _resolve_url(tile: dict) -> str | None:
    """
    Return the best download URL for a tile.
    Prefers the URL stored in the manifest (from TNM API), then tries
    the known USGS URL templates with a HEAD request.
    """
    stored = tile.get("download_url")
    if stored:
        return stored

    filename = tile["laz_filename"]
    for template in USGS_URL_TEMPLATES:
        url = template.format(filename=filename)
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "GlitchOS/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            continue
    return None


# ── single-file download ──────────────────────────────────────────────────────

def _download_one(
    tile:      dict,
    dest_dir:  Path,
    progress:  Progress,
    file_task: TaskID,
) -> tuple[bool, str]:
    """
    Download one LAZ file. Updates the Rich progress task as bytes arrive.
    Returns (success: bool, message: str).
    """
    filename = tile["laz_filename"]
    dest     = dest_dir / filename

    if dest.exists():
        size_mb = dest.stat().st_size / 1_048_576
        progress.update(file_task, description=f"[dim]{filename}[/dim]",
                        completed=1, total=1)
        return True, f"already on disk ({size_mb:.0f} MB)"

    url = _resolve_url(tile)
    if not url:
        progress.update(file_task,
                        description=f"[red]{filename} — no URL[/red]",
                        completed=1, total=1)
        return False, "no download URL found"

    tmp = dest.with_suffix(".laz.tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            total = int(resp.headers.get("Content-Length", 0)) or None
            progress.update(file_task,
                            description=f"[cyan]{filename}[/cyan]",
                            total=total or 1,
                            completed=0)
            downloaded = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update(file_task, completed=downloaded)

        tmp.rename(dest)
        size_mb = dest.stat().st_size / 1_048_576
        progress.update(file_task,
                        description=f"[green]✓ {filename}[/green]",
                        completed=progress.tasks[file_task].total or 1)
        return True, f"downloaded {size_mb:.0f} MB"

    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if tmp.exists():
            tmp.unlink()
        progress.update(file_task,
                        description=f"[red]✗ {filename}[/red]",
                        completed=1, total=1)
        return False, f"download error: {reason}"
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        progress.update(file_task,
                        description=f"[red]✗ {filename}[/red]",
                        completed=1, total=1)
        return False, f"error: {e}"


# ── dry run ────────────────────────────────────────────────────────────────────

def dry_run(city_id: str, limit: int | None):
    tiles   = _load_manifest(city_id)
    missing = [t for t in tiles if not (LAZ_DIR / t["laz_filename"]).exists()]
    present = len(tiles) - len(missing)

    if limit is not None:
        missing = missing[:limit]

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — LAZ Downloader[/bold magenta]\n"
        f"[cyan]DRY RUN[/cyan] — no files will be written\n"
        f"City: [white]{city_id}[/white]   "
        f"Total tiles: [white]{len(tiles)}[/white]   "
        f"Present: [green]{present}[/green]   "
        f"To download: [yellow]{len(missing)}[/yellow]",
        box=box.ROUNDED,
    ))

    if not missing:
        console.print("[bold green]✓ All tiles already on disk. Nothing to download.[/bold green]")
        return 0

    tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
    tbl.add_column("Tile ID",   min_width=20)
    tbl.add_column("LAZ File",  min_width=52)
    tbl.add_column("URL source", min_width=12)

    for t in missing:
        stored = t.get("download_url")
        src    = "[dim]manifest URL[/dim]" if stored else "[yellow]USGS template[/yellow]"
        tbl.add_row(t["tile_id"], t["laz_filename"], src)

    console.print(tbl)

    est_gb = (len(missing) * 300) / 1024
    console.print(
        f"\n  Est. download: ~[yellow]{est_gb:.1f} GB[/yellow]  "
        f"(~300 MB avg per tile)\n"
        f"  Destination:   [dim]{LAZ_DIR}[/dim]"
    )
    console.print(
        f"\nTo execute:\n"
        f"  [cyan]python scripts/la/download_city_tiles.py --city {city_id}[/cyan]"
    )
    return 0


# ── main download ──────────────────────────────────────────────────────────────

def download(city_id: str, limit: int | None, workers: int):
    tiles   = _load_manifest(city_id)
    missing = [t for t in tiles if not (LAZ_DIR / t["laz_filename"]).exists()]
    present = len(tiles) - len(missing)

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — LAZ Downloader[/bold magenta]\n"
        f"City: [white]{city_id}[/white]   "
        f"Total: [white]{len(tiles)}[/white]   "
        f"Present: [green]{present}[/green]   "
        f"To download: [yellow]{len(missing)}[/yellow]",
        box=box.ROUNDED,
    ))

    if not missing:
        console.print("[bold green]✓ All tiles already on disk. Nothing to download.[/bold green]")
        return 0

    if limit is not None:
        console.print(f"[yellow]--limit {limit}: downloading first {limit} of {len(missing)} missing tiles.[/yellow]")
        missing = missing[:limit]

    LAZ_DIR.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Destination: {LAZ_DIR}[/dim]")
    console.print(f"[dim]Workers: {workers}  Chunk: {CHUNK_SIZE // 1024} KiB  Timeout: {TIMEOUT_S}s[/dim]\n")

    results: dict[str, tuple[bool, str]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=28),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        overall_task = progress.add_task(
            f"[magenta]{city_id}  overall", total=len(missing)
        )

        if workers == 1:
            for tile in missing:
                file_task = progress.add_task(
                    f"[cyan]{tile['laz_filename']}[/cyan]", total=None
                )
                ok, msg = _download_one(tile, LAZ_DIR, progress, file_task)
                results[tile["tile_id"]] = (ok, msg)
                progress.advance(overall_task)
        else:
            # Parallel: each worker gets its own file_task, but we create them
            # upfront so the overall bar is visible throughout.
            file_tasks: dict[str, TaskID] = {}
            for tile in missing:
                file_tasks[tile["tile_id"]] = progress.add_task(
                    f"[dim]{tile['laz_filename']}[/dim]", total=None
                )

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        _download_one, tile, LAZ_DIR, progress,
                        file_tasks[tile["tile_id"]]
                    ): tile
                    for tile in missing
                }
                for fut in as_completed(futures):
                    tile = futures[fut]
                    ok, msg = fut.result()
                    results[tile["tile_id"]] = (ok, msg)
                    progress.advance(overall_task)

    # ── final summary ─────────────────────────────────────────────────────────
    n_ok   = sum(1 for ok, _ in results.values() if ok)
    n_fail = len(results) - n_ok

    # Re-count entire manifest (not just this batch)
    all_tiles    = _load_manifest(city_id)
    now_on_disk  = sum(1 for t in all_tiles if (LAZ_DIR / t["laz_filename"]).exists())
    still_missing = len(all_tiles) - now_on_disk

    console.print()
    if n_fail:
        console.print(f"[red]{n_fail} download(s) failed:[/red]")
        for tid, (ok, msg) in results.items():
            if not ok:
                console.print(f"  [red]{tid}: {msg}[/red]")

    console.print(
        f"\nOn disk now:   [green]{now_on_disk}[/green] / {len(all_tiles)}"
    )
    console.print(
        f"Still missing: {'[red]' if still_missing else '[green]'}"
        f"{still_missing}{'[/red]' if still_missing else '[/green]'}"
    )

    if still_missing == 0:
        console.print("\n[bold green]✓ All tiles on disk. Ready to run:[/bold green]")
        console.print(f"  [cyan]python scripts/la/run_city.py {city_id} --execute[/cyan]")

    return 0 if n_fail == 0 else 1


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    args    = sys.argv[1:]
    city_id = "los_angeles"
    dry     = "--dry-run" in args
    limit   = None
    workers = 1

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--city" and i + 1 < len(args):
            city_id = args[i + 1]
            i += 2
            continue
        if a == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                console.print(f"[red]--limit requires an integer, got {args[i+1]!r}[/red]")
                return 1
            i += 2
            continue
        if a == "--workers" and i + 1 < len(args):
            try:
                workers = max(1, int(args[i + 1]))
            except ValueError:
                console.print(f"[red]--workers requires an integer, got {args[i+1]!r}[/red]")
                return 1
            i += 2
            continue
        i += 1

    try:
        from city_config import CITIES, CITY_ORDER
    except ImportError:
        console.print("[red]Cannot import city_config. Run from the scripts/la/ directory "
                      "or the glytchdraft root.[/red]")
        return 1

    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        from city_config import CITY_ORDER
        console.print(f"Valid: {CITY_ORDER}")
        return 1

    try:
        if dry:
            return dry_run(city_id, limit)
        else:
            return download(city_id, limit, workers)
    except FileNotFoundError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
