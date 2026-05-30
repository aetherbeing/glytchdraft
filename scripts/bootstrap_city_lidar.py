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
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_COMMON_TOKEN_RE = re.compile(r"^(usgs|lpc|laz|las|lidar|point|cloud|city|county|parish|borough|countywide|project|survey|staged|elevation|data|the|and|of)$", re.I)

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


def _cfg_text(cfg: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = cfg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for inner_key in ("path", "title", "name", "sample_project"):
                inner_value = value.get(inner_key)
                if isinstance(inner_value, str) and inner_value.strip():
                    return inner_value.strip()
    return default


def _cfg_path(cfg: dict, *keys: str) -> Path | None:
    text = _cfg_text(cfg, *keys)
    return Path(text) if text else None


def _normalize_tokens(*texts: str) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        if not text:
            continue
        for token in _WORD_RE.findall(text.lower()):
            if token.isdigit():
                continue
            if _COMMON_TOKEN_RE.fullmatch(token):
                continue
            tokens.add(token)
            if len(token) > 3 and token.isalnum():
                tokens.add(token.replace("-", ""))
    return tokens


def _city_terms(cfg: dict) -> set[str]:
    region = _cfg_text(cfg, "region")
    sample_project = _cfg_text(cfg, "laz_source", "sample_project")
    display_name = _cfg_text(cfg, "display_name", default=cfg.get("city_slug", ""))
    city_slug = cfg.get("city_slug", "")
    return _normalize_tokens(city_slug, display_name, region, sample_project)


def _human_gb(num_bytes: int | float | None) -> str:
    if not num_bytes:
        return "0.00 GB"
    return f"{float(num_bytes) / 1_073_741_824:.2f} GB"


def _best_detailed_prefix(detailed_prefixes: dict[str, int]) -> str:
    if not detailed_prefixes:
        return "unknown"
    return max(
        detailed_prefixes,
        key=lambda pfx: (
            detailed_prefixes[pfx],
            _extract_year_from_prefix(pfx) or 0,
            len(pfx),
        ),
    )


def slugify_city_name(value: str) -> str:
    """Normalize a city name or slug to the config filename convention."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", slug).strip("_")


def _available_city_configs() -> list[Path]:
    return sorted(CONFIGS_DIR.glob("*.json"))


def _load_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_city_config(city_or_path: str) -> Path | None:
    p = Path(city_or_path)
    if p.exists():
        return p

    slug = slugify_city_name(city_or_path)
    direct = CONFIGS_DIR / f"{slug}.json"
    if direct.exists():
        return direct

    for cfg_path in _available_city_configs():
        try:
            cfg = _load_json_file(cfg_path)
        except (json.JSONDecodeError, OSError):
            continue
        names = {
            slugify_city_name(cfg_path.stem),
            slugify_city_name(cfg.get("city_slug", "")),
            slugify_city_name(cfg.get("display_name", "")),
        }
        aliases = cfg.get("aliases", [])
        if isinstance(aliases, list):
            names.update(slugify_city_name(str(alias)) for alias in aliases)
        if slug in names:
            return cfg_path
    return None


def validate_city_config(cfg: dict) -> list[str]:
    """Return config issues that block repeatable city onboarding."""
    warnings: list[str] = []
    required = ("city_slug", "display_name", "bbox_4326", "laz_dir", "output_root")
    for key in required:
        if not cfg.get(key):
            warnings.append(f"Missing required city config key: {key}")

    bbox = cfg.get("bbox_4326")
    if isinstance(bbox, dict):
        missing = [k for k in ("xmin", "ymin", "xmax", "ymax") if k not in bbox]
        if missing:
            warnings.append(f"bbox_4326 is missing keys: {', '.join(missing)}")
        else:
            try:
                xmin, ymin, xmax, ymax = (float(bbox[k]) for k in ("xmin", "ymin", "xmax", "ymax"))
                if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
                    warnings.append("bbox_4326 values are outside valid lon/lat ranges or are inverted.")
            except (TypeError, ValueError):
                warnings.append("bbox_4326 values must be numeric.")
    elif bbox is not None:
        warnings.append("bbox_4326 must be an object with xmin/ymin/xmax/ymax.")

    if not cfg.get("output_epsg"):
        warnings.append("No output_epsg configured. Downstream projection must be chosen manually.")

    return warnings


# ── Config ────────────────────────────────────────────────────────────────────


def load_city_config(city_or_path: str) -> dict:
    """Load city config from slug name (e.g. 'detroit') or explicit file path."""
    p = _find_city_config(city_or_path)
    if p is None or not p.exists():
        available = ", ".join(f.stem for f in _available_city_configs())
        sys.exit(
            f"Config not found for city: {city_or_path}\n"
            f"Expected: {CONFIGS_DIR}/<city>.json\n"
            f"Available: {available}\n"
            "Create a city config with bbox_4326, laz_dir, output_root, and output_epsg first."
        )
    cfg = json.loads(p.read_text(encoding="utf-8"))
    if "city_slug" not in cfg:
        cfg["city_slug"] = p.stem
    if not str(cfg.get("display_name", "")).strip():
        cfg["display_name"] = cfg["city_slug"].replace("_", " ").title()
    return cfg


def normalize_city_config(cfg: dict) -> dict:
    """Fill derived paths so downstream code can treat every city the same way."""
    normalized = dict(cfg)
    city_slug = str(normalized.get("city_slug", "")).strip() or slugify_city_name(
        str(normalized.get("display_name", "city"))
    )
    normalized["city_slug"] = city_slug
    if not str(normalized.get("display_name", "")).strip():
        normalized["display_name"] = city_slug.replace("_", " ").title()

    output_root = normalized.get("output_root")
    if output_root:
        output_root_path = Path(output_root)
        normalized.setdefault("laz_dir", str(output_root_path / "laz"))
        normalized.setdefault("tiles_root", str(output_root_path / "tiles"))
        normalized.setdefault("logs_dir", str(output_root_path / "logs"))
        normalized.setdefault("status_dir", str(output_root_path / "status"))
        normalized.setdefault("audit_dir", str(output_root_path / "audit"))
        normalized.setdefault("catalog_root", str(output_root_path / "catalogs"))
    return normalized


def scaffold_dirs(cfg: dict) -> None:
    """Create expected output directories if they do not already exist."""
    output_root = Path(cfg["output_root"])
    laz_dir = Path(cfg["laz_dir"])
    tiles_root = Path(cfg.get("tiles_root", str(output_root / "tiles")))
    logs_dir = Path(cfg.get("logs_dir", str(output_root / "logs")))
    status_dir = Path(cfg.get("status_dir", str(output_root / "status")))
    audit_dir = Path(cfg.get("audit_dir", str(output_root / "audit")))

    dirs = [
        laz_dir,
        tiles_root,
        output_root / "catalogs",
        logs_dir,
        status_dir,
        audit_dir,
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
                "titles": [],
                "project_names": [],
                "on_disk_count": 0,
                "has_laz": False,
                "bbox_count": 0,
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

        title = tile.get("title")
        if title and len(g["titles"]) < 3:
            g["titles"].append(title)

        project = tile.get("project")
        if project and len(g["project_names"]) < 3:
            g["project_names"].append(project)

        if tile.get("on_disk"):
            g["on_disk_count"] += 1

        if tile.get("filename", "").lower().endswith(".laz"):
            g["has_laz"] = True

        if tile.get("bbox_4326"):
            g["bbox_count"] += 1

    for g in groups.values():
        g["publication_dates"] = sorted(g["publication_dates"])
        g["total_gb"] = round(g["total_bytes"] / 1_073_741_824, 2)
        g["bbox_coverage_pct"] = round((g["bbox_count"] / g["tile_count"]) * 100, 1) if g["tile_count"] else 0.0
        g["project_text"] = " ".join(g["project_names"])
        g["title_text"] = " ".join(g["titles"])

    return groups


# ── Campaign recommendation ───────────────────────────────────────────────────


def _extract_year_from_prefix(text: str) -> int | None:
    m = re.search(r"\b(19|20)(\d{2})\b", text)
    return int(m.group()) if m else None


def _years_from_dates(dates: list[str]) -> list[int]:
    years: list[int] = []
    for date in dates:
        m = re.match(r"^(19|20)\d{2}", str(date))
        if m:
            years.append(int(m.group()))
    return years


def _score_campaign_details(group: dict, cfg: dict) -> tuple[float, list[str]]:
    """Score a campaign for recommendation. Higher = better."""
    score = 0.0
    reasons: list[str] = []
    city_slug = cfg.get("city_slug", "")
    display_name = cfg.get("display_name", city_slug)
    name_lower = group["campaign_group"].lower()
    all_prefixes = " ".join(group["detailed_prefixes"].keys()).lower()
    title_text = str(group.get("title_text", "")).lower()
    project_text = str(group.get("project_text", "")).lower()
    haystack = f"{name_lower} {all_prefixes} {title_text} {project_text} {' '.join(group.get('sample_filenames', [])).lower()}"

    # Newer surveys preferred
    year = _extract_year_from_prefix(all_prefixes)
    date_years = _years_from_dates(group.get("publication_dates", []))
    if date_years:
        candidates = ([year] if year else []) + date_years
        year = max(candidates)
    if year:
        delta = (year - 2000) * 2.5
        score += delta
        reasons.append(f"newer survey signal ({year}, +{delta:.1f})")

    # City/county name match is a strong signal
    configured_keywords = cfg.get("campaign_keywords", [])
    if not isinstance(configured_keywords, list):
        configured_keywords = []
    terms = [
        city_slug.lower(),
        display_name.lower().replace(" ", ""),
        *[str(term).lower().replace(" ", "") for term in configured_keywords],
    ]
    city_terms = _normalize_tokens(city_slug, display_name, cfg.get("region", ""), cfg.get("laz_source", {}).get("sample_project", ""))
    overlap = sorted(term for term in city_terms if term in haystack)
    if overlap:
        bonus = min(12 + len(overlap) * 4, 40)
        score += bonus
        reasons.append(f"city metadata overlap ({', '.join(overlap[:3])}, +{bonus})")
    for term in terms:
        if term and len(term) >= 4 and term in haystack:
            score += 30
            reasons.append(f"city/campaign keyword match ({term}, +30)")
            break

    sample_project = str(cfg.get("laz_source", {}).get("sample_project", "")).lower()
    if sample_project and sample_project in haystack:
        score += 50
        reasons.append(f"sample project match ({sample_project}, +50)")

    # ARRA = older legacy program
    avoid_keywords = cfg.get("avoid_campaign_keywords", ["arra", "legacy"])
    if not isinstance(avoid_keywords, list):
        avoid_keywords = ["arra", "legacy"]
    matched_avoid = [str(term).lower() for term in avoid_keywords if str(term).lower() in haystack]
    if matched_avoid:
        score -= 25
        reasons.append(f"legacy/avoid keyword ({matched_avoid[0]}, -25)")

    # Sanity-check tile count
    count = group["tile_count"]
    if 30 <= count <= 3000:
        score += 10
        reasons.append("plausible tile count (+10)")
    elif count < 5:
        score -= 20
        reasons.append("very low tile count (-20)")

    # LAZ format preferred over LAS
    if group["has_laz"]:
        score += 5
        reasons.append("LAZ available (+5)")

    if group.get("on_disk_count", 0):
        on_disk_bonus = min(group["on_disk_count"], 25)
        score += on_disk_bonus
        reasons.append(f"existing local coverage (+{on_disk_bonus})")

    bbox_pct = group.get("bbox_coverage_pct", 0)
    if bbox_pct >= 95:
        score += 8
        reasons.append("complete tile bbox metadata (+8)")
    elif bbox_pct == 0 and count:
        score -= 15
        reasons.append("missing tile bbox metadata (-15)")

    # Bogus 1899 publication date = likely bad metadata
    for d in group["publication_dates"]:
        if d.startswith("1899"):
            score -= 40
            reasons.append("bogus 1899 publication date (-40)")
            break

    return score, reasons


def _score_campaign(group: dict, city_slug: str, display_name: str) -> float:
    """Backwards-compatible score helper used by older tests."""
    cfg = {"city_slug": city_slug, "display_name": display_name}
    score, _ = _score_campaign_details(group, cfg)
    return score


def recommend_campaign(groups: dict[str, dict], cfg: dict) -> tuple[str, str, str]:
    """
    Returns (best_campaign_group, best_detailed_prefix, reason_string).
    """
    if not groups:
        return "none", "none", "No campaigns found in remote manifest."

    city_slug = cfg.get("city_slug", "")
    display_name = cfg.get("display_name", city_slug)

    scored = []
    for grp, info in groups.items():
        score, reasons = _score_campaign_details(info, cfg)
        scored.append((grp, score, info, reasons))
    scored.sort(key=lambda x: -x[1])

    best_grp, best_score, best_info, best_reasons = scored[0]

    # Most-common detailed prefix within the winning group
    best_prefix = _best_detailed_prefix(best_info["detailed_prefixes"])

    year = _extract_year_from_prefix(best_prefix)
    year_str = f", acquisition year ~{year}" if year else ""
    legacy_note = " (ARRA/legacy — no better option found)" if "arra" in best_grp.lower() else ""

    reason = (
        f"Highest-scoring campaign: {best_grp} ({best_prefix}), "
        f"{best_info['tile_count']} tiles, "
        f"{best_info['total_gb']:.2f} GB"
        f"{year_str}{legacy_note}. Score {best_score:.1f}; "
        f"{'; '.join(best_reasons[:4]) or 'no strong positive signals'}."
    )
    return best_grp, best_prefix, reason


# ── Support data audit ───────────────────────────────────────────────────────


def audit_support_data(cfg: dict) -> list[str]:
    """
    Audit non-LAZ support data AND any existing processed phase outputs.

    Distinguishes three states:
      1. Source footprint file configured and present on disk
      2. Processed tile outputs exist but contain only fallback geometry
         (convex_hull / rotated_bbox from DBSCAN clusters)
      3. Processed tile outputs contain authoritative county footprint geometry

    "Support data OK" requires BOTH:
      - source footprint path configured and on disk
      - no processed outputs that indicate fallback mode was used

    NOLA failure mode: source footprints exist, tile.bbox_4326 = null in the
    tile manifest causes Phase 06 to ignore county features and fall back to
    cluster hulls. Outputs are technically valid but geometrically wrong.

    Returns a list of warning strings (empty = all clear).
    """
    warnings: list[str] = []
    warnings.extend(validate_city_config(cfg))

    # ── Building footprint source ─────────────────────────────────────────────
    fp_path_str = _cfg_text(cfg, "county_footprints_path", "building_footprints_path", "footprint_source")
    fp_source_ok = False
    if not fp_path_str:
        warnings.append(
            "No building footprint source configured in city config. "
            "Phase 06 will fall back to cluster convex hulls — "
            "outputs will NOT resemble real building massing."
        )
    elif not Path(fp_path_str).exists():
        warnings.append(
            f"Building footprint file not found on disk: {fp_path_str}. "
            "Phase 06 will fall back to cluster hulls. "
            "Download footprints before running the pipeline."
        )
    else:
        fp_source_ok = True

    # ── Processed phase output audit ─────────────────────────────────────────
    # Scan existing tile footprint outputs to detect whether footprint-assisted
    # or fallback (cluster hull) geometry was actually used.
    tiles_root = Path(cfg.get("tiles_root", cfg["output_root"] + "/tiles"))
    output_audit = _audit_footprint_outputs(tiles_root)

    if output_audit["total_output_files"] > 0:
        n_hull = output_audit["convex_hull_count"]
        n_county = output_audit["county_count"]
        n_unknown = output_audit["unknown_count"]

        if n_hull > 0 and n_county == 0:
            warnings.append(
                f"Only fallback footprint outputs found ({n_hull} features, "
                f"footprint_method=convex_hull across {output_audit['tile_count']} tile(s)). "
                "Authoritative building footprint source was NOT used during Phase 06. "
                "Blender massing will contain cluster hull artifacts."
            )
            warnings.append(
                "Convex/rotated bbox footprints detected; these are DBSCAN cluster outlines, "
                "not building footprints. Geometry will appear as slab/coastal hulls in Blender."
            )
            if fp_source_ok:
                warnings.append(
                    "Footprint source file EXISTS on disk but was not applied. "
                    "Likely cause: tile.bbox_4326 = null in tile_manifest.json, "
                    "which causes Phase 06 to skip county footprint mode. "
                    "Fix tile manifest bbox before re-running Phase 06."
                )
        elif n_county > 0 and n_hull == 0:
            pass  # all good — county footprints used
        elif n_county > 0 and n_hull > 0:
            warnings.append(
                f"Mixed footprint methods: {n_county} county features, {n_hull} convex_hull features. "
                "Some tiles used authoritative footprints; others fell back to cluster hulls."
            )

        if not fp_source_ok and n_hull > 0:
            warnings.append(
                "Footprint support is not OK: no source footprint path configured "
                "AND processed outputs confirm fallback hull geometry was used."
            )

    # ── City boundary ─────────────────────────────────────────────────────────
    boundary_path_str = _cfg_text(cfg, "boundary_geojson", "boundary_cache")
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

    # ── Address source ────────────────────────────────────────────────────────
    addr_path_str = _cfg_text(cfg, "addresses_path", "address_source")
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


def _audit_footprint_outputs(tiles_root: Path) -> dict:
    """
    Scan tile footprint output geojsons and count features by footprint_method.

    Returns:
        total_output_files: int
        tile_count: int
        convex_hull_count: int   — cluster hull fallback features
        county_count: int        — authoritative county footprint features
        unknown_count: int       — features with missing/unrecognised method
        fallback_tile_ids: list  — tile IDs where any convex_hull feature found
        county_tile_ids: list    — tile IDs where county features found
    """
    result = {
        "total_output_files": 0,
        "tile_count": 0,
        "convex_hull_count": 0,
        "county_count": 0,
        "unknown_count": 0,
        "fallback_tile_ids": [],
        "county_tile_ids": [],
    }

    if not tiles_root.exists():
        return result

    for tile_dir in sorted(tiles_root.iterdir()):
        fp_dir = tile_dir / "footprints"
        if not fp_dir.is_dir():
            continue

        fp_files = list(fp_dir.glob("*_footprints_convex_*.geojson"))
        if not fp_files:
            continue

        result["tile_count"] += 1
        result["total_output_files"] += len(list(fp_dir.glob("*.geojson")))
        tile_id = tile_dir.name
        tile_hull = 0
        tile_county = 0

        for fp_file in fp_files:
            try:
                data = json.loads(fp_file.read_text(encoding="utf-8"))
                for feat in data.get("features", []):
                    method = feat.get("properties", {}).get("footprint_method", "unknown")
                    if method == "convex_hull":
                        result["convex_hull_count"] += 1
                        tile_hull += 1
                    elif method == "county":
                        result["county_count"] += 1
                        tile_county += 1
                    else:
                        result["unknown_count"] += 1
            except (json.JSONDecodeError, OSError):
                pass

        if tile_hull > 0 and tile_id not in result["fallback_tile_ids"]:
            result["fallback_tile_ids"].append(tile_id)
        if tile_county > 0 and tile_id not in result["county_tile_ids"]:
            result["county_tile_ids"].append(tile_id)

    return result


def print_support_data_audit(cfg: dict) -> None:
    """Print support data audit including phase output analysis."""
    warnings = audit_support_data(cfg)

    # Also print the raw output audit counts for visibility
    tiles_root = Path(cfg.get("tiles_root", cfg["output_root"] + "/tiles"))
    output_audit = _audit_footprint_outputs(tiles_root)

    if output_audit["total_output_files"] > 0:
        _pr("\n  ── Phase 06 output audit ──────────────────────────────────")
        _pr(f"  Tiles with footprint outputs : {output_audit['tile_count']}")
        _pr(f"  County footprint features    : {output_audit['county_count']}")
        _pr(f"  Convex hull (fallback) feats : {output_audit['convex_hull_count']}")
        if output_audit["unknown_count"]:
            _pr(f"  Unknown method features      : {output_audit['unknown_count']}")
        if output_audit["fallback_tile_ids"]:
            for tid in output_audit["fallback_tile_ids"]:
                _pr(f"  [red]  Fallback tile:[/red] {tid}")
        if output_audit["county_tile_ids"]:
            for tid in output_audit["county_tile_ids"]:
                _pr(f"  [green]  County tile:[/green] {tid}")

    if not warnings:
        _pr("  [green]Support data OK[/green] — footprints, boundary, addresses present; outputs use county geometry")
        return

    _pr("\n  [bold yellow]Support data warnings:[/bold yellow]")
    for w in warnings:
        _pr(f"  [yellow]  !  {w}[/yellow]")
    _pr(
        "\n  [dim]LiDAR can be staged now, but pipeline outputs may be degraded or "
        "produce hull artifacts if support data issues are not resolved before ingestion.[/dim]"
    )


def _print_onboarding_roadmap(
    cfg: dict,
    manifest: dict | None = None,
    support_warnings: list[str] | None = None,
    recommendation: tuple[str, str, str] | None = None,
) -> None:
    """Print the remaining manual steps needed to fully automate onboarding."""
    support_warnings = support_warnings if support_warnings is not None else audit_support_data(cfg)
    roadmap: list[tuple[str, str, str]] = []

    city_slug = cfg.get("city_slug", "city")
    display_name = cfg.get("display_name", city_slug)
    tiles_root = Path(cfg.get("tiles_root", str(Path(cfg["output_root"]) / "tiles")))
    catalog_dir = Path(cfg.get("catalog_root", str(Path(cfg["output_root"]) / "catalogs")))
    catalog_path = catalog_dir / f"{city_slug}_catalog.json"
    local_catalog = build_local_catalog(cfg)
    bbox = cfg.get("bbox_4326") or {}
    manifest_path = Path(cfg.get("tile_manifest", str(Path(cfg["output_root"]) / "tile_manifest.json")))
    tile_manifest = _load_manifest(manifest_path)

    roadmap.append((
        "complete" if recommendation else "manual",
        "Discover campaigns",
        "Remote manifest already exists" if manifest else "Run --query-tnm to discover campaigns",
    ))

    if recommendation:
        best_grp, best_prefix, reason = recommendation
        roadmap.append((
            "complete",
            "Recommend best campaign",
            f"{best_prefix} ({best_grp}) - {reason}",
        ))
    else:
        roadmap.append((
            "manual",
            "Recommend best campaign",
            "No recommendation yet; query TNM first",
        ))

    pending_tiles = 0
    if manifest:
        pending_tiles = sum(1 for tile in manifest.get("tiles", []) if not Path(tile["local_path"]).exists())
    roadmap.append((
        "complete" if manifest and pending_tiles == 0 else "manual",
        "Download tiles",
        f"{pending_tiles} tile(s) still missing locally" if manifest else "Need a remote manifest first",
    ))

    if support_warnings:
        roadmap.append((
            "manual",
            "Audit support data",
            f"{len(support_warnings)} issue(s) remain in footprints, boundary, or addresses",
        ))
    else:
        roadmap.append((
            "complete",
            "Audit support data",
            "Footprints, boundary, and addresses are present",
        ))

    if tile_manifest and isinstance(tile_manifest.get("tiles"), list):
        null_bbox = [t for t in tile_manifest["tiles"] if not t.get("bbox_4326")]
        roadmap.append((
            "manual" if null_bbox else "complete",
            "Verify readiness",
            "Regenerate Phase 02 so every tile has bbox_4326" if null_bbox else "Tile manifest contains tile bboxes",
        ))
    else:
        roadmap.append((
            "manual",
            "Verify readiness",
            "Tile manifest is missing; run Phase 02 first",
        ))

    roadmap.append((
        "complete" if local_catalog["count"] > 0 else "manual",
        "Build catalog",
        f"{local_catalog['count']} local LAZ/LAS file(s) found" if local_catalog["count"] > 0 else "Download at least one tile first",
    ))

    ready_for_pipeline = local_catalog["count"] > 0 and not support_warnings
    roadmap.append((
        "complete" if ready_for_pipeline else "manual",
        "Hand off to pipeline",
        f"Run scripts/run_city_pipeline.py with {catalog_path}" if ready_for_pipeline else "Resolve blockers before pipeline execution",
    ))

    _pr(f"\n[bold]Onboarding roadmap — {display_name}[/bold]")
    for idx, (state, title, detail) in enumerate(roadmap, 1):
        label = {
            "complete": "[green]done[/green]",
            "manual": "[yellow]manual[/yellow]",
            "blocked": "[red]blocked[/red]",
        }.get(state, "[dim]pending[/dim]")
        _pr(f"  {idx}. {title:<24} {label}  {detail}")

    if support_warnings:
        _pr("\n  Remaining manual checks:")
        for warning in support_warnings[:6]:
            _pr(f"    - {warning}")
        if len(support_warnings) > 6:
            _pr(f"    - ... and {len(support_warnings) - 6} more")

    if recommendation:
        _pr("\n  Suggested next command:")
        _pr(f"    python scripts/bootstrap_city_lidar.py {city_slug} --campaign {recommendation[1]} --download-dry-run")


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

    return {
        "tile_count": len(tiles),
        "on_disk_count": on_disk_count,
        "pending_count": len(pending),
        "pending_bytes": pending_bytes,
    }


def download_tiles(
    manifest: dict,
    laz_dir: Path,
    limit: int | None = None,
    download_all: bool = False,
) -> dict:
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
        return {"downloaded": 0, "failed": 0, "pending": 0, "bytes": 0}

    tiles = manifest.get("tiles", [])
    pending = [t for t in tiles if not Path(t["local_path"]).exists()]

    if limit is not None:
        pending = pending[:limit]

    total_bytes = sum(t.get("file_size_bytes") or 0 for t in pending)
    _pr(f"\n  Tiles to download: {len(pending)}  (~{total_bytes / 1_073_741_824:.2f} GB)")

    if not pending:
        _pr("  All tiles already on disk.")
        return {"downloaded": 0, "failed": 0, "pending": 0, "bytes": 0}

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
    return {
        "downloaded": ok,
        "failed": fail,
        "pending": len(pending),
        "bytes": total_bytes,
    }


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
        "pipeline_handoff": {
            "config": f"configs/cities/{cfg['city_slug']}.json",
            "catalog": f"{cfg['city_slug']}_catalog.json",
            "suggested_command": (
                "python scripts/run_city_pipeline.py "
                f"--config configs/cities/{cfg['city_slug']}.json "
                f"--catalog {cfg['city_slug']}_catalog.json "
                "--to-phase 08 --execute"
            ),
        },
    }


def build_readiness_report(cfg: dict, manifest: dict | None = None) -> dict:
    """
    Build a structured onboarding readiness report.

    This is read-only and intentionally separates "can download LiDAR" from
    "safe to hand off to the geometry pipeline".
    """
    support_warnings = audit_support_data(cfg)
    local_catalog = build_local_catalog(cfg)

    report: dict = {
        "schema_version": "1.0",
        "city_slug": cfg.get("city_slug"),
        "display_name": cfg.get("display_name"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "support_warnings": support_warnings,
        "local_laz_count": local_catalog["count"],
        "ready": False,
        "ready_for_download_test": False,
        "ready_for_pipeline_handoff": False,
        "recommended_campaign": None,
        "manual_steps_remaining": [],
        "pipeline_handoff": local_catalog["pipeline_handoff"],
    }

    if support_warnings:
        report["manual_steps_remaining"].append("Resolve support-data warnings before production ingestion.")

    if manifest:
        groups = group_by_campaign(manifest.get("tiles", []))
        rec = recommend_campaign(groups, cfg)
        best_grp, best_prefix, reason = rec
        report["remote_manifest"] = {
            "tile_count": manifest.get("tile_count", len(manifest.get("tiles", []))),
            "on_disk_count": sum(1 for t in manifest.get("tiles", []) if Path(t.get("local_path", "")).exists()),
            "campaign_count": len(groups),
        }
        report["recommended_campaign"] = {
            "campaign_group": best_grp,
            "detailed_prefix": best_prefix,
            "reason": reason,
        }
        report["ready_for_download_test"] = bool(manifest.get("tiles"))
        if not manifest.get("tiles"):
            report["manual_steps_remaining"].append("No remote tiles found; inspect bbox or TNM availability.")
    else:
        report["manual_steps_remaining"].append("Build or provide a remote manifest with --query-tnm.")

    report["ready_for_pipeline_handoff"] = local_catalog["count"] > 0 and not support_warnings
    report["ready"] = report["ready_for_pipeline_handoff"]
    if local_catalog["count"] == 0:
        report["manual_steps_remaining"].append("Download at least one verified LAZ/LAS tile before pipeline handoff.")

    return report


def print_readiness_report(report: dict) -> None:
    """Print a compact readiness report."""
    _pr("\n  --- City onboarding readiness ---")
    _pr(f"  City                     : {report.get('display_name') or report.get('city_slug')}")
    _pr(f"  Local LAZ/LAS files      : {report['local_laz_count']}")
    if report.get("remote_manifest"):
        rm = report["remote_manifest"]
        _pr(f"  Remote manifest tiles    : {rm['tile_count']}")
        _pr(f"  Campaigns discovered     : {rm['campaign_count']}")
    if report.get("recommended_campaign"):
        rec = report["recommended_campaign"]
        _pr(f"  Recommended campaign     : {rec['detailed_prefix']}")
    _pr(f"  Download test ready      : {'YES' if report['ready_for_download_test'] else 'NO'}")
    _pr(f"  Pipeline handoff ready   : {'YES' if report['ready_for_pipeline_handoff'] else 'NO'}")
    if report["manual_steps_remaining"]:
        _pr("\n  Manual steps remaining:")
        for step in report["manual_steps_remaining"]:
            _pr(f"    - {step}")


def print_failure_report(stage: str, message: str, cfg: dict, details: list[str] | None = None) -> None:
    """Print a repeatable failure block with concrete next actions."""
    _pr(f"\n[bold red]Bootstrap failed at {stage}[/bold red]")
    _pr(f"  City       : {cfg.get('display_name', cfg.get('city_slug', 'unknown'))}")
    _pr(f"  Reason     : {message}")
    if details:
        _pr("  Details:")
        for detail in details:
            _pr(f"    - {detail}")
    _pr("  Recovery:")
    _pr("    - Re-run with --dry-run or --download-dry-run before any download.")
    _pr("    - Check bbox_4326, output paths, support data paths, and TNM service availability.")


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


def _print_onboarding_roadmap(
    cfg: dict,
    manifest: dict | None = None,
    support_warnings: list[str] | None = None,
    recommendation: tuple[str, str, str] | None = None,
) -> None:
    """Print the remaining manual steps and automation roadmap."""
    support_warnings = support_warnings if support_warnings is not None else audit_support_data(cfg)
    if recommendation is None and manifest:
        recommendation = recommend_campaign(group_by_campaign(manifest.get("tiles", [])), cfg)

    city_slug = cfg.get("city_slug", "city")
    display_name = cfg.get("display_name", city_slug)
    output_root = Path(cfg["output_root"])
    catalog_dir = Path(cfg.get("catalog_root", str(output_root / "catalogs")))
    catalog_path = catalog_dir / f"{city_slug}_catalog.json"
    local_catalog = build_local_catalog(cfg)
    manifest_path = Path(cfg.get("tile_manifest", str(output_root / "tile_manifest.json")))
    tile_manifest = _load_manifest(manifest_path)

    _pr(f"\n[bold]Onboarding roadmap — {display_name}[/bold]")
    steps: list[tuple[str, str, str]] = []

    steps.append((
        "complete" if recommendation else "manual",
        "Discover campaigns",
        "Remote manifest already exists" if manifest else "Run --query-tnm to discover campaigns",
    ))

    if recommendation:
        steps.append((
            "complete",
            "Recommend best campaign",
            f"{recommendation[1]} ({recommendation[0]})",
        ))
    else:
        steps.append((
            "manual",
            "Recommend best campaign",
            "No recommendation yet; run --query-tnm first",
        ))

    pending_tiles = 0
    if manifest:
        pending_tiles = sum(1 for tile in manifest.get("tiles", []) if not Path(tile["local_path"]).exists())
    steps.append((
        "complete" if manifest and pending_tiles == 0 else "manual",
        "Download tiles",
        f"{pending_tiles} tile(s) still missing locally" if manifest else "Need a remote manifest first",
    ))

    if support_warnings:
        steps.append((
            "manual",
            "Audit support data",
            f"{len(support_warnings)} issue(s) remain in footprints, boundary, or addresses",
        ))
    else:
        steps.append((
            "complete",
            "Audit support data",
            "Footprints, boundary, and addresses are present",
        ))

    if tile_manifest and isinstance(tile_manifest.get("tiles"), list):
        null_bbox = [t for t in tile_manifest["tiles"] if not t.get("bbox_4326")]
        steps.append((
            "manual" if null_bbox else "complete",
            "Verify readiness",
            "Regenerate Phase 02 so every tile has bbox_4326" if null_bbox else "Tile manifest contains tile bboxes",
        ))
    else:
        steps.append((
            "manual",
            "Verify readiness",
            "Tile manifest is missing; run Phase 02 first",
        ))

    steps.append((
        "complete" if local_catalog["count"] > 0 else "manual",
        "Build catalog",
        f"{local_catalog['count']} local LAZ/LAS file(s) found" if local_catalog["count"] > 0 else "Download at least one tile first",
    ))

    ready_for_pipeline = local_catalog["count"] > 0 and not support_warnings
    steps.append((
        "complete" if ready_for_pipeline else "manual",
        "Hand off to pipeline",
        f"Run scripts/run_city_pipeline.py with {catalog_path}" if ready_for_pipeline else "Resolve blockers before pipeline execution",
    ))

    for idx, (state, title, detail) in enumerate(steps, 1):
        label = {
            "complete": "[green]done[/green]",
            "manual": "[yellow]manual[/yellow]",
            "blocked": "[red]blocked[/red]",
        }.get(state, "[dim]pending[/dim]")
        _pr(f"  {idx}. {title:<24} {label}  {detail}")

    _pr("\n[bold]Automation roadmap[/bold]")
    _pr("  1. Generate city configs from a single source of truth for bbox, CRS, and support-data paths.")
    _pr("  2. Persist TNM discovery state so campaign searches can resume without requerying from scratch.")
    _pr("  3. Rank campaigns with metadata overlap, year signals, bbox coverage, and existing local coverage.")
    _pr("  4. Auto-discover footprint, boundary, and address datasets from city/county portals where available.")
    _pr("  5. Validate tile manifests and LAZ headers before downloading anything beyond a test tile.")
    _pr("  6. Emit a structured handoff artifact that run_city_pipeline.py can consume directly.")


# ── Phase output diagnosis ───────────────────────────────────────────────────


def _diagnose_phase_outputs(cfg: dict) -> None:
    """
    Read-only deep audit of Phase 06 footprint outputs.

    Reports:
      - footprint source path from config and whether it exists on disk
      - per-tile footprint mode (county vs convex_hull fallback)
      - count of convex fallback, rotated bbox, and county footprint files
      - sample of affected tile IDs
      - tile manifest bbox_4326 status (null = triggers Phase 06 fallback)
    """
    city_slug = cfg["city_slug"]
    output_root = Path(cfg["output_root"])
    tiles_root = Path(cfg.get("tiles_root", str(output_root / "tiles")))
    tile_manifest_path = Path(cfg.get("tile_manifest", str(output_root / "tile_manifest.json")))

    fp_path_str = _cfg_text(cfg, "county_footprints_path", "building_footprints_path", "footprint_source")
    boundary_path_str = _cfg_text(cfg, "boundary_geojson", "boundary_cache")

    _pr(f"\n  ── {city_slug} Phase 06 Footprint Diagnosis " + "─" * 30)

    # Source files
    _pr(f"\n  Footprint source path  : {fp_path_str or '(not configured)'}")
    if fp_path_str:
        exists = Path(fp_path_str).exists()
        _pr(f"  Footprint source exists: {'[green]YES[/green]' if exists else '[red]NO[/red]'}")
        if exists:
            try:
                size_mb = Path(fp_path_str).stat().st_size / 1_048_576
                _pr(f"  Footprint file size    : {size_mb:.1f} MB")
            except OSError:
                pass

    _pr(f"\n  Boundary source path   : {boundary_path_str or '(not configured)'}")
    if boundary_path_str:
        _pr(f"  Boundary exists        : {'[green]YES[/green]' if Path(boundary_path_str).exists() else '[red]NO[/red]'}")

    # Tile manifest bbox status
    _pr(f"\n  Tile manifest          : {tile_manifest_path}")
    if tile_manifest_path.exists():
        try:
            tm = json.loads(tile_manifest_path.read_text(encoding="utf-8"))
            tiles = tm.get("tiles", [])
            null_bbox = [t["tile_id"] for t in tiles if not t.get("bbox_4326")]
            has_bbox = [t["tile_id"] for t in tiles if t.get("bbox_4326")]
            _pr(f"  Total tiles            : {len(tiles)}")
            _pr(f"  Tiles with bbox_4326   : {len(has_bbox)}")
            if null_bbox:
                _pr(f"  [red]Tiles with null bbox   : {len(null_bbox)}[/red]  "
                    f"← Phase 06 cannot use county footprints without bbox")
                for tid in null_bbox[:5]:
                    _pr(f"    {tid}")
                if len(null_bbox) > 5:
                    _pr(f"    … and {len(null_bbox) - 5} more")
        except (json.JSONDecodeError, OSError) as exc:
            _pr(f"  [red]Could not read tile manifest: {exc}[/red]")
    else:
        _pr("  [yellow]Tile manifest not found[/yellow] (Phase 02 not run yet)")

    # Per-tile phase output scan
    _pr(f"\n  Tiles root             : {tiles_root}")
    output_audit = _audit_footprint_outputs(tiles_root)

    if output_audit["total_output_files"] == 0:
        _pr("  [dim]No Phase 06 outputs found (pipeline not run yet)[/dim]")
        return

    _pr(f"  Tiles with outputs     : {output_audit['tile_count']}")
    _pr(f"  County fp features     : [green]{output_audit['county_count']}[/green]"
        if output_audit["county_count"] else f"  County fp features     : [red]{output_audit['county_count']}[/red]")
    _pr(f"  Convex hull features   : [red]{output_audit['convex_hull_count']}[/red]"
        if output_audit["convex_hull_count"] else f"  Convex hull features   : [green]{output_audit['convex_hull_count']}[/green]")
    if output_audit["unknown_count"]:
        _pr(f"  Unknown method features: {output_audit['unknown_count']}")

    if output_audit["fallback_tile_ids"]:
        _pr(f"\n  [red]Tiles using cluster hull fallback ({len(output_audit['fallback_tile_ids'])}):[/red]")
        for tid in output_audit["fallback_tile_ids"]:
            _pr(f"    {tid}")
            convex_path = tiles_root / tid / "footprints" / f"{tid}_footprints_convex_*.geojson"
            matches = list((tiles_root / tid / "footprints").glob(f"{tid}_footprints_convex_*.geojson"))
            if matches:
                _pr(f"      {matches[0]}")

    if output_audit["county_tile_ids"]:
        _pr(f"\n  [green]Tiles using county footprints ({len(output_audit['county_tile_ids'])}):[/green]")
        for tid in output_audit["county_tile_ids"]:
            _pr(f"    {tid}")

    # Verdict
    _pr("\n  ── Verdict " + "─" * 58)
    if output_audit["convex_hull_count"] > 0 and output_audit["county_count"] == 0:
        _pr(
            "  [bold red]ALL outputs are cluster hull fallback geometry.[/bold red]\n"
            "  Blender massing will show convex/slab cluster outlines, not building shapes.\n"
            "  Do NOT re-run ingestion without fixing the root cause first."
        )
        if fp_path_str and Path(fp_path_str).exists():
            _pr(
                "\n  Root cause: footprint source exists on disk but tile.bbox_4326 = null\n"
                "  in the tile manifest. Phase 06 requires a tile bbox to clip county\n"
                "  footprints to the tile's spatial extent. Without it, the county\n"
                "  footprint path cannot run and the phase falls back to cluster hulls.\n"
                "\n  Next fixes to check:\n"
                "    • regenerate the tile manifest after Phase 02\n"
                "    • confirm bbox_4326 is populated for every tile\n"
                "    • ensure boundary_geojson is configured when you want city clipping"
            )
    elif output_audit["county_count"] > 0 and output_audit["convex_hull_count"] == 0:
        _pr("  [green]All outputs use authoritative county footprint geometry. OK.[/green]")
    else:
        _pr("  [yellow]Mixed geometry: some tiles used county footprints, others used hull fallback.[/yellow]")


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

    # Diagnostics
    parser.add_argument("--diagnose", action="store_true",
                        help="Run deep phase output audit: report footprint mode per tile, "
                             "count fallback vs county outputs (read-only)")
    parser.add_argument("--roadmap", action="store_true",
                        help="Print remaining manual steps and automation roadmap, then exit")
    parser.add_argument("--readiness-report", action="store_true",
                        help="Print a structured city onboarding readiness report")
    parser.add_argument("--write-readiness-report", action="store_true",
                        help="Write readiness report JSON to output_root/status")

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

    cfg = normalize_city_config(cfg)

    city_slug = cfg["city_slug"]
    output_root = Path(cfg["output_root"])
    laz_dir = Path(cfg["laz_dir"])
    catalog_dir = Path(cfg.get("catalog_root", str(output_root / "catalogs")))

    _pr(f"\n[bold cyan]GlitchOS City LiDAR Bootstrapper — {cfg.get('display_name', city_slug)}[/bold cyan]")
    _pr(f"  City slug   : {city_slug}")
    _pr(f"  LAZ dir     : {laz_dir}")
    _pr(f"  Output root : {output_root}")

    config_warnings = validate_city_config(cfg)
    if config_warnings:
        _pr("\n[bold yellow]City config warnings:[/bold yellow]")
        for w in config_warnings:
            _pr(f"  [yellow]! {w}[/yellow]")

    # ── Scaffold
    _pr("\n[bold]Scaffolding directories…[/bold]")
    scaffold_dirs(cfg)

    # ── Support data audit (runs always — warns early about missing footprints/boundary)
    _pr("\n[bold]Checking support data…[/bold]")
    print_support_data_audit(cfg)
    support_warnings = audit_support_data(cfg)

    remote_manifest_path = args.manifest or (catalog_dir / f"{city_slug}_remote_manifest.json")

    # ── Query TNM
    active_manifest: dict | None = None

    if args.query_tnm:
        _pr(f"\n[bold]Querying USGS TNM (max={args.max})…[/bold]")
        manifest = build_remote_manifest(cfg, max_results=args.max)
        if manifest is None:
            print_failure_report("TNM discovery", "TNM query failed; no files written.", cfg)
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
                    args.verify_first, args.build_local_catalog, args.roadmap,
                    args.diagnose, args.readiness_report, args.write_readiness_report]):
            _, best_prefix, _ = rec
            _pr(f"\n  Next step — filter to recommended campaign:")
            _pr(f"    python scripts/bootstrap_city_lidar.py {city_slug} \\")
            _pr(f"        --campaign {best_prefix} --download-dry-run")
            _print_onboarding_roadmap(cfg, manifest=manifest, support_warnings=support_warnings, recommendation=rec)
            return 0

    else:
        # Load existing remote manifest for subsequent operations
        active_manifest = _load_manifest(remote_manifest_path)

    # ── Campaign / pattern filter
    if args.campaign or args.filter_pattern:
        if active_manifest is None:
            print_failure_report(
                "campaign filtering",
                f"No remote manifest found at {remote_manifest_path}",
                cfg,
                ["Run --query-tnm first to build the remote manifest."],
            )
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
            print_failure_report("download dry-run", "No manifest available.", cfg, ["Run --query-tnm first."])
            return 1
        _pr("\n[bold]Download dry-run:[/bold]")
        dry_run_download(active_manifest)

    # ── Actual download
    if args.download_limit or args.download_all:
        if active_manifest is None:
            print_failure_report("download", "No manifest available.", cfg, ["Run --query-tnm first."])
            return 1
        _pr("\n[bold]Downloading tiles…[/bold]")
        download_report = download_tiles(
            active_manifest, laz_dir,
            limit=args.download_limit,
            download_all=args.download_all,
        )
        if download_report.get("failed", 0):
            _pr(
                f"  [yellow]Download finished with {download_report['failed']} failure(s).[/yellow] "
                "Re-run after checking network, disk space, or file permissions."
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

    # ── Diagnose phase outputs
    if args.diagnose:
        _pr("\n[bold]Phase output diagnosis (read-only)…[/bold]")
        _diagnose_phase_outputs(cfg)

    if args.roadmap:
        _print_onboarding_roadmap(cfg, manifest=active_manifest, support_warnings=support_warnings)

    if args.readiness_report or args.write_readiness_report:
        if active_manifest is None:
            active_manifest = _load_manifest(remote_manifest_path)
        report = build_readiness_report(cfg, active_manifest)
        if args.readiness_report:
            print_readiness_report(report)
        if args.write_readiness_report:
            if args.dry_run:
                _pr("  [dim]Dry run — readiness report not written.[/dim]")
            else:
                status_dir = Path(cfg.get("status_dir", str(output_root / "status")))
                status_dir.mkdir(parents=True, exist_ok=True)
                report_path = status_dir / f"{city_slug}_readiness_report.json"
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                _pr(f"  [green]Readiness report written:[/green] {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
