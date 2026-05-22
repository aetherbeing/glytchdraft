"""
boundary_downloader.py  [LA city pipeline — GlitchOS.io]

Download and cache the official City of Los Angeles municipal boundary.

Source cascade (tries each in order until one succeeds):
  1. LA City GeoHub  — ArcGIS Feature Service (authoritative, always current)
  2. Census TIGER    — US Census Bureau TIGER/Line shapefile download API
  3. OSM Overpass    — OpenStreetMap admin boundary relation

Output: GeoJSON in EPSG:4326, cached at:
  /mnt/t7/la/data_processed/cities/los_angeles/boundaries/
  los_angeles_boundary_4326.geojson

Usage:
    python scripts/la/boundary_downloader.py --city los_angeles
    python scripts/la/boundary_downloader.py --city los_angeles --force
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER

from rich.console import Console

console = Console()

# ── source endpoints ──────────────────────────────────────────────────────────

# LA City GeoHub: City Boundary feature layer
LA_GEOHUB_URL = (
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/"
    "City_Boundary/FeatureServer/0/query?"
    "where=1%3D1&outFields=*&outSR=4326&f=geojson"
)

# Census TIGER API — Places layer, FIPS 06 (California), filter LA city
CENSUS_TIGER_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Places_CouSub_ConCity_SubMCD/MapServer/4/query?"
    "where=STATE%3D%2706%27+AND+NAME%3D%27Los+Angeles%27+AND+LSAD%3D%2725%27"
    "&outFields=NAME,GEOID&outSR=4326&f=geojson"
)

# OSM Overpass — City of Los Angeles admin_level=8 boundary
OSM_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_QUERY = """
[out:json][timeout:60];
relation["name"="Los Angeles"]["admin_level"="8"]["boundary"="administrative"];
out geom;
"""

TIMEOUT = 60


def _http_get(url: str, data: bytes | None = None, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _try_la_geohub() -> dict | None:
    console.print("  [dim]Trying LA City GeoHub...[/dim]")
    try:
        raw = _http_get(LA_GEOHUB_URL)
        fc = json.loads(raw)
        if fc.get("type") == "FeatureCollection" and fc.get("features"):
            console.print(f"  [green]LA GeoHub: {len(fc['features'])} feature(s)[/green]")
            return fc
    except Exception as e:
        console.print(f"  [yellow]LA GeoHub failed: {e}[/yellow]")
    return None


def _try_census_tiger() -> dict | None:
    console.print("  [dim]Trying Census TIGER...[/dim]")
    try:
        raw = _http_get(CENSUS_TIGER_URL)
        fc = json.loads(raw)
        if fc.get("type") == "FeatureCollection" and fc.get("features"):
            console.print(f"  [green]Census TIGER: {len(fc['features'])} feature(s)[/green]")
            return fc
    except Exception as e:
        console.print(f"  [yellow]Census TIGER failed: {e}[/yellow]")
    return None


def _osm_to_geojson(osm_data: dict) -> dict | None:
    """Convert OSM Overpass relation with geom to GeoJSON FeatureCollection."""
    try:
        features = []
        for element in osm_data.get("elements", []):
            if element["type"] != "relation":
                continue
            members = element.get("members", [])
            outer_rings = []
            for m in members:
                if m.get("role") == "outer" and m.get("type") == "way":
                    coords = [(n["lon"], n["lat"]) for n in m.get("geometry", [])]
                    if len(coords) >= 4:
                        # Close ring if needed
                        if coords[0] != coords[-1]:
                            coords.append(coords[0])
                        outer_rings.append(coords)

            if not outer_rings:
                continue

            if len(outer_rings) == 1:
                geometry = {"type": "Polygon", "coordinates": outer_rings}
            else:
                geometry = {"type": "MultiPolygon",
                            "coordinates": [[ring] for ring in outer_rings]}

            features.append({
                "type": "Feature",
                "properties": element.get("tags", {}),
                "geometry": geometry,
            })

        if not features:
            return None

        return {"type": "FeatureCollection", "features": features}
    except Exception:
        return None


def _try_osm_overpass() -> dict | None:
    console.print("  [dim]Trying OSM Overpass (slow)...[/dim]")
    try:
        data = urllib.parse.urlencode({"data": OSM_QUERY}).encode()
        raw = _http_get(OSM_OVERPASS_URL, data=data, timeout=90)
        osm_data = json.loads(raw)
        fc = _osm_to_geojson(osm_data)
        if fc and fc.get("features"):
            console.print(f"  [green]OSM Overpass: {len(fc['features'])} feature(s)[/green]")
            return fc
    except Exception as e:
        console.print(f"  [yellow]OSM Overpass failed: {e}[/yellow]")
    return None


SOURCE_FNS = {
    "la_geohub":    _try_la_geohub,
    "census_tiger": _try_census_tiger,
    "osm":          _try_osm_overpass,
}


def download_boundary(city_id: str, force: bool = False) -> Path:
    """
    Download the city boundary and write it to the cache path.
    Returns the path on success. Raises RuntimeError if all sources fail.
    """
    if city_id not in CITIES:
        raise KeyError(f"Unknown city: {city_id!r}. Valid: {CITY_ORDER}")

    cfg = CITIES[city_id]
    out_path = cfg.boundary_cache

    if out_path.exists() and not force:
        size_kb = out_path.stat().st_size / 1024
        if size_kb > 1:
            console.print(f"  [dim]Using cached boundary ({size_kb:.0f} KB): {out_path}[/dim]")
            return out_path
        console.print(f"  [yellow]Cached file is too small ({size_kb:.1f} KB) — re-downloading[/yellow]")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold cyan]Downloading {cfg.display_name} boundary...[/bold cyan]")

    for source in cfg.boundary_sources:
        fn = SOURCE_FNS.get(source)
        if fn is None:
            continue
        fc = fn()
        if fc:
            # Annotate with source metadata
            for feat in fc.get("features", []):
                feat.setdefault("properties", {})["_source"] = source
                feat["properties"]["_city_id"] = city_id
                feat["properties"]["_downloaded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            out_path.write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
            size_kb = out_path.stat().st_size / 1024
            console.print(f"  [green]Saved to {out_path} ({size_kb:.0f} KB)[/green]")
            return out_path

    raise RuntimeError(
        f"All boundary sources failed for {city_id!r}. "
        "Check network connectivity and try again."
    )


def load_boundary(city_id: str, force: bool = False) -> dict:
    """Download (if needed) and return the boundary GeoJSON dict."""
    path = download_boundary(city_id, force=force)
    return json.loads(path.read_text(encoding="utf-8"))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    city_id = "los_angeles"
    force   = "--force" in args

    for i, a in enumerate(args):
        if a == "--city" and i + 1 < len(args):
            city_id = args[i + 1]

    try:
        path = download_boundary(city_id, force=force)
        fc = json.loads(path.read_text(encoding="utf-8"))
        console.print(f"\nBoundary ready: {len(fc.get('features', []))} feature(s)  →  {path}")
        return 0
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
