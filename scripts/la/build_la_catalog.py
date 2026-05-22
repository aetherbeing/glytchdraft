"""
build_la_catalog.py  [LA pipeline — GlitchOS.io]

Build an authoritative LAZ tile catalog for the USGS CA_LosAngeles_2016 project.
No grid enumeration. No synthetic IDs. Every tile in the output is a real file.

Step 1 — Find source
  Probe S3 path prefixes using the known seed tile
  (USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz) to identify
  the working S3 directory.

Step 2 — List all tiles
  Paginate the S3 XML listing under the confirmed prefix.
  Fallback: paginated USGS TNM API query for the project.
  Final fallback: build from local /mnt/t7/la/data_raw/laz/*.laz.
  Every filename returned is a real USGS product.

Step 3 — Build catalog
  Parse each filename → stem_x, stem_y, quarter.
  Compute bbox_2229 and bbox_4326 per quarter tile via pyproj.
  Check local disk status.
  Write to /mnt/t7/la/data_raw/la_2016_laz_catalog.json.

Output schema:
  {
    "schema_version": "1.0",
    "project": "CA_LosAngeles_2016",
    "source": "s3" | "tnm" | "local",
    "s3_prefix": "StagedProducts/...",
    "generated_at": "2026-...",
    "tile_count": N,
    "tiles": [
      {
        "filename":      "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz",
        "local_path":    "/mnt/t7/la/data_raw/laz/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz",
        "download_url":  "https://prd-tnm.s3.amazonaws.com/...",
        "project":       "CA_LosAngeles_2016",
        "tile_stem":     "6477_1836b",
        "stem_x":        6477,
        "stem_y":        1836,
        "quarter":       "b",
        "bbox_2229":     {"xmin": ..., "ymin": ..., "xmax": ..., "ymax": ...},
        "bbox_4326":     {"xmin": ..., "ymin": ..., "xmax": ..., "ymax": ...},
        "s3_size_bytes": 489123456,
        "on_disk":       true
      }
    ]
  }

Usage:
    python scripts/la/build_la_catalog.py
    python scripts/la/build_la_catalog.py --force     # re-fetch even if cached
    python scripts/la/build_la_catalog.py --tnm-only  # skip S3, use TNM API
    python scripts/la/build_la_catalog.py --s3-only   # skip TNM fallback
    python scripts/la/build_la_catalog.py --local-only
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tile_config import LAZ_DIR, SRC_EPSG

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TextColumn,
    MofNCompleteColumn, TimeElapsedColumn,
)
from rich.panel import Panel
from rich import box

console = Console()

# ── paths ─────────────────────────────────────────────────────────────────────

CATALOG_PATH = LAZ_DIR.parent / "la_2016_laz_catalog.json"

# ── seed tile (known to exist, used to probe S3) ──────────────────────────────

SEED_FILENAME  = "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"
FILENAME_PREFIX = "USGS_LPC_CA_LosAngeles_2016_L4_"

# ── S3 ────────────────────────────────────────────────────────────────────────

S3_BUCKET  = "https://prd-tnm.s3.amazonaws.com"
S3_TIMEOUT = 30

# Probed in order; seed file HEAD-checked to confirm.
S3_PREFIXES = [
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016_D16/CA_LosAngeles_2016/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016/CA_LosAngeles_2016/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016_D16/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016/LAZ/",
]

S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"

# ── TNM ───────────────────────────────────────────────────────────────────────

TNM_URL      = "https://tnmaccess.nationalmap.gov/api/v1/products"
TNM_DATASETS = "Lidar Point Cloud (LPC)"
TNM_PROJECT  = "CA_LosAngeles_2016"
TNM_TIMEOUT  = 60

# Wide bbox covering all of LA County (used only for TNM fallback)
TNM_BBOX = "-118.95,33.70,-117.65,34.85"

# ── quarter geometry ──────────────────────────────────────────────────────────

GRID_STEP   = 3000.0  # US survey feet per stem cell
HALF_STEP   = 1500.0
QUARTERS    = ("a", "b", "c", "d")

# NW=a, NE=b, SW=c, SE=d  (USGS CA 2016 convention)
QUARTER_OFFSETS = {
    "a": (0,         HALF_STEP, HALF_STEP,  GRID_STEP),
    "b": (HALF_STEP, HALF_STEP, GRID_STEP,  GRID_STEP),
    "c": (0,         0,         HALF_STEP,  HALF_STEP),
    "d": (HALF_STEP, 0,         GRID_STEP,  HALF_STEP),
}

_transformer_to_4326 = None


def _to_4326():
    global _transformer_to_4326
    if _transformer_to_4326 is None:
        from pyproj import Transformer
        _transformer_to_4326 = Transformer.from_crs(SRC_EPSG, 4326, always_xy=True)
    return _transformer_to_4326


def _quarter_bboxes(stem_x: int, stem_y: int, quarter: str) -> tuple[dict, dict]:
    """Return (bbox_2229, bbox_4326) for one quarter tile."""
    ox = float(stem_x) * 1000.0
    oy = float(stem_y) * 1000.0
    dx0, dy0, dx1, dy1 = QUARTER_OFFSETS[quarter]
    b2229 = {
        "xmin": ox + dx0, "ymin": oy + dy0,
        "xmax": ox + dx1, "ymax": oy + dy1,
    }
    try:
        t = _to_4326()
        corners = [
            t.transform(b2229["xmin"], b2229["ymin"]),
            t.transform(b2229["xmax"], b2229["ymin"]),
            t.transform(b2229["xmin"], b2229["ymax"]),
            t.transform(b2229["xmax"], b2229["ymax"]),
        ]
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        b4326 = {"xmin": min(lons), "ymin": min(lats),
                 "xmax": max(lons), "ymax": max(lats)}
    except Exception:
        b4326 = {}
    return b2229, b4326


# ── filename parsing ──────────────────────────────────────────────────────────

def parse_filename(filename: str) -> tuple[int, int, str] | None:
    """
    Parse USGS_LPC_CA_LosAngeles_2016_L4_{X}_{Y}{q}_LAS_2018.laz
    Returns (stem_x, stem_y, quarter) or None.
    """
    if not filename.startswith(FILENAME_PREFIX) or not filename.endswith(".laz"):
        return None
    stem = filename.replace("_LAS_2018.laz", "").replace(".laz", "")
    parts = stem.split("_")
    # parts: USGS LPC CA LosAngeles 2016 L4 {X} {Yq}
    if len(parts) < 8:
        return None
    try:
        x_str  = parts[6]
        yq_str = parts[7]
        q      = yq_str[-1]
        y_str  = yq_str[:-1]
        if q not in QUARTERS:
            return None
        return int(x_str), int(y_str), q
    except (ValueError, IndexError):
        return None


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(url: str, timeout: int) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code not in (403, 404):
            console.print(f"  [yellow]HTTP {e.code}: {url[:80]}[/yellow]")
        return None
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        msg = "timed out" if "timed out" in str(reason).lower() else str(reason)
        console.print(f"  [yellow]{msg}: {url[:80]}[/yellow]")
        return None
    except Exception as e:
        console.print(f"  [yellow]Request error: {e}[/yellow]")
        return None


def _head_200(url: str, timeout: int = S3_TIMEOUT) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── S3 source ─────────────────────────────────────────────────────────────────

def _find_s3_prefix() -> str | None:
    """Probe prefixes using the seed file to find the working S3 directory."""
    console.print(f"  Seed probe: [dim]{SEED_FILENAME}[/dim]")
    for prefix in S3_PREFIXES:
        url = f"{S3_BUCKET}/{prefix}{SEED_FILENAME}"
        console.print(f"    [dim]{prefix}[/dim] ... ", end="")
        if _head_200(url):
            console.print("[green]✓[/green]")
            return prefix
        console.print("[red]✗[/red]")
    return None


def _s3_list_page(prefix: str, token: str | None) -> tuple[list[tuple[str, int]], str | None]:
    """One page of S3 XML listing. Returns ([(key, size_bytes)], next_token)."""
    params: dict = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
    if token:
        params["continuation-token"] = token
    url = f"{S3_BUCKET}/?" + urllib.parse.urlencode(params)
    raw = _get(url, timeout=S3_TIMEOUT)
    if not raw:
        return [], None

    def _tag(name: str) -> str:
        return f"{{{S3_NS}}}{name}"

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        console.print(f"  [yellow]XML parse error: {e}[/yellow]")
        return [], None

    entries = []
    for content in root.findall(_tag("Contents")):
        key_el  = content.find(_tag("Key"))
        size_el = content.find(_tag("Size"))
        if key_el is None or not key_el.text:
            continue
        key  = key_el.text
        size = int(size_el.text) if size_el is not None and size_el.text else 0
        if key.endswith(".laz"):
            entries.append((key, size))

    next_tok = None
    trunc = root.find(_tag("IsTruncated"))
    if trunc is not None and trunc.text == "true":
        tok_el = root.find(_tag("NextContinuationToken"))
        if tok_el is not None:
            next_tok = tok_el.text

    return entries, next_tok


def fetch_via_s3() -> tuple[list[tuple[str, int, str]], str] | tuple[None, None]:
    """
    List all LAZ files in the project S3 directory.
    Returns ([(filename, size_bytes, download_url)], working_prefix) or (None, None).
    """
    console.print("\n[bold cyan]Source: S3 directory listing[/bold cyan]")
    prefix = _find_s3_prefix()
    if not prefix:
        console.print("  [red]Could not locate S3 prefix.[/red]")
        return None, None

    console.print(f"  [green]Prefix: {prefix}[/green]")
    console.print("  Listing all LAZ files (paginated)...")

    all_entries: list[tuple[str, int, str]] = []
    token = None
    page  = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console, transient=False,
    ) as progress:
        task = progress.add_task("  S3 page 1", total=None)

        while True:
            page += 1
            keys, token = _s3_list_page(prefix, token)

            for key, size in keys:
                filename = key.rsplit("/", 1)[-1]
                if not filename.startswith(FILENAME_PREFIX):
                    continue
                url = f"{S3_BUCKET}/{key}"
                all_entries.append((filename, size, url))

            progress.update(
                task,
                description=f"  S3 page {page}  files={len(all_entries)}",
            )
            if not token:
                break

        progress.update(task, description=f"  S3 done  {len(all_entries)} LAZ files")

    console.print(f"  [green]{len(all_entries)} LAZ files found[/green]")
    return all_entries, prefix


# ── TNM fallback ──────────────────────────────────────────────────────────────

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


def _tnm_filename_from_item(item: dict) -> str | None:
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


def fetch_via_tnm() -> list[tuple[str, int, str]]:
    """
    Paginated TNM API query for all CA_LosAngeles_2016 LPC products.
    Returns [(filename, 0, download_url)] — sizes not available from TNM.
    """
    console.print("\n[bold cyan]Source: USGS TNM API (paginated)[/bold cyan]")
    console.print(f"  bbox: {TNM_BBOX}")

    results: list[tuple[str, int, str]] = []
    offset = 0
    page   = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console, transient=False,
    ) as progress:
        task = progress.add_task("  TNM page 1", total=None)

        while True:
            page += 1
            params = {
                "datasets":     TNM_DATASETS,
                "bbox":         TNM_BBOX,
                "max":          "1000",
                "offset":       str(offset),
                "outputFormat": "json",
            }
            url = TNM_URL + "?" + urllib.parse.urlencode(params)
            raw = _get(url, timeout=TNM_TIMEOUT)
            if not raw:
                break

            data  = json.loads(raw)
            items = data.get("items", [])
            total = data.get("total", 0)

            for item in items:
                if TNM_PROJECT.lower() not in item.get("title", "").lower():
                    continue
                fn  = _tnm_filename_from_item(item)
                url = _tnm_url_from_item(item)
                if fn and url:
                    results.append((fn, 0, url))

            offset += len(items)
            progress.update(
                task,
                description=(
                    f"  TNM page {page}  "
                    f"fetched {offset}/{total}  "
                    f"matched {len(results)}"
                ),
            )
            if not items or offset >= total:
                break

        progress.update(task, description=f"  TNM done  {len(results)} matched")

    console.print(f"  [green]{len(results)} {TNM_PROJECT!r} tiles[/green]")
    return results


# ── catalog builder ───────────────────────────────────────────────────────────

def fetch_via_local() -> list[tuple[str, int, str | None]]:
    """
    Build a catalog source from LAZ files already present on local disk.
    Returns [(filename, size_bytes, None)].
    """
    console.print("\n[bold cyan]Source: local LAZ directory[/bold cyan]")
    console.print(f"  directory: [dim]{LAZ_DIR}[/dim]")

    if not LAZ_DIR.exists():
        console.print("  [yellow]Local LAZ directory does not exist.[/yellow]")
        return []

    results: list[tuple[str, int, str | None]] = []
    skipped = 0
    for path in sorted(LAZ_DIR.glob("*.laz")):
        if parse_filename(path.name) is None:
            skipped += 1
            continue
        results.append((path.name, path.stat().st_size, None))

    console.print(f"  [green]{len(results)} local {TNM_PROJECT!r} LAZ file(s)[/green]")
    if skipped:
        console.print(f"  [yellow]Skipped {skipped} unparseable local LAZ file(s)[/yellow]")
    return results


def build_catalog(
    s3_first: bool = True,
    tnm_fallback: bool = True,
    local_fallback: bool = True,
    local_only: bool = False,
) -> dict:
    """
    Fetch the full tile list, parse filenames, compute bboxes, write catalog.
    Returns the catalog dict.
    """
    raw_entries: list[tuple[str, int, str | None]] = []
    source      = "unknown"
    s3_prefix   = ""

    if local_only:
        raw_entries = fetch_via_local()
        source      = "local"

    if not raw_entries and s3_first and not local_only:
        entries, prefix = fetch_via_s3()
        if entries:
            raw_entries = entries
            source      = "s3"
            s3_prefix   = prefix or ""

    if not raw_entries and tnm_fallback and not local_only:
        raw_entries = fetch_via_tnm()
        source      = "tnm"

    if not raw_entries and local_fallback:
        raw_entries = fetch_via_local()
        source      = "local"

    if not raw_entries:
        console.print(
            "\n[yellow]No S3, TNM, or local LAZ entries found. "
            "Writing an empty local catalog.[/yellow]"
        )
        source = "local"

    # Parse and enrich
    console.print(f"\n[dim]Parsing {len(raw_entries)} filenames...[/dim]")
    tiles = []
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console, transient=False,
    ) as progress:
        task = progress.add_task("  Parsing tiles", total=len(raw_entries))

        for filename, size_bytes, url in raw_entries:
            parsed = parse_filename(filename)
            if parsed is None:
                skipped += 1
                progress.advance(task)
                continue

            stem_x, stem_y, quarter = parsed
            bbox_2229, bbox_4326   = _quarter_bboxes(stem_x, stem_y, quarter)
            local_path = LAZ_DIR / filename
            on_disk = local_path.exists()

            tiles.append({
                "filename":      filename,
                "local_path":    str(local_path),
                "download_url":  url,
                "project":       TNM_PROJECT,
                "tile_stem":     f"{stem_x}_{stem_y}{quarter}",
                "stem_x":        stem_x,
                "stem_y":        stem_y,
                "quarter":       quarter,
                "bbox_2229":     bbox_2229,
                "bbox_4326":     bbox_4326 if bbox_4326 else None,
                "s3_size_bytes": size_bytes if source == "s3" and size_bytes else None,
                "on_disk":       on_disk,
            })
            progress.advance(task)

        progress.update(task, description=f"  Parsed {len(tiles)} tiles")

    if skipped:
        console.print(f"  [yellow]Skipped {skipped} unparseable entries[/yellow]")

    # Sort by stem_x, stem_y, quarter for deterministic output
    tiles.sort(key=lambda t: (t["stem_x"], t["stem_y"], t["quarter"]))

    catalog = {
        "schema_version": "1.0",
        "project":        "CA_LosAngeles_2016",
        "source":         source,
        "s3_prefix":      s3_prefix,
        "s3_base":        S3_BUCKET,
        "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tile_count":     len(tiles),
        "tiles":          tiles,
    }

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    size_kb = CATALOG_PATH.stat().st_size / 1024
    console.print(
        f"\n[bold green]Catalog written:[/bold green] {len(tiles)} real tiles  "
        f"({size_kb:.0f} KB)\n"
        f"  → {CATALOG_PATH}"
    )

    return catalog


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    force    = "--force"    in args
    s3_only  = "--s3-only"  in args
    tnm_only = "--tnm-only" in args
    local_only = "--local-only" in args

    if CATALOG_PATH.exists() and not force and not local_only:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        n    = data.get("tile_count", len(data.get("tiles", [])))
        ts   = data.get("generated_at", "unknown")
        src  = data.get("source", "unknown")
        console.print()
        console.print(Panel(
            f"[bold magenta]GlitchOS.io — LA 2016 LAZ Catalog[/bold magenta]\n"
            f"Catalog already exists: [green]{n} tiles[/green]   "
            f"source=[white]{src}[/white]   "
            f"built=[dim]{ts}[/dim]\n"
            f"  → {CATALOG_PATH}\n\n"
            f"Pass [cyan]--force[/cyan] to re-fetch.",
            box=box.ROUNDED,
        ))
        return 0

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — LA 2016 LAZ Catalog Builder[/bold magenta]\n"
        f"Seed: [cyan]{SEED_FILENAME}[/cyan]\n"
        f"Output: [dim]{CATALOG_PATH}[/dim]",
        box=box.ROUNDED,
    ))

    try:
        catalog = build_catalog(
            s3_first    = not tnm_only,
            tnm_fallback= not s3_only,
            local_only  = local_only,
        )
    except RuntimeError as e:
        console.print(f"\n[red]ERROR: {e}[/red]")
        return 1

    n_on_disk = sum(1 for t in catalog["tiles"] if t["on_disk"])
    console.print(
        f"\nNext steps:\n"
        f"  [cyan]python scripts/la/list_city_tiles.py --city los_angeles[/cyan]"
        f"   — filter catalog by city boundary\n"
        f"  [cyan]python scripts/la/expand_dtla_tiles.py --expand 2[/cyan]"
        f"   — find real DTLA neighbors"
    )
    console.print(
        f"\nOn disk already: [green]{n_on_disk}[/green] / {catalog['tile_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
