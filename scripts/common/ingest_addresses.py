"""
ingest_addresses.py  [GlitchOS city pipeline — common]

Optional street address ingestion stage.

Reads a local GeoJSON, CSV, or Shapefile of address points, normalises the
schema, reprojects to the city working CRS, and writes:

    <city_output_root>/metadata/address_points.geojson

Output geometry is always lon/lat EPSG:4326 (standard GeoJSON).
City-projected x/y are stored as feature properties alongside lon/lat so
the file can be used for both web display and spatial analysis.

Normalised schema per feature
──────────────────────────────
  address_id    str   sequential id within this ingest
  full_address  str   "123 Main St, Los Angeles, CA 90012"
  house_number  str
  street        str
  city          str
  state         str
  postcode      str
  source        str   source_name from config
  lon           float WGS84 longitude
  lat           float WGS84 latitude
  x             float projected easting  (city CRS)
  y             float projected northing (city CRS)

Fail-soft contract
──────────────────
All public functions return (success: bool, count: int) and never raise.
Missing files, malformed records, and import failures are warned and skipped.
The main city pipeline should treat (True, 0) as "skipped gracefully".

Supported input formats
───────────────────────
  .geojson / .json   — standard GeoJSON FeatureCollection (Point or Polygon)
  .csv               — flat CSV with lon/lat columns (auto-detected or via
                       field_map keys "_lon" and "_lat")
  .shp               — Shapefile (requires osgeo.ogr, present in pdal_env)
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

TAG = "[ADDR]"


# ── CRS helpers ───────────────────────────────────────────────────────────────

def _transformer(src: str, dst: str):
    """Return a pyproj Transformer (always_xy=True), or None on failure."""
    try:
        from pyproj import Transformer
        return Transformer.from_crs(src, dst, always_xy=True)
    except Exception as exc:
        warnings.warn(f"{TAG} pyproj Transformer({src!r} → {dst!r}) failed: {exc}")
        return None


# ── field helpers ─────────────────────────────────────────────────────────────

def _get(row: dict, key: str | None) -> str:
    if key is None:
        return ""
    return str(row.get(key) or "").strip()


def _build_full_address(hn: str, street: str, city: str, state: str, pc: str) -> str:
    parts = []
    if hn and street:
        parts.append(f"{hn} {street}")
    elif street:
        parts.append(street)
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if pc:
        parts.append(pc)
    return ", ".join(parts)


def _normalise(
    props: dict,
    lon: float,
    lat: float,
    field_map: dict,
    source_name: str,
    address_id: str,
    to_4326,
    to_city,
) -> dict | None:
    """Normalise one raw record into the output schema. Returns None to skip."""
    try:
        if to_4326 is not None:
            lon, lat = to_4326.transform(lon, lat)
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return None

        hn     = _get(props, field_map.get("house_number"))
        street = _get(props, field_map.get("street"))
        city_v = _get(props, field_map.get("city"))
        state  = _get(props, field_map.get("state"))
        pc     = _get(props, field_map.get("postcode"))
        fa_key = field_map.get("full_address")
        full   = _get(props, fa_key) if fa_key else ""
        if not full:
            full = _build_full_address(hn, street, city_v, state, pc)

        x, y = None, None
        if to_city is not None:
            x, y = to_city.transform(lon, lat)

        return {
            "address_id":   address_id,
            "full_address": full,
            "house_number": hn,
            "street":       street,
            "city":         city_v,
            "state":        state,
            "postcode":     pc,
            "source":       source_name,
            "lon":          round(lon, 7),
            "lat":          round(lat, 7),
            "x":            round(x, 3) if x is not None else None,
            "y":            round(y, 3) if y is not None else None,
        }
    except Exception:
        return None


def _dedup_key(r: dict) -> tuple:
    return (
        round(r["lon"], 4),
        round(r["lat"], 4),
        (r["house_number"] or "").lower(),
        (r["street"] or "").lower()[:40],
    )


# ── format readers ────────────────────────────────────────────────────────────

def _read_geojson(path: Path) -> list[tuple[dict, float, float]]:
    """Return [(props, lon, lat), …] for each readable feature."""
    fc = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for feat in fc.get("features") or []:
        geom  = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        gtype = geom.get("type", "")
        c     = geom.get("coordinates")
        if c is None:
            continue
        if gtype == "Point":
            lon, lat = float(c[0]), float(c[1])
        elif gtype == "Polygon":
            ring = c[0]
            lon = sum(p[0] for p in ring) / len(ring)
            lat = sum(p[1] for p in ring) / len(ring)
        elif gtype == "MultiPolygon":
            ring = c[0][0]
            lon = sum(p[0] for p in ring) / len(ring)
            lat = sum(p[1] for p in ring) / len(ring)
        else:
            continue
        out.append((props, lon, lat))
    return out


def _read_csv(path: Path, field_map: dict) -> list[tuple[dict, float, float]]:
    """Read CSV; lon/lat column names from field_map['_lon'/'_lat'] or auto-detected."""
    _ALT_LON = {"longitude", "long", "lon", "x"}
    _ALT_LAT = {"latitude",  "lat",        "y"}
    out = []
    with path.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = [c.lower() for c in (reader.fieldnames or [])]
        raw_cols = reader.fieldnames or []

        lon_col = field_map.get("_lon")
        lat_col = field_map.get("_lat")
        if not lon_col:
            lon_col = next((rc for rc, lc in zip(raw_cols, cols) if lc in _ALT_LON), None)
        if not lat_col:
            lat_col = next((rc for rc, lc in zip(raw_cols, cols) if lc in _ALT_LAT), None)

        if not lon_col or not lat_col:
            warnings.warn(f"{TAG} CSV: cannot find lon/lat columns in {raw_cols}")
            return []

        for row in reader:
            try:
                lon = float(row[lon_col])
                lat = float(row[lat_col])
            except (ValueError, KeyError):
                continue
            out.append((dict(row), lon, lat))
    return out


def _read_shapefile(path: Path) -> list[tuple[dict, float, float]]:
    """Read Shapefile via osgeo.ogr (present in pdal_env conda environment)."""
    try:
        from osgeo import ogr
        ogr.UseExceptions()
    except ImportError:
        warnings.warn(f"{TAG} osgeo.ogr not available; cannot read Shapefile {path.name}")
        return []
    ds = ogr.Open(str(path))
    if ds is None:
        warnings.warn(f"{TAG} ogr.Open failed for {path}")
        return []
    lyr  = ds.GetLayer(0)
    defn = lyr.GetLayerDefn()
    field_names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
    out = []
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        centroid = geom.Centroid()
        lon, lat = centroid.GetX(), centroid.GetY()
        props = {name: feat.GetField(name) for name in field_names}
        out.append((props, lon, lat))
    ds = None
    return out


# ── bounding box helper ───────────────────────────────────────────────────────

def _bbox(features: list[dict]) -> dict | None:
    if not features:
        return None
    lons = [f["properties"]["lon"] for f in features]
    lats = [f["properties"]["lat"] for f in features]
    return {
        "xmin": round(min(lons), 6),
        "ymin": round(min(lats), 6),
        "xmax": round(max(lons), 6),
        "ymax": round(max(lats), 6),
    }


# ── public API ────────────────────────────────────────────────────────────────

def ingest_addresses(
    source_path: Path,
    field_map: dict,
    source_name: str,
    input_crs: str,
    output_path: Path,
    dst_crs: str,
    city_name: str = "",
) -> tuple[bool, int]:
    """
    Read, normalise, deduplicate, and write address points to GeoJSON.

    Parameters
    ----------
    source_path : Path
        Input file (.geojson, .csv, or .shp).
    field_map : dict
        Maps normalised field names to source column names.
        Special CSV keys: "_lon", "_lat" to override auto-detection.
    source_name : str
        Human-readable source label stored in each feature's `source` field.
    input_crs : str
        CRS of the input coordinates, e.g. "EPSG:4326".
    output_path : Path
        Where to write address_points.geojson.
    dst_crs : str
        City working CRS for x/y properties, e.g. "EPSG:32617".
    city_name : str
        Used in log prefix only.

    Returns
    -------
    (success, count)
        success=True even when skipped (count=0); False only on errors.
    """
    tag = f"{TAG}[{city_name}]" if city_name else TAG

    if not source_path.exists():
        print(f"{tag} source file not found: {source_path}")
        return False, 0

    suffix = source_path.suffix.lower()
    print(f"{tag} ingesting {source_path.name}  ({input_crs}) …")

    try:
        if suffix in (".geojson", ".json"):
            raw = _read_geojson(source_path)
        elif suffix == ".csv":
            raw = _read_csv(source_path, field_map)
        elif suffix == ".shp":
            raw = _read_shapefile(source_path)
        else:
            print(f"{tag} unsupported format {suffix!r} — supported: .geojson .csv .shp")
            return False, 0
    except Exception as exc:
        print(f"{tag} read error: {exc}")
        return False, 0

    if not raw:
        print(f"{tag} 0 readable features in source file")
        return False, 0

    print(f"{tag} {len(raw):,} raw records loaded")

    # Build reprojection transformers
    wgs84 = "EPSG:4326"
    normalised_input = input_crs.upper().replace(" ", "")
    to_4326 = (
        _transformer(input_crs, wgs84)
        if normalised_input not in (wgs84.upper(), "EPSG:4326", "4326")
        else None
    )
    to_city = _transformer(wgs84, dst_crs)

    # Normalise + deduplicate
    seen: set[tuple] = set()
    features: list[dict] = []
    skipped = 0
    for i, (props, lon, lat) in enumerate(raw):
        rec = _normalise(props, lon, lat, field_map, source_name,
                         address_id=str(i), to_4326=to_4326, to_city=to_city)
        if rec is None:
            skipped += 1
            continue
        dk = _dedup_key(rec)
        if dk in seen:
            continue
        seen.add(dk)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [rec["lon"], rec["lat"]]},
            "properties": rec,
        })

    if skipped:
        print(f"{tag} {skipped} records skipped (invalid geometry or out-of-range coords)")
    if not features:
        print(f"{tag} 0 valid features after normalisation; nothing written")
        return False, 0

    # Write output
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fc = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            },
            "metadata": {
                "source":        source_name,
                "input_crs":     input_crs,
                "city_crs":      dst_crs,
                "feature_count": len(features),
                "bbox_4326":     _bbox(features),
            },
            "features": features,
        }
        output_path.write_text(
            json.dumps(fc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"{tag} wrote {len(features):,} address points → {output_path}")
        return True, len(features)
    except Exception as exc:
        print(f"{tag} write failed: {exc}")
        return False, 0


def run_for_city(cfg, dst_epsg: int) -> tuple[bool, int]:
    """
    Convenience wrapper: run address ingestion from a CityConfig or
    bikini_config module-level namespace.

    Reads  cfg.address_source  (dataclass field, dict or None).
    Writes to cfg.address_points if the property exists, otherwise
    <cfg.output_root>/metadata/address_points.geojson.

    Always returns (True, 0) when no address_source is configured.
    """
    addr_src = getattr(cfg, "address_source", None)
    if not addr_src:
        print(f"{TAG} no address source configured; skipping")
        return True, 0

    src_path = addr_src.get("path")
    if not src_path:
        print(f"{TAG} address_source.path not set; skipping")
        return True, 0

    source_name = addr_src.get("source_name", Path(src_path).name)
    input_crs   = addr_src.get("input_crs", "EPSG:4326")
    field_map   = addr_src.get("field_map") or {}

    if hasattr(cfg, "address_points"):
        out_path = cfg.address_points
    elif hasattr(cfg, "output_root"):
        out_path = cfg.output_root / "metadata" / "address_points.geojson"
    else:
        print(f"{TAG} cannot determine output path; skipping")
        return False, 0

    city_name = getattr(cfg, "city_id", "")
    dst_crs   = f"EPSG:{dst_epsg}"

    return ingest_addresses(
        source_path=Path(src_path),
        field_map=field_map,
        source_name=source_name,
        input_crs=input_crs,
        output_path=out_path,
        dst_crs=dst_crs,
        city_name=city_name,
    )
