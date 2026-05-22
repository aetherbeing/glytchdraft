"""
stages/s05_manifest.py  [LA block pipeline]

Write per-tile manifest.json and the combined block manifest.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tile_config import TileConfig, BLOCK_MANIFEST_PATH, TILE_ORDER, TILES

PIPELINE_VERSION = "1.1"


def write_tile_manifest(tile: TileConfig, stage_results: dict) -> Path:
    """
    Collects outputs from all completed stages and writes tile_manifest.json.

    stage_results keys expected:
      s00: {"bbox_2229": {...}, "bbox_32611": {...}, "shift": {"x":..,"y":..}}
      s01: {"count_4326": n, "count_32611": n}
      s02: {"ground_points": n, "elapsed_s": f}
      s03: {"passed": bool, "failures": [...], "batch_results": [...]}
      s04: {"lod0": n, "lod1": n, "quality": {...}, "footprints": n}
      errors: {stage_name: error_message}
    """
    tile.manifest_dir.mkdir(parents=True, exist_ok=True)

    s00 = stage_results.get("s00") or {}
    s01 = stage_results.get("s01") or {}
    s02 = stage_results.get("s02") or {}
    s03 = stage_results.get("s03") or {}
    s04 = stage_results.get("s04") or {}
    errors = stage_results.get("errors") or {}
    terrain_only = bool(s01.get("no_footprints") or s01.get("terrain_only"))

    all_passed = not errors

    manifest = {
        "schema_version":   PIPELINE_VERSION,
        "pipeline":         "GlitchOS.io LA block pipeline",
        "tile_id":          tile.tile_id,
        "source_laz":       tile.laz_filename,
        "source_crs":       "EPSG:2229",
        "target_crs":       "EPSG:32611",
        "processed_at":     datetime.now(timezone.utc).isoformat(),
        "all_stages_passed": all_passed,
        "stage_status": {
            "s00_extent":     "ok"   if "s00" in stage_results else ("error: " + errors.get("s00", "skipped")),
            "s01_footprints": "ok"   if "s01" in stage_results else ("error: " + errors.get("s01", "skipped")),
            "s02_pointcloud": "ok"   if "s02" in stage_results else ("error: " + errors.get("s02", "skipped")),
            "s03_validate":   "pass" if s03.get("passed") else ("error: " + errors.get("s03", "skipped")),
            "s04_masses":     ("skipped: no_footprints" if terrain_only else ("ok" if "s04" in stage_results else ("error: " + errors.get("s04", "skipped")))),
        },
        "bbox_2229":        s00.get("bbox_2229"),
        "bbox_32611":       s00.get("bbox_32611"),
        "blender_shift":    s00.get("shift"),
        "footprint_count":  s01.get("count_32611"),
        "terrain_only":     terrain_only,
        "ground_points":    s02.get("ground_points"),
        "building_mass_lod0": s04.get("lod0"),
        "building_mass_lod1": s04.get("lod1"),
        "quality_breakdown":  s04.get("quality"),
        "crs_validation":   {"passed": s03.get("passed"), "failures": s03.get("failures", [])},
        "errors":           errors,
        "outputs": {
            "extent_json":      str(tile.extent_json),
            "footprints_32611": str(tile.footprints_32611),
            "ground_ply":       str(tile.ground_ply),
            "lod0_obj":         str(tile.lod0_obj),
            "lod1_obj":         str(tile.lod1_obj),
            "masses_metadata":  str(tile.masses_metadata),
        },
    }

    tile.tile_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[{tile.tile_id}] manifest → {tile.tile_manifest}")
    return tile.tile_manifest


def write_block_manifest(tile_results: dict[str, dict]) -> Path:
    """
    Aggregate all 4 tile manifests into a single block-level manifest.
    tile_results: {tile_id: stage_results_dict}
    """
    BLOCK_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    tiles_summary = {}
    total_footprints = 0
    total_ground_pts = 0
    total_lod0 = 0
    all_ok = True

    for tile_id in TILE_ORDER:
        tile = TILES[tile_id]
        res  = tile_results.get(tile_id, {})
        s00  = res.get("s00") or {}
        s01  = res.get("s01") or {}
        s02  = res.get("s02") or {}
        s04  = res.get("s04") or {}
        errors = res.get("errors") or {}

        ok = not errors
        all_ok = all_ok and ok

        fp  = s01.get("count_32611") or 0
        gp  = s02.get("ground_points") or 0
        lod = s04.get("lod0") or 0
        total_footprints += fp
        total_ground_pts += gp
        total_lod0 += lod

        tiles_summary[tile_id] = {
            "status":          "ok" if ok else "failed",
            "source_laz":      tile.laz_filename,
            "bbox_32611":      s00.get("bbox_32611"),
            "blender_shift":   s00.get("shift"),
            "footprint_count": fp,
            "ground_points":   gp,
            "lod0_prisms":     lod,
            "quality":         (s04.get("quality") or {}),
            "errors":          errors,
            "manifest_path":   str(tile.tile_manifest),
        }

    block_manifest = {
        "schema_version":   PIPELINE_VERSION,
        "pipeline":         "GlitchOS.io LA block pipeline",
        "block_id":         "la_1836",
        "description":      "4-tile Downtown LA / Bunker Hill block (USGS 3DEP 2016)",
        "source_crs":       "EPSG:2229",
        "target_crs":       "EPSG:32611",
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "all_tiles_passed": all_ok,
        "totals": {
            "tiles":            len(TILE_ORDER),
            "tiles_ok":         sum(1 for t in tiles_summary.values() if t["status"] == "ok"),
            "total_footprints": total_footprints,
            "total_ground_pts": total_ground_pts,
            "total_lod0_prisms": total_lod0,
        },
        "tiles": tiles_summary,
    }

    BLOCK_MANIFEST_PATH.write_text(json.dumps(block_manifest, indent=2), encoding="utf-8")
    print(f"\nBlock manifest → {BLOCK_MANIFEST_PATH}")
    return BLOCK_MANIFEST_PATH
