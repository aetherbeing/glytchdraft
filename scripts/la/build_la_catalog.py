"""
build_la_catalog.py  [LA pipeline - GlitchOS.io]

Build an authoritative LAZ tile catalog for the USGS Los Angeles 2016 dataset.
No grid enumeration. No synthetic IDs. Every remote tile comes from the USGS
RockyWeb vdelivery directory; local fallback uses files already on disk.

Remote source:
  https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/
  USGS_LPC_CA_LosAngeles_2016_LAS_2018/laz/

Output:
  /mnt/t7/la/data_raw/la_2016_laz_catalog.json

Usage:
    python scripts/la/build_la_catalog.py
    python scripts/la/build_la_catalog.py --force
    python scripts/la/build_la_catalog.py --local-only
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tile_config import LAZ_DIR, SRC_EPSG

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

console = Console()

CATALOG_PATH = LAZ_DIR.parent / "la_2016_laz_catalog.json"

PROJECT = "CA_LosAngeles_2016"
DATASET = "USGS_LPC_CA_LosAngeles_2016_LAS_2018"
FILENAME_PREFIX = "USGS_LPC_CA_LosAngeles_2016_L4_"
SEED_FILENAME = "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"

ROCKYWEB_BASE = (
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/"
    f"Projects/{DATASET}/laz/"
)
HTTP_TIMEOUT = 60

GRID_STEP = 3000.0
HALF_STEP = 1500.0
QUARTERS = ("a", "b", "c", "d")

# NW=a, NE=b, SW=c, SE=d (USGS CA 2016 convention)
QUARTER_OFFSETS = {
    "a": (0, HALF_STEP, HALF_STEP, GRID_STEP),
    "b": (HALF_STEP, HALF_STEP, GRID_STEP, GRID_STEP),
    "c": (0, 0, HALF_STEP, HALF_STEP),
    "d": (HALF_STEP, 0, GRID_STEP, HALF_STEP),
}

_transformer_to_4326 = None


class _HrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _to_4326():
    global _transformer_to_4326
    if _transformer_to_4326 is None:
        from pyproj import Transformer

        _transformer_to_4326 = Transformer.from_crs(SRC_EPSG, 4326, always_xy=True)
    return _transformer_to_4326


def _quarter_bboxes(stem_x: int, stem_y: int, quarter: str) -> tuple[dict, dict]:
    ox = float(stem_x) * 1000.0
    oy = float(stem_y) * 1000.0
    dx0, dy0, dx1, dy1 = QUARTER_OFFSETS[quarter]
    bbox_2229 = {
        "xmin": ox + dx0,
        "ymin": oy + dy0,
        "xmax": ox + dx1,
        "ymax": oy + dy1,
    }
    try:
        t = _to_4326()
        corners = [
            t.transform(bbox_2229["xmin"], bbox_2229["ymin"]),
            t.transform(bbox_2229["xmax"], bbox_2229["ymin"]),
            t.transform(bbox_2229["xmin"], bbox_2229["ymax"]),
            t.transform(bbox_2229["xmax"], bbox_2229["ymax"]),
        ]
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        bbox_4326 = {
            "xmin": min(lons),
            "ymin": min(lats),
            "xmax": max(lons),
            "ymax": max(lats),
        }
    except Exception:
        bbox_4326 = {}
    return bbox_2229, bbox_4326


def parse_filename(filename: str) -> tuple[int, int, str] | None:
    """
    Parse USGS_LPC_CA_LosAngeles_2016_L4_{X}_{Y}{q}_LAS_2018.laz.
    Returns (stem_x, stem_y, quarter) or None.
    """
    if not filename.startswith(FILENAME_PREFIX) or not filename.endswith(".laz"):
        return None
    stem = filename.replace("_LAS_2018.laz", "").replace(".laz", "")
    parts = stem.split("_")
    if len(parts) < 8:
        return None
    try:
        x_str = parts[6]
        yq_str = parts[7]
        quarter = yq_str[-1]
        y_str = yq_str[:-1]
        if quarter not in QUARTERS:
            return None
        return int(x_str), int(y_str), quarter
    except (IndexError, ValueError):
        return None


def _get(url: str, timeout: int = HTTP_TIMEOUT) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code not in (403, 404):
            console.print(f"  [yellow]HTTP {e.code}: {url[:100]}[/yellow]")
        return None
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        msg = "timed out" if "timed out" in str(reason).lower() else str(reason)
        console.print(f"  [yellow]{msg}: {url[:100]}[/yellow]")
        return None
    except Exception as e:
        console.print(f"  [yellow]Request error: {e}[/yellow]")
        return None


def _rockyweb_url(filename: str) -> str:
    return urllib.parse.urljoin(ROCKYWEB_BASE, urllib.parse.quote(filename))


def _extract_laz_links(raw_html: bytes) -> list[tuple[str, int | None, str | None]]:
    parser = _HrefParser()
    parser.feed(raw_html.decode("utf-8", errors="replace"))

    entries: dict[str, tuple[str, int | None, str | None]] = {}
    for href in parser.hrefs:
        href_path = urllib.parse.urlparse(href).path
        filename = urllib.parse.unquote(href_path.rsplit("/", 1)[-1])
        if parse_filename(filename) is None:
            continue
        entries[filename] = (filename, None, urllib.parse.urljoin(ROCKYWEB_BASE, href))

    return [entries[k] for k in sorted(entries)]


def fetch_via_rockyweb() -> list[tuple[str, int | None, str | None]]:
    console.print("\n[bold cyan]Source: USGS RockyWeb vdelivery[/bold cyan]")
    console.print(f"  dataset: [white]{DATASET}[/white]")
    console.print(f"  base: [dim]{ROCKYWEB_BASE}[/dim]")

    raw = _get(ROCKYWEB_BASE)
    if not raw:
        console.print("  [yellow]Could not read RockyWeb directory listing.[/yellow]")
        return []

    entries = _extract_laz_links(raw)
    console.print(f"  [green]{len(entries)} RockyWeb LAZ URL(s) found[/green]")
    return entries


def fetch_via_local(with_rockyweb_urls: bool = False) -> list[tuple[str, int | None, str | None]]:
    console.print("\n[bold cyan]Source: local LAZ directory[/bold cyan]")
    console.print(f"  directory: [dim]{LAZ_DIR}[/dim]")

    if not LAZ_DIR.exists():
        console.print("  [yellow]Local LAZ directory does not exist.[/yellow]")
        return []

    results: list[tuple[str, int | None, str | None]] = []
    skipped = 0
    for path in sorted(LAZ_DIR.glob("*.laz")):
        if parse_filename(path.name) is None:
            skipped += 1
            continue
        url = _rockyweb_url(path.name) if with_rockyweb_urls else None
        results.append((path.name, path.stat().st_size, url))

    console.print(f"  [green]{len(results)} local {PROJECT!r} LAZ file(s)[/green]")
    if skipped:
        console.print(f"  [yellow]Skipped {skipped} unparseable local LAZ file(s)[/yellow]")
    return results


def _entry_to_tile(filename: str, size_bytes: int | None, url: str | None) -> dict | None:
    parsed = parse_filename(filename)
    if parsed is None:
        return None

    stem_x, stem_y, quarter = parsed
    bbox_2229, bbox_4326 = _quarter_bboxes(stem_x, stem_y, quarter)
    local_path = LAZ_DIR / filename
    on_disk = local_path.exists()

    return {
        "filename": filename,
        "local_path": str(local_path),
        "download_url": url,
        "project": PROJECT,
        "dataset": DATASET,
        "tile_stem": f"{stem_x}_{stem_y}{quarter}",
        "stem_x": stem_x,
        "stem_y": stem_y,
        "quarter": quarter,
        "bbox_2229": bbox_2229,
        "bbox_4326": bbox_4326 if bbox_4326 else None,
        "source_size_bytes": size_bytes,
        "on_disk": on_disk,
    }


def build_catalog(
    rockyweb_first: bool = True,
    local_fallback: bool = True,
    local_only: bool = False,
) -> dict:
    raw_entries: list[tuple[str, int | None, str | None]] = []
    source = "unknown"

    if local_only:
        raw_entries = fetch_via_local(with_rockyweb_urls=False)
        source = "local"

    if not raw_entries and rockyweb_first and not local_only:
        raw_entries = fetch_via_rockyweb()
        source = "rockyweb"

    if not raw_entries and local_fallback:
        raw_entries = fetch_via_local(with_rockyweb_urls=not local_only)
        source = "rockyweb_local_names" if raw_entries and not local_only else "local"

    if not raw_entries:
        console.print(
            "\n[yellow]No RockyWeb or local LAZ entries found. "
            "Writing an empty local catalog.[/yellow]"
        )
        source = "local"

    console.print(f"\n[dim]Parsing {len(raw_entries)} filenames...[/dim]")
    tiles = []
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("  Parsing tiles", total=len(raw_entries))

        for filename, size_bytes, url in raw_entries:
            tile = _entry_to_tile(filename, size_bytes, url)
            if tile is None:
                skipped += 1
            else:
                tiles.append(tile)
            progress.advance(task)

        progress.update(task, description=f"  Parsed {len(tiles)} tiles")

    if skipped:
        console.print(f"  [yellow]Skipped {skipped} unparseable entries[/yellow]")

    tiles.sort(key=lambda t: (t["stem_x"], t["stem_y"], t["quarter"]))

    catalog = {
        "schema_version": "1.0",
        "project": PROJECT,
        "dataset": DATASET,
        "source": source,
        "rockyweb_base": ROCKYWEB_BASE,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tile_count": len(tiles),
        "tiles": tiles,
    }

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    size_kb = CATALOG_PATH.stat().st_size / 1024
    console.print(
        f"\n[bold green]Catalog written:[/bold green] {len(tiles)} real tiles "
        f"({size_kb:.0f} KB)\n"
        f"  -> {CATALOG_PATH}"
    )
    return catalog


def main():
    args = sys.argv[1:]
    force = "--force" in args
    local_only = "--local-only" in args

    if CATALOG_PATH.exists() and not force and not local_only:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        n = data.get("tile_count", len(data.get("tiles", [])))
        ts = data.get("generated_at", "unknown")
        src = data.get("source", "unknown")
        console.print()
        console.print(
            Panel(
                f"[bold magenta]GlitchOS.io - LA 2016 LAZ Catalog[/bold magenta]\n"
                f"Catalog already exists: [green]{n} tiles[/green]   "
                f"source=[white]{src}[/white]   "
                f"built=[dim]{ts}[/dim]\n"
                f"  -> {CATALOG_PATH}\n\n"
                f"Pass [cyan]--force[/cyan] to re-fetch.",
                box=box.ROUNDED,
            )
        )
        return 0

    console.print()
    console.print(
        Panel(
            f"[bold magenta]GlitchOS.io - LA 2016 LAZ Catalog Builder[/bold magenta]\n"
            f"Dataset: [cyan]{DATASET}[/cyan]\n"
            f"Source: [dim]{ROCKYWEB_BASE}[/dim]\n"
            f"Output: [dim]{CATALOG_PATH}[/dim]",
            box=box.ROUNDED,
        )
    )

    catalog = build_catalog(local_only=local_only)

    n_on_disk = sum(1 for t in catalog["tiles"] if t["on_disk"])
    n_with_urls = sum(1 for t in catalog["tiles"] if t["download_url"])
    console.print(
        f"\nURLs: [green]{n_with_urls}[/green] / {catalog['tile_count']}   "
        f"On disk: [green]{n_on_disk}[/green] / {catalog['tile_count']}"
    )
    console.print(
        f"\nNext steps:\n"
        f"  [cyan]python scripts/la/list_city_tiles.py --city los_angeles --refresh[/cyan]\n"
        f"  [cyan]python scripts/la/download_city_tiles.py --city los_angeles[/cyan]"
        f"   - download missing real LAZ URLs into {LAZ_DIR}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
