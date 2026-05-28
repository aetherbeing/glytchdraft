"""
build_detroit_catalog.py  [GlitchOS city pipeline — Detroit]

Preflight / catalog tool for the Detroit LAZ dataset.

Two modes:
  --remote   Query USGS TNM API and build a remote URL manifest (no download).
             Writes: detroit_remote_manifest.json  (all tiles available from TNM)
  (default)  Scan on-disk LAZ files in laz_dir and build a local catalog.
             Writes: detroit_catalog.json  (only files already downloaded)

Does NOT run the processing pipeline, move, or delete raw LAZ.

Usage:
    python scripts/detroit/build_detroit_catalog.py --help
    python scripts/detroit/build_detroit_catalog.py --dry-run
    python scripts/detroit/build_detroit_catalog.py --remote --dry-run
    python scripts/detroit/build_detroit_catalog.py --spatial-filter --dry-run
    python scripts/detroit/build_detroit_catalog.py \\
        --output /mnt/t7/detroit/data_processed/detroit/catalogs/detroit_catalog.json

Source:
    USGS 3DEP TNM — Lidar Point Cloud (LPC)
    TNM API: https://tnmaccess.nationalmap.gov/api/v1/products
    Expected CRS: NAD83(2011) / UTM Zone 17N  (EPSG:6344)
    Target CRS:   UTM Zone 17N  (EPSG:32617)
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "cities" / "detroit.json"
DEFAULT_CATALOG = Path("/mnt/t7/detroit/data_processed/detroit/catalogs/detroit_catalog.json")
DEFAULT_REMOTE_MANIFEST = Path("/mnt/t7/detroit/data_processed/detroit/catalogs/detroit_remote_manifest.json")

TNM_BASE = "https://tnmaccess.nationalmap.gov/api/v1/products"
HTTP_TIMEOUT = 60

# LAS public header bbox at byte offset 179
_LAS_BBOX_OFFSET = 179
_LAS_HDR_BYTES = 227

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def _pr(msg: str) -> None:
    if console:
        console.print(msg)
    else:
        print(msg)


# ── TNM API ────────────────────────────────────────────────────────────────────

def _build_tnm_url(bbox: dict, max_results: int = 500) -> str:
    """
    Build TNM API URL without urllib.parse.urlencode.

    urlencode encodes bbox commas as %2C and spaces as +, both of which
    cause TNM's backend to reject the query.  Build the query string manually
    to match TNM's expected format: %20 for spaces, literal commas in bbox,
    unencoded parentheses in the dataset name.
    """
    # urllib.parse.quote encodes spaces as %20; safe="()" leaves parens literal
    datasets_enc = urllib.parse.quote("Lidar Point Cloud (LPC)", safe="()")
    bbox_str = f"{bbox['xmin']},{bbox['ymin']},{bbox['xmax']},{bbox['ymax']}"
    return (
        f"{TNM_BASE}?datasets={datasets_enc}"
        f"&bbox={bbox_str}"
        f"&prodFormats=LAS,LAZ"
        f"&max={max_results}"
    )


def query_tnm(bbox: dict, max_results: int = 500) -> list[dict] | None:
    """
    Query USGS TNM API for LPC tiles within bbox_4326.

    Returns:
        list[dict]  — product dicts on success (may be empty if no tiles in bbox)
        None        — on any network or API error (caller should treat as failure)

    Does not download any files.
    Does not raise exceptions — all errors are printed and None is returned.

    TNM backend notes:
      - Sometimes returns HTTP 200 with a malformed non-JSON body when its Lambda
        backend crashes: {errorMessage=[BadRequest] ...}
      - Sometimes returns HTTP 200 with valid JSON containing {"error": "..."} or
        {"errorMessage": "..."} keys on bad queries.
      - The datasets= filter can trigger 504 Gateway Timeout under load.
    """
    url = _build_tnm_url(bbox, max_results)
    _pr(f"  Querying TNM API: {url}")

    raw: bytes = b""
    status: int = 0
    content_type: str = "unknown"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "unknown")
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        content_type = exc.headers.get("Content-Type", "unknown") if exc.headers else "unknown"
        try:
            raw = exc.read()
        except Exception:
            raw = b""
        _pr(
            f"  [red]TNM HTTP {status}[/red]  Content-Type: {content_type}"
            if HAS_RICH else
            f"  TNM HTTP {status}  Content-Type: {content_type}"
        )
    except urllib.error.URLError as exc:
        _pr(
            f"  [red]TNM network error: {exc}[/red]"
            if HAS_RICH else
            f"  TNM network error: {exc}"
        )
        _pr(f"  Query URL: {url}")
        return None

    _pr(f"  TNM response: HTTP {status}  Content-Type: {content_type}")

    text = raw.decode("utf-8", errors="replace")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        snippet = text[:500]
        _pr(
            f"  [red]TNM returned non-JSON body (first 500 chars):[/red]\n{snippet}"
            if HAS_RICH else
            f"  TNM returned non-JSON body (first 500 chars):\n{snippet}"
        )
        _pr(f"  Query URL: {url}")
        _pr("  TNM API may be temporarily unavailable — try again later.")
        return None

    # TNM returns HTTP 200 with a JSON error body on bad queries or backend failures
    if "error" in data or "errorMessage" in data:
        err = data.get("error") or data.get("errorMessage") or "(no message)"
        _pr(
            f"  [red]TNM API error response:[/red] {err}"
            if HAS_RICH else
            f"  TNM API error response: {err}"
        )
        _pr(f"  Query URL: {url}")
        return None

    items: list[dict] = data.get("items", [])
    _pr(f"  TNM returned {len(items)} item(s)")
    return items


def build_remote_manifest(cfg: dict) -> dict | None:
    """
    Query TNM API and return a remote URL manifest (no download).
    Returns None if the TNM query failed (caller should exit nonzero).
    """
    bbox = cfg["bbox_4326"]
    items = query_tnm(bbox)
    if items is None:
        return None
    laz_dir = Path(cfg["laz_dir"])

    tiles = []
    for item in items:
        urls = item.get("downloadURLs", {})
        download_url = (
            urls.get("LAZ") or urls.get("LAS")
            or next(iter(urls.values()), None)
        )
        if not download_url:
            continue
        filename = urllib.parse.unquote(download_url.rsplit("/", 1)[-1])
        local_path = laz_dir / filename
        tile: dict = {
            "tile_id": Path(filename).stem,
            "filename": filename,
            "download_url": download_url,
            "local_path": str(local_path),
            "on_disk": local_path.exists(),
            "project": item.get("sourceId", ""),
            "title": item.get("title", ""),
            "publication_date": item.get("publicationDate", ""),
            "file_size_bytes": item.get("sizeInBytes"),
        }
        tiles.append(tile)

    tiles.sort(key=lambda t: t["tile_id"])
    manifest = {
        "schema_version": "1.0",
        "city_slug": cfg.get("city_slug", "detroit"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tnm_bbox_4326": bbox,
        "tnm_query_url": _build_tnm_url(bbox),
        "tile_count": len(tiles),
        "on_disk_count": sum(1 for t in tiles if t["on_disk"]),
        "tiles": tiles,
    }
    return manifest


# ── local catalog (on-disk) ────────────────────────────────────────────────────

def scan_laz(laz_dir: Path) -> list[Path]:
    if not laz_dir.exists():
        return []
    return sorted(laz_dir.glob("*.laz")) + sorted(laz_dir.glob("*.las"))


def read_header_bbox(path: Path) -> tuple[float, float, float, float] | None:
    try:
        chunk = path.read_bytes()[:_LAS_HDR_BYTES]
        if len(chunk) < _LAS_HDR_BYTES or chunk[:4] != b"LASF":
            return None
        max_x, min_x, max_y, min_y = struct.unpack_from("<dddd", chunk, _LAS_BBOX_OFFSET)
        return min_x, min_y, max_x, max_y
    except Exception:
        return None


def _bbox_intersects(tile: tuple[float, float, float, float], city: dict) -> bool:
    return (
        tile[0] <= city["xmax"] and tile[2] >= city["xmin"] and
        tile[1] <= city["ymax"] and tile[3] >= city["ymin"]
    )


def apply_spatial_filter(
    files: list[Path], city_bbox: dict, output_epsg: int = 6344
) -> tuple[list[Path], list[Path], list[Path]]:
    """
    Partition files into (hit, miss, unknown) relative to city_bbox.
    Reads the LAS header bbox and reprojects to WGS84 using pyproj.
    Returns (hit, miss, unknown).
    """
    try:
        from pyproj import Transformer
        transformer = Transformer.from_crs(
            f"EPSG:{output_epsg}", "EPSG:4326", always_xy=True
        )
    except Exception:
        _pr("  [yellow]pyproj unavailable — spatial filter skipped[/yellow]" if HAS_RICH else
            "  pyproj unavailable — spatial filter skipped")
        return [], [], files

    hit: list[Path] = []
    miss: list[Path] = []
    unknown: list[Path] = []

    def _check(f: Path) -> tuple[Path, str]:
        raw = read_header_bbox(f)
        if raw is None:
            return f, "unknown"
        xmin, ymin, xmax, ymax = raw
        if -181.0 < xmin < 181.0 and -91.0 < ymin < 91.0:
            wb: tuple[float, float, float, float] = (xmin, ymin, xmax, ymax)
        else:
            lons, lats = zip(*[
                transformer.transform(cx, cy)
                for cx, cy in [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]
            ])
            wb = (min(lons), min(lats), max(lons), max(lats))
        return f, "hit" if _bbox_intersects(wb, city_bbox) else "miss"

    with ThreadPoolExecutor(max_workers=8) as ex:
        for path_result, outcome in ex.map(_check, files):
            if outcome == "hit":
                hit.append(path_result)
            elif outcome == "miss":
                miss.append(path_result)
            else:
                unknown.append(path_result)

    return hit, miss, unknown


def build_local_catalog(cfg: dict, spatial_filter: bool = False) -> dict:
    """Scan on-disk LAZ files and return a catalog dict ready for the pipeline."""
    laz_dir = Path(cfg["laz_dir"])
    all_files = scan_laz(laz_dir)
    total_bytes = sum(f.stat().st_size for f in all_files)

    pipeline_files = all_files
    spatial_meta: dict = {"spatial_filter_applied": False}

    if spatial_filter and all_files:
        city_bbox = cfg.get("bbox_4326")
        if not city_bbox:
            sys.exit("--spatial-filter requires bbox_4326 in config")
        src_epsg = cfg.get("source_epsg", 6344)
        hit, miss, unk = apply_spatial_filter(all_files, city_bbox, src_epsg)
        pipeline_files = sorted(hit, key=lambda p: p.name)
        bbox_bytes = sum(f.stat().st_size for f in pipeline_files)
        spatial_meta = {
            "spatial_filter_applied": True,
            "spatial_bbox_4326": city_bbox,
            "laz_count_bbox": len(hit),
            "laz_count_bbox_excluded": len(miss),
            "laz_count_bbox_unknown": len(unk),
            "bbox_selected_bytes": bbox_bytes,
            "bbox_selected_gb": round(bbox_bytes / 1_073_741_824, 2),
        }

    catalog: dict = {
        "schema_version": "1.0",
        "city_slug": cfg.get("city_slug", "detroit"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "laz_dir": str(laz_dir),
        "laz_count_total": len(all_files),
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / 1_073_741_824, 2),
        **spatial_meta,
        "first_file": pipeline_files[0].name if pipeline_files else None,
        "last_file":  pipeline_files[-1].name if pipeline_files else None,
        "files": [str(f) for f in pipeline_files],
        "count": len(pipeline_files),
        "output_root":   cfg.get("output_root"),
        "tile_manifest": cfg.get("tile_manifest"),
        "city_manifest": cfg.get("city_manifest"),
        "keep_raw_laz":  cfg.get("keep_raw_laz", True),
        "output_epsg":   cfg.get("output_epsg"),
    }
    return catalog


# ── report ─────────────────────────────────────────────────────────────────────

def print_local_report(catalog: dict) -> None:
    spatial_on = catalog.get("spatial_filter_applied", False)
    if HAS_RICH and console:
        console.print(Panel("[bold cyan]GlitchOS — Detroit LAZ Preflight[/bold cyan]", box=box.ROUNDED))
        t = Table(box=box.SIMPLE, show_header=False)
        t.add_column("Key", style="dim cyan", min_width=26)
        t.add_column("Value", style="white")
        t.add_row("LAZ directory",  catalog["laz_dir"])
        t.add_row("Files on disk",  f"{catalog['laz_count_total']}  ({catalog['total_gb']:.2f} GB)")
        if spatial_on:
            t.add_row("[bold green]After bbox filter[/bold green]",
                      f"[bold green]{catalog['laz_count_bbox']}[/bold green]"
                      f"  ({catalog['bbox_selected_gb']:.2f} GB)")
            t.add_row("  Excluded by bbox",   f"[dim]{catalog['laz_count_bbox_excluded']}[/dim]")
            t.add_row("  Unknown CRS/header", f"[dim]{catalog['laz_count_bbox_unknown']}[/dim]")
        t.add_row("Pipeline files", str(catalog["count"]))
        t.add_row("Output root",    str(catalog["output_root"]))
        t.add_row("Output EPSG",    str(catalog["output_epsg"]))
        console.print(t)
    else:
        print(f"  LAZ directory : {catalog['laz_dir']}")
        print(f"  Files on disk : {catalog['laz_count_total']}  ({catalog['total_gb']:.2f} GB)")
        if spatial_on:
            print(f"  After bbox    : {catalog['laz_count_bbox']}  ({catalog['bbox_selected_gb']:.2f} GB)")
        print(f"  Pipeline files: {catalog['count']}")
        print(f"  Output root   : {catalog['output_root']}")
        print(f"  Output EPSG   : {catalog['output_epsg']}")


def print_remote_report(manifest: dict) -> None:
    if HAS_RICH and console:
        console.print(Panel("[bold cyan]GlitchOS — Detroit Remote LAZ Manifest (TNM)[/bold cyan]", box=box.ROUNDED))
        t = Table(box=box.SIMPLE, show_header=False)
        t.add_column("Key", style="dim cyan", min_width=26)
        t.add_column("Value", style="white")
        t.add_row("TNM tiles found",  str(manifest["tile_count"]))
        t.add_row("Already on disk",  str(manifest["on_disk_count"]))
        t.add_row("Still to download", str(manifest["tile_count"] - manifest["on_disk_count"]))
        t.add_row("TNM query URL", manifest["tnm_query_url"])
        console.print(t)
    else:
        print(f"  TNM tiles found  : {manifest['tile_count']}")
        print(f"  Already on disk  : {manifest['on_disk_count']}")
        print(f"  Still to download: {manifest['tile_count'] - manifest['on_disk_count']}")
        if manifest["tiles"]:
            print(f"  First tile       : {manifest['tiles'][0]['filename']}")
            print(f"  Sample URL       : {manifest['tiles'][0]['download_url']}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detroit LAZ preflight / catalog builder.  "
            "Builds a local catalog from on-disk LAZ files, or queries USGS TNM "
            "for a remote URL manifest.  Does NOT run the pipeline or move/delete files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --dry-run\n"
            "  %(prog)s --remote --dry-run\n"
            "  %(prog)s --spatial-filter --dry-run\n"
            "  %(prog)s --output /mnt/t7/detroit/data_processed/detroit/catalogs/detroit_catalog.json\n"
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--remote", action="store_true",
                        help="Query TNM API and build remote URL manifest (no download)")
    parser.add_argument("--spatial-filter", action="store_true",
                        help="Filter on-disk files by city bbox_4326 (requires pyproj)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Write catalog/manifest JSON here (skipped with --dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print report only; do not write files")

    args = parser.parse_args()

    if not args.config.exists():
        sys.exit(f"Config not found: {args.config}")
    cfg = json.loads(args.config.read_text(encoding="utf-8"))

    if args.remote:
        manifest = build_remote_manifest(cfg)
        if manifest is None:
            _pr(
                "[red]ERROR:[/red] TNM query failed — see messages above. No files written."
                if HAS_RICH else
                "ERROR: TNM query failed — see messages above. No files written."
            )
            return 1
        print_remote_report(manifest)
        if args.dry_run:
            _pr("[dim]Dry run — no files written.[/dim]" if HAS_RICH else "Dry run — no files written.")
            return 0
        out = args.output or DEFAULT_REMOTE_MANIFEST
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _pr(f"[green]Remote manifest written:[/green] {out}" if HAS_RICH else f"Remote manifest written: {out}")
    else:
        catalog = build_local_catalog(cfg, spatial_filter=args.spatial_filter)
        print_local_report(catalog)
        if args.dry_run:
            _pr("[dim]Dry run — no files written.[/dim]" if HAS_RICH else "Dry run — no files written.")
            return 0
        out = args.output or DEFAULT_CATALOG
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
        _pr(f"[green]Catalog written:[/green] {out}" if HAS_RICH else f"Catalog written: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
