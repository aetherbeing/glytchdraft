"""
s07_metadata.py  [Project Bikini — GlitchOS.io]

Generate the web-native metadata package for the Three.js / R3F GlitchOS viewer.

Reads existing processed outputs and writes derived JSON to exports/miami_bikini/.
Does not touch any LAZ, PLY, or OBJ files.

Outputs (exports/miami_bikini/):
  tile_manifest.json         one-stop pointer for the viewer
  buildings.json             per-building flat array: ID, centroid, height, bbox, quality
  buildings_preview.json     first 50 buildings — for fast viewer seed

Usage:
    python scripts/miami/s07_metadata.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

SCHEMA_VERSION = "1.1"


def read_masses_metadata() -> list[dict]:
    """Read bikini_masses_metadata.csv from the masses directory."""
    csv_path = CFG.MASS_DIR / "bikini_masses_metadata.csv"
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_masses_geometry() -> dict[int, "Polygon"]:
    """Read cluster_id -> footprint polygon from bikini_masses_metadata.geojson.

    s05_masses.py writes this file alongside the CSV, keyed by the same
    cluster_id, with the authoritative building polygon (county footprint or
    convex hull) already used to compute the CSV row for that building.
    Coordinates are absolute EPSG:32617 (UTM 17N meters, no shift applied) —
    the same convention as the source footprint/masses geometry.
    """
    from shapely.geometry import MultiPolygon, shape

    path = CFG.MASS_DIR / "bikini_masses_metadata.geojson"
    if not path.exists():
        return {}
    gj = json.loads(path.read_text(encoding="utf-8"))
    geometry_by_id: dict[int, "Polygon"] = {}
    for feature in gj.get("features", []):
        props = feature.get("properties", {})
        if "cluster_id" not in props or props["cluster_id"] is None:
            continue
        cid = int(float(props["cluster_id"]))
        geom = shape(feature["geometry"])
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)
        geometry_by_id[cid] = geom
    return geometry_by_id


def read_shift() -> dict:
    shift_file = CFG.SHIFT_DIR / "bikini.shift.txt"
    out = {
        "epsg": str(CFG.OUT_EPSG),
        "shift_x": CFG.SHIFT_X,
        "shift_y": CFG.SHIFT_Y,
        "vertical_unit": CFG.vertical_unit_label(),
    }
    if not shift_file.exists():
        return out
    for line in shift_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("shift_x:"):
            out["shift_x"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("shift_y:"):
            out["shift_y"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("epsg:"):
            out["epsg"] = line.split(":", 1)[1].strip()
        elif line.startswith("shift_z:"):
            out["shift_z"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("vertical_unit:"):
            out["vertical_unit"] = line.split(":", 1)[1].strip()
    return out


def read_normalization_provenance() -> dict | None:
    path = CFG.META_DIR / "normalization_provenance.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_buildings_json(rows: list[dict], geometry_by_id: dict[int, "Polygon"],
                         shift_x: float, shift_y: float) -> list[dict]:
    """Convert CSV rows to the per-building JSON format for the viewer.

    cx/cy are the true polygon centroid of each building's authoritative
    footprint geometry (see read_masses_geometry), projected into the same
    local-shifted EPSG:32617 convention as the exported GLB geometry and
    tile_manifest.json ("coordinate_system.local_shift"): local = utm - shift.
    """
    buildings = []
    for row in rows:
        try:
            cid    = int(float(row["cluster_id"]))
            height = float(row["estimated_height"] or 0)
            quality = row.get("source_quality", "unknown")
            lod0   = str(row.get("lod0_included", "")).lower() in ("true", "1")
        except (ValueError, TypeError):
            continue

        geom = geometry_by_id.get(cid)
        if geom is None or geom.is_empty:
            raise ValueError(
                f"no matching footprint geometry for building cluster_id={cid} "
                f"in bikini_masses_metadata.geojson; refusing to fall back to "
                f"cx=0.0, cy=0.0"
            )

        centroid = geom.centroid
        cx = centroid.x - shift_x
        cy = centroid.y - shift_y

        buildings.append({
            "id":      cid,
            "h":       round(height, 2),
            "cx":      round(cx, 2),
            "cy":      round(cy, 2),
            "quality": quality,
            "lod0":    lod0,
        })
    return buildings


def compute_local_bounds(rows: list[dict], shift: dict) -> dict:
    """Derive approximate local (shifted) bounds from metadata CSV."""
    if not rows:
        return {}
    try:
        # Centroids from cluster summary (not directly in masses CSV —
        # use footprint area as proxy that they exist, bounds from global bbox)
        sx, sy = shift["shift_x"], shift["shift_y"]
        return {
            "local_bbox_approx": {
                "xmin": round(CFG.BBOX_4326["xmin"] + sx, 1),
                "ymin": round(CFG.BBOX_4326["ymin"] + sy, 1),
                "xmax": round(CFG.BBOX_4326["xmax"] + sx, 1),
                "ymax": round(CFG.BBOX_4326["ymax"] + sy, 1),
            },
            "note": "local coords = UTM 32617 minus shift; see shift values above",
        }
    except Exception:
        return {}


def check_glb_inventory() -> dict:
    glbs = {}
    for lod, fname in (
        ("LOD0", "MIAMI_BIKINI_LOD0.glb"),
        ("LOD1", "MIAMI_BIKINI_LOD1.glb"),
        ("LOD2", "MIAMI_BIKINI_LOD2.glb"),
    ):
        p = CFG.EXPORT_ROOT / fname
        glbs[lod] = {
            "file":    fname,
            "exists":  p.exists(),
            "size_mb": round(p.stat().st_size / 1_048_576, 2) if p.exists() else None,
        }
    return glbs


def main() -> int:
    CFG.EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

    print("reading masses metadata...")
    rows = read_masses_metadata()
    if not rows:
        print("WARNING: bikini_masses_metadata.csv not found or empty.")
        print("  Run s05_masses.py first for full metadata.")

    shift = read_shift()
    normalization_provenance = read_normalization_provenance()
    geometry_by_id = read_masses_geometry()
    buildings = build_buildings_json(rows, geometry_by_id, shift["shift_x"], shift["shift_y"])
    glbs = check_glb_inventory()

    quality_counts: dict[str, int] = {}
    for b in buildings:
        quality_counts[b["quality"]] = quality_counts.get(b["quality"], 0) + 1

    # ── tile_manifest.json ─────────────────────────────────────────────────────

    manifest = {
        "schema_version":  SCHEMA_VERSION,
        "project":         "GlitchOS — Project Bikini",
        "tile_name":       "miami_bikini_v001",
        "generated_at":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "project":    "FL_MiamiDade_D23",
            "dataset":    "USGS LiDAR Point Cloud 2024",
            "license":    "public domain (17 U.S.C. § 105)",
            "tile_count": len(CFG.LAZ_TILES),
            "tiles":      CFG.LAZ_TILES,
        },
        "zones": CFG.ZONES,
        "bbox_4326": CFG.BBOX_4326,
        "coordinate_system": {
            "processed_crs":  f"EPSG:{CFG.OUT_EPSG}",
            "local_shift":    shift,
            "xy_unit":         "meters",
            "z_unit":          CFG.vertical_unit_label(),
            "z_values_metric": CFG.z_values_are_metric(),
            "note": "All exported geometry is in local coords (UTM 32617 minus shift). "
                    "To recover real-world UTM: add shift_x to X, shift_y to Y.",
        },
        "metric_normalization": {
            **CFG.METRIC_NORMALIZATION_CONFIG,
            "provenance_path": (
                str(CFG.META_DIR / "normalization_provenance.json")
                if normalization_provenance else None
            ),
            "source_laz": (
                normalization_provenance.get("source_laz")
                if normalization_provenance else None
            ),
            "pipeline_commit": (
                normalization_provenance.get("pipeline_commit")
                if normalization_provenance else None
            ),
            "generated_at": (
                normalization_provenance.get("generated_at")
                if normalization_provenance else None
            ),
        },
        "building_summary": {
            "total":   len(buildings),
            "quality": quality_counts,
        },
        "layers": {
            "masses_LOD0": glbs.get("LOD0", {}),
            "masses_LOD1": glbs.get("LOD1", {}),
            "masses_LOD2": glbs.get("LOD2", {}),
        },
        "data_files": {
            "buildings_json":         "buildings.json",
            "buildings_preview_json": "buildings_preview.json",
            "tile_manifest":          "tile_manifest.json",
        },
        "viewer_hints": {
            "origin":        "SW corner of combined Bikini bbox, UTM 17N rounded to 1 km",
            "units":         "meters" if CFG.z_values_are_metric() else "xy_meters_z_source_vertical_units",
            "vertical_units_are_metric": CFG.z_values_are_metric(),
            "y_up":          True,
            "recommended_import_order": [
                "MIAMI_BIKINI_LOD2.glb  (fast overview — block silhouettes)",
                "MIAMI_BIKINI_LOD0.glb  (full detail — per-building convex hull prisms)",
            ],
        },
    }

    manifest_path = CFG.EXPORT_ROOT / "tile_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {manifest_path.name}")

    # ── buildings.json ─────────────────────────────────────────────────────────

    buildings_path = CFG.EXPORT_ROOT / "buildings.json"
    buildings_path.write_text(json.dumps(buildings, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {buildings_path.name}  ({len(buildings)} buildings)")

    # ── buildings_preview.json (first 50, for fast viewer seed) ───────────────

    # Sort by estimated_height descending so preview shows the tallest first
    sorted_buildings = sorted(buildings, key=lambda b: b["h"], reverse=True)
    preview = sorted_buildings[:50]
    preview_path = CFG.EXPORT_ROOT / "buildings_preview.json"
    preview_path.write_text(json.dumps(preview, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {preview_path.name}  ({len(preview)} buildings — tallest first)")

    # ── summary ────────────────────────────────────────────────────────────────

    print(f"\n{'='*50}")
    print(f"  Project Bikini metadata complete")
    print(f"  buildings:  {len(buildings)}")
    print(f"  quality:    {quality_counts}")
    print(f"  GLBs:       {sum(1 for v in glbs.values() if v.get('exists'))} / 3 present")
    print(f"  exports ->  {CFG.EXPORT_ROOT}")
    print(f"{'='*50}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
