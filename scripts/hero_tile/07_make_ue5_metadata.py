"""
07_make_ue5_metadata.py

Generate the JSON/CSV/Markdown metadata package Codex needs to wire the
UE5 side without re-deriving anything from the raw geodata.

Inputs:
  - data_processed/miami/hero_tile/blender_ready/masses/hero_tile_building_masses_metadata.geojson
  - data_processed/miami/hero_tile/notes/hero_tile.shift.txt
  - data_processed/miami/hero_tile/notes/hero_tile_extent.txt

Outputs:
  exports/miami_hero_tile/metadata/
    tile_manifest.json          one-stop pointer for Codex
    buildings_metadata.json     per-UNIQUEID flat array (UE Data Asset friendly)
    buildings_metadata.csv      same data, importable as a UE DataTable
    lod_manifest.json           per-class point-cloud + mass LOD inventory
  exports/miami_hero_tile_preview/preview_20_buildings_metadata.json

This script does NOT touch the raw LAZ or the Blender scene; it just reads
existing processed files and writes derived metadata.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Glytc\glytchdraft")
HERO = ROOT / "data_processed" / "miami" / "hero_tile"
MASSES_META_GEOJSON = HERO / "blender_ready" / "masses" / "hero_tile_building_masses_metadata.geojson"
SHIFT_FILE = HERO / "notes" / "hero_tile.shift.txt"
EXTENT_FILE = HERO / "notes" / "hero_tile_extent.txt"

EXPORT_DIR = ROOT / "exports" / "miami_hero_tile"
META_DIR = EXPORT_DIR / "metadata"
PREVIEW_DIR = ROOT / "exports" / "miami_hero_tile_preview"

META_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def read_shift() -> dict:
    out = {"epsg": None, "shift_x": None, "shift_y": None, "anchor": None}
    for line in SHIFT_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("epsg:"):
            out["epsg"] = line.split(":", 1)[1].strip()
        elif line.startswith("shift_x:"):
            out["shift_x"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("shift_y:"):
            out["shift_y"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("anchor:"):
            out["anchor"] = line.split(":", 1)[1].strip()
    return out


def read_extent() -> dict:
    """Parse hero_tile_extent.txt; return both 3857 and 32617 bboxes."""
    text = EXTENT_FILE.read_text(encoding="utf-8")
    out = {"epsg_3857": None, "epsg_32617": None}
    section = None
    bbox = {}
    for line in text.splitlines():
        line = line.strip()
        if "EPSG:3857" in line:
            if section and bbox:
                out[section] = bbox
            section = "epsg_3857"
            bbox = {}
        elif line.startswith("## EPSG:32617"):
            if section and bbox:
                out[section] = bbox
            section = "epsg_32617"
            bbox = {}
        m = re.match(r"min:\s*\(([-\d.]+),\s*([-\d.]+)(?:,\s*([-\d.]+))?\)", line)
        if m:
            bbox["min_x"] = float(m.group(1))
            bbox["min_y"] = float(m.group(2))
            if m.group(3):
                bbox["min_z"] = float(m.group(3))
        m = re.match(r"max:\s*\(([-\d.]+),\s*([-\d.]+)(?:,\s*([-\d.]+))?\)", line)
        if m:
            bbox["max_x"] = float(m.group(1))
            bbox["max_y"] = float(m.group(2))
            if m.group(3):
                bbox["max_z"] = float(m.group(3))
    if section and bbox:
        out[section] = bbox
    return out


def main():
    print("loading source metadata...")
    shift = read_shift()
    extent = read_extent()
    masses_gj = json.loads(MASSES_META_GEOJSON.read_text(encoding="utf-8"))

    features = masses_gj.get("features", [])
    print(f"  building features in source: {len(features)}")

    # ---- per-building metadata, flat list of dicts -----
    buildings = []
    centroids = []
    for ft in features:
        p = ft.get("properties", {}) or {}
        # Compute polygon centroid in local (shifted) coords for spawn hints
        coords = (ft.get("geometry") or {}).get("coordinates") or []
        cx_l = cy_l = None
        if coords and coords[0]:
            ring = coords[0]
            if len(ring) > 1:
                xs = [pt[0] for pt in ring]
                ys = [pt[1] for pt in ring]
                # centroid in UTM
                cx_utm = sum(xs) / len(xs)
                cy_utm = sum(ys) / len(ys)
                cx_l = cx_utm - shift["shift_x"]
                cy_l = cy_utm - shift["shift_y"]

        entry = {
            "uniqueid": p.get("UNIQUEID"),
            "source_objectid": p.get("OBJECTID"),
            "type": p.get("TYPE"),
            "year_update": p.get("YEARUPDATE"),
            "shape_area_m2": p.get("Shape__Are"),
            "shape_length_m": p.get("Shape__Len"),
            "height_p50": p.get("height_p50"),
            "height_p90": p.get("height_p90"),
            "height_max": p.get("height_max"),
            "ground_z": p.get("ground_z"),
            "estimated_height": p.get("estimated_height"),
            "point_count_inside": p.get("point_count_inside"),
            "source_quality": p.get("source_quality"),
            "roof_complexity_score": None,
            "order_affinity": None,
            "claim_status": "open",
            "centroid_local_x": cx_l,
            "centroid_local_y": cy_l,
            "centroid_local_z": p.get("ground_z"),  # at ground; UE can offset
        }
        buildings.append(entry)

    # ---- buildings_metadata.json ----
    out_json = META_DIR / "buildings_metadata.json"
    out_json.write_text(json.dumps({
        "schema_version": "1.0",
        "tile": "miami_hero_tile_v001",
        "coordinate_frame": "blender_local_meters (after hero_tile.shift)",
        "primary_key": "uniqueid",
        "building_count": len(buildings),
        "buildings": buildings,
    }, indent=2), encoding="utf-8")
    print(f"  wrote {out_json.name}  ({out_json.stat().st_size / 1024:.0f} KB)")

    # ---- buildings_metadata.csv ----
    out_csv = META_DIR / "buildings_metadata.csv"
    if buildings:
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(buildings[0].keys()))
            w.writeheader()
            for b in buildings:
                w.writerow(b)
    print(f"  wrote {out_csv.name}")

    # ---- 20-building preview metadata ----
    preview = buildings[:20]
    out_preview = PREVIEW_DIR / "preview_20_buildings_metadata.json"
    out_preview.write_text(json.dumps({
        "schema_version": "1.0",
        "tile": "miami_hero_tile_v001_preview",
        "building_count": len(preview),
        "buildings": preview,
    }, indent=2), encoding="utf-8")
    print(f"  wrote {out_preview.name}")

    # ---- tile_manifest.json (Codex's first read) ----
    manifest = {
        "schema_version": "1.0",
        "tile_name": "miami_hero_tile_v001",
        "source_city": "Miami",
        "source_laz": "fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz",
        "original_crs": "EPSG:3857",
        "processed_crs": "EPSG:32617",
        "local_origin_shift": {
            "epsg": shift["epsg"],
            "shift_x": shift["shift_x"],
            "shift_y": shift["shift_y"],
            "shift_z": 0,
            "anchor": shift["anchor"],
        },
        "bounds_local_meters": {
            "min_x": 0, "min_y": 0,
            "max_x": 4652.0, "max_y": 3923.0,
            "min_z_approx": -2.0, "max_z_approx": 84.0,
        },
        "bounds_utm_32617": extent.get("epsg_32617"),
        "bounds_mercator_3857": extent.get("epsg_3857"),
        "units": "meters",
        "axis_convention": "Blender (Z-up). GLB written Y-up by glTF convention; Unreal converts on import.",
        "recommended_ue_scale": {
            "glb_to_ue": "GLB defaults to 1.0 (handled by UE5 glTF importer; 1 meter = 100 UE units automatic).",
            "fbx_to_ue": "FBX exported with apply_unit_scale=True. Set Import Uniform Scale = 1.0; UE will read meters from FBX FbxSystemUnit.",
            "verify_after_import": "Place an actor at world (4652, 3923, 0); it should sit at the NE corner of the tile. Tile bbox wireframe is the reference."
        },
        "available_layers": {
            "masses_LOD0_per_building": "miami_hero_tile_masses.glb (2670 named meshes — primary)",
            "masses_LOD0_merged":       "miami_hero_tile_masses_merged.glb (single Nanite-friendly mesh)",
            "masses_LOD0_fbx":          "miami_hero_tile_masses.fbx (FBX fallback)",
            "masses_LOD1_simplified":   "miami_hero_tile_masses_LOD1_simplified.glb (rotated bbox, far LOD)",
            "reference_bounds":         "miami_hero_tile_reference_bounds.glb (tile bbox + anchor)",
            "ai_markers":               "miami_hero_tile_ai_markers.glb (6 companion empties)",
            "order_overlays":           "miami_hero_tile_order_overlays.glb (Mirrorsweat + Pink Opaque)"
        },
        "metadata": {
            "buildings_json": "metadata/buildings_metadata.json",
            "buildings_csv":  "metadata/buildings_metadata.csv",
            "lod_manifest":   "metadata/lod_manifest.json",
            "coordinate_system_notes": "metadata/coordinate_system_notes.md",
            "import_scale_notes":      "metadata/import_scale_notes.md"
        },
        "recommended_import_order": [
            "miami_hero_tile_reference_bounds.glb  (visual sanity — confirms scale and origin)",
            "miami_hero_tile_masses_merged.glb     (one StaticMesh actor — fastest preview)",
            "OR miami_hero_tile_masses.glb         (2670 selectable actors — pick this once preview looks right)",
            "miami_hero_tile_ai_markers.glb        (6 empties — spawn AGlytchCompanionMarkerActor at each)",
            "miami_hero_tile_order_overlays.glb    (2 empties — feed UGlytchOrderOverlayComponent)"
        ],
        "do_not_import": [
            "raw LAZ in OneDrive/Desktop/GLYTCHDRAFT_MIAMI/3DEP_LiDAR_MIAMI/",
            "raw shapefile in OneDrive/Desktop/GLYTCHDRAFT_MIAMI/Building_Footprint_2D_2018/",
            "PLY files under data_processed/miami/hero_tile/pointcloud/ until point-rendering pipeline is in place"
        ],
        "building_count": len(buildings),
        "building_quality_breakdown": _quality_breakdown(buildings),
    }
    out_manifest = META_DIR / "tile_manifest.json"
    out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  wrote {out_manifest.name}")

    # ---- lod_manifest.json ----
    lod = {
        "schema_version": "1.0",
        "tile_name": "miami_hero_tile_v001",
        "point_clouds": {
            "buildings": [
                {"lod": "LOD0", "spacing_m": 0.25, "path": "data_processed/miami/hero_tile/pointcloud/hero_tile_building_32617_0p25m.ply",  "approx_points": 4907094, "use": "cinematic / inspection"},
                {"lod": "LOD1", "spacing_m": 0.5,  "path": "data_processed/miami/hero_tile/pointcloud/hero_tile_building_32617_0p5m.ply",  "approx_points": 1716678, "use": "interactive close"},
                {"lod": "LOD2", "spacing_m": 1.0,  "path": "data_processed/miami/hero_tile/pointcloud/hero_tile_building_32617_1m.ply",    "approx_points": 555624,  "use": "navigation / context"}
            ],
            "ground": [
                {"lod": "LOD0", "spacing_m": 1.0,  "path": "data_processed/miami/hero_tile/pointcloud/hero_tile_ground_32617_1m.ply",      "approx_points": 2335945},
                {"lod": "LOD1", "spacing_m": 2.0,  "path": "data_processed/miami/hero_tile/pointcloud/hero_tile_ground_32617_2m.ply",      "approx_points": 719748}
            ],
            "water": [
                {"lod": "LOD0", "spacing_m": 1.0,  "path": "data_processed/miami/hero_tile/pointcloud/hero_tile_water_32617_1m.ply",       "approx_points": 2206705},
                {"lod": "LOD1", "spacing_m": 2.0,  "path": "data_processed/miami/hero_tile/pointcloud/hero_tile_water_32617_2m.ply",       "approx_points": 670450}
            ]
        },
        "masses": {
            "LOD0_individual_per_building_glb": "exports/miami_hero_tile/miami_hero_tile_masses.glb",
            "LOD0_merged_glb":                  "exports/miami_hero_tile/miami_hero_tile_masses_merged.glb",
            "LOD0_fbx":                         "exports/miami_hero_tile/miami_hero_tile_masses.fbx",
            "LOD1_simplified_glb":              "exports/miami_hero_tile/miami_hero_tile_masses_LOD1_simplified.glb"
        },
        "ue_default_mode": {
            "name": "navigation",
            "show": ["masses_LOD0_merged_or_per_building", "reference_bounds", "ai_markers"],
            "hide": ["point_clouds_all", "order_overlays_geometry"]
        },
        "ue_modes": {
            "navigation":    ["masses_LOD0", "reference_bounds", "ai_markers"],
            "inspection":    ["masses_LOD0", "point_clouds_LOD2", "ai_markers"],
            "cinematic":     ["masses_LOD0", "point_clouds_LOD1", "order_overlays", "ai_markers"],
            "architectural": ["masses_LOD0", "reference_bounds"],
            "evidence_only": ["point_clouds_LOD1"],
            "meaning_only":  ["masses_LOD1_simplified", "order_overlays", "ai_markers"]
        }
    }
    out_lod = META_DIR / "lod_manifest.json"
    out_lod.write_text(json.dumps(lod, indent=2), encoding="utf-8")
    print(f"  wrote {out_lod.name}")

    print("\nmetadata generation complete.")


def _quality_breakdown(buildings: list[dict]) -> dict:
    out = {}
    for b in buildings:
        q = b.get("source_quality") or "unknown"
        out[q] = out.get(q, 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main() or 0)
