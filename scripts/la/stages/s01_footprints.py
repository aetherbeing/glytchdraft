"""
stages/s01_footprints.py  [LA block / city pipeline]

Clip building footprints to this tile's bbox, reproject to EPSG:32611,
write per-tile footprint files.

Requires: tile_extent.json written by s00_extent.

Footprint source selection (first available wins):
  1. tile.footprints_src      — explicit override (set by run_city city pipeline)
  2. CITY_FOOTPRINTS_RAW      — city-wide file (download_city_footprints.py)
  3. BLOCK_FOOTPRINTS_RAW     — 4-tile DTLA block (00_download_block_footprints.py)
  4. Live ESRI / OSM query    — per-tile network fetch (fallback, no local file needed)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from osgeo import gdal, ogr, osr

from tile_config import (
    TileConfig,
    BLOCK_FOOTPRINTS_RAW,
    CITY_FOOTPRINTS_RAW,
    SRC_EPSG,
    DST_EPSG,
)

ogr.UseExceptions()
osr.UseExceptions()
gdal.UseExceptions()

# LA County / LA City ESRI FeatureServer endpoints (tried in order)
_ESRI_SERVICES = [
    "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Building/MapServer/0",
    "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/LA_County_Building_Outlines/FeatureServer/0",
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/Building_Footprint/FeatureServer/0",
]


# ── live fetch helpers ────────────────────────────────────────────────────────

def _esri_query(service_url: str, bbox: tuple) -> dict | None:
    xmin, ymin, xmax, ymax = bbox
    geometry = json.dumps({
        "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
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
    try:
        with urllib.request.urlopen(f"{service_url}/query?{params}", timeout=30) as resp:
            data = json.loads(resp.read())
        if "error" in data:
            return None
        features = data.get("features", [])
        return data if features else None
    except Exception:
        return None


def _overpass_query(bbox: tuple) -> dict | None:
    xmin, ymin, xmax, ymax = bbox
    b = f"{ymin},{xmin},{ymax},{xmax}"
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
            req = urllib.request.Request(endpoint, data=data_enc, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as resp:
                osm = json.loads(resp.read())
            result = _osm_to_geojson(osm)
            if result:
                return result
        except Exception:
            continue
    return None


def _osm_to_geojson(osm: dict) -> dict | None:
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
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def _fetch_footprints_live(bbox_4326: tuple, tile_id: str) -> dict | None:
    """Try ESRI services then OSM. Returns GeoJSON dict or None."""
    print(f"[{tile_id}] s01 footprints: no local source — querying live...")
    for svc in _ESRI_SERVICES:
        result = _esri_query(svc, bbox_4326)
        if result:
            n = len(result.get("features", []))
            print(f"[{tile_id}]   ESRI: {n} features")
            return result
    print(f"[{tile_id}]   ESRI failed, trying OSM Overpass...")
    result = _overpass_query(bbox_4326)
    if result:
        n = len(result.get("features", []))
        print(f"[{tile_id}]   OSM: {n} features")
    return result


# ── core helpers ──────────────────────────────────────────────────────────────

def _reproject_bbox_to_4326(minx, miny, maxx, maxy, src_epsg):
    src = osr.SpatialReference()
    src.ImportFromEPSG(src_epsg)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tx = osr.CoordinateTransformation(src, dst)
    corners = [
        (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy),
        ((minx + maxx) / 2, (miny + maxy) / 2),
    ]
    pts = [tx.TransformPoint(x, y)[:2] for x, y in corners]
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def _clip_and_reproject(src_path: Path, out_path: Path, clip_bbox_4326, t_srs, out_format):
    minx, miny, maxx, maxy = clip_bbox_4326
    opts = gdal.VectorTranslateOptions(
        format=out_format,
        spatFilter=[minx, miny, maxx, maxy],
        spatSRS="EPSG:4326",
        dstSRS=t_srs,
        reproject=(t_srs is not None),
        makeValid=True,
    )
    if out_path.exists():
        out_path.unlink()
    ds = gdal.VectorTranslate(str(out_path), str(src_path), options=opts)
    ds = None


def _feature_count(path: Path) -> int:
    ds = ogr.Open(str(path))
    if ds is None:
        return 0
    n = ds.GetLayer(0).GetFeatureCount()
    ds = None
    return n


def _pick_footprints_src(tile: TileConfig) -> Path | None:
    """Return the first available local footprint file, or None for live fetch."""
    if tile.footprints_src is not None and tile.footprints_src.exists():
        return tile.footprints_src
    if CITY_FOOTPRINTS_RAW.exists():
        return CITY_FOOTPRINTS_RAW
    if BLOCK_FOOTPRINTS_RAW.exists():
        return BLOCK_FOOTPRINTS_RAW
    return None


# ── stage entry point ─────────────────────────────────────────────────────────

def run(tile: TileConfig) -> dict:
    """
    Returns: {"count_4326": n, "count_32611": n, "no_footprints": bool,
              "source": str, "live_fetch": bool}
    """
    extent = json.loads(tile.extent_json.read_text(encoding="utf-8"))
    b = extent["bbox_2229"]

    bbox_4326 = _reproject_bbox_to_4326(b["minx"], b["miny"], b["maxx"], b["maxy"], SRC_EPSG)
    print(f"[{tile.tile_id}] s01 footprints  clip bbox 4326: {[round(v, 5) for v in bbox_4326]}")

    tile.footprints_dir.mkdir(parents=True, exist_ok=True)

    footprints_src = _pick_footprints_src(tile)
    live_fetch = footprints_src is None
    source_label = str(footprints_src) if footprints_src else "live:ESRI/OSM"

    if footprints_src is not None:
        _clip_and_reproject(footprints_src, tile.footprints_4326, bbox_4326, t_srs=None, out_format="GeoJSON")
        _clip_and_reproject(footprints_src, tile.footprints_32611, bbox_4326, t_srs=f"EPSG:{DST_EPSG}", out_format="GeoJSON")
    else:
        geojson = _fetch_footprints_live(bbox_4326, tile.tile_id)
        if geojson is None:
            raise RuntimeError(
                f"[{tile.tile_id}] No local footprint source found and live fetch failed.\n"
                "  Fix: python scripts/la/download_city_footprints.py los_angeles"
            )
        tile.footprints_4326.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
        _clip_and_reproject(
            tile.footprints_4326, tile.footprints_32611, bbox_4326,
            t_srs=f"EPSG:{DST_EPSG}", out_format="GeoJSON",
        )

    n_4326   = _feature_count(tile.footprints_4326)
    n_32611  = _feature_count(tile.footprints_32611)

    if n_32611 == 0:
        print(f"[{tile.tile_id}]   0 footprints after clip; marking terrain-only")
        return {
            "count_4326": n_4326,
            "count_32611": n_32611,
            "no_footprints": True,
            "terrain_only": True,
            "source": source_label,
            "live_fetch": live_fetch,
        }

    print(f"[{tile.tile_id}]   {n_4326} features (4326),  {n_32611} features (32611)  [src: {Path(source_label).name if not live_fetch else source_label}]")
    return {
        "count_4326": n_4326,
        "count_32611": n_32611,
        "no_footprints": False,
        "source": source_label,
        "live_fetch": live_fetch,
    }
