"""
00_download_footprints.py  [LA]

Downloads LA County building footprints for the hero tile area only.
Clips at query time — no county-wide download.

Sources tried in order:
  1. LA County FeatureServer (ESRI REST) — has HEIGHT/YEAR_BUILT attributes
  2. LA City GeoHub FeatureServer — city limits only, good coverage for DTLA
  3. OSM Overpass API — reliable fallback, geometry only

Output: /mnt/t7/la/data_raw/geojson/la_county_building_outlines_4326.geojson

The hero tile bbox in EPSG:4326 (computed from EPSG:2229 tile 1836b):
  lon: -118.279382 to -118.270643
  lat:   34.046327 to  34.053601
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

OUT_DIR  = Path("/mnt/t7/la/data_raw/geojson")
OUT_FILE = OUT_DIR / "la_county_building_outlines_4326.geojson"

# Hero tile bbox (EPSG:4326) — computed from EPSG:2229 tile 1836b bounds
BBOX = {
    "xmin": -118.279382,
    "ymin":   34.046327,
    "xmax": -118.270643,
    "ymax":   34.053601,
}

# Add a small buffer so edge buildings aren't clipped
BUFFER = 0.002  # ~200 m in degrees at this latitude
BBOX_BUFFERED = {
    "xmin": BBOX["xmin"] - BUFFER,
    "ymin": BBOX["ymin"] - BUFFER,
    "xmax": BBOX["xmax"] + BUFFER,
    "ymax": BBOX["ymax"] + BUFFER,
}


def esri_query(service_url: str, bbox: dict) -> dict | None:
    """Query an ESRI FeatureServer layer with a bbox spatial filter."""
    geometry = json.dumps({
        "xmin": bbox["xmin"], "ymin": bbox["ymin"],
        "xmax": bbox["xmax"], "ymax": bbox["ymax"],
        "spatialReference": {"wkid": 4326},
    })
    params = urllib.parse.urlencode({
        "where": "1=1",
        "geometry": geometry,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": 5000,
    })
    url = f"{service_url}/query?{params}"
    try:
        print(f"  trying: {service_url.split('/arcgis')[0]}...")
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        if "error" in data:
            print(f"  service error: {data['error']}")
            return None
        features = data.get("features", [])
        print(f"  got {len(features)} features")
        return data if features else None
    except Exception as e:
        print(f"  failed: {e}")
        return None


def overpass_query(bbox: dict) -> dict | None:
    """Query OSM Overpass API for buildings in the bbox."""
    b = f"{bbox['ymin']},{bbox['xmin']},{bbox['ymax']},{bbox['xmax']}"
    query = (
        f"[out:json][timeout:60][bbox:{b}];"
        "(way[\"building\"];relation[\"building\"][\"type\"=\"multipolygon\"];);"
        "out body;>;out skel qt;"
    )
    headers = {
        "User-Agent": "GlytchDraft/1.0 (spatial pipeline; contact charleshopeart@gmail.com)",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data_enc = urllib.parse.urlencode({"data": query}).encode()
    for endpoint in [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]:
        try:
            print(f"  querying Overpass: {endpoint.split('/api')[0]}...")
            req = urllib.request.Request(endpoint, data=data_enc, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as resp:
                osm = json.loads(resp.read())
            result = osm_to_geojson(osm)
            if result:
                return result
        except Exception as e:
            print(f"  failed: {e}")
    return None


def osm_to_geojson(osm: dict) -> dict | None:
    """Convert Overpass JSON to a minimal GeoJSON FeatureCollection."""
    nodes = {el["id"]: el for el in osm["elements"] if el["type"] == "node"}
    features = []
    for el in osm["elements"]:
        if el["type"] != "way" or "nodes" not in el:
            continue
        coords = []
        for nid in el["nodes"]:
            n = nodes.get(nid)
            if n:
                coords.append([n["lon"], n["lat"]])
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
                "name": tags.get("name"),
                "source": "OpenStreetMap",
            },
        })
    if not features:
        return None
    print(f"  converted {len(features)} OSM ways to GeoJSON polygons")
    return {"type": "FeatureCollection", "features": features}


ESRI_SERVICES = [
    # LA County building outlines — primary
    "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Building/MapServer/0",
    # LA County via EGIS hub
    "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/LA_County_Building_Outlines/FeatureServer/0",
    # LA City GeoHub building footprints
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/Building_Footprint/FeatureServer/0",
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Hero tile bbox (EPSG:4326 + {BUFFER:.3f}° buffer):")
    print(f"  lon {BBOX_BUFFERED['xmin']:.6f} to {BBOX_BUFFERED['xmax']:.6f}")
    print(f"  lat {BBOX_BUFFERED['ymin']:.6f} to {BBOX_BUFFERED['ymax']:.6f}")
    print()

    geojson = None

    # Try ESRI sources first (have building attributes)
    for svc in ESRI_SERVICES:
        print(f"Source: ESRI FeatureServer")
        geojson = esri_query(svc, BBOX_BUFFERED)
        if geojson:
            break

    # Fall back to OSM Overpass
    if not geojson:
        print("Source: OSM Overpass (fallback — geometry only, no HEIGHT attribute)")
        geojson = overpass_query(BBOX_BUFFERED)

    if not geojson:
        print("\nERROR: all sources failed.")
        print("Manual download:")
        print("  https://egis-lacounty.hub.arcgis.com/datasets/lacounty::la-county-building-outlines")
        print(f"  Save to: {OUT_FILE}")
        return 1

    OUT_FILE.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    n = len(geojson.get("features", []))
    size_kb = OUT_FILE.stat().st_size // 1024
    print(f"\nwrote: {OUT_FILE}")
    print(f"  {n} features, {size_kb} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
