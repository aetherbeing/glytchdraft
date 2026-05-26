"""
build_miami_catalog.py  [GlitchOS city pipeline — Miami]

Query the USGS TNM API for all FL_MiamiDade_D23 LAZ tiles and save
a local catalog JSON alongside the LAZ directory.

Catalog path:  /mnt/e/miami/data_raw/miami_d23_catalog.json
               (E:\\miami\\data_raw\\miami_d23_catalog.json on Windows)

Usage:
    python scripts/miami/build_miami_catalog.py
    python scripts/miami/build_miami_catalog.py --force    # re-query even if cached
    python scripts/miami/build_miami_catalog.py --dry-run  # print summary, don't write

Exit codes:
    0  catalog written (or already exists)
    1  API returned no tiles matching FL_MiamiDade_D23
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import miami_city_config as CFG

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None

# ── USGS TNM API ───────────────────────────────────────────────────────────────

TNM_BASE    = "https://tnmaccess.nationalmap.gov/api/v1/products"
HTTP_TIMEOUT = 90

# Search bbox: full Miami-Dade county (wider than the city, we filter afterwards)
SEARCH_BBOX = "-80.90,25.08,-80.07,25.98"

# Max items per request (TNM hard limit is 1000)
PAGE_MAX = 1000

DATASET_MATCH = CFG.USGS_DATASET_MATCH     # "MiamiDade_D23"
DATASET_FULL  = CFG.USGS_PROJECT_FULL      # "FL_MiamiDade_D23_LID2024"


# ── helpers ────────────────────────────────────────────────────────────────────

def _get_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        _warn(f"HTTP error: {exc}")
        return None


def _warn(msg: str):
    if console:
        console.print(f"  [yellow]{msg}[/yellow]")
    else:
        print(f"  WARN: {msg}", file=sys.stderr)


def _matches_dataset(item: dict) -> bool:
    """Return True if the TNM item belongs to the FL_MiamiDade_D23 dataset."""
    for field in ("title", "sourceName", "sourceId", "metaUrl", "downloadURL"):
        val = str(item.get(field) or "")
        if DATASET_MATCH in val:
            return True
    return False


def _laz_url(item: dict) -> str | None:
    """Extract the LAZ download URL from a TNM product item."""
    urls = item.get("urls") or {}
    if isinstance(urls, dict):
        for key in ("LAZ", "laz", "LiDAR", "lidar"):
            if urls.get(key):
                return urls[key]
    if item.get("downloadURL"):
        url = item["downloadURL"]
        if url.lower().endswith(".laz"):
            return url
    return None


def _filename_from_url(url: str) -> str | None:
    path = urllib.parse.urlparse(url).path
    name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
    return name if name.lower().endswith(".laz") else None


def _bbox_from_item(item: dict) -> dict | None:
    bb = item.get("boundingBox") or {}
    try:
        return {
            "xmin": float(bb.get("minX") or bb.get("xmin") or bb.get("minLon")),
            "ymin": float(bb.get("minY") or bb.get("ymin") or bb.get("minLat")),
            "xmax": float(bb.get("maxX") or bb.get("xmax") or bb.get("maxLon")),
            "ymax": float(bb.get("maxY") or bb.get("ymax") or bb.get("maxLat")),
        }
    except (TypeError, ValueError):
        return None


def _tile_id(filename: str) -> str:
    return Path(filename).stem   # strips .laz


# ── catalog build ──────────────────────────────────────────────────────────────

def _query_tnm_pages() -> list[dict]:
    """Page through USGS TNM API and collect all FL_MiamiDade_D23 LAZ items."""
    params = {
        "datasets":   "Lidar Point Cloud (LPC)",
        "bbox":       SEARCH_BBOX,
        "prodFormats":"LAZ",
        "outputFormat": "JSON",
        "max":        PAGE_MAX,
        "offset":     0,
    }

    items: list[dict] = []
    page = 1

    while True:
        url = f"{TNM_BASE}?{urllib.parse.urlencode(params)}"
        if console:
            console.print(f"  [dim]page {page}: {url[:100]}…[/dim]")
        else:
            print(f"  page {page}: querying TNM…")

        data = _get_json(url)
        if data is None:
            _warn("TNM API returned no data; stopping pagination")
            break

        page_items = data.get("items") or []
        items.extend(page_items)

        total = data.get("total", 0)
        if not page_items or len(items) >= total:
            break

        params["offset"] = len(items)
        page += 1
        time.sleep(0.5)   # be polite

    return items


def build_catalog(force: bool = False, dry_run: bool = False) -> dict | None:
    catalog_path = CFG.CATALOG_PATH
    laz_dir      = CFG.LAZ_DIR

    if catalog_path.exists() and not force and not dry_run:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        n = data.get("tile_count", 0)
        if console:
            console.print(f"[dim]Catalog cached: {catalog_path} ({n} tiles) — use --force to refresh[/dim]")
        else:
            print(f"Catalog cached: {catalog_path} ({n} tiles)")
        return data

    if console:
        console.print(Panel(
            "[bold magenta]GlitchOS.io — Miami LAZ Catalog Builder[/bold magenta]\n"
            f"Dataset: [cyan]{DATASET_FULL}[/cyan]\n"
            f"Search bbox: [dim]{SEARCH_BBOX}[/dim]\n"
            f"Catalog: [dim]{catalog_path}[/dim]",
            box=box.ROUNDED,
        ))
    else:
        print(f"Querying USGS TNM for {DATASET_FULL}…")

    raw_items = _query_tnm_pages()

    # Filter to the target dataset only
    matched = [it for it in raw_items if _matches_dataset(it)]
    if console:
        console.print(f"  [dim]TNM returned {len(raw_items)} item(s); "
                      f"{len(matched)} match '{DATASET_MATCH}'[/dim]")
    else:
        print(f"  {len(raw_items)} items from TNM; {len(matched)} match {DATASET_MATCH!r}")

    if not matched:
        _warn(
            f"No TNM items matched '{DATASET_MATCH}'.\n"
            "Falling back to on-disk tile discovery."
        )
        matched = []

    # Build tile records
    local_files = sorted(laz_dir.glob("*.laz")) if laz_dir.exists() else []
    local_by_name: dict[str, Path] = {p.name: p for p in local_files}

    tiles: list[dict] = []
    seen_filenames: set[str] = set()

    for item in matched:
        laz_url = _laz_url(item)
        if not laz_url:
            continue
        filename = _filename_from_url(laz_url)
        if not filename:
            continue
        if filename in seen_filenames:
            continue
        seen_filenames.add(filename)

        local_path = laz_dir / filename
        on_disk    = local_path.exists()
        size_bytes = item.get("sizeInBytes") or (
            local_path.stat().st_size if on_disk else None
        )

        tiles.append({
            "tile_id":      _tile_id(filename),
            "filename":     filename,
            "laz_filename": filename,
            "download_url": laz_url,
            "local_path":   str(local_path),
            "project":      DATASET_FULL,
            "dataset":      DATASET_MATCH,
            "bbox_4326":    _bbox_from_item(item),
            "on_disk":      on_disk,
            "size_bytes":   size_bytes,
            "size_mb":      round(size_bytes / 1_048_576, 1) if size_bytes else None,
        })

    # Add on-disk files not in TNM response (can happen for tiles outside bbox query)
    for fname, fpath in local_by_name.items():
        if fname in seen_filenames:
            continue
        if DATASET_MATCH not in fname and DATASET_FULL not in fname:
            continue
        tiles.append({
            "tile_id":      _tile_id(fname),
            "filename":     fname,
            "laz_filename": fname,
            "download_url": None,
            "local_path":   str(fpath),
            "project":      DATASET_FULL,
            "dataset":      DATASET_MATCH,
            "bbox_4326":    None,
            "on_disk":      True,
            "size_bytes":   fpath.stat().st_size,
            "size_mb":      round(fpath.stat().st_size / 1_048_576, 1),
        })
        seen_filenames.add(fname)

    tiles.sort(key=lambda t: t["tile_id"])
    n_on_disk = sum(1 for t in tiles if t["on_disk"])

    catalog = {
        "schema_version": "1.0",
        "project":        DATASET_FULL,
        "dataset":        DATASET_MATCH,
        "tnm_query_bbox": SEARCH_BBOX,
        "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tile_count":     len(tiles),
        "on_disk_count":  n_on_disk,
        "tiles":          tiles,
    }

    # Pretty summary table
    if console and tiles:
        tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
        tbl.add_column("Tile ID",     min_width=50)
        tbl.add_column("On Disk",     min_width=10)
        tbl.add_column("Size MB",     min_width=8, justify="right")
        tbl.add_column("BBox West",   min_width=10, justify="right")
        for t in tiles[:30]:
            bb = t["bbox_4326"] or {}
            disk = "[green]✓[/green]" if t["on_disk"] else "[dim]—[/dim]"
            sz   = str(t["size_mb"]) if t["size_mb"] else "[dim]?[/dim]"
            west = f"{bb.get('xmin','?'):.4f}" if bb else "[dim]?[/dim]"
            tbl.add_row(t["tile_id"], disk, sz, west)
        if len(tiles) > 30:
            tbl.add_row(f"… {len(tiles)-30} more …", "", "", "")
        console.print(tbl)

        total_gb = sum(t["size_mb"] or 0 for t in tiles) / 1024
        console.print(f"  [white]{len(tiles)}[/white] tiles   "
                      f"[green]{n_on_disk}[/green] on disk   "
                      f"[dim]{total_gb:.1f} GB total[/dim]")
    else:
        total_gb = sum(t["size_mb"] or 0 for t in tiles) / 1024
        print(f"  {len(tiles)} tiles, {n_on_disk} on disk, {total_gb:.1f} GB total")

    if dry_run:
        if console:
            console.print("[dim]Dry run — catalog not written.[/dim]")
        return catalog

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    if console:
        console.print(f"[green]Catalog written:[/green] {catalog_path}")
    else:
        print(f"Catalog written: {catalog_path}")

    return catalog


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    args    = sys.argv[1:]
    force   = "--force"   in args
    dry_run = "--dry-run" in args

    result = build_catalog(force=force, dry_run=dry_run)
    return 0 if result is not None else 1


if __name__ == "__main__":
    sys.exit(main())
