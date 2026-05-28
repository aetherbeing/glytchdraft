#!/usr/bin/env python3
"""
bootstrap_city_lidar.py  [GlitchOS — City LiDAR Bootstrapper]

Generalized workflow for onboarding any new city into the GlitchOS pipeline:
  1. Load city config  (configs/cities/<city>.json)
  2. Scaffold output directories
  3. Query USGS TNM API for Lidar Point Cloud (LPC) tiles
  4. Build remote manifest (all tiles available, no download)
  5. Group tiles by campaign; recommend best candidate
  6. Filter manifest to chosen campaign (--campaign / --filter-pattern)
  7. Dry-run download plan (--download-dry-run)
  8. Test download (--download-limit 1)
  9. PDAL verification (--verify-first)
 10. Build local catalog for the pipeline (--build-local-catalog)

Safety: full downloads never run unless --download-all is explicitly passed.
        Pipeline ingestion is never triggered automatically.

Usage:
    python scripts/bootstrap_city_lidar.py detroit --query-tnm --dry-run
    python scripts/bootstrap_city_lidar.py portland --query-tnm
    python scripts/bootstrap_city_lidar.py detroit --campaign MI_WayneCounty_2017_A17 --download-limit 1
    python scripts/bootstrap_city_lidar.py detroit --verify-first
    python scripts/bootstrap_city_lidar.py detroit --build-local-catalog
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = REPO_ROOT / "configs" / "cities"

TNM_BASE = "https://tnmaccess.nationalmap.gov/api/v1/products"
HTTP_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 300
CHUNK_SIZE = 1 << 20  # 1 MB

_MARKUP_RE = re.compile(r"\[/?[^\]]+\]")

try:
    from rich.console import Console
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def _pr(msg: str) -> None:
    if console:
        console.print(msg)
    else:
        print(_MARKUP_RE.sub("", msg))


# ── Config ────────────────────────────────────────────────────────────────────


def load_city_config(city_or_path: str) -> dict:
    """Load city config from slug name (e.g. 'detroit') or explicit file path."""
    p = Path(city_or_path)
    if not p.exists():
        p = CONFIGS_DIR / f"{city_or_path}.json"
    if not p.exists():
        sys.exit(
            f"Config not found: {p}\n"
            f"Expected: {CONFIGS_DIR}/<city>.json\n"
            f"Available: {', '.join(f.stem for f in sorted(CONFIGS_DIR.glob('*.json')))}"
        )
    cfg = json.loads(p.read_text(encoding="utf-8"))
    if "city_slug" not in cfg:
        cfg["city_slug"] = p.stem
    return cfg


def scaffold_dirs(cfg: dict) -> None:
    """Create expected output directories if they do not already exist."""
    output_root = Path(cfg["output_root"])
    laz_dir = Path(cfg["laz_dir"])

    dirs = [
        laz_dir,
        output_root / "catalogs",
        output_root / "logs",
        output_root / "status",
    ]
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            _pr(f"  Created : {d}")
        else:
            _pr(f"  Exists  : {d}")


# ── TNM API ───────────────────────────────────────────────────────────────────


def _build_tnm_url(bbox: dict, max_results: int = 1000) -> str:
    """
    Build TNM API URL with literal bbox commas and %20-encoded spaces.

    TNM rejects %2C (percent-encoded commas) and + (plus-encoded spaces) in the
    dataset name and bbox parameters, so we build the query string manually
    rather than using urllib.parse.urlencode.
    """
    datasets_enc = urllib.parse.quote("Lidar Point Cloud (LPC)", safe="()")
    bbox_str = f"{bbox['xmin']},{bbox['ymin']},{bbox['xmax']},{bbox['ymax']}"
    return (
        f"{TNM_BASE}?datasets={datasets_enc}"
        f"&bbox={bbox_str}"
        f"&prodFormats=LAS,LAZ"
        f"&max={max_results}"
    )


def query_tnm(bbox: dict, max_results: int = 1000) -> list[dict] | None:
    """
    Query USGS TNM API for LPC tiles within bbox_4326.

    Returns:
        list[dict]  on success (may be empty if genuinely no tiles)
        None        on any network or API error

    Never treats an API failure as "zero tiles" — the caller should exit
    nonzero when None is returned.

    TNM backend quirks handled:
      - HTTP 200 with non-JSON Lambda crash body
      - HTTP 200 with JSON {"error": ...} or {"errorMessage": ...} payload
      - HTTP 4xx / 5xx (including 504 Gateway Timeout)
      - URLError (DNS / connection failures)
      - Result cap warnings when items == max_results
    """
    url = _build_tnm_url(bbox, max_results)
    _pr(f"  Querying TNM: {url}")

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
        _pr(f"  [red]TNM HTTP {status}[/red]  Content-Type: {content_type}")
    except urllib.error.URLError as exc:
        _pr(f"  [red]TNM network error:[/red] {exc}")
        _pr(f"  Query URL: {url}")
        return None

    _pr(f"  TNM response: HTTP {status}  Content-Type: {content_type}")
    text = raw.decode("utf-8", errors="replace")

    if status >= 400:
        _pr(f"  [red]TNM HTTP {status} — server error body (first 500 chars):[/red]\n{text[:500]}")
        _pr(f"  Query URL: {url}")
        _pr("  TNM API returned HTTP error — try again later.")
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _pr(f"  [red]TNM returned non-JSON body (first 500 chars):[/red]\n{text[:500]}")
        _pr(f"  Query URL: {url}")
        _pr("  TNM API may be temporarily unavailable — try again later.")
        return None

    if "error" in data or "errorMessage" in data:
        err = data.get("error") or data.get("errorMessage") or "(no message)"
        _pr(f"  [red]TNM API error response:[/red] {err}")
        _pr(f"  Query URL: {url}")
        return None

    items: list[dict] = data.get("items", [])
    if items and len(items) >= max_results:
        _pr(
            f"  [yellow]WARNING: TNM returned {len(items)} items at cap (max={max_results}).[/yellow]\n"
            f"  Real total may be higher. Increase --max to fetch more tiles."
        )
    else:
        _pr(f"  TNM returned {len(items)} item(s)")
    return items


# ── Remote manifest ───────────────────────────────────────────────────────────


def build_remote_manifest(cfg: dict, max_results: int = 1000) -> dict | None:
    """
    Query TNM and return a remote manifest dict (no files downloaded).
    Returns None if the TNM query failed.
    """
    bbox = cfg["bbox_4326"]
    items = query_tnm(bbox, max_results=max_results)
    if items is None:
        return None

    laz_dir = Path(cfg["laz_dir"])
    city_slug = cfg.get("city_slug", "unknown")

    tiles = []
    for item in items:
        url_dict: dict = item.get("urls") or {}
        download_url = (
            url_dict.get("LAZ")
            or url_dict.get("LAS")
            or item.get("downloadLazURL")
            or item.get("downloadURL")
            or next((v for v in url_dict.values() if v), None)
        )
        if not download_url:
            continue

        filename = urllib.parse.unquote(download_url.rsplit("/", 1)[-1])
        local_path = laz_dir / filename

        raw_bb = item.get("boundingBox") or {}
        bbox_4326 = (
            {
                "xmin": raw_bb["minX"], "ymin": raw_bb["minY"],
                "xmax": raw_bb["maxX"], "ymax": raw_bb["maxY"],
            }
            if raw_bb and all(k in raw_bb for k in ("minX", "minY", "maxX", "maxY"))
            else None
        )

        campaign_group, detailed_prefix = extract_campaign_info(filename)

        tiles.append({
            "tile_id": Path(filename).stem,
            "filename": filename,
            "download_url": download_url,
            "local_path": str(local_path),
            "on_disk": local_path.exists(),
            "project": item.get("sourceId", ""),
            "title": item.get("title", ""),
            "publication_date": item.get("publicationDate", ""),
            "file_size_bytes": item.get("sizeInBytes"),
            "bbox_4326": bbox_4326,
            "campaign_group": campaign_group,
            "detailed_prefix": detailed_prefix,
        })

    tiles.sort(key=lambda t: t["tile_id"])

    return {
        "schema_version": "1.0",
        "city_slug": city_slug,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tnm_bbox_4326": bbox,
        "tnm_query_url": _build_tnm_url(bbox, max_results),
        "tnm_items_returned": len(items),
        "tile_count": len(tiles),
        "on_disk_count": sum(1 for t in tiles if t["on_disk"]),
        "tiles": tiles,
    }


# ── Campaign grouping ─────────────────────────────────────────────────────────


def extract_campaign_info(filename: str) -> tuple[str, str]:
    """
    Extract (campaign_group, detailed_prefix) from a USGS LAZ filename.

    Rules:
      - Strip USGS_LPC_ prefix if present
      - Remove trailing pure-numeric tile IDs (e.g. 397272, 001445)
      - detailed_prefix = remaining joined string
      - campaign_group  = first 2 parts before the first 4-digit year

    Examples:
      USGS_LPC_MI_WayneCounty_2017_A17_397272.laz
        → (MI_WayneCounty, MI_WayneCounty_2017_A17)
      USGS_LPC_MI_WAYNECO_2009_000321.laz
        → (MI_WAYNECO, MI_WAYNECO_2009)
      USGS_LPC_ARRA_MI_4SECOUNTIES_2010_001445.laz
        → (ARRA_MI, ARRA_MI_4SECOUNTIES_2010)
    """
    stem = Path(filename).stem
    if stem[:9].upper() == "USGS_LPC_":
        stem = stem[9:]

    parts = stem.split("_")

    # Strip trailing pure-numeric tile IDs (e.g. 397272, 001445).
    # Do NOT strip 4-digit years (2009, 2017, 2010) — they are part of the prefix.
    while parts and re.fullmatch(r"\d+", parts[-1]) and not re.fullmatch(r"\d{4}", parts[-1]):
        parts.pop()

    if not parts:
        return "unknown", "unknown"

    detailed_prefix = "_".join(parts)

    # Campaign group: first 2 parts before the first 4-digit year
    campaign_parts: list[str] = []
    for p in parts:
        if re.fullmatch(r"\d{4}", p):
            break
        campaign_parts.append(p)
        if len(campaign_parts) >= 2:
            break

    campaign = "_".join(campaign_parts) if campaign_parts else parts[0]
    return campaign, detailed_prefix


def group_by_campaign(tiles: list[dict]) -> dict[str, dict]:
    """
    Group tiles by campaign_group.

    Returns a dict keyed by campaign_group with summary info:
      tile_count, total_bytes/gb, detailed_prefixes, publication_dates,
      sample_filenames, on_disk_count, has_laz.
    """
    groups: dict[str, dict] = {}

    for tile in tiles:
        grp = tile.get("campaign_group", "unknown")
        pfx = tile.get("detailed_prefix", "unknown")

        if grp not in groups:
            groups[grp] = {
                "campaign_group": grp,
                "detailed_prefixes": {},
                "tile_count": 0,
                "total_bytes": 0,
                "publication_dates": set(),
                "sample_filenames": [],
                "on_disk_count": 0,
                "has_laz": False,
            }

        g = groups[grp]
        g["tile_count"] += 1
        g["detailed_prefixes"][pfx] = g["detailed_prefixes"].get(pfx, 0) + 1

        size = tile.get("file_size_bytes")
        if size:
            g["total_bytes"] += size

        pub = tile.get("publication_date")
        if pub:
            g["publication_dates"].add(pub)

        if len(g["sample_filenames"]) < 3:
            g["sample_filenames"].append(tile["filename"])

        if tile.get("on_disk"):
            g["on_disk_count"] += 1

        if tile.get("filename", "").lower().endswith(".laz"):
            g["has_laz"] = True

    for g in groups.values():
        g["publication_dates"] = sorted(g["publication_dates"])
        g["total_gb"] = round(g["total_bytes"] / 1_073_741_824, 2)

    return groups


# ── Campaign recommendation ───────────────────────────────────────────────────


def _extract_year_from_prefix(text: str) -> int | None:
    m = re.search(r"\b(19|20)(\d{2})\b", text)
    return int(m.group()) if m else None


def _score_campaign(group: dict, city_slug: str, display_name: str) -> float:
    """Score a campaign for recommendation. Higher = better."""
    score = 0.0
    name_lower = group["campaign_group"].lower()
    all_prefixes = " ".join(group["detailed_prefixes"].keys()).lower()

    # Newer surveys preferred
    year = _extract_year_from_prefix(all_prefixes)
    if year:
        score += (year - 2000) * 2.5

    # City/county name match is a strong signal
    for term in [city_slug.lower(), display_name.lower().replace(" ", "")]:
        if term and len(term) >= 4 and term in name_lower:
            score += 30
            break

    # ARRA = older legacy program
    if "arra" in name_lower:
        score -= 25

    # Sanity-check tile count
    count = group["tile_count"]
    if 30 <= count <= 3000:
        score += 10
    elif count < 5:
        score -= 20

    # LAZ format preferred over LAS
    if group["has_laz"]:
        score += 5

    # Bogus 1899 publication date = likely bad metadata
    for d in group["publication_dates"]:
        if d.startswith("1899"):
            score -= 40
            break

    return score


def recommend_campaign(groups: dict[str, dict], cfg: dict) -> tuple[str, str, str]:
    """
    Returns (best_campaign_group, best_detailed_prefix, reason_string).
    """
    if not groups:
        return "none", "none", "No campaigns found in remote manifest."

    city_slug = cfg.get("city_slug", "")
    display_name = cfg.get("display_name", city_slug)

    scored = [
        (grp, _score_campaign(info, city_slug, display_name), info)
        for grp, info in groups.items()
    ]
    scored.sort(key=lambda x: -x[1])

    best_grp, best_score, best_info = scored[0]

    # Most-common detailed prefix within the winning group
    best_prefix = max(
        best_info["detailed_prefixes"],
        key=lambda k: best_info["detailed_prefixes"][k],
    )

    year = _extract_year_from_prefix(best_prefix)
    year_str = f", acquisition year ~{year}" if year else ""
    legacy_note = " (ARRA/legacy — no better option found)" if "arra" in best_grp.lower() else ""

    reason = (
        f"Highest-scoring campaign: {best_grp} ({best_prefix}), "
        f"{best_info['tile_count']} tiles, "
        f"{best_info['total_gb']:.2f} GB"
        f"{year_str}{legacy_note}."
    )
    return best_grp, best_prefix, reason


# ── Support data audit ───────────────────────────────────────────────────────


def audit_support_data(cfg: dict) -> list[str]:
    """
    Check whether the non-LAZ support data needed for clean building massing
    is present in the config and on disk.

    Returns a list of warning strings (empty = all good).

    Motivation: LAZ can be staged and the pipeline can run successfully while
    producing coastal/cluster hull artifacts instead of footprint-respecting
    building massing — as seen in the NOLA Blender import failure.  This audit
    surfaces missing support data BEFORE the user commits to a full download.
    """
    warnings: list[str] = []

    # Building footprints
    fp_path_str = (
        cfg.get("county_footprints_path")
        or cfg.get("footprint_source", {}).get("path")
        or cfg.get("building_footprints_path")
    )
    if not fp_path_str:
        warnings.append(
            "No building footprint source configured in city config. "
            "Phase 06 will fall back to cluster convex hulls — "
            "outputs will NOT resemble real building massing."
        )
    elif not Path(fp_path_str).exists():
        warnings.append(
            f"Building footprint file not found on disk: {fp_path_str}. "
            "Download footprints before running the pipeline, or Phase 06 "
            "will fall back to cluster hulls."
        )

    # City boundary
    boundary_path_str = cfg.get("boundary_geojson")
    if not boundary_path_str:
        warnings.append(
            "No city boundary geojson configured. "
            "Bbox fallback may include water, coastal, or out-of-city junk geometry."
        )
    elif not Path(boundary_path_str).exists():
        warnings.append(
            f"City boundary file not found on disk: {boundary_path_str}. "
            "Without a boundary mask, pipeline bbox may capture water or coastal artifacts."
        )

    # Address source
    addr_path_str = cfg.get("address_source", {}).get("path") or cfg.get("addresses_path")
    if not addr_path_str:
        warnings.append(
            "No address source configured. Building address labels will not be available."
        )
    elif not Path(addr_path_str).exists():
        warnings.append(
            f"Address source file not found on disk: {addr_path_str}. "
            "Address join will be skipped at Phase 07."
        )

    return warnings


def print_support_data_audit(cfg: dict) -> None:
    """Print support data audit warnings."""
    warnings = audit_support_data(cfg)
    if not warnings:
        _pr("  [green]Support data OK[/green] (footprints, boundary, addresses found)")
        return
    _pr("\n  [bold yellow]Support data warnings:[/bold yellow]")
    for w in warnings:
        _pr(f"  [yellow]  ⚠  {w}[/yellow]")
    _pr(
        "\n  [dim]LiDAR can be staged now, but pipeline outputs may be degraded or "
        "produce hull artifacts if support data is missing when ingestion runs.[/dim]"
    )


# ── Filtered manifest ─────────────────────────────────────────────────────────


def filter_manifest(
    manifest: dict,
    campaign: str | None = None,
    pattern: str | None = None,
) -> dict:
    """
    Return a copy of manifest filtered to matching tiles.

    campaign: matches campaign_group (exact, case-insensitive) or detailed_prefix
              (prefix match) or filename substring.
    pattern:  substring match on filename (applied after campaign filter).
    """
    tiles = list(manifest["tiles"])

    if campaign:
        c = campaign.lower()
        tiles = [
            t for t in tiles
            if (t.get("campaign_group", "").lower() == c
                or t.get("detailed_prefix", "").lower().startswith(c)
                or c in t.get("filename", "").lower())
        ]

    if pattern:
        p = pattern.lower()
        tiles = [t for t in tiles if p in t.get("filename", "").lower()]

    filtered = dict(manifest)
    filtered["tiles"] = tiles
    filtered["tile_count"] = len(tiles)
    filtered["on_disk_count"] = sum(1 for t in tiles if t.get("on_disk"))
    filtered["filtered_by_campaign"] = campaign
    filtered["filtered_by_pattern"] = pattern
    filtered["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return filtered


# ── Download ──────────────────────────────────────────────────────────────────


def _download_one(url: str, dest: Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, dest.open("wb") as fh:
        total = 0
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            fh.write(chunk)
            total += len(chunk)
    return total


def dry_run_download(manifest: dict) -> None:
    """Print download plan without downloading anything."""
    tiles = manifest.get("tiles", [])
    pending = [t for t in tiles if not Path(t["local_path"]).exists()]
    on_disk_count = len(tiles) - len(pending)
    pending_bytes = sum(t.get("file_size_bytes") or 0 for t in pending)

    _pr(f"\n  Total tiles    : {len(tiles)}")
    _pr(f"  On disk        : {on_disk_count}")
    _pr(f"  To download    : {len(pending)}")
    _pr(f"  Approx size    : {pending_bytes / 1_073_741_824:.2f} GB")

    if pending:
        _pr("\n  First 10 pending tiles:")
        for t in pending[:10]:
            _pr(f"    {t['filename']}")
            _pr(f"      URL  : {t['download_url']}")
            _pr(f"      Local: {t['local_path']}")
        if len(pending) > 10:
            _pr(f"  ... and {len(pending) - 10} more")


def download_tiles(
    manifest: dict,
    laz_dir: Path,
    limit: int | None = None,
    download_all: bool = False,
) -> None:
    """
    Download tiles from manifest.

    Safety rules:
      - limit=None, download_all=False  → refuses to start (no implicit full download)
      - limit=N                          → downloads at most N tiles (test mode)
      - download_all=True                → downloads all pending tiles
    """
    if limit is None and not download_all:
        _pr("[red]ERROR: No download mode specified.[/red]")
        _pr("  Use --download-limit 1   for a single test tile.")
        _pr("  Use --download-all       only when you are ready for the full dataset.")
        return

    tiles = manifest.get("tiles", [])
    pending = [t for t in tiles if not Path(t["local_path"]).exists()]

    if limit is not None:
        pending = pending[:limit]

    total_bytes = sum(t.get("file_size_bytes") or 0 for t in pending)
    _pr(f"\n  Tiles to download: {len(pending)}  (~{total_bytes / 1_073_741_824:.2f} GB)")

    if not pending:
        _pr("  All tiles already on disk.")
        return

    laz_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    fail = 0

    for i, tile in enumerate(pending, 1):
        dest = Path(tile["local_path"])
        _pr(f"  [{i}/{len(pending)}] {tile['filename']} …")
        t0 = time.time()
        try:
            nbytes = _download_one(tile["download_url"], dest)
            elapsed = time.time() - t0
            _pr(f"    OK  {nbytes / 1_048_576:.1f} MB  {elapsed:.1f}s")
            ok += 1
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            _pr(f"    FAIL: {exc}")
            if dest.exists():
                dest.unlink()
            fail += 1

    _pr(f"\n  Downloaded: {ok}  Failed: {fail}")


# ── PDAL verification ─────────────────────────────────────────────────────────


def verify_with_pdal(path: Path) -> None:
    """Run pdal info --metadata on path and report key attributes."""
    if not path.exists():
        _pr(f"  [red]File not found for PDAL verify:[/red] {path}")
        return

    _pr(f"\n  PDAL verification: {path}")
    try:
        result = subprocess.run(
            ["pdal", "info", "--metadata", str(path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            _pr(f"  [red]pdal info failed (exit {result.returncode}):[/red]")
            _pr(f"  {result.stderr[:500]}")
            return

        try:
            meta = json.loads(result.stdout)
            stats = meta.get("metadata", {})
            _pr(f"  Point count : {stats.get('count', 'unknown')}")
            _pr(f"  Scale X/Y/Z : {stats.get('scale_x')}/{stats.get('scale_y')}/{stats.get('scale_z')}")
            _pr(f"  Min X/Y/Z   : {stats.get('minx')}/{stats.get('miny')}/{stats.get('minz')}")
            _pr(f"  Max X/Y/Z   : {stats.get('maxx')}/{stats.get('maxy')}/{stats.get('maxz')}")
            _pr(f"  SRS (comp.) : {str(stats.get('comp_spatialreference', 'N/A'))[:80]}")
            _pr("  Readable    : YES")
        except (json.JSONDecodeError, KeyError):
            _pr("  Readable    : YES (raw output snippet):")
            _pr(f"  {result.stdout[:500]}")

    except FileNotFoundError:
        _pr("  [yellow]pdal not found in PATH.[/yellow]")
        _pr("  Activate the conda environment:  conda activate pdal_env")
        _pr(f"  Then run manually:  pdal info --metadata {path}")
    except subprocess.TimeoutExpired:
        _pr("  [yellow]pdal info timed out (120s)[/yellow]")


# ── Local catalog ─────────────────────────────────────────────────────────────


def build_local_catalog(cfg: dict) -> dict:
    """
    Scan on-disk LAZ/LAS files and return a catalog dict consumable by
    run_city_pipeline.py.

    Only includes files that actually exist on disk.
    """
    laz_dir = Path(cfg["laz_dir"])
    files: list[Path] = []
    if laz_dir.exists():
        files = sorted(laz_dir.glob("*.laz")) + sorted(laz_dir.glob("*.las"))

    return {
        "schema_version": "1.0",
        "city_slug": cfg["city_slug"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "laz_dir": str(laz_dir),
        "files": [str(f) for f in files],
        "count": len(files),
    }


# ── I/O helpers ───────────────────────────────────────────────────────────────


def _load_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _pr(f"  [red]Failed to load manifest {path}: {exc}[/red]")
        return None


def _write_json_safe(path: Path, data: dict) -> bool:
    """Write JSON to path. Warns and skips if the file already exists."""
    if path.exists():
        _pr(f"  [yellow]Already exists — not overwriting:[/yellow] {path}")
        _pr("  Delete it first to regenerate.")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _pr(f"  [green]Written:[/green] {path}")
    return True


def _campaign_catalog_path(catalog_dir: Path, city_slug: str, campaign: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", campaign).strip("_")
    return catalog_dir / f"{city_slug}_{safe}_catalog.json"


# ── Report ────────────────────────────────────────────────────────────────────


def print_campaign_summary(groups: dict[str, dict], recommendation: tuple[str, str, str]) -> None:
    best_grp, best_prefix, reason = recommendation

    _pr("\n  ── Campaign Summary " + "─" * 50)
    for grp, info in sorted(groups.items(), key=lambda x: -x[1]["tile_count"]):
        marker = "  [bold green]← RECOMMENDED[/bold green]" if grp == best_grp else ""
        _pr(f"\n  [bold]{grp}[/bold]{marker}")
        _pr(f"    Tiles      : {info['tile_count']}")
        _pr(f"    Size       : {info['total_gb']:.2f} GB")
        _pr(f"    On disk    : {info['on_disk_count']}")
        for pfx, cnt in sorted(info["detailed_prefixes"].items(), key=lambda x: -x[1]):
            _pr(f"    Prefix     : {pfx}  ({cnt} tiles)")
        if info["publication_dates"]:
            dates = info["publication_dates"]
            _pr(f"    Pub dates  : {dates[0]} … {dates[-1]}")
        if info["sample_filenames"]:
            _pr(f"    Example    : {info['sample_filenames'][0]}")

    _pr(f"\n  [bold green]Recommended campaign:[/bold green] {best_prefix}")
    _pr(f"  Reason: {reason}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GlitchOS City LiDAR Bootstrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discover Detroit campaigns (no files written)
  python scripts/bootstrap_city_lidar.py detroit --query-tnm --dry-run

  # Write remote manifest for Detroit
  python scripts/bootstrap_city_lidar.py detroit --query-tnm

  # Filter and preview download plan
  python scripts/bootstrap_city_lidar.py detroit \\
      --campaign MI_WayneCounty_2017_A17 --download-dry-run

  # Test download: one tile only
  python scripts/bootstrap_city_lidar.py detroit \\
      --campaign MI_WayneCounty_2017_A17 --download-limit 1

  # Verify the downloaded tile with PDAL
  python scripts/bootstrap_city_lidar.py detroit --verify-first

  # Build local catalog for the pipeline
  python scripts/bootstrap_city_lidar.py detroit --build-local-catalog

  # Same flow for other cities
  python scripts/bootstrap_city_lidar.py portland --query-tnm --dry-run
  python scripts/bootstrap_city_lidar.py boston   --query-tnm --dry-run
  python scripts/bootstrap_city_lidar.py toledo   --query-tnm --dry-run
  python scripts/bootstrap_city_lidar.py tempe    --query-tnm --dry-run
""",
    )

    parser.add_argument("city", nargs="?",
                        help="City slug (e.g. detroit, portland) or path to config JSON")
    parser.add_argument("--config", type=Path, default=None,
                        help="Explicit path to city JSON config")

    # TNM query
    parser.add_argument("--query-tnm", action="store_true",
                        help="Query USGS TNM API and build a remote manifest")
    parser.add_argument("--max", type=int, default=1000, metavar="N",
                        help="Max TNM results to request (default: 1000)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results but do not write any files")

    # Campaign filtering
    parser.add_argument("--campaign", type=str, default=None,
                        help="Filter to this campaign (group name or detailed prefix)")
    parser.add_argument("--filter-pattern", type=str, default=None,
                        help="Filter tiles by substring match on filename")

    # Download
    parser.add_argument("--download-dry-run", action="store_true",
                        help="Print what would be downloaded; do not download")
    parser.add_argument("--download-limit", type=int, default=None, metavar="N",
                        help="Download at most N tiles (use 1 for a test tile)")
    parser.add_argument("--download-all", action="store_true",
                        help="Download all pending tiles (requires explicit flag)")

    # Verification
    parser.add_argument("--verify-first", action="store_true",
                        help="Run pdal info on the first on-disk LAZ tile")

    # Local catalog
    parser.add_argument("--build-local-catalog", action="store_true",
                        help="Scan on-disk files and write local catalog for the pipeline")

    # Manifest override
    parser.add_argument("--manifest", type=Path, default=None,
                        help="Explicit remote manifest path (overrides default location)")

    args = parser.parse_args()

    # ── Load config
    if args.config:
        if not args.config.exists():
            sys.exit(f"Config not found: {args.config}")
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        if "city_slug" not in cfg:
            cfg["city_slug"] = args.config.stem
    elif args.city:
        cfg = load_city_config(args.city)
    else:
        parser.print_help()
        return 1

    city_slug = cfg["city_slug"]
    output_root = Path(cfg["output_root"])
    laz_dir = Path(cfg["laz_dir"])
    catalog_dir = output_root / "catalogs"

    _pr(f"\n[bold cyan]GlitchOS City LiDAR Bootstrapper — {cfg.get('display_name', city_slug)}[/bold cyan]")
    _pr(f"  City slug   : {city_slug}")
    _pr(f"  LAZ dir     : {laz_dir}")
    _pr(f"  Output root : {output_root}")

    # ── Scaffold
    _pr("\n[bold]Scaffolding directories…[/bold]")
    scaffold_dirs(cfg)

    # ── Support data audit (runs always — warns early about missing footprints/boundary)
    _pr("\n[bold]Checking support data…[/bold]")
    print_support_data_audit(cfg)

    remote_manifest_path = args.manifest or (catalog_dir / f"{city_slug}_remote_manifest.json")

    # ── Query TNM
    active_manifest: dict | None = None

    if args.query_tnm:
        _pr(f"\n[bold]Querying USGS TNM (max={args.max})…[/bold]")
        manifest = build_remote_manifest(cfg, max_results=args.max)
        if manifest is None:
            _pr("[red]ERROR: TNM query failed — see messages above. No files written.[/red]")
            return 1

        groups = group_by_campaign(manifest["tiles"])
        rec = recommend_campaign(groups, cfg)
        print_campaign_summary(groups, rec)

        if not args.dry_run:
            _write_json_safe(remote_manifest_path, manifest)
        else:
            _pr("\n  [dim]Dry run — remote manifest not written.[/dim]")

        active_manifest = manifest

        # If no further action requested, print next-step guidance
        if not any([args.campaign, args.filter_pattern, args.download_dry_run,
                    args.download_limit, args.download_all,
                    args.verify_first, args.build_local_catalog]):
            _, best_prefix, _ = rec
            _pr(f"\n  Next step — filter to recommended campaign:")
            _pr(f"    python scripts/bootstrap_city_lidar.py {city_slug} \\")
            _pr(f"        --campaign {best_prefix} --download-dry-run")
            return 0

    else:
        # Load existing remote manifest for subsequent operations
        active_manifest = _load_manifest(remote_manifest_path)

    # ── Campaign / pattern filter
    if args.campaign or args.filter_pattern:
        if active_manifest is None:
            _pr(f"  [red]No remote manifest found at {remote_manifest_path}[/red]")
            _pr("  Run --query-tnm first to build the remote manifest.")
            return 1

        filtered = filter_manifest(active_manifest, campaign=args.campaign, pattern=args.filter_pattern)
        _pr(f"\n  Filtered: {filtered['tile_count']} tiles match "
            f"{'campaign=' + repr(args.campaign) if args.campaign else ''}"
            f"{'pattern=' + repr(args.filter_pattern) if args.filter_pattern else ''}")

        if not args.dry_run and not args.download_dry_run:
            key = args.campaign or args.filter_pattern or "filtered"
            filtered_path = _campaign_catalog_path(catalog_dir, city_slug, key)
            _write_json_safe(filtered_path, filtered)

        active_manifest = filtered

    # ── Download dry-run
    if args.download_dry_run:
        if active_manifest is None:
            _pr("[red]No manifest available. Run --query-tnm first.[/red]")
            return 1
        _pr("\n[bold]Download dry-run:[/bold]")
        dry_run_download(active_manifest)

    # ── Actual download
    if args.download_limit or args.download_all:
        if active_manifest is None:
            _pr("[red]No manifest available. Run --query-tnm first.[/red]")
            return 1
        _pr("\n[bold]Downloading tiles…[/bold]")
        download_tiles(
            active_manifest, laz_dir,
            limit=args.download_limit,
            download_all=args.download_all,
        )

    # ── PDAL verify
    if args.verify_first:
        _pr("\n[bold]PDAL verification…[/bold]")
        laz_files = sorted(laz_dir.glob("*.laz")) + sorted(laz_dir.glob("*.las"))
        if laz_files:
            verify_with_pdal(laz_files[0])
        else:
            _pr(f"  [yellow]No LAZ/LAS files in {laz_dir}[/yellow]")
            _pr("  Download a test tile first:  --download-limit 1")

    # ── Build local catalog
    if args.build_local_catalog:
        _pr("\n[bold]Building local catalog…[/bold]")
        catalog = build_local_catalog(cfg)
        catalog_path = catalog_dir / f"{city_slug}_catalog.json"
        _pr(f"  Files found : {catalog['count']}")
        _pr(f"  LAZ dir     : {catalog['laz_dir']}")
        if not args.dry_run:
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
            _pr(f"  [green]Local catalog written:[/green] {catalog_path}")
            if catalog["count"] > 0:
                _pr("\n  Ready to run pipeline:")
                _pr(f"    python scripts/run_city_pipeline.py \\")
                _pr(f"        --config configs/cities/{city_slug}.json \\")
                _pr(f"        --catalog {catalog_path} \\")
                _pr(f"        --to-phase 08 --execute")
            else:
                _pr("  [yellow]No files on disk — download tiles first.[/yellow]")
        else:
            _pr("  [dim]Dry run — catalog not written.[/dim]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
