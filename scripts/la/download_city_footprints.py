"""
download_city_footprints.py  [LA city pipeline - GlitchOS.io]

Downloads building footprints for the full City of Los Angeles boundary.
Uses a tiled approach (grid of 0.1° × 0.1° cells) to stay under the server's
MaxRecordCount limit.

Source: LA County ArcGIS REST — confirmed working endpoint.

Output: /mnt/e/la/data_raw/geojson/los_angeles_city_footprints_4326.geojson

Usage:
    python scripts/la/download_city_footprints.py los_angeles
    python scripts/la/download_city_footprints.py los_angeles --force      # overwrite existing
    python scripts/la/download_city_footprints.py los_angeles --osm-only   # skip ESRI, use OSM
    python scripts/la/download_city_footprints.py los_angeles --cell 0.05  # smaller grid cells
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

from city_config import CITIES, CITY_ORDER
from tile_config import CITY_FOOTPRINTS_RAW

try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn,
    )
    _RICH = True
    console = Console()
    def _print(msg: str):
        console.print(msg)
except ImportError:
    _RICH = False
    def _print(msg: str):
        print(msg)

# ── confirmed-working endpoint ────────────────────────────────────────────────

_SERVICE_URL = (
    "https://arcgis.gis.lacounty.gov/arcgis/rest/services/"
    "DRP/GISNET_Public/MapServer/434/query"
)

USER_AGENT = "GlytchDraft/1.0 (spatial pipeline; contact charleshopeart@gmail.com)"

_PAGE_SIZE  = 1000   # conservative; server MaxRecordCount may be 1000 or 2000
_CELL_DEG   = 0.1    # default grid cell size in degrees


# ── ESRI helpers ──────────────────────────────────────────────────────────────

def _geometry_param(xmin: float, ymin: float, xmax: float, ymax: float) -> str:
    """Return the ESRI envelope geometry JSON string for use as the `geometry` param."""
    return json.dumps({
        "xmin": xmin, "ymin": ymin,
        "xmax": xmax, "ymax": ymax,
        "spatialReference": {"wkid": 4326},
    }, separators=(",", ":"))


def _esri_count(bbox: tuple, debug: bool = False) -> int:
    """Return feature count for bbox, or -1 on error."""
    xmin, ymin, xmax, ymax = bbox
    params = {
        "where": "1=1",
        "geometry": _geometry_param(xmin, ymin, xmax, ymax),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnCountOnly": "true",
        "f": "json",
    }
    url = f"{_SERVICE_URL}?{urllib.parse.urlencode(params)}"
    if debug:
        _print(f"[dim]COUNT  {url}[/dim]" if _RICH else f"COUNT  {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if "error" in data:
            _print(f"[red]ArcGIS error (count): {data['error']}[/red]" if _RICH else f"ArcGIS error (count): {data['error']}")
            return -1
        return int(data.get("count", 0))
    except Exception as e:
        _print(f"[red]count request failed: {e}[/red]" if _RICH else f"count request failed: {e}")
        return -1


def _esri_page(bbox: tuple, offset: int, page_size: int, debug: bool = False) -> tuple[list, bool]:
    """
    Fetch one page of GeoJSON features.
    Returns (features, exceeded_transfer_limit).
    """
    xmin, ymin, xmax, ymax = bbox
    params = {
        "where": "1=1",
        "geometry": _geometry_param(xmin, ymin, xmax, ymax),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
        "outFields": "*",
        "outSR": "4326",
        "resultOffset": str(offset),
        "resultRecordCount": str(page_size),
        "f": "geojson",
    }
    url = f"{_SERVICE_URL}?{urllib.parse.urlencode(params)}"
    if debug:
        _print(f"[dim]PAGE   offset={offset}  {url}[/dim]" if _RICH else f"PAGE   offset={offset}  {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        if "error" in data:
            _print(f"[red]ArcGIS error (page offset={offset}): {data['error']}[/red]" if _RICH else f"ArcGIS error (page offset={offset}): {data['error']}")
            return [], False
        features = data.get("features", [])
        exceeded = bool(data.get("exceededTransferLimit"))
        return features, exceeded
    except Exception as e:
        _print(f"[red]page request failed (offset={offset}): {e}[/red]" if _RICH else f"page request failed (offset={offset}): {e}")
        return [], False


def _esri_fetch_cell(cell_bbox: tuple, cell_index: int) -> list:
    """Fetch all features for one grid cell, paginating until done."""
    debug_first = (cell_index == 0)

    # Count first so we know what to expect
    total = _esri_count(cell_bbox, debug=debug_first)
    if total == 0:
        return []
    if total > 0:
        _print(
            f"[dim]  cell {cell_index}: {total} features expected[/dim]"
            if _RICH else f"  cell {cell_index}: {total} features expected"
        )

    features: list = []
    offset = 0
    while True:
        batch, exceeded = _esri_page(cell_bbox, offset, _PAGE_SIZE, debug=debug_first)
        debug_first = False   # only log full URL for first page of first cell
        if not batch:
            break
        features.extend(batch)
        if not exceeded and len(batch) < _PAGE_SIZE:
            break
        offset += len(batch)
        time.sleep(0.15)

    return features


# ── OSM fallback ──────────────────────────────────────────────────────────────

def _overpass_query(bbox: tuple) -> list:
    xmin, ymin, xmax, ymax = bbox
    b = f"{ymin},{xmin},{ymax},{xmax}"
    query = (
        f"[out:json][timeout:90][bbox:{b}];"
        "(way[\"building\"];relation[\"building\"][\"type\"=\"multipolygon\"];);"
        "out body;>;out skel qt;"
    )
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data_enc = urllib.parse.urlencode({"data": query}).encode()
    for endpoint in [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]:
        try:
            req = urllib.request.Request(endpoint, data=data_enc, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                osm = json.loads(resp.read())
            nodes = {el["id"]: el for el in osm["elements"] if el["type"] == "node"}
            features = []
            for el in osm["elements"]:
                if el["type"] != "way" or "nodes" not in el:
                    continue
                coords = [[nodes[n]["lon"], nodes[n]["lat"]] for n in el["nodes"] if n in nodes]
                if len(coords) < 4:
                    continue
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                tags = el.get("tags", {})
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {
                        "osm_id": el["id"],
                        "building": tags.get("building", "yes"),
                        "height": tags.get("height") or tags.get("building:levels"),
                        "source": "OpenStreetMap",
                    },
                })
            if features:
                return features
        except Exception:
            time.sleep(2)
            continue
    return []


# ── tile grid ─────────────────────────────────────────────────────────────────

def _make_grid(bbox: dict, cell_deg: float) -> list[tuple]:
    cells = []
    x = bbox["xmin"]
    while x < bbox["xmax"]:
        y = bbox["ymin"]
        while y < bbox["ymax"]:
            cells.append((
                round(x, 6),
                round(y, 6),
                round(min(x + cell_deg, bbox["xmax"]), 6),
                round(min(y + cell_deg, bbox["ymax"]), 6),
            ))
            y = round(y + cell_deg, 6)
        x = round(x + cell_deg, 6)
    return cells


# ── deduplication ─────────────────────────────────────────────────────────────

def _dedup_key(feature: dict) -> str | None:
    props = feature.get("properties") or {}
    fid = props.get("OBJECTID") or props.get("FID") or props.get("GlobalID") or props.get("osm_id")
    return str(fid) if fid is not None else None


# ── main ──────────────────────────────────────────────────────────────────────

def download(city_id: str, force: bool = False, osm_only: bool = False, cell_deg: float = _CELL_DEG) -> int:
    if city_id not in CITIES:
        _print(f"Unknown city: {city_id!r}  valid: {CITY_ORDER}")
        return 1

    cfg = CITIES[city_id]
    out_path = CITY_FOOTPRINTS_RAW

    if out_path.exists() and not force:
        size_kb = out_path.stat().st_size // 1024
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        n = len(existing.get("features", []))
        _print(f"Already exists: {out_path}  ({n} features, {size_kb} KB)\n  Use --force to re-download.")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)

    bbox     = cfg.bbox_4326
    cells    = _make_grid(bbox, cell_deg=cell_deg)
    use_esri = not osm_only

    _print(f"City bbox: lon {bbox['xmin']} to {bbox['xmax']}, lat {bbox['ymin']} to {bbox['ymax']}")
    _print(f"Grid: {len(cells)} cells ({cell_deg}° × {cell_deg}°)")
    _print(f"Source: {'LA County ArcGIS' if use_esri else 'OSM Overpass'}")
    _print(f"Endpoint: {_SERVICE_URL}" if use_esri else "")
    _print("")

    # Probe first cell to confirm service is reachable
    if use_esri:
        probe_count = _esri_count(cells[0], debug=True)
        if probe_count < 0:
            _print("[yellow]ArcGIS service probe failed — falling back to OSM Overpass.[/yellow]" if _RICH else "ArcGIS service probe failed — falling back to OSM Overpass.")
            use_esri = False
        else:
            _print(f"Service probe OK: {probe_count} features in first cell.\n")

    all_features: list = []
    seen_ids: set = set()

    def _add(features: list):
        for f in features:
            key = _dedup_key(f)
            if key is not None:
                if key in seen_ids:
                    continue
                seen_ids.add(key)
            all_features.append(f)

    if _RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=28),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("fetching", total=len(cells))
            for i, cell in enumerate(cells):
                if use_esri:
                    features = _esri_fetch_cell(cell, i)
                else:
                    features = _overpass_query(cell)
                    time.sleep(1)
                _add(features)
                progress.update(
                    task, advance=1,
                    description=f"cell {i+1}/{len(cells)}  n={len(all_features)}",
                )
    else:
        for i, cell in enumerate(cells):
            if use_esri:
                features = _esri_fetch_cell(cell, i)
            else:
                features = _overpass_query(cell)
                time.sleep(1)
            _add(features)
            if (i + 1) % 5 == 0 or i == 0:
                print(f"  cell {i+1}/{len(cells)}  total={len(all_features)}")

    _print(f"\nTotal: {len(all_features)} features  ({len(seen_ids)} unique IDs tracked)")

    geojson = {
        "type": "FeatureCollection",
        "name": "glitchos_la_city_building_footprints",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": all_features,
    }
    out_path.write_text(json.dumps(geojson), encoding="utf-8")
    size_mb = out_path.stat().st_size / 1_048_576
    _print(f"Wrote: {out_path}  ({len(all_features)} features, {size_mb:.1f} MB)")
    return 0


def main() -> int:
    args = sys.argv[1:]
    city_id  = next((a for a in args if not a.startswith("--")), "los_angeles")
    force    = "--force" in args
    osm_only = "--osm-only" in args
    cell_deg = _CELL_DEG
    for a in args:
        if a.startswith("--cell"):
            try:
                cell_deg = float(a.split("=", 1)[1] if "=" in a else args[args.index(a) + 1])
            except (IndexError, ValueError):
                pass
    return download(city_id, force=force, osm_only=osm_only, cell_deg=cell_deg)


if __name__ == "__main__":
    sys.exit(main())
