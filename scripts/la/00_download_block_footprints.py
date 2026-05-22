"""
00_download_block_footprints.py  [LA block pipeline — GlitchOS.io]

Download building footprints for the full LA 1836 block (all four quarter-tiles).
This is a one-time download that covers the union bbox of tiles a/b/c/d.

Output: /mnt/t7/la/data_raw/geojson/la_block_1836_footprints_4326.geojson

The hero_tile footprints (/mnt/t7/la/data_raw/geojson/la_county_building_outlines_4326.geojson)
cover only tile b's bbox — this script downloads a wider area for all 4 tiles.

Sources tried in order:
  1. LA County FeatureServer (ESRI REST) — has HEIGHT/YEAR_BUILT attributes
  2. LA City GeoHub FeatureServer — city limits only, DTLA coverage
  3. OSM Overpass API — reliable fallback, geometry only

Block bbox (EPSG:4326, covers ~915×915 m 3DEP grid cell + 400 m buffer):
  lon: -118.310 to -118.250
  lat:   34.030 to  34.075
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tile_config import BLOCK_FOOTPRINTS_RAW, BLOCK_BBOX_4326

OUT_DIR  = BLOCK_FOOTPRINTS_RAW.parent
BUFFER   = 0.003   # ~300 m additional buffer

BBOX = {
    "xmin": BLOCK_BBOX_4326["xmin"] - BUFFER,
    "ymin": BLOCK_BBOX_4326["ymin"] - BUFFER,
    "xmax": BLOCK_BBOX_4326["xmax"] + BUFFER,
    "ymax": BLOCK_BBOX_4326["ymax"] + BUFFER,
}

ESRI_SERVICES = [
    "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Building/MapServer/0",
    "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/LA_County_Building_Outlines/FeatureServer/0",
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/Building_Footprint/FeatureServer/0",
]


def esri_query(service_url: str, bbox: dict) -> dict | None:
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
        label = service_url.split("/arcgis")[0].split("//")[-1]
        print(f"  trying ESRI: {label}...")
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
    b = f"{bbox['ymin']},{bbox['xmin']},{bbox['ymax']},{bbox['xmax']}"
    query = (
        f"[out:json][timeout:90][bbox:{b}];"
        "(way[\"building\"];relation[\"building\"][\"type\"=\"multipolygon\"];);"
        "out body;>;out skel qt;"
    )
    headers = {
        "User-Agent": "GlitchOS.io/1.0 (spatial pipeline; contact charleshopeart@gmail.com)",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data_enc = urllib.parse.urlencode({"data": query}).encode()
    for endpoint in [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]:
        try:
            label = endpoint.split("/api")[0].split("//")[-1]
            print(f"  trying Overpass: {label}...")
            req = urllib.request.Request(endpoint, data=data_enc, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                osm = json.loads(resp.read())
            result = _osm_to_geojson(osm)
            if result:
                return result
        except Exception as e:
            print(f"  failed: {e}")
    return None


def _osm_to_geojson(osm: dict) -> dict | None:
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
                "osm_id":   el["id"],
                "building": tags.get("building", "yes"),
                "height":   tags.get("height") or tags.get("building:levels"),
                "name":     tags.get("name"),
                "source":   "OpenStreetMap",
            },
        })
    if not features:
        return None
    print(f"  converted {len(features)} OSM ways to GeoJSON polygons")
    return {"type": "FeatureCollection", "features": features}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if BLOCK_FOOTPRINTS_RAW.exists() and BLOCK_FOOTPRINTS_RAW.stat().st_size > 1024:
        size_kb = BLOCK_FOOTPRINTS_RAW.stat().st_size // 1024
        print(f"Block footprints already exist ({size_kb} KB): {BLOCK_FOOTPRINTS_RAW}")
        print("Delete the file and re-run to refresh.")
        return 0

    print(f"GlitchOS.io — downloading LA block 1836 building footprints")
    print(f"Block bbox (EPSG:4326 + {BUFFER:.3f} deg buffer):")
    print(f"  lon {BBOX['xmin']:.5f} to {BBOX['xmax']:.5f}")
    print(f"  lat {BBOX['ymin']:.5f} to {BBOX['ymax']:.5f}")
    print()

    geojson = None

    for svc in ESRI_SERVICES:
        geojson = esri_query(svc, BBOX)
        if geojson:
            break

    if not geojson:
        print("ESRI sources unavailable — falling back to OSM Overpass...")
        geojson = overpass_query(BBOX)

    if not geojson:
        print("\nERROR: all sources failed.")
        print("Manual download options:")
        print("  https://egis-lacounty.hub.arcgis.com/datasets/lacounty::la-county-building-outlines")
        print(f"  Save to: {BLOCK_FOOTPRINTS_RAW}")
        return 1

    BLOCK_FOOTPRINTS_RAW.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    n = len(geojson.get("features", []))
    size_kb = BLOCK_FOOTPRINTS_RAW.stat().st_size // 1024
    print(f"\nwrote: {BLOCK_FOOTPRINTS_RAW}")
    print(f"  {n} features,  {size_kb} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
