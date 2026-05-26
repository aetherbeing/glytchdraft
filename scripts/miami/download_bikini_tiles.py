"""
download_bikini_tiles.py  [Project Bikini — GlitchOS.io]

Download 3DEP LAZ tiles for Downtown Miami/Brickell and South Beach.
Source: USGS FL_MiamiDade_D23 (2024), hosted on rockyweb.usgs.gov

Reads:
    data_processed/miami/bikini/catalog_raw.json

Downloads to:
    /mnt/t7/miami/data_raw/laz/   (T7 drive — change LAZ_DIR below if needed)

Usage:
    python scripts/miami/download_bikini_tiles.py
    python scripts/miami/download_bikini_tiles.py --dry-run
    python scripts/miami/download_bikini_tiles.py --zone downtown
    python scripts/miami/download_bikini_tiles.py --zone south_beach
    python scripts/miami/download_bikini_tiles.py --workers 2
    python scripts/miami/download_bikini_tiles.py --limit 3

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

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn, DownloadColumn, MofNCompleteColumn, Progress,
        SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn,
        TransferSpeedColumn,
    )
    from rich.table import Table
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── paths ──────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).resolve().parents[2]
CATALOG    = ROOT / "data_processed" / "miami" / "bikini" / "catalog_raw.json"
LAZ_DIR    = Path("/mnt/t7/miami/data_raw/laz")

HTTP_TIMEOUT   = 120
CHUNK_SIZE     = 1 << 17   # 128 KB

console = Console() if HAS_RICH else None

# ── catalog helpers ────────────────────────────────────────────────────────────

def load_tiles(zone_filter: str | None) -> list[dict]:
    if not CATALOG.exists():
        _die(f"Catalog not found: {CATALOG}\nRun: python scripts/miami/build_bikini_catalog.py")
    data = json.loads(CATALOG.read_text(encoding="utf-8"))

    if zone_filter and zone_filter in ("downtown", "downtown_brickell"):
        tiles = data["zones"]["downtown_brickell"]["tiles"]
    elif zone_filter and zone_filter in ("south_beach", "sb"):
        tiles = data["zones"]["south_beach"]["tiles"]
    else:
        # Both zones, dedup by filename
        seen: set[str] = set()
        tiles = []
        for zone in data["zones"].values():
            for t in zone["tiles"]:
                if t["filename"] not in seen:
                    seen.add(t["filename"])
                    tiles.append(t)

    tiles.sort(key=lambda t: t["filename"])
    return tiles


# ── download ───────────────────────────────────────────────────────────────────

def _download_one(tile: dict, progress: "Progress | None", overall_task) -> tuple[bool, str]:
    filename = tile["filename"]
    url      = tile["url"]
    dest     = LAZ_DIR / filename

    if dest.exists():
        if progress:
            progress.advance(overall_task)
        return True, f"skip:{filename}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".laz.tmp")

    file_task = None
    if progress:
        size_b = int(tile.get("size_mb", 0) * 1_048_576)
        file_task = progress.add_task(
            f"  [cyan]{filename[-40:]}", total=size_b or None
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
            progress.advance(overall_task)
        return True, filename

    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        if progress and file_task is not None:
            progress.remove_task(file_task)
        return False, f"FAIL:{filename} — {exc}"


def download_tiles(
    tiles: list[dict],
    dry_run: bool = False,
    workers: int = 1,
    limit: int | None = None,
) -> int:
    on_disk   = [t for t in tiles if (LAZ_DIR / t["filename"]).exists()]
    missing   = [t for t in tiles if not (LAZ_DIR / t["filename"]).exists()]

    if limit is not None:
        missing = missing[:limit]

    total_mb_needed = sum(t.get("size_mb", 0) for t in missing)
    total_mb_all    = sum(t.get("size_mb", 0) for t in tiles)

    if HAS_RICH:
        console.print()
        console.print(Panel(
            f"[bold magenta]GlitchOS — Project Bikini LAZ Downloader[/bold magenta]\n"
            f"  Project:  [white]FL_MiamiDade_D23 (2024)[/white]\n"
            f"  LAZ dir:  [white]{LAZ_DIR}[/white]\n"
            f"  Tiles:    [white]{len(tiles)} targeted  "
            f"({len(on_disk)} on disk, {len(missing)} to download)[/white]\n"
            f"  Download: [white]{total_mb_needed:.0f} MB needed  "
            f"/ {total_mb_all:.0f} MB total[/white]"
            + (f"\n  [yellow]DRY RUN — no files will be written[/yellow]" if dry_run else ""),
            box=box.ROUNDED,
        ))
    else:
        print(f"Bikini downloader: {len(missing)} tiles to download ({total_mb_needed:.0f} MB)")

    if dry_run:
        for t in tiles:
            disk = "ON DISK" if (LAZ_DIR / t["filename"]).exists() else "DOWNLOAD"
            zones = ",".join(t.get("zones", []))
            print(f"  [{disk:8s}] {t['filename']}  {t.get('size_mb',0):.1f} MB  [{zones}]")
        return 0

    if not missing:
        if HAS_RICH:
            console.print("[bold green]All tiles already on disk.[/bold green]")
        else:
            print("All tiles already on disk.")
        return 0

    LAZ_DIR.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []

    if HAS_RICH:
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
                f"  [bold white]Bikini tiles", total=len(missing)
            )
            if workers <= 1:
                for tile in missing:
                    ok, msg = _download_one(tile, progress, overall)
                    if not ok:
                        failures.append(msg)
                        console.print(f"  [red]{msg}[/red]")
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futs = {pool.submit(_download_one, t, progress, overall): t for t in missing}
                    for fut in as_completed(futs):
                        ok, msg = fut.result()
                        if not ok:
                            failures.append(msg)
                            console.print(f"  [red]{msg}[/red]")
    else:
        for i, tile in enumerate(missing, 1):
            print(f"[{i}/{len(missing)}] {tile['filename']} …", end=" ", flush=True)
            ok, msg = _download_one(tile, None, None)
            print("ok" if ok else f"FAILED: {msg}")
            if not ok:
                failures.append(msg)

    if HAS_RICH:
        n_ok = len(missing) - len(failures)
        console.print(Panel(
            f"[bold]Download complete[/bold]\n"
            f"  Success:  [green]{n_ok}[/green]\n"
            f"  Failed:   {'[red]' if failures else '[green]'}{len(failures)}{'[/red]' if failures else '[/green]'}\n"
            f"  On disk:  {len(on_disk) + n_ok} / {len(tiles)}",
            box=box.ROUNDED,
        ))

    return 1 if failures else 0


# ── CLI ────────────────────────────────────────────────────────────────────────

def _die(msg: str):
    if HAS_RICH:
        console.print(f"[bold red]Error:[/bold red] {msg}")
    else:
        print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    args      = sys.argv[1:]
    dry_run   = "--dry-run" in args
    workers   = 1
    zone      = None
    limit     = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--workers" and i + 1 < len(args):
            workers = int(args[i + 1]); i += 2
        elif a == "--zone" and i + 1 < len(args):
            zone = args[i + 1]; i += 2
        elif a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        else:
            i += 1

    tiles = load_tiles(zone)
    return download_tiles(tiles, dry_run=dry_run, workers=workers, limit=limit)


if __name__ == "__main__":
    sys.exit(main())
