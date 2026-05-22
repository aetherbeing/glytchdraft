"""
expand_dtla_tiles.py  [LA block pipeline — GlitchOS.io]

Expand the confirmed DTLA 1836 block to real neighboring tiles.

Seed
----
The 4 confirmed working tiles:
  USGS_LPC_CA_LosAngeles_2016_L4_6477_1836{a,b,c,d}_LAS_2018.laz

Approach
--------
Generate candidate filenames from neighboring stems (not a municipal grid).
Check each candidate against authoritative sources in order:

  1. Local disk              — instant, no network
  2. USGS TNM API            — single bbox query, paginated, authoritative
  3. S3 HEAD request         — fast fallback per-file; tries known path prefixes

Only tiles confirmed by TNM or S3 are reported as real.
Synthetic IDs that match no real product are silently dropped.

Output
------
  Grid view (by stem) showing which quarters exist and whether on disk.
  Flat table with download URL for each confirmed tile.
  --download  fetch missing confirmed tiles to /mnt/t7/la/data_raw/laz/

Usage
-----
    python scripts/la/expand_dtla_tiles.py
    python scripts/la/expand_dtla_tiles.py --expand 2    # ±2 stems each axis
    python scripts/la/expand_dtla_tiles.py --download    # also fetch missing
    python scripts/la/expand_dtla_tiles.py --no-s3       # TNM only
    python scripts/la/expand_dtla_tiles.py --dry-run     # skip network, show plan
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tile_config import LAZ_DIR, SRC_EPSG

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    DownloadColumn, TransferSpeedColumn, TimeRemainingColumn,
    TimeElapsedColumn, MofNCompleteColumn,
)
from rich import box

console = Console()

# ── seed ──────────────────────────────────────────────────────────────────────

SEED_X = 6477
SEED_Y = 1836
QUARTERS = ("a", "b", "c", "d")

# Full filename for one tile
FILENAME_TEMPLATE = "USGS_LPC_CA_LosAngeles_2016_L4_{x}_{y}{q}_LAS_2018.laz"
FILENAME_PREFIX   = "USGS_LPC_CA_LosAngeles_2016_L4_"

# ── USGS / S3 constants ────────────────────────────────────────────────────────

TNM_URL      = "https://tnmaccess.nationalmap.gov/api/v1/products"
TNM_DATASETS = "Lidar Point Cloud (LPC)"
TNM_PROJECT  = "CA_LosAngeles_2016"
TNM_TIMEOUT  = 60

S3_BUCKET  = "https://prd-tnm.s3.amazonaws.com"
S3_TIMEOUT = 20

# Probed in order; first that returns HTTP 200 on HEAD wins.
S3_PREFIXES = [
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016_D16/CA_LosAngeles_2016/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016/CA_LosAngeles_2016/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016_D16/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016/LAZ/",
]

CHUNK_SIZE = 1 << 20  # 1 MiB


# ── data model ─────────────────────────────────────────────────────────────────

@dataclass
class TileEntry:
    stem_x:       int          # e.g. 6477
    stem_y:       int          # e.g. 1836
    quarter:      str          # a/b/c/d
    filename:     str          # full LAZ filename
    on_disk:      bool         # present in LAZ_DIR
    confirmed:    bool         # real USGS product (TNM or S3 confirmed)
    download_url: str | None   # resolved URL
    source:       str          # "disk" | "tnm" | "s3" | "seed" | "none"

    @property
    def stem(self) -> str:
        return f"{self.stem_x}_{self.stem_y}"

    @property
    def tile_id(self) -> str:
        return f"{self.stem_x}_{self.stem_y}{self.quarter}"

    @property
    def is_seed(self) -> bool:
        return self.stem_x == SEED_X and self.stem_y == SEED_Y


# ── candidate generation ───────────────────────────────────────────────────────

def _make_filename(x: int, y: int, q: str) -> str:
    return FILENAME_TEMPLATE.format(x=x, y=y, q=q)


def generate_candidates(expand: int) -> list[TileEntry]:
    """Generate all (stem_x, stem_y, quarter) combinations within expand radius."""
    entries = []
    for dx in range(-expand, expand + 1):
        for dy in range(-expand, expand + 1):
            gx = SEED_X + dx
            gy = SEED_Y + dy
            for q in QUARTERS:
                fn      = _make_filename(gx, gy, q)
                on_disk = (LAZ_DIR / fn).exists()
                entries.append(TileEntry(
                    stem_x=gx, stem_y=gy, quarter=q,
                    filename=fn, on_disk=on_disk,
                    confirmed=on_disk,          # disk presence = confirmed real
                    download_url=None,
                    source="seed" if (gx == SEED_X and gy == SEED_Y) else
                           "disk" if on_disk else "none",
                ))
    return entries


# ── coordinate conversion ──────────────────────────────────────────────────────

def _stems_to_4326_bbox(
    x_stems: list[int], y_stems: list[int]
) -> dict:
    """Convert a stem range to an EPSG:4326 bbox for the TNM query."""
    # Each stem covers [stem * 1000, (stem+1) * 1000 + 2000] in EPSG:2229
    # (the full 3000 ft cell: stem*1000 to stem*1000 + 3000)
    x_min_ft = min(x_stems) * 1000.0
    x_max_ft = (max(x_stems) + 1) * 1000.0 + 2000.0
    y_min_ft = min(y_stems) * 1000.0
    y_max_ft = (max(y_stems) + 1) * 1000.0 + 2000.0

    try:
        from pyproj import Transformer
        t = Transformer.from_crs(SRC_EPSG, 4326, always_xy=True)
        corners = [
            t.transform(x_min_ft, y_min_ft),
            t.transform(x_max_ft, y_min_ft),
            t.transform(x_min_ft, y_max_ft),
            t.transform(x_max_ft, y_max_ft),
        ]
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        return {
            "xmin": min(lons) - 0.005,
            "ymin": min(lats) - 0.005,
            "xmax": max(lons) + 0.005,
            "ymax": max(lats) + 0.005,
        }
    except Exception:
        # Hard-coded fallback: seed bbox + generous buffer
        return {"xmin": -118.360, "ymin": 33.990,
                "xmax": -118.200, "ymax": 34.120}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _http_get(url: str, timeout: int, data: bytes | None = None) -> bytes | None:
    try:
        req = urllib.request.Request(
            url, data=data, headers={"User-Agent": "GlitchOS/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code not in (403, 404):
            console.print(f"  [yellow]HTTP {e.code}: {url[:80]}[/yellow]")
        return None
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if "timed out" in str(reason).lower():
            console.print(f"  [yellow]Timeout ({timeout}s): {url[:80]}[/yellow]")
        else:
            console.print(f"  [yellow]Network error: {reason}[/yellow]")
        return None
    except Exception as e:
        console.print(f"  [yellow]Request error: {e}[/yellow]")
        return None


def _http_head_200(url: str, timeout: int) -> bool:
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "GlitchOS/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Strategy 1: TNM API ────────────────────────────────────────────────────────

def _tnm_url_from_item(item: dict) -> str | None:
    urls = item.get("urls", {})
    for key in ("LAZ", "LAZ ", "laz"):
        v = urls.get(key)
        if isinstance(v, str) and v.lower().endswith(".laz"):
            return v
    for v in urls.values():
        if isinstance(v, str) and v.lower().endswith(".laz"):
            return v
    return None


def _filename_from_item(item: dict) -> str | None:
    url = _tnm_url_from_item(item)
    if url:
        name = url.rsplit("/", 1)[-1]
        if name.startswith(FILENAME_PREFIX):
            return name
    title = item.get("title", "")
    if FILENAME_PREFIX in title:
        idx  = title.find(FILENAME_PREFIX)
        part = title[idx:].split()[0]
        if not part.endswith(".laz"):
            part += "_LAS_2018.laz"
        if part.startswith(FILENAME_PREFIX):
            return part
    return None


def query_tnm(bbox: dict) -> dict[str, str]:
    """
    Paginated TNM API query.
    Returns {laz_filename: download_url} for all CA_LosAngeles_2016 products.
    """
    catalog: dict[str, str] = {}
    offset  = 0

    console.print(
        f"  bbox (4326): "
        f"lon [{bbox['xmin']:.4f}, {bbox['xmax']:.4f}]  "
        f"lat [{bbox['ymin']:.4f}, {bbox['ymax']:.4f}]"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console, transient=False,
    ) as progress:
        task = progress.add_task("  TNM page 1", total=None)

        page = 0
        while True:
            page += 1
            params = {
                "datasets":     TNM_DATASETS,
                "bbox":         (f"{bbox['xmin']},{bbox['ymin']},"
                                 f"{bbox['xmax']},{bbox['ymax']}"),
                "max":          "1000",
                "offset":       str(offset),
                "outputFormat": "json",
            }
            url  = TNM_URL + "?" + urllib.parse.urlencode(params)
            raw  = _http_get(url, timeout=TNM_TIMEOUT)
            if not raw:
                break

            data  = json.loads(raw)
            items = data.get("items", [])
            total = data.get("total", 0)

            for item in items:
                if TNM_PROJECT.lower() not in item.get("title", "").lower():
                    continue
                fn  = _filename_from_item(item)
                dl  = _tnm_url_from_item(item)
                if fn and dl:
                    catalog[fn] = dl

            offset += len(items)
            progress.update(
                task,
                description=(
                    f"  TNM page {page}  "
                    f"fetched {offset}/{total}  "
                    f"matched {len(catalog)}"
                ),
            )

            if not items or offset >= total:
                break

        progress.update(task, description=f"  TNM done  {len(catalog)} products")

    console.print(f"  [green]TNM: {len(catalog)} {TNM_PROJECT!r} tiles[/green]")
    return catalog


# ── Strategy 2: S3 HEAD per file ───────────────────────────────────────────────

_s3_working_prefix: str | None = None


def _find_s3_prefix() -> str | None:
    global _s3_working_prefix
    if _s3_working_prefix is not None:
        return _s3_working_prefix

    # Probe with the known seed tile (guaranteed to exist if any prefix works)
    probe_file = _make_filename(SEED_X, SEED_Y, "b")
    for prefix in S3_PREFIXES:
        url = f"{S3_BUCKET}/{prefix}{probe_file}"
        if _http_head_200(url, timeout=S3_TIMEOUT):
            console.print(f"  [green]S3 prefix: {prefix}[/green]")
            _s3_working_prefix = prefix
            return prefix

    console.print("  [yellow]No working S3 prefix found.[/yellow]")
    return None


def check_s3(filenames: list[str]) -> dict[str, str]:
    """HEAD-check each filename against S3. Returns {filename: url} for 200s."""
    if not filenames:
        return {}

    prefix = _find_s3_prefix()
    if not prefix:
        return {}

    found: dict[str, str] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console, transient=False,
    ) as progress:
        task = progress.add_task(
            f"  S3 HEAD checks", total=len(filenames)
        )
        for fn in filenames:
            url = f"{S3_BUCKET}/{prefix}{fn}"
            if _http_head_200(url, timeout=S3_TIMEOUT):
                found[fn] = url
                progress.update(
                    task,
                    description=f"  S3  found={len(found)}  [green]{fn}[/green]",
                )
            else:
                progress.update(task, description=f"  S3  checking…")
            progress.advance(task)

        progress.update(task, description=f"  S3 done  {len(found)} confirmed")

    console.print(f"  [green]S3: {len(found)} confirmed[/green]")
    return found


# ── main resolution pass ───────────────────────────────────────────────────────

def resolve(
    entries: list[TileEntry],
    use_tnm: bool = True,
    use_s3:  bool = True,
    dry_run: bool = False,
) -> list[TileEntry]:
    """
    Confirm which candidate entries are real USGS products and fill download_url.
    Modifies entries in place; returns the same list.
    """
    # Disk-confirmed tiles already have confirmed=True from generation
    need_confirm = [e for e in entries if not e.confirmed]
    if not need_confirm:
        console.print("[dim]All candidates already confirmed from disk.[/dim]")
        return entries

    if dry_run:
        console.print(
            f"[cyan]DRY RUN — would check {len(need_confirm)} candidate(s) "
            f"via TNM/S3[/cyan]"
        )
        return entries

    # Build filename → entry index map for fast lookup
    fn_map: dict[str, int] = {e.filename: i for i, e in enumerate(entries)}

    # ── TNM ──
    if use_tnm:
        console.print("\n[bold cyan]Strategy 1: USGS TNM API[/bold cyan]")
        x_stems = sorted({e.stem_x for e in entries})
        y_stems = sorted({e.stem_y for e in entries})
        bbox    = _stems_to_4326_bbox(x_stems, y_stems)
        tnm_catalog = query_tnm(bbox)

        for fn, url in tnm_catalog.items():
            if fn in fn_map:
                i = fn_map[fn]
                entries[i].confirmed    = True
                entries[i].download_url = url
                entries[i].source       = "seed" if entries[i].is_seed else "tnm"

    # ── S3 HEAD for remaining unconfirmed ──
    still_unknown = [e for e in entries if not e.confirmed]
    if still_unknown and use_s3:
        console.print(
            f"\n[bold cyan]Strategy 2: S3 HEAD "
            f"({len(still_unknown)} unresolved)[/bold cyan]"
        )
        s3_results = check_s3([e.filename for e in still_unknown])
        for fn, url in s3_results.items():
            if fn in fn_map:
                i = fn_map[fn]
                entries[i].confirmed    = True
                entries[i].download_url = url
                entries[i].source       = "s3"

    return entries


# ── display ────────────────────────────────────────────────────────────────────

def _print_grid(entries: list[TileEntry], expand: int):
    """Print a stem-by-stem grid showing confirmed quarters."""
    x_stems = sorted({e.stem_x for e in entries})
    y_stems = sorted({e.stem_y for e in entries}, reverse=True)  # north = top

    tbl = Table(
        box=box.ROUNDED, header_style="bold cyan", show_lines=True,
        title=f"[bold]Neighbor grid (seed {SEED_X}_{SEED_Y}, expand={expand})[/bold]",
    )
    tbl.add_column("y \\ x", style="dim", min_width=6)
    for gx in x_stems:
        style = "bold white" if gx == SEED_X else "white"
        tbl.add_column(str(gx), style=style, justify="center", min_width=14)

    for gy in y_stems:
        row = ["[bold white]" + str(gy) + "[/bold white]"
               if gy == SEED_Y else str(gy)]
        for gx in x_stems:
            cell_parts = []
            for q in QUARTERS:
                fn  = _make_filename(gx, gy, q)
                # Find matching entry
                match = next((e for e in entries
                              if e.stem_x == gx and e.stem_y == gy and e.quarter == q), None)
                if match is None:
                    cell_parts.append(f"[dim]{q}[/dim]")
                elif match.on_disk:
                    cell_parts.append(f"[green]{q}[/green]")
                elif match.confirmed:
                    cell_parts.append(f"[cyan]{q}[/cyan]")
                else:
                    cell_parts.append(f"[red]{q}✗[/red]")
            row.append("  ".join(cell_parts))
        tbl.add_row(*row)

    console.print()
    console.print(tbl)
    console.print(
        "  [green]green[/green] = on disk   "
        "[cyan]cyan[/cyan] = real, not downloaded   "
        "[red]red ✗[/red] = not a real tile"
    )


def _print_tile_table(confirmed: list[TileEntry]):
    if not confirmed:
        return

    tbl = Table(
        box=box.ROUNDED, header_style="bold cyan", show_lines=False,
        title=f"[bold green]Confirmed real tiles ({len(confirmed)})[/bold green]",
    )
    tbl.add_column("Stem",       style="white",  justify="center", min_width=10)
    tbl.add_column("Quarter",    justify="center", min_width=8)
    tbl.add_column("Filename",   style="dim",    min_width=56)
    tbl.add_column("On Disk",    justify="center", min_width=9)
    tbl.add_column("Source",     min_width=7)
    tbl.add_column("URL",        style="dim",    min_width=16)

    for e in confirmed:
        disk = "[green]✓[/green]" if e.on_disk else "[dim]—[/dim]"
        url  = e.download_url or "—"
        url_short = ("…" + url[-44:]) if len(url) > 47 else url
        src_style = "green" if e.source == "seed" else "cyan" if e.source == "tnm" else "yellow"
        tbl.add_row(
            e.stem, e.quarter, e.filename, disk,
            f"[{src_style}]{e.source}[/{src_style}]",
            url_short,
        )

    console.print()
    console.print(tbl)


# ── download ───────────────────────────────────────────────────────────────────

def _download_one(entry: TileEntry, progress: Progress, task_id) -> tuple[bool, str]:
    dest = LAZ_DIR / entry.filename
    if dest.exists():
        return True, "already on disk"

    if not entry.download_url:
        return False, "no download URL"

    tmp = dest.with_suffix(".laz.tmp")
    try:
        req = urllib.request.Request(
            entry.download_url, headers={"User-Agent": "GlitchOS/1.0"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0)) or None
            progress.update(task_id, total=total or 1, completed=0,
                            description=f"  [cyan]{entry.tile_id}[/cyan]")
            downloaded = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update(task_id, completed=downloaded)

        tmp.rename(dest)
        size_mb = dest.stat().st_size / 1_048_576
        progress.update(task_id,
                        description=f"  [green]✓ {entry.tile_id}[/green]",
                        completed=progress.tasks[task_id].total or 1)
        return True, f"{size_mb:.0f} MB"

    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        progress.update(task_id, description=f"  [red]✗ {entry.tile_id}[/red]",
                        completed=1, total=1)
        return False, str(e)


def download_missing(entries: list[TileEntry]) -> int:
    """Download all confirmed-real tiles not yet on disk. Returns fail count."""
    to_download = [e for e in entries if e.confirmed and not e.on_disk and e.download_url]
    if not to_download:
        console.print("[green]No confirmed tiles to download — all on disk.[/green]")
        return 0

    console.print(
        f"\n[bold cyan]Downloading {len(to_download)} tile(s)[/bold cyan]"
        f"  →  {LAZ_DIR}"
    )
    LAZ_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, tuple[bool, str]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=24),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console, transient=False,
    ) as progress:
        overall = progress.add_task(
            "[magenta]overall", total=len(to_download)
        )
        for entry in to_download:
            file_task = progress.add_task(f"  {entry.tile_id}", total=None)
            ok, msg   = _download_one(entry, progress, file_task)
            results[entry.tile_id] = (ok, msg)
            progress.advance(overall)
            if ok:
                entry.on_disk = True

    n_fail = sum(1 for ok, _ in results.values() if not ok)
    if n_fail:
        console.print(f"\n[red]{n_fail} download(s) failed:[/red]")
        for tid, (ok, msg) in results.items():
            if not ok:
                console.print(f"  [red]{tid}: {msg}[/red]")
    return n_fail


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    args    = sys.argv[1:]
    expand  = 1
    do_dl   = "--download" in args
    dry_run = "--dry-run"  in args
    use_tnm = "--no-tnm"   not in args
    use_s3  = "--no-s3"    not in args

    for i, a in enumerate(args):
        if a == "--expand" and i + 1 < len(args):
            try:
                expand = max(0, int(args[i + 1]))
            except ValueError:
                console.print(f"[red]--expand requires an integer[/red]")
                return 1

    x_range = list(range(SEED_X - expand, SEED_X + expand + 1))
    y_range = list(range(SEED_Y - expand, SEED_Y + expand + 1))
    n_cand  = len(x_range) * len(y_range) * 4

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — DTLA Neighbor Expander[/bold magenta]\n"
        f"Seed: [cyan]{SEED_X}_{SEED_Y}[/cyan]   "
        f"Expand: [white]±{expand}[/white]   "
        f"x stems: [white]{x_range[0]}–{x_range[-1]}[/white]   "
        f"y stems: [white]{y_range[0]}–{y_range[-1]}[/white]   "
        f"Candidates: [white]{n_cand}[/white]",
        box=box.ROUNDED,
    ))

    entries = generate_candidates(expand)

    n_on_disk = sum(1 for e in entries if e.on_disk)
    console.print(
        f"\n[dim]Disk check: {n_on_disk}/{n_cand} candidates already on disk[/dim]"
    )

    entries = resolve(entries, use_tnm=use_tnm, use_s3=use_s3, dry_run=dry_run)

    confirmed = [e for e in entries if e.confirmed]
    real_not_disk = [e for e in confirmed if not e.on_disk]
    unconfirmed   = [e for e in entries if not e.confirmed]

    _print_grid(entries, expand)
    _print_tile_table(confirmed)

    if unconfirmed:
        console.print()
        console.print(
            f"[dim]{len(unconfirmed)} candidate(s) not found in TNM or S3 "
            f"— no real USGS product at those grid positions:[/dim]"
        )
        for e in unconfirmed:
            console.print(f"  [dim]{e.tile_id}  {e.filename}[/dim]")

    console.print()
    console.print(Panel(
        f"  Confirmed real tiles:    [green]{len(confirmed)}[/green]\n"
        f"  On disk now:            [green]{n_on_disk}[/green]\n"
        f"  Available to download:  "
        f"{'[cyan]' if real_not_disk else '[green]'}"
        f"{len(real_not_disk)}"
        f"{'[/cyan]' if real_not_disk else '[/green]'}\n"
        f"  Not a real tile:        [dim]{len(unconfirmed)}[/dim]",
        box=box.ROUNDED,
    ))

    if real_not_disk and not do_dl:
        console.print(
            f"\n[dim]To download {len(real_not_disk)} missing tile(s):[/dim]\n"
            f"  [cyan]python scripts/la/expand_dtla_tiles.py "
            f"--expand {expand} --download[/cyan]"
        )

    if do_dl and not dry_run:
        fail_count = download_missing(entries)
        return 1 if fail_count else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
