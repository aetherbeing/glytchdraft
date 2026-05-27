"""
run_miami_city.py  [GlitchOS city pipeline — Miami]

Orchestrator for the full City of Miami 3DEP pipeline.

CONTRACT (non-negotiable):
  - Source LAZ files in CFG.LAZ_DIR are NEVER modified (PRESERVE_RAW_LAZ).
  - All outputs go under CFG.TILES_ROOT / CFG.OUT_ROOT only.
  - Processing does not start until preflight passes (rule 11).
  - Address ingestion is optional/fail-soft (rule 4).
  - Audit written after every execute run (rule 9).
  - city_manifest.json written with all asset paths (rule 10).

Usage:
    python scripts/miami/run_miami_city.py --dry-run
    python scripts/miami/run_miami_city.py --dry-run --force-catalog
    python scripts/miami/run_miami_city.py --execute
    python scripts/miami/run_miami_city.py --execute --limit 5
    python scripts/miami/run_miami_city.py --execute --tile <tile_id>
    python scripts/miami/run_miami_city.py --execute --force-preflight
    python scripts/miami/run_miami_city.py --preflight
    python scripts/miami/run_miami_city.py --audit

Exit codes:
    0  all OK (or dry-run complete)
    1  preflight failed / one or more tiles failed
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))

import miami_city_config as CFG
from build_miami_catalog import build_catalog
from preflight_miami import run_preflight
from audit_miami_city import build_audit
from merge_city_assets import merge_terrain_ply, merge_vegetation_ply, export_city_glb

try:
    from rich import box
    from rich.console import Console, Group as RGroup
    from rich.live import Live
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console(force_terminal=True) if HAS_RICH else None

# ── dashboard constants ────────────────────────────────────────────────────────

TILE_STAGES = ["extract", "clean", "cluster", "footprints", "masses"]
# vegetation stage added when enabled — evaluated after CFG is imported
if CFG.VEGETATION_ENABLED:
    TILE_STAGES = TILE_STAGES + ["vegetation"]

_STATUS_LABEL = {
    "pending": ("dim",   "○ pending"),
    "running": ("cyan",  "▶ running"),
    "done":    ("green", "✓ done"),
    "failed":  ("red",   "✗ failed"),
    "skipped": ("dim",   "– skipped"),
}

# Patterns to detect stage transitions from run_tile_miami.py stdout
_RE_COMPLETE = re.compile(r"^\s+\[(\w+)\] (\S+) \([\d.]+s\)")   # "  [cluster] ok (12.3s)"
_RE_RESUME   = re.compile(r"^\s+\[resume\] (\w+) already passed") # "  [resume] extract already passed"
_RE_START    = re.compile(r"^\s+\[(\w+)\] ")                      # "  [extract] ..."


def _fmt(secs: float) -> str:
    if secs < 60:
        return f"{secs:.0f}s"
    m, s = divmod(int(secs), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _bar(done: int, total: int, width: int = 32) -> str:
    filled = int(width * done / max(total, 1))
    return "█" * filled + "░" * (width - filled)


def _detect_stage(line: str, state: dict) -> None:
    """Parse one stdout line from run_tile_miami.py and update stage tracking."""
    now = time.monotonic()

    m = _RE_RESUME.match(line)
    if m:
        s = m.group(1)
        if s in TILE_STAGES:
            state["stage_statuses"][s] = "skipped"
        return

    m = _RE_COMPLETE.match(line)
    if m:
        s, word = m.group(1), m.group(2)
        if s in TILE_STAGES:
            if s in state["stage_starts"]:
                state["stage_durations"][s] = now - state["stage_starts"][s]
            state["stage_statuses"][s] = "done" if word == "ok" else "failed"
        return

    m = _RE_START.match(line)
    if m:
        s = m.group(1)
        if s in TILE_STAGES and state["stage_statuses"].get(s) == "pending":
            state["stage_statuses"][s] = "running"
            state["stage_starts"][s]   = now


def _render_dashboard(state: dict) -> Panel:
    now     = time.monotonic()
    elapsed = now - state["run_start"]
    n_done  = state["n_done"]
    n_total = state["n_total"]

    # ── header ────────────────────────────────────────────────────────────────
    hdr = Text()
    hdr.append("GlitchOS.io", style="bold magenta")
    hdr.append("  ·  City of Miami  ·  ", style="dim")
    hdr.append(f"v{PIPELINE_VERSION}", style="dim")
    hdr.append(f"   started {state['start_clock']}", style="dim")
    hdr.append(f"\n{_disk_stats()}", style="dim cyan")
    if n_total:
        hdr.append(f"   {n_total} tiles", style="dim")

    # ── elapsed + ETA ─────────────────────────────────────────────────────────
    durs = state["tile_durations"]
    if durs and n_done < n_total:
        eta_str = _fmt(sum(durs) / len(durs) * (n_total - n_done))
    else:
        eta_str = "—"
    timing = Text()
    timing.append(f"  elapsed {_fmt(elapsed)}", style="dim")
    timing.append(f"   ETA {eta_str}", style="dim")
    if state["phase"] != "processing":
        timing.append(f"   phase: {state['phase']}", style="dim yellow")

    # ── overall progress bar ──────────────────────────────────────────────────
    pct  = n_done / max(n_total, 1) * 100
    prog = Text()
    prog.append(f"  {_bar(n_done, n_total)} ", style="cyan")
    prog.append(f"{n_done}/{n_total if n_total else '?'} tiles", style="bold white")
    prog.append(f"  ({pct:.0f}%)", style="dim")

    ok_fail = Text()
    ok_fail.append(f"  ✓ {state['n_ok']} ok", style="green")
    if state["n_failed"]:
        ok_fail.append(f"   ✗ {state['n_failed']} failed", style="bold red")
    ok_fail.append(f"   buildings: {state['n_buildings']:,}", style="green")

    # ── current tile + per-stage table ────────────────────────────────────────
    cur = state["current_tile"]
    if cur:
        short = cur[-42:] if len(cur) > 42 else cur
        tile_hdr = Text()
        tile_hdr.append("  Tile  ", style="dim")
        tile_hdr.append(short, style="bold cyan")

        stbl = Table(box=None, show_header=False, padding=(0, 1))
        stbl.add_column("",      width=4)
        stbl.add_column("stage", width=12)
        stbl.add_column("state", width=14)
        stbl.add_column("time",  width=8, justify="right")
        for s in TILE_STAGES:
            st           = state["stage_statuses"].get(s, "pending")
            sty, label   = _STATUS_LABEL[st]
            if st == "running" and s in state["stage_starts"]:
                t_str = _fmt(now - state["stage_starts"][s])
            elif s in state["stage_durations"]:
                t_str = _fmt(state["stage_durations"][s])
            else:
                t_str = ""
            stbl.add_row("  ", s, Text(label, style=sty), t_str)
    else:
        tile_hdr = Text(f"  {state['phase']}…", style="dim yellow")
        stbl     = Text("")

    # ── log tail ──────────────────────────────────────────────────────────────
    tail    = list(state["log_tail"])
    tail_mk = "\n".join(f"  [dim]{ln[:112]}[/dim]" for ln in tail) if tail else "  [dim]—[/dim]"

    body = RGroup(
        hdr,
        Text(""),
        timing,
        prog,
        ok_fail,
        Text(""),
        tile_hdr,
        stbl,
        Rule(style="dim"),
        Text.from_markup(tail_mk),
    )
    return Panel(body, box=box.ROUNDED, padding=(0, 1))

PIPELINE_VERSION = CFG.PIPELINE_VERSION
_TILE_RUNNER = str(Path(__file__).parent / "run_tile_miami.py")


# ── boundary helpers ───────────────────────────────────────────────────────────

_CITY_BOUNDARY_URLS = [
    "https://opendata.arcgis.com/datasets/5b5d47fcf96b4a1890cfbbf1d2a2c803_0.geojson",
    (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
        "Places_CouSub_ConCity_SubMCD/MapServer/10/query"
        "?where=STATEFP%3D'12'+AND+PLACEFP%3D'45000'"
        "&outFields=*&f=geojson&outSR=4326"
    ),
]

_HTTP_TIMEOUT = 60


def _get(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError):
        return None


def _collect_coords(obj, xs: list, ys: list):
    if not obj:
        return
    if isinstance(obj[0], (int, float)):
        xs.append(obj[0]); ys.append(obj[1])
    else:
        for sub in obj:
            _collect_coords(sub, xs, ys)


def _bbox_from_geojson(fc: dict) -> dict | None:
    xs, ys = [], []
    for feat in fc.get("features", []):
        _collect_coords(feat.get("geometry", {}).get("coordinates", []), xs, ys)
    if not xs:
        return None
    return {"xmin": min(xs), "ymin": min(ys), "xmax": max(xs), "ymax": max(ys)}


def _download_boundary() -> tuple[dict | None, str]:
    CFG.BOUNDARIES_DIR.mkdir(parents=True, exist_ok=True)
    if CFG.BOUNDARY_CACHE.exists():
        try:
            fc = json.loads(CFG.BOUNDARY_CACHE.read_text(encoding="utf-8"))
            return fc, f"cached {CFG.BOUNDARY_CACHE}"
        except Exception:
            pass
    for url in _CITY_BOUNDARY_URLS:
        raw = _get(url)
        if not raw:
            continue
        try:
            fc = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        if fc.get("features"):
            CFG.BOUNDARY_CACHE.write_text(json.dumps(fc), encoding="utf-8")
            return fc, url
    return None, "hardcoded bbox fallback"


def _bbox_intersects(a: dict, b: dict) -> bool:
    return (
        a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"]
        and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]
    )


def _city_bbox(boundary_fc: dict | None) -> dict:
    if boundary_fc:
        bb = _bbox_from_geojson(boundary_fc)
        if bb:
            return bb
    return CFG.CITY_BBOX_4326


def _disk_stats() -> str:
    path = "/mnt/t7" if sys.platform != "win32" else r"T:/"
    try:
        u = shutil.disk_usage(path)
        return f"T7 {u.used/1e9:.0f}/{u.total/1e9:.0f} GB ({u.used/u.total*100:.0f}% used)"
    except Exception:
        return "T7: unavailable"


# ── tile helpers ───────────────────────────────────────────────────────────────

def _load_catalog(force_catalog: bool) -> dict:
    return build_catalog(force=force_catalog)


def _tiles_in_city(tiles: list[dict], city_bb: dict) -> list[dict]:
    result = []
    for t in tiles:
        if t.get("bbox_4326") and not _bbox_intersects(t["bbox_4326"], city_bb):
            continue
        # Always refresh on_disk from filesystem — catalog can be stale
        laz_path = CFG.LAZ_DIR / t["laz_filename"]
        t = dict(t)
        t["on_disk"] = laz_path.exists()
        if t["on_disk"] and t.get("size_mb") is None:
            t["size_mb"] = round(laz_path.stat().st_size / 1_048_576, 1)
        result.append(t)
    return result


# ── address ingestion ─────────────────────────────────────────────────────────

def _run_address_ingest() -> tuple[str, int]:
    """
    Returns (addr_status, count).
    addr_status: "ok" | "missing_source" | "failed"
    Never raises.
    """
    def _log(msg: str, warn: bool = False):
        tag = "yellow" if warn else "dim"
        if console:
            console.print(f"  [{tag}][ADDR] {msg}[/{tag}]")
        else:
            print(f"[ADDR] {msg}")

    if CFG.ADDRESS_SOURCE is None:
        _log("ADDRESS_SOURCE is None — package will be marked incomplete_missing_addresses", warn=True)
        return "missing_source", 0

    src_path = Path(CFG.ADDRESS_SOURCE.get("path", ""))
    if not src_path.exists():
        _log(f"source file not found: {src_path} — package will be marked incomplete_missing_addresses", warn=True)
        return "missing_source", 0

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
        from ingest_addresses import ingest_addresses

        src = CFG.ADDRESS_SOURCE
        ok, count = ingest_addresses(
            source_path = src_path,
            field_map   = src.get("field_map", {}),
            source_name = src.get("source_name", "unknown"),
            input_crs   = src.get("input_crs", "EPSG:4326"),
            output_path = CFG.ADDRESS_POINTS,
            dst_crs     = f"EPSG:{CFG.OUT_EPSG}",
            city_name   = "miami_city",
        )
        if not ok:
            _log("ingest returned failure — package will be marked incomplete_address_enrichment_failed", warn=True)
            return "failed", 0
        _log(f"{count:,} address points ingested → {CFG.ADDRESS_POINTS.name}")
        return "ok", count
    except Exception as exc:
        _log(f"address ingest error: {exc} — package will be marked incomplete_address_enrichment_failed", warn=True)
        return "failed", 0


# ── structure address enrichment ──────────────────────────────────────────────

def _run_structures_enrichment(addr_status: str, addr_count: int) -> dict:
    """
    Build structures_enriched.geojson from all processed tile masses CSVs.

    Always writes the file — every structure gets an address_status field:
      "matched"        — nearest address within ADDRESS_JOIN_RADIUS_M
      "unmatched"      — no address within radius
      "missing_source" — address ingest was not configured or file missing
      "error"          — unexpected failure during enrichment

    Returns stats dict with counts and coverage.
    """
    def _log(msg: str, warn: bool = False):
        tag = "yellow" if warn else "dim"
        if console:
            console.print(f"  [{tag}][ADDR] {msg}[/{tag}]")
        else:
            print(f"[ADDR] {msg}")

    _EMPTY_STATS: dict = {
        "status":                    "skipped",
        "structures_count":          0,
        "address_points_count":      addr_count,
        "structures_with_address":   0,
        "structures_without_address": 0,
        "coverage_pct":              0.0,
        "avg_distance_m":            None,
        "max_distance_m":            None,
    }

    if not CFG.TILES_ROOT.exists():
        return _EMPTY_STATS

    # ── collect all structures from tile masses CSVs ───────────────────────────
    import csv as _csv
    structures: list[dict] = []
    global_idx = 0
    for tile_dir in sorted(CFG.TILES_ROOT.iterdir()):
        if not tile_dir.is_dir():
            continue
        tile_id  = tile_dir.name
        csv_path = tile_dir / "masses" / f"{tile_id}_masses_metadata.csv"
        if not csv_path.exists():
            continue
        with csv_path.open(encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                try:
                    cx = float(row["centroid_x"])
                    cy = float(row["centroid_y"])
                except (KeyError, ValueError):
                    continue
                structures.append({
                    "structure_id": f"MIA-STR-{global_idx:06d}",
                    "tile_id":      tile_id,
                    "cluster_id":   row.get("cluster_id"),
                    "centroid_x":   cx,
                    "centroid_y":   cy,
                    "height_m":     row.get("estimated_height"),
                    "height_p90":   row.get("height_p90"),
                    "footprint_area_m2": row.get("footprint_area_m2"),
                    "bbox_area_m2": row.get("bbox_area_m2"),
                    "source_quality": row.get("source_quality"),
                    "lod0_included":  row.get("lod0_included"),
                    "lod1_included":  row.get("lod1_included"),
                })
                global_idx += 1

    if not structures:
        _log("no structures found across any tile — nothing to enrich", warn=True)
        return _EMPTY_STATS

    n_total = len(structures)
    _log(f"{n_total:,} structures collected from {CFG.TILES_ROOT.name}/")

    # ── address matching ───────────────────────────────────────────────────────
    addr_props: list[dict] = []
    addr_xy_list: list[tuple[float, float]] = []
    addr_tree = None

    if addr_status == "ok" and CFG.ADDRESS_POINTS.exists():
        try:
            import numpy as np
            from scipy.spatial import cKDTree

            fc = json.loads(CFG.ADDRESS_POINTS.read_text(encoding="utf-8"))
            for feat in fc.get("features", []):
                p = feat.get("properties", {})
                x, y = p.get("x"), p.get("y")
                if x is not None and y is not None:
                    addr_props.append(p)
                    addr_xy_list.append((float(x), float(y)))

            if addr_xy_list:
                addr_xy = np.array(addr_xy_list, dtype=np.float64)
                addr_tree = cKDTree(addr_xy)
                _log(f"{len(addr_props):,} address points loaded for KD-tree query")
            else:
                _log("address_points.geojson has no valid x/y coords — marking all unmatched", warn=True)
                addr_status = "failed"
        except Exception as exc:
            _log(f"KD-tree setup failed: {exc} — marking all unmatched", warn=True)
            addr_status = "failed"
    elif addr_status == "ok":
        _log("address_points.geojson expected but missing — marking all as error", warn=True)
        addr_status = "failed"

    # ── UTM → WGS84 transformer for GeoJSON geometry ─────────────────────────
    utm_to_wgs84 = None
    try:
        from pyproj import Transformer
        utm_to_wgs84 = Transformer.from_crs(
            f"EPSG:{CFG.OUT_EPSG}", "EPSG:4326", always_xy=True
        )
    except Exception:
        pass

    # ── build enriched features ───────────────────────────────────────────────
    features: list[dict] = []
    matched_dists: list[float] = []

    for s in structures:
        cx, cy = s["centroid_x"], s["centroid_y"]

        # Geometry: WGS84 lon/lat
        if utm_to_wgs84 is not None:
            try:
                lon, lat = utm_to_wgs84.transform(cx, cy)
            except Exception:
                lon, lat = None, None
        else:
            lon, lat = None, None

        # Address fields
        if addr_status not in ("ok",) or addr_tree is None:
            a_status = "missing_source" if addr_status == "missing_source" else "error"
            addr_fields = {
                "nearest_address_id": None,
                "nearest_address":    None,
                "address_distance_m": None,
                "address_source":     None,
                "match_status":       a_status,
                "house_number":       None,
                "street":             None,
                "city":               None,
                "state":              None,
                "postcode":           None,
                "address_status":     a_status,
            }
        else:
            try:
                dist, idx = addr_tree.query([cx, cy], k=1)
                dist = float(dist)
                if dist <= CFG.ADDRESS_JOIN_RADIUS_M:
                    ap = addr_props[idx]
                    matched_dists.append(dist)
                    addr_fields = {
                        "nearest_address_id": ap.get("address_id"),
                        "nearest_address":    ap.get("full_address"),
                        "address_distance_m": round(dist, 2),
                        "address_source":     ap.get("source"),
                        "match_status":       "matched",
                        "house_number":       ap.get("house_number"),
                        "street":             ap.get("street"),
                        "city":               ap.get("city"),
                        "state":              ap.get("state"),
                        "postcode":           ap.get("postcode"),
                        "address_status":     "matched",
                    }
                else:
                    addr_fields = {
                        "nearest_address_id": None,
                        "nearest_address":    None,
                        "address_distance_m": None,
                        "address_source":     None,
                        "match_status":       "unmatched",
                        "house_number":       None,
                        "street":             None,
                        "city":               None,
                        "state":              None,
                        "postcode":           None,
                        "address_status":     "unmatched",
                    }
            except Exception:
                addr_fields = {
                    "nearest_address_id": None,
                    "nearest_address":    None,
                    "address_distance_m": None,
                    "address_source":     None,
                    "match_status":       "error",
                    "house_number":       None,
                    "street":             None,
                    "city":               None,
                    "state":              None,
                    "postcode":           None,
                    "address_status":     "error",
                }

        props = {
            "structure_id":       s["structure_id"],
            "tile_id":            s["tile_id"],
            "cluster_id":         s["cluster_id"],
            "centroid_x":         round(cx, 3),
            "centroid_y":         round(cy, 3),
            "height_m":           s["height_m"],
            "height_p90":         s["height_p90"],
            "footprint_area_m2":  s["footprint_area_m2"],
            "bbox_area_m2":       s["bbox_area_m2"],
            "source_quality":     s["source_quality"],
            "lod0_included":      s["lod0_included"],
            "lod1_included":      s["lod1_included"],
            **addr_fields,
        }

        geom = (
            {"type": "Point", "coordinates": [round(lon, 7), round(lat, 7)]}
            if lon is not None
            else None
        )
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    # ── write output ──────────────────────────────────────────────────────────
    n_matched   = sum(1 for f in features if f["properties"]["address_status"] == "matched")
    n_unmatched = n_total - n_matched
    coverage    = round(n_matched / n_total * 100, 1) if n_total else 0.0
    avg_dist    = round(sum(matched_dists) / len(matched_dists), 2) if matched_dists else None
    max_dist    = round(max(matched_dists), 2) if matched_dists else None

    try:
        CFG.METADATA_DIR.mkdir(parents=True, exist_ok=True)
        CFG.STRUCTURES_ENRICHED.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
            encoding="utf-8",
        )
        _log(
            f"structures_enriched.geojson written — "
            f"{n_matched:,} matched / {n_unmatched:,} unmatched "
            f"({coverage}% coverage) → {CFG.STRUCTURES_ENRICHED.name}"
        )
        enrich_status = "ok"
    except Exception as exc:
        _log(f"failed to write structures_enriched.geojson: {exc}", warn=True)
        enrich_status = "failed"

    return {
        "status":                     enrich_status,
        "structures_count":           n_total,
        "address_points_count":       len(addr_props) if addr_props else addr_count,
        "structures_with_address":    n_matched,
        "structures_without_address": n_unmatched,
        "coverage_pct":               coverage,
        "avg_distance_m":             avg_dist,
        "max_distance_m":             max_dist,
    }


# ── package status ─────────────────────────────────────────────────────────────

def _compute_package_status(addr_status: str, enrichment_stats: dict) -> str:
    if addr_status == "missing_source":
        return "incomplete_missing_addresses"
    if addr_status == "failed" or enrichment_stats.get("status") == "failed":
        return "incomplete_address_enrichment_failed"
    if (enrichment_stats.get("structures_count", 0) > 0
            and enrichment_stats.get("address_points_count", 0) > 0
            and CFG.STRUCTURES_ENRICHED.exists()):
        return "complete"
    return "incomplete_missing_addresses"


# ── city manifest ──────────────────────────────────────────────────────────────

def _write_city_manifest(
    tile_results: dict,
    tile_exit_codes: dict,
    addr_status: str,
    addr_count: int,
    enrichment_stats: dict,
    merge_stats: dict | None = None,
) -> dict:
    n_ok     = sum(1 for rc in tile_exit_codes.values() if rc == 0)
    n_lod0   = sum(r.get("lod0") or 0 for r in tile_results.values())
    n_lod1   = sum(r.get("lod1") or 0 for r in tile_results.values())
    n_clust  = sum(r.get("n_clusters") or 0 for r in tile_results.values())
    pkg_status = _compute_package_status(addr_status, enrichment_stats)

    manifest = {
        "schema_version":   PIPELINE_VERSION,
        "pipeline":         "GlitchOS.io Miami city pipeline",
        "city_id":          "miami_city",
        "display_name":     "City of Miami",
        "CRS":              f"EPSG:{CFG.OUT_EPSG}",
        "bounds_4326":      CFG.CITY_BBOX_4326,
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "preserve_raw_laz": CFG.PRESERVE_RAW_LAZ,
        "package_status":   pkg_status,
        "all_tiles_passed": n_ok == len(tile_exit_codes),
        "totals": {
            "tiles_attempted": len(tile_exit_codes),
            "tiles_ok":        n_ok,
            "buildings_lod0":  n_lod0,
            "buildings_lod1":  n_lod1,
            "clusters":        n_clust,
        },
        "assets": {
            "address_points":       "metadata/address_points.geojson",
            "structures_enriched":  "metadata/structures_enriched.geojson",
            "tiles_root":           str(CFG.TILES_ROOT),
            "blender_ready":        str(CFG.BLENDER_ROOT),
            "metadata":             str(CFG.METADATA_DIR),
            "audit":                str(CFG.AUDIT_DIR),
            "city_audit_json":      str(CFG.CITY_AUDIT_JSON),
            "city_audit_md":        str(CFG.CITY_AUDIT_MD),
            "boundary_cache":       str(CFG.BOUNDARY_CACHE),
            "tile_manifest":        str(CFG.TILE_MANIFEST),
            "city_terrain_ply":     str(CFG.CITY_TERRAIN_PLY),
            "city_vegetation_ply":  str(CFG.CITY_VEGETATION_PLY) if CFG.VEGETATION_ENABLED else None,
            "city_glb":             str(CFG.CITY_GLB),
            "city_glb_offset":      str(CFG.CITY_GLB_OFFSET_JSON),
        },
        "city_assets": (merge_stats or {}),
        "address_enrichment": {
            "required":                       True,
            "source":                         (CFG.ADDRESS_SOURCE or {}).get("path"),
            "join_radius_m":                  CFG.ADDRESS_JOIN_RADIUS_M,
            "structures_count":               enrichment_stats.get("structures_count", 0),
            "address_points_count":           enrichment_stats.get("address_points_count", addr_count),
            "structures_with_address_count":  enrichment_stats.get("structures_with_address", 0),
            "structures_without_address_count": enrichment_stats.get("structures_without_address", 0),
            "coverage_pct":                   enrichment_stats.get("coverage_pct", 0.0),
            "avg_address_distance_m":         enrichment_stats.get("avg_distance_m"),
            "max_address_distance_m":         enrichment_stats.get("max_distance_m"),
        },
        "tiles": {
            tid: {
                "status":       "ok" if tile_exit_codes.get(tid, 1) == 0 else "failed",
                "terrain_only": r.get("terrain_only", False),
                "n_clusters":   r.get("n_clusters", 0),
                "n_footprints": r.get("n_footprints", 0),
                "lod0_count":   r.get("lod0"),
                "lod1_count":   r.get("lod1"),
                "errors":       r.get("errors", {}),
            }
            for tid, r in tile_results.items()
        },
    }

    CFG.METADATA_DIR.mkdir(parents=True, exist_ok=True)
    CFG.CITY_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if console:
        status_color = "green" if pkg_status == "complete" else "yellow"
        console.print(f"  [dim]City manifest → {CFG.CITY_MANIFEST}[/dim]")
        console.print(f"  Package status: [{status_color}]{pkg_status}[/{status_color}]")
    else:
        print(f"City manifest -> {CFG.CITY_MANIFEST}  status={pkg_status}")

    return manifest


# ── city-wide terrain / vegetation / GLB merge ────────────────────────────────

def _run_city_merge() -> dict:
    """
    Merge per-tile ground and vegetation PLYs, then export the city GLB.
    Never raises — returns a stats dict with 'ok', 'terrain', 'vegetation', 'glb' keys.
    Logs to console if Rich is available.
    """
    def _log(msg: str, warn: bool = False):
        tag = "yellow" if warn else "dim"
        if console:
            console.print(f"  [{tag}][MERGE] {msg}[/{tag}]")
        else:
            print(f"[MERGE] {msg}")

    stats: dict = {"ok": True, "terrain": {}, "vegetation": {}, "glb": {}}

    CFG.BLENDER_ROOT.mkdir(parents=True, exist_ok=True)

    _log("Merging per-tile terrain point clouds…")
    try:
        ok, n = merge_terrain_ply()
        stats["terrain"] = {"ok": ok, "n_pts": n}
        _log(f"Terrain PLY: {n:,} ground points → {CFG.CITY_TERRAIN_PLY.name}")
    except Exception as exc:
        _log(f"Terrain merge failed: {exc}", warn=True)
        stats["terrain"] = {"ok": False, "error": str(exc)}
        stats["ok"] = False

    if CFG.VEGETATION_ENABLED:
        _log("Merging per-tile vegetation point clouds…")
        try:
            ok, n = merge_vegetation_ply()
            stats["vegetation"] = {"ok": ok, "n_pts": n}
            _log(f"Vegetation PLY: {n:,} points → {CFG.CITY_VEGETATION_PLY.name}")
        except Exception as exc:
            _log(f"Vegetation merge failed: {exc}", warn=True)
            stats["vegetation"] = {"ok": False, "error": str(exc)}
            # vegetation is optional — don't set stats["ok"] = False

    _log("Exporting city GLB (buildings + terrain + vegetation)…")
    try:
        glb_stats = export_city_glb()
        stats["glb"] = glb_stats
        if glb_stats.get("ok"):
            _log(
                f"GLB: {glb_stats.get('glb_mb', 0):.1f} MB — "
                f"{glb_stats.get('buildings_tris', 0):,} building tris, "
                f"{glb_stats.get('terrain_tris', 0):,} terrain tris, "
                f"{glb_stats.get('vegetation_pts', 0):,} veg pts"
            )
        else:
            _log(f"GLB export failed: {glb_stats.get('reason', 'unknown')}", warn=True)
    except Exception as exc:
        _log(f"GLB export error: {exc}", warn=True)
        stats["glb"] = {"ok": False, "error": str(exc)}
        stats["ok"] = False

    return stats


# ── dry-run ────────────────────────────────────────────────────────────────────

def dry_run(force_catalog: bool = False, tile_filter: str | None = None,
            limit: int | None = None):
    if console:
        console.print()
        console.print(Panel(
            "[bold magenta]GlitchOS.io — Miami City Pipeline[/bold magenta]\n"
            "[cyan]DRY RUN[/cyan] — no files will be written\n"
            f"PRESERVE_RAW_LAZ: [green]{CFG.PRESERVE_RAW_LAZ}[/green]  "
            f"Output root: [dim]{CFG.OUT_ROOT}[/dim]",
            box=box.ROUNDED,
        ))
    else:
        print("GlitchOS Miami City Pipeline — DRY RUN")

    boundary_fc, boundary_src = _download_boundary()
    city_bb = _city_bbox(boundary_fc)

    if console:
        console.print(f"  Boundary: [dim]{boundary_src}[/dim]")
        console.print(
            f"  City bbox:  W={city_bb['xmin']}  S={city_bb['ymin']}  "
            f"E={city_bb['xmax']}  N={city_bb['ymax']}"
        )

    catalog    = _load_catalog(force_catalog)
    all_tiles  = catalog.get("tiles", [])
    city_tiles = _tiles_in_city(all_tiles, city_bb)

    if tile_filter:
        city_tiles = [t for t in city_tiles if tile_filter in t["tile_id"]]
    if limit is not None:
        city_tiles = city_tiles[:limit]

    n_total   = len(city_tiles)
    n_on_disk = sum(1 for t in city_tiles if t["on_disk"])
    n_missing = n_total - n_on_disk
    local_gb  = sum((t.get("size_mb") or 0) for t in city_tiles if t["on_disk"]) / 1024
    avg_mb    = (sum(t.get("size_mb") or 0 for t in all_tiles if t.get("size_mb"))
                 / max(1, sum(1 for t in all_tiles if t.get("size_mb"))))
    est_dl_gb = n_missing * avg_mb / 1024

    if console:
        console.print()
        console.rule("[cyan]Tiles intersecting City of Miami[/cyan]")
        tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
        tbl.add_column("Tile ID",    min_width=52)
        tbl.add_column("On Disk",    min_width=12)
        tbl.add_column("Size MB",    min_width=8, justify="right")
        tbl.add_column("Output Dir")
        for t in city_tiles[:60]:
            disk = (f"[green]✓ {t.get('size_mb',0):.0f} MB[/green]"
                    if t["on_disk"] else "[red]✗ missing[/red]")
            sz   = str(t.get("size_mb", "?"))
            out  = str(CFG.TILES_ROOT / t["tile_id"])
            tbl.add_row(t["tile_id"], disk, sz, f"[dim]{out}[/dim]")
        if n_total > 60:
            tbl.add_row(f"… {n_total - 60} more …", "", "", "")
        console.print(tbl)
        console.print(f"  Tiles in city limits:    [white]{n_total}[/white]")
        console.print(f"  On disk:                 [green]{n_on_disk}[/green]")
        console.print(f"  Missing:                 {'[red]' if n_missing else '[dim]'}"
                      f"{n_missing}{'[/red]' if n_missing else '[/dim]'}")
        console.print(f"  Local data:              [white]{local_gb:.1f} GB[/white]")
        console.print(f"  Est. to download:        [yellow]{est_dl_gb:.1f} GB[/yellow]")
        console.print(f"  {_disk_stats()}")
        console.print()
        if n_on_disk == n_total and n_total > 0:
            console.print("[bold green]✓ All tiles on disk. Ready to execute.[/bold green]")
            console.print("\n  [cyan]python scripts/miami/run_miami_city.py --execute[/cyan]")
        elif n_on_disk == 0:
            console.print("[red]✗ No tiles on disk. Run download_miami_city_tiles.py first.[/red]")
        else:
            console.print(f"[yellow]◐ {n_on_disk}/{n_total} tiles ready.[/yellow]")
            console.print(
                f"\n  [cyan]python scripts/miami/run_miami_city.py --execute[/cyan]"
                f"   — will process {n_on_disk} on-disk tiles"
            )
    else:
        print(f"  Tiles: {n_total}  on disk: {n_on_disk}  missing: {n_missing}")
        print(f"  Local: {local_gb:.1f} GB  est. download: {est_dl_gb:.1f} GB")

    console.print() if console else None
    return 0


# ── execute ────────────────────────────────────────────────────────────────────

def execute(force_catalog: bool = False, tile_filter: str | None = None,
            limit: int | None = None, force_preflight: bool = False):

    # ── announce execute mode immediately, before Live starts ─────────────────
    _ts = datetime.now().strftime("%H:%M:%S")
    print(f"[EXECUTE] GlitchOS Miami pipeline — {_ts}", file=sys.stderr, flush=True)
    if console:
        console.print(
            f"\n[bold magenta]GlitchOS.io — Miami City Pipeline[/bold magenta]"
            f"  [cyan]EXECUTE[/cyan]  [dim]started {_ts}[/dim]"
        )
    else:
        print(f"GlitchOS Miami Pipeline — EXECUTE — {_ts}", flush=True)

    python    = sys.executable
    proj_data = str(Path(python).parent.parent / "share" / "proj")

    state: dict = {
        "run_start":       time.monotonic(),
        "start_clock":     datetime.now().strftime("%H:%M:%S"),
        "phase":           "starting",
        "n_total":         0,
        "n_done":          0,
        "n_ok":            0,
        "n_failed":        0,
        "n_buildings":     0,
        "current_tile":    "",
        "stage_statuses":  {},
        "stage_starts":    {},
        "stage_durations": {},
        "log_tail":        deque(maxlen=6),
        "tile_durations":  [],
    }

    def _run_tile_live(t: dict, live: "Live | None") -> tuple[int, dict, float]:
        tile_out = CFG.TILES_ROOT / t["tile_id"]
        tile_out.mkdir(parents=True, exist_ok=True)
        env = {**os.environ}
        env.setdefault("PROJ_DATA", proj_data)

        state["current_tile"]    = t["tile_id"]
        state["stage_statuses"]  = {s: "pending" for s in TILE_STAGES}
        state["stage_starts"]    = {}
        state["stage_durations"] = {}
        state["log_tail"].clear()
        tile_start   = time.monotonic()
        stdout_lines: list[str] = []

        proc = subprocess.Popen(
            [python, _TILE_RUNNER,
             "--laz", str(CFG.LAZ_DIR / t["laz_filename"]),
             "--out", str(tile_out),
             "--resume"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env,
        )

        def _reader() -> None:
            for raw in proc.stdout:
                ln = raw.rstrip()
                stdout_lines.append(ln)
                state["log_tail"].append(ln)
                _detect_stage(ln, state)

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()

        while proc.poll() is None:
            if live:
                live.update(_render_dashboard(state))
            time.sleep(0.25)

        reader.join(timeout=2)
        if live:
            live.update(_render_dashboard(state))

        rc           = proc.returncode
        tile_elapsed = time.monotonic() - tile_start

        for s in TILE_STAGES:
            if state["stage_statuses"].get(s) == "running":
                if s in state["stage_starts"]:
                    state["stage_durations"][s] = tile_elapsed
                state["stage_statuses"][s] = "done" if rc == 0 else "failed"

        manifest_path = tile_out / "manifest" / f"{t['tile_id']}_manifest.json"
        manifest_data: dict = {}
        if manifest_path.exists():
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        return rc, {
            "errors":       manifest_data.get("errors", {}) if rc != 0 else {},
            "n_clusters":   manifest_data.get("n_clusters", 0),
            "n_footprints": manifest_data.get("n_footprints", 0),
            "lod0":         manifest_data.get("building_mass_lod0"),
            "lod1":         manifest_data.get("building_mass_lod1"),
            "terrain_only": manifest_data.get("terrain_only", False),
            "stdout":       "\n".join(stdout_lines),
            "stderr":       "",
        }, tile_elapsed

    # ── plain-text fallback (no Rich) ─────────────────────────────────────────
    if not (console and HAS_RICH):
        print("Running preflight…", flush=True)
        rep = run_preflight(force=force_preflight)
        if not rep.ok:
            print("Preflight FAILED — aborting.")
            return 1
        CFG.METADATA_DIR.mkdir(parents=True, exist_ok=True)
        addr_status, addr_count = _run_address_ingest()
        boundary_fc, _ = _download_boundary()
        city_bb = _city_bbox(boundary_fc)
        catalog    = _load_catalog(force_catalog)
        city_tiles = _tiles_in_city(catalog.get("tiles", []), city_bb)
        runnable   = [t for t in city_tiles if t["on_disk"]]
        if tile_filter:
            runnable = [t for t in runnable if tile_filter in t["tile_id"]]
        if limit is not None:
            runnable = runnable[:limit]
        if not runnable:
            print("No on-disk tiles. Run --dry-run for details.")
            return 1
        CFG.TILES_ROOT.mkdir(parents=True, exist_ok=True)
        tile_results:    dict[str, dict] = {}
        tile_exit_codes: dict[str, int]  = {}
        for i, t in enumerate(runnable, 1):
            print(f"[{i}/{len(runnable)}] {t['tile_id']} …", flush=True)
            rc, result, _ = _run_tile_live(t, None)
            tile_exit_codes[t["tile_id"]] = rc
            tile_results[t["tile_id"]]    = result
            print("  OK" if rc == 0 else f"  FAIL (rc={rc})")
        enrichment_stats = _run_structures_enrichment(addr_status, addr_count)
        merge_stats = _run_city_merge()
        manifest = _write_city_manifest(tile_results, tile_exit_codes, addr_status, addr_count, enrichment_stats, merge_stats)
        build_audit(quiet=False)
        n_fail = sum(1 for rc in tile_exit_codes.values() if rc != 0)
        return 0 if n_fail == 0 else 1

    # ── Rich Live dashboard ────────────────────────────────────────────────────
    tile_results:    dict[str, dict] = {}
    tile_exit_codes: dict[str, int]  = {}
    preflight_ok     = True
    addr_status      = "missing_source"
    addr_count       = 0
    merge_stats:     dict            = {}
    runnable: list[dict] = []

    with Live(
        _render_dashboard(state),
        console=console,
        refresh_per_second=4,
        transient=False,
    ) as live:

        # ── preflight ─────────────────────────────────────────────────────────
        state["phase"] = "preflight"
        state["log_tail"].append("Running preflight checks…")
        live.update(_render_dashboard(state))

        rep = run_preflight(force=force_preflight, quiet=True)
        if not rep.ok:
            state["log_tail"].append("PREFLIGHT FAILED — aborting. Use --force-preflight to skip.")
            live.update(_render_dashboard(state))
            time.sleep(1.5)
            preflight_ok = False
        else:
            state["log_tail"].append("✓ Preflight passed")
            live.update(_render_dashboard(state))

        if not preflight_ok:
            return 1

        # ── address ingestion ──────────────────────────────────────────────────
        state["phase"] = "address ingest"
        state["log_tail"].append("Running address ingestion…")
        live.update(_render_dashboard(state))

        CFG.METADATA_DIR.mkdir(parents=True, exist_ok=True)
        addr_status, addr_count = _run_address_ingest()
        state["log_tail"].append(
            f"Address ingest: {addr_status}"
            + (f" ({addr_count:,} pts)" if addr_count else "")
        )
        live.update(_render_dashboard(state))

        # ── boundary + catalog ─────────────────────────────────────────────────
        state["phase"] = "tile discovery"
        state["log_tail"].append("Loading tile catalog…")
        live.update(_render_dashboard(state))

        boundary_fc, _ = _download_boundary()
        city_bb        = _city_bbox(boundary_fc)
        catalog        = _load_catalog(force_catalog)
        city_tiles     = _tiles_in_city(catalog.get("tiles", []), city_bb)
        runnable       = [t for t in city_tiles if t["on_disk"]]

        if tile_filter:
            runnable = [t for t in runnable if tile_filter in t["tile_id"]]
        if limit is not None:
            runnable = runnable[:limit]

        state["n_total"] = len(runnable)
        state["log_tail"].append(f"Found {len(runnable)} on-disk tiles to process")
        live.update(_render_dashboard(state))

        if not runnable:
            state["log_tail"].append("No on-disk tiles. Run --dry-run for details.")
            live.update(_render_dashboard(state))
            time.sleep(1.5)
            return 1

        CFG.TILES_ROOT.mkdir(parents=True, exist_ok=True)

        # ── tile processing ────────────────────────────────────────────────────
        state["phase"] = "processing"
        live.update(_render_dashboard(state))

        for t in runnable:
            rc, result, tile_dur = _run_tile_live(t, live)

            tile_exit_codes[t["tile_id"]] = rc
            tile_results[t["tile_id"]]    = result
            state["n_done"]      += 1
            state["n_ok"]        += int(rc == 0)
            state["n_failed"]    += int(rc != 0)
            state["n_buildings"]  = sum(r.get("lod0") or 0 for r in tile_results.values())
            state["tile_durations"].append(tile_dur)
            live.update(_render_dashboard(state))

        # ── enrichment + manifest + audit ──────────────────────────────────────
        state["phase"]        = "enrichment"
        state["current_tile"] = ""
        state["log_tail"].append("Running structure address enrichment…")
        live.update(_render_dashboard(state))

        enrichment_stats = _run_structures_enrichment(addr_status, addr_count)

        state["phase"] = "manifest"
        state["log_tail"].append("Writing city manifest…")
        live.update(_render_dashboard(state))

        manifest = _write_city_manifest(
            tile_results, tile_exit_codes, addr_status, addr_count,
            enrichment_stats, merge_stats,
        )

        state["phase"] = "merge"
        state["log_tail"].append("Merging terrain + vegetation PLYs…")
        live.update(_render_dashboard(state))

        merge_stats = _run_city_merge()

        if merge_stats.get("glb", {}).get("ok"):
            glb_mb = merge_stats["glb"].get("glb_mb", 0)
            state["log_tail"].append(f"✓ City GLB: {glb_mb:.1f} MB → {CFG.CITY_GLB.name}")
        else:
            state["log_tail"].append("⚠ GLB export incomplete (check logs)")
        live.update(_render_dashboard(state))

        state["phase"] = "audit"
        state["log_tail"].append("Writing audit…")
        live.update(_render_dashboard(state))

        build_audit(quiet=True)

        state["phase"] = "done"
        state["log_tail"].append("Pipeline complete.")
        live.update(_render_dashboard(state))

    # ── summary panel (after Live closes) ─────────────────────────────────────
    n_ok       = sum(1 for rc in tile_exit_codes.values() if rc == 0)
    n_fail     = len(tile_exit_codes) - n_ok
    n_lod0     = sum(r.get("lod0") or 0 for r in tile_results.values())
    pkg_status = manifest.get("package_status", "unknown")
    n_matched  = enrichment_stats.get("structures_with_address", 0)
    coverage   = enrichment_stats.get("coverage_pct", 0.0)
    pkg_color  = "green" if pkg_status == "complete" else "yellow"

    glb_line = ""
    if merge_stats.get("glb", {}).get("ok"):
        gstats   = merge_stats["glb"]
        glb_line = (
            f"\n  GLB: [white]{gstats.get('glb_mb', 0):.1f} MB[/white]  "
            f"bldg {gstats.get('buildings_tris', 0):,} tris  "
            f"terrain {gstats.get('terrain_tris', 0):,} tris  "
            f"veg {gstats.get('vegetation_pts', 0):,} pts"
        )

    console.print(Panel(
        f"[bold]Miami city pipeline complete[/bold]\n"
        f"  {n_ok}/{len(tile_exit_codes)} tiles OK  "
        f"{'[green]ALL PASSED[/green]' if n_fail == 0 else f'[red]{n_fail} FAILED[/red]'}\n"
        f"  Buildings (LOD0): [white]{n_lod0:,}[/white]   "
        f"Addresses: [white]{addr_count:,}[/white]   "
        f"Matched: [white]{n_matched:,}[/white] ({coverage}%)\n"
        f"  Package: [{pkg_color}]{pkg_status}[/{pkg_color}]"
        f"{glb_line}\n"
        f"  [dim]{_disk_stats()}[/dim]",
        box=box.ROUNDED,
    ))

    return 0 if n_fail == 0 else 1


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    args             = sys.argv[1:]
    is_execute       = "--execute"        in args
    is_dry_run       = "--dry-run"        in args
    is_preflight     = "--preflight"      in args
    is_audit         = "--audit"          in args
    force_catalog    = "--force-catalog"  in args
    force_preflight  = "--force-preflight" in args
    tile_filter      = None
    limit            = None

    i = 0
    while i < len(args):
        if args[i] == "--tile"  and i + 1 < len(args):
            tile_filter = args[i + 1]; i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        else:
            i += 1

    if is_preflight:
        rep = run_preflight(force=force_preflight)
        return 0 if rep.ok else 1

    if is_audit:
        build_audit()
        return 0

    if is_execute:
        print(
            f"[EXECUTE] GlitchOS Miami pipeline — {datetime.now().strftime('%H:%M:%S')}",
            file=sys.stderr, flush=True,
        )
        return execute(
            force_catalog=force_catalog,
            tile_filter=tile_filter,
            limit=limit,
            force_preflight=force_preflight,
        )

    if is_dry_run or not args:
        return dry_run(
            force_catalog=force_catalog,
            tile_filter=tile_filter,
            limit=limit,
        )

    # Unknown flags — print usage instead of silently dry-running
    print(
        "Usage:\n"
        "  python run_miami_city.py --execute              # run all on-disk tiles\n"
        "  python run_miami_city.py --execute --limit N    # run first N tiles\n"
        "  python run_miami_city.py --execute --tile <id>  # run one tile\n"
        "  python run_miami_city.py --dry-run              # preview only\n"
        "  python run_miami_city.py --preflight            # check LAZ dir + catalog\n"
        "  python run_miami_city.py --audit                # write audit outputs\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
