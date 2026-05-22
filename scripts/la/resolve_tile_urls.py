"""
resolve_tile_urls.py  [LA city pipeline — GlitchOS.io]

Resolve real USGS TNM download URLs for tiles listed in the city manifest.

The Problem
-----------
Grid-fallback tile discovery in tile_discovery.py generates synthetic tile IDs
(e.g. la_6357_1713a) from geometric enumeration of the State Plane grid.
These tiles have no download_url because they were never looked up in the TNM
catalog — they may or may not correspond to real USGS products.

This script is the authoritative URL resolution layer. It builds a complete
LAZ filename → download URL catalog by:

  Strategy 1 — Paginated USGS TNM API
    Query all LPC products matching CA_LosAngeles_2016 in the city bbox.
    Paginate until the full result set is fetched.
    Extract filename and download URL from each product.

  Strategy 2 — S3 XML directory listing (fallback)
    Enumerate known S3 path prefixes for the CA_LosAngeles_2016 project.
    Parse XML <Key> elements to recover all filenames on the bucket.
    Construct download URLs directly.

Then matches each manifest tile by laz_filename.

Outputs
-------
  - Table: resolved tiles  (synthetic_id → laz_filename → URL → source)
  - Table: unresolved tiles (synthetic_id → laz_filename → reason)
  - --patch  : write resolved URLs back into tile_manifest.json
  - --json   : machine-readable output to stdout

Unresolved tiles represent synthetic grid cells that have no real USGS
product and cannot be downloaded. They should be removed or marked invalid
before running download_city_tiles.py.

Usage
-----
    python scripts/la/resolve_tile_urls.py --city los_angeles
    python scripts/la/resolve_tile_urls.py --city los_angeles --patch
    python scripts/la/resolve_tile_urls.py --city los_angeles --json
    python scripts/la/resolve_tile_urls.py --city los_angeles --no-s3
    python scripts/la/resolve_tile_urls.py --city los_angeles --no-api
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

from tile_config import LAZ_DIR
from city_config import CITIES, CITY_ORDER

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich import box

console = Console()

# ── constants ──────────────────────────────────────────────────────────────────

TNM_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
TNM_DATASETS     = "Lidar Point Cloud (LPC)"
TNM_PROJECT_MATCH = "CA_LosAngeles_2016"
TNM_PAGE_SIZE    = 1000
TNM_TIMEOUT      = 60

S3_BUCKET        = "https://prd-tnm.s3.amazonaws.com"
S3_TIMEOUT       = 30

# Known path prefixes for the CA_LosAngeles_2016 project on S3.
# Tried in order — the first one that returns a valid XML listing wins.
S3_LAZ_PREFIXES = [
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016_D16/CA_LosAngeles_2016/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016/CA_LosAngeles_2016/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016_D16/LAZ/",
    "StagedProducts/Elevation/LPC/Projects/CA_LosAngeles_2016/LAZ/",
]

LAZ_FILENAME_PREFIX = "USGS_LPC_CA_LosAngeles_2016_L4_"


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(url: str, timeout: int, data: bytes | None = None) -> bytes | None:
    try:
        req = urllib.request.Request(
            url, data=data, headers={"User-Agent": "GlitchOS/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if "timed out" in str(reason).lower():
            console.print(f"  [yellow]Timeout ({timeout}s): {url[:80]}[/yellow]")
        else:
            console.print(f"  [yellow]HTTP error: {reason}[/yellow]")
        return None
    except Exception as e:
        console.print(f"  [yellow]HTTP error: {e}[/yellow]")
        return None


def _get_json(url: str, timeout: int = TNM_TIMEOUT) -> dict | None:
    raw = _get(url, timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        console.print(f"  [yellow]JSON parse error: {e}[/yellow]")
        return None


# ── Strategy 1: Paginated TNM API ─────────────────────────────────────────────

def _tnm_url_from_item(item: dict) -> str | None:
    """Extract the LAZ download URL from a TNM product dict."""
    urls = item.get("urls", {})
    # Try common key spellings
    for key in ("LAZ", "LAZ ", "laz", "downloadURL"):
        v = urls.get(key)
        if isinstance(v, str) and v.lower().endswith(".laz"):
            return v
    for v in urls.values():
        if isinstance(v, str) and v.lower().endswith(".laz"):
            return v
    return None


def _filename_from_item(item: dict) -> str | None:
    """Extract the LAZ filename from a TNM product dict."""
    url = _tnm_url_from_item(item)
    if url:
        name = url.rsplit("/", 1)[-1]
        if name.startswith(LAZ_FILENAME_PREFIX):
            return name

    title = item.get("title", "")
    if LAZ_FILENAME_PREFIX in title:
        idx  = title.find(LAZ_FILENAME_PREFIX)
        part = title[idx:].split()[0]
        if not part.endswith(".laz"):
            part += "_LAS_2018.laz"
        if part.startswith(LAZ_FILENAME_PREFIX):
            return part

    return None


def build_catalog_via_tnm(bbox: dict, project_match: str) -> dict[str, str]:
    """
    Paginated TNM API pull.
    Returns {laz_filename: download_url} for all matched products.
    """
    catalog: dict[str, str] = {}
    offset  = 0
    fetched = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(
            f"  TNM API  offset=0  matched=0", total=None
        )

        while True:
            params = {
                "datasets":     TNM_DATASETS,
                "bbox":         (f"{bbox['xmin']},{bbox['ymin']},"
                                 f"{bbox['xmax']},{bbox['ymax']}"),
                "max":          str(TNM_PAGE_SIZE),
                "offset":       str(offset),
                "outputFormat": "json",
            }
            url  = TNM_PRODUCTS_URL + "?" + urllib.parse.urlencode(params)
            data = _get_json(url, timeout=TNM_TIMEOUT)

            if not data:
                console.print("  [yellow]TNM API returned nothing — stopping pagination[/yellow]")
                break

            items = data.get("items", [])
            total = data.get("total", 0)
            fetched += len(items)

            for item in items:
                title = item.get("title", "")
                if project_match.lower() not in title.lower():
                    continue
                filename = _filename_from_item(item)
                dl_url   = _tnm_url_from_item(item)
                if filename and dl_url:
                    catalog[filename] = dl_url

            progress.update(
                task,
                description=(
                    f"  TNM API  page offset={offset}  "
                    f"fetched={fetched}/{total}  "
                    f"matched={len(catalog)}"
                ),
            )

            offset += len(items)
            if not items or fetched >= total:
                break

        progress.update(
            task,
            description=f"  TNM API  done  fetched={fetched}  matched={len(catalog)}",
        )

    console.print(
        f"  [green]TNM API: {len(catalog)} {project_match!r} LAZ products[/green]"
    )
    return catalog


# ── Strategy 2: S3 XML listing ─────────────────────────────────────────────────

_S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"

def _s3_list_page(prefix: str, continuation_token: str | None) -> tuple[list[str], str | None]:
    """
    Fetch one page of S3 XML listing.
    Returns (keys, next_continuation_token | None).
    """
    params: dict = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
    if continuation_token:
        params["continuation-token"] = continuation_token

    url = S3_BUCKET + "/?" + urllib.parse.urlencode(params)
    raw = _get(url, timeout=S3_TIMEOUT)
    if not raw:
        return [], None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        console.print(f"  [yellow]S3 XML parse error: {e}[/yellow]")
        return [], None

    def _tag(name: str) -> str:
        return f"{{{_S3_NS}}}{name}"

    keys = [
        el.text for el in root.findall(_tag("Contents") + "/" + _tag("Key"))
        if el.text and el.text.endswith(".laz")
    ]

    next_tok = None
    truncated = root.find(_tag("IsTruncated"))
    if truncated is not None and truncated.text == "true":
        tok_el = root.find(_tag("NextContinuationToken"))
        if tok_el is not None:
            next_tok = tok_el.text

    return keys, next_tok


def _probe_s3_prefix(prefix: str) -> bool:
    """Return True if this S3 prefix has at least one LAZ file."""
    params = {"list-type": "2", "prefix": prefix, "max-keys": "1"}
    url = S3_BUCKET + "/?" + urllib.parse.urlencode(params)
    raw = _get(url, timeout=S3_TIMEOUT)
    if not raw:
        return False
    try:
        root = ET.fromstring(raw)
        def _tag(name: str) -> str:
            return f"{{{_S3_NS}}}{name}"
        keys = root.findall(_tag("Contents"))
        return len(keys) > 0
    except Exception:
        return False


def build_catalog_via_s3(filename_filter: str = LAZ_FILENAME_PREFIX) -> dict[str, str]:
    """
    S3 XML directory listing fallback.
    Probes known prefixes, paginates through the working one.
    Returns {laz_filename: download_url}.
    """
    working_prefix = None

    console.print("  [dim]Probing S3 path prefixes...[/dim]")
    for prefix in S3_LAZ_PREFIXES:
        console.print(f"    [dim]{prefix}[/dim]", end=" ")
        if _probe_s3_prefix(prefix):
            console.print("[green]✓[/green]")
            working_prefix = prefix
            break
        else:
            console.print("[red]✗[/red]")

    if not working_prefix:
        console.print("  [red]No valid S3 prefix found.[/red]")
        return {}

    console.print(f"  [dim]Listing keys under: {working_prefix}[/dim]")

    catalog: dict[str, str] = {}
    token = None
    page  = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("  S3 listing  page=0", total=None)

        while True:
            keys, token = _s3_list_page(working_prefix, token)
            page += 1

            for key in keys:
                filename = key.rsplit("/", 1)[-1]
                if not filename.startswith(filename_filter):
                    continue
                url = f"{S3_BUCKET}/{key}"
                catalog[filename] = url

            progress.update(
                task,
                description=f"  S3 listing  page={page}  keys={len(catalog)}",
            )

            if not token:
                break

        progress.update(
            task,
            description=f"  S3 listing  done  {len(catalog)} LAZ files",
        )

    console.print(f"  [green]S3: {len(catalog)} LAZ files found[/green]")
    return catalog


# ── match against manifest ─────────────────────────────────────────────────────

def resolve_manifest(
    city_id:  str,
    use_api:  bool = True,
    use_s3:   bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    Build the URL catalog and match each manifest tile by laz_filename.
    Returns (resolved, unresolved) lists of dicts.
    """
    cfg = CITIES[city_id]

    if not cfg.tile_manifest.exists():
        console.print(f"[red]Tile manifest not found: {cfg.tile_manifest}[/red]")
        console.print(
            f"Run first:\n"
            f"  [cyan]python scripts/la/list_city_tiles.py --city {city_id}[/cyan]"
        )
        raise FileNotFoundError(cfg.tile_manifest)

    manifest_data = json.loads(cfg.tile_manifest.read_text(encoding="utf-8"))
    tiles         = manifest_data.get("tiles", [])

    console.print(f"\n[dim]Manifest: {cfg.tile_manifest}[/dim]")
    console.print(f"[dim]{len(tiles)} tile(s) to resolve[/dim]\n")

    # Separate already-resolved from missing
    need_resolve = [t for t in tiles if not t.get("download_url")]
    already      = [t for t in tiles if t.get("download_url")]

    if already:
        console.print(f"  [dim]{len(already)} tile(s) already have URLs — skipping[/dim]")

    if not need_resolve:
        console.print("[green]All tiles already have download URLs.[/green]")
        return [dict(t, _source="manifest") for t in already], []

    # Build URL catalog
    catalog: dict[str, str] = {}

    if use_api:
        console.print("[bold cyan]Strategy 1: USGS TNM API (paginated)[/bold cyan]")
        console.print(
            f"  bbox: lon [{cfg.bbox_4326['xmin']}, {cfg.bbox_4326['xmax']}]  "
            f"lat [{cfg.bbox_4326['ymin']}, {cfg.bbox_4326['ymax']}]"
        )
        tnm_catalog = build_catalog_via_tnm(cfg.bbox_4326, TNM_PROJECT_MATCH)
        catalog.update(tnm_catalog)

    still_missing_filenames = {
        t["laz_filename"] for t in need_resolve if t["laz_filename"] not in catalog
    }

    if still_missing_filenames and use_s3:
        console.print(
            f"\n[bold cyan]Strategy 2: S3 directory listing[/bold cyan]"
            f"  [dim]({len(still_missing_filenames)} tile(s) not in TNM results)[/dim]"
        )
        s3_catalog = build_catalog_via_s3()
        catalog.update(s3_catalog)

    # Match
    resolved:   list[dict] = list(dict(t, _source="manifest") for t in already)
    unresolved: list[dict] = []

    for t in need_resolve:
        fn  = t["laz_filename"]
        url = catalog.get(fn)

        # Also check if it's already on disk (no download needed)
        on_disk = (LAZ_DIR / fn).exists()

        if url:
            resolved.append({**t, "download_url": url, "_source": "catalog", "on_disk": on_disk})
        else:
            unresolved.append({**t, "_reason": "no matching product in TNM API or S3"})

    return resolved, unresolved


# ── patch manifest ─────────────────────────────────────────────────────────────

def patch_manifest(city_id: str, resolved: list[dict], unresolved: list[dict]):
    """
    Write resolved URLs back into tile_manifest.json.
    Tiles that could not be resolved are flagged with _unresolvable=true.
    """
    cfg = CITIES[city_id]
    data = json.loads(cfg.tile_manifest.read_text(encoding="utf-8"))

    url_map = {t["tile_id"]: t.get("download_url") for t in resolved}
    bad_ids = {t["tile_id"] for t in unresolved}

    patched = 0
    flagged = 0

    for tile in data["tiles"]:
        tid = tile["tile_id"]
        if tid in url_map and url_map[tid] and not tile.get("download_url"):
            tile["download_url"] = url_map[tid]
            patched += 1
        if tid in bad_ids:
            tile["_unresolvable"] = True
            flagged += 1

    data["_resolve_ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["_resolve_patched"] = patched
    data["_resolve_flagged"] = flagged

    cfg.tile_manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(
        f"\n[green]Manifest patched:[/green] "
        f"{patched} URL(s) added, {flagged} tile(s) flagged unresolvable"
        f"\n  → {cfg.tile_manifest}"
    )


# ── display ────────────────────────────────────────────────────────────────────

def _print_resolved(resolved: list[dict]):
    if not resolved:
        return
    tbl = Table(
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
        title=f"[bold green]Resolved ({len(resolved)})[/bold green]",
    )
    tbl.add_column("Tile ID",      style="white",   min_width=20)
    tbl.add_column("LAZ Filename", style="dim",     min_width=52)
    tbl.add_column("On Disk",      justify="center", min_width=8)
    tbl.add_column("Source",       min_width=10)
    tbl.add_column("URL (truncated)", style="dim", min_width=40)

    for t in resolved:
        disk = "[green]✓[/green]" if t.get("on_disk") else "[dim]—[/dim]"
        url  = t.get("download_url") or ""
        url_short = ("…" + url[-50:]) if len(url) > 53 else url
        tbl.add_row(
            t["tile_id"],
            t["laz_filename"],
            disk,
            t.get("_source", "—"),
            url_short,
        )

    console.print()
    console.print(tbl)


def _print_unresolved(unresolved: list[dict]):
    if not unresolved:
        return
    tbl = Table(
        box=box.ROUNDED,
        header_style="bold red",
        show_lines=False,
        title=f"[bold red]Unresolved ({len(unresolved)})[/bold red]",
    )
    tbl.add_column("Tile ID",      style="white",  min_width=20)
    tbl.add_column("LAZ Filename", style="dim",    min_width=52)
    tbl.add_column("Reason",       style="yellow", min_width=40)

    for t in unresolved:
        tbl.add_row(t["tile_id"], t["laz_filename"], t.get("_reason", "unknown"))

    console.print()
    console.print(tbl)
    console.print(
        f"\n[yellow]Unresolved tiles are synthetic grid cells with no real USGS product.\n"
        f"Run with [cyan]--patch[/cyan] to flag them in the manifest.[/yellow]"
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    args    = sys.argv[1:]
    city_id = "los_angeles"
    patch   = "--patch"  in args
    as_json = "--json"   in args
    use_api = "--no-api" not in args
    use_s3  = "--no-s3"  not in args

    for i, a in enumerate(args):
        if a == "--city" and i + 1 < len(args):
            city_id = args[i + 1]

    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        console.print(f"Valid: {CITY_ORDER}")
        return 1

    cfg = CITIES[city_id]

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — Tile URL Resolver[/bold magenta]\n"
        f"City: [white]{cfg.display_name}[/white]   "
        f"API: [white]{'yes' if use_api else 'no'}[/white]   "
        f"S3: [white]{'yes' if use_s3 else 'no'}[/white]   "
        f"Patch: [white]{'yes' if patch else 'no (dry run)'}[/white]",
        box=box.ROUNDED,
    ))

    try:
        resolved, unresolved = resolve_manifest(city_id, use_api=use_api, use_s3=use_s3)
    except FileNotFoundError:
        return 1

    if as_json:
        print(json.dumps({
            "resolved":   [{k: v for k, v in t.items() if not k.startswith("_")}
                           for t in resolved],
            "unresolved": [{k: v for k, v in t.items() if not k.startswith("_")}
                           for t in unresolved],
        }, indent=2, default=str))
        return 0

    _print_resolved(resolved)
    _print_unresolved(unresolved)

    # Summary
    n_on_disk = sum(1 for t in resolved if (LAZ_DIR / t["laz_filename"]).exists())
    console.print()
    console.print(Panel(
        f"[bold]Resolution summary[/bold]\n"
        f"  Resolved:     [green]{len(resolved)}[/green]\n"
        f"  Unresolved:   {'[red]' if unresolved else '[green]'}"
        f"{len(unresolved)}{'[/red]' if unresolved else '[/green]'}\n"
        f"  On disk now:  [green]{n_on_disk}[/green] of {len(resolved)} resolved",
        box=box.ROUNDED,
    ))

    if patch:
        patch_manifest(city_id, resolved, unresolved)
    else:
        console.print(
            "\n[dim]Run with [cyan]--patch[/cyan] to write resolved URLs "
            "into tile_manifest.json.[/dim]"
        )

    if resolved and not unresolved:
        console.print(
            f"\n[bold green]✓ All tiles resolved.[/bold green]\n"
            f"  [cyan]python scripts/la/download_city_tiles.py --city {city_id}[/cyan]"
        )
    elif unresolved:
        console.print(
            f"\n[yellow]{len(unresolved)} tile(s) have no real USGS product and "
            f"will be skipped by the downloader.[/yellow]"
        )

    return 0 if not unresolved else 2


if __name__ == "__main__":
    sys.exit(main())
