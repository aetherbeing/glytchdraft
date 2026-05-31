#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np

from phase_common import add_phase_args, load_city, print_header, resolve_mode, utc_now
from phase_tile_common import (
    crs_tag, load_tiles, mesh_shift_from_vertices, obj_to_flat_triangles,
    output_summary, pack_glb, read_geojson_features, read_ply_xyz, require_execute,
    should_skip_phase, validate_or_fail, write_json,
)


PHASE_ID = "10"
TITLE = "merge city-wide outputs"

# City-wide GLB is optional. If the merged geometry exceeds the 4 GiB GLB
# binary chunk limit (struct 'I' max = 4,294,967,295 bytes), we record
# city_glb_status: "skipped_oversize" and fall back to per-tile GLBs.
_GLB_SIZE_EXCEPTIONS = (struct.error, OverflowError, ValueError, MemoryError)


def _points_mesh(name: str, xyz: np.ndarray, shift: tuple, color: list) -> dict | None:
    if len(xyz) == 0:
        return None
    sx, sy, sz = shift
    verts = np.column_stack([
        xyz[:, 0] - sx, xyz[:, 2] - sz, -(xyz[:, 1] - sy)
    ]).astype(np.float32)
    faces = np.empty((0, 3), dtype=np.uint32)
    colors = np.tile(np.array(color, dtype=np.float32), (len(verts), 1))
    return {"name": name, "vertices": verts, "faces": faces, "colors": colors, "mode": 0}


def _try_pack_city_glb(
    glb: Path,
    offset_path: Path,
    meshes: list[dict],
    shift: tuple,
    out_epsg: int,
) -> tuple[str, str | None]:
    """
    Attempt to write the city-wide GLB. Returns (status, error_message).

    Possible statuses:
      written            — GLB written successfully
      skipped_no_meshes  — no building/terrain data to pack
      skipped_oversize   — geometry exceeds the GLB 4 GiB binary chunk limit
      failed             — unexpected error
    """
    if not meshes:
        return "skipped_no_meshes", None
    try:
        glb_bytes = pack_glb(meshes)
        glb.parent.mkdir(parents=True, exist_ok=True)
        glb.write_bytes(glb_bytes)
        write_json(offset_path, {
            "crs": f"EPSG:{out_epsg}",
            "shift_x": shift[0],
            "shift_y": shift[1],
            "shift_z": shift[2],
        })
        return "written", None
    except _GLB_SIZE_EXCEPTIONS as exc:
        return "skipped_oversize", str(exc)
    except Exception as exc:
        return "failed", str(exc)


def _aggregate_structures(tiles, epsg: int) -> list[dict]:
    """
    Aggregate per-tile mass metadata GeoJSONs into a single feature list.

    Each feature already carries polygon geometry and height estimates from
    Phase 07. We enrich with footprint_method and footprint_provenance from
    the Phase 06 convex footprint GeoJSON via a cluster_id join.
    """
    features: list[dict] = []
    for tile in tiles:
        meta_gj = tile.tile_dir / "masses" / f"{tile.tile_id}_masses_metadata.geojson"
        if not meta_gj.exists():
            continue

        # Build cluster_id → provenance lookup from Phase 06 footprint GeoJSON.
        fp_provenance: dict[str | int, dict] = {}
        fp_path = tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_convex_{epsg}.geojson"
        if fp_path.exists():
            for fp_feat in read_geojson_features(fp_path):
                props = fp_feat.get("properties") or {}
                cid = props.get("cluster_id")
                if cid is not None:
                    fp_provenance[cid] = {
                        "footprint_method": props.get("footprint_method"),
                        "footprint_provenance": props.get("footprint_provenance"),
                    }

        for feat in read_geojson_features(meta_gj):
            props = dict(feat.get("properties") or {})
            props.setdefault("tile_id", tile.tile_id)
            cid = props.get("cluster_id")
            if cid is not None and cid in fp_provenance:
                props.update(fp_provenance[cid])
            features.append({
                "type": "Feature",
                "geometry": feat.get("geometry"),
                "properties": props,
            })
    return features


def _tile_glb_index(tiles) -> list[dict[str, Any]]:
    """Build a tile-level GLB reference list for the city manifest."""
    index = []
    for tile in tiles:
        glb_path = tile.tile_dir / "blender_ready" / f"{tile.tile_id}.glb"
        offset_path = tile.tile_dir / "blender_ready" / f"{tile.tile_id}_glb_offset.json"
        entry: dict[str, Any] = {
            "tile_id": tile.tile_id,
            "glb_path": str(glb_path) if glb_path.exists() else None,
            "glb_exists": glb_path.exists(),
            "bbox_4326": tile.bbox_4326,
        }
        if offset_path.exists():
            try:
                entry["glb_offset"] = json.loads(offset_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        index.append(entry)
    return index


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    tiles = load_tiles(city, args.limit)

    city_glb = city.output_root / "blender_ready" / f"{city.city_id}.glb"
    offset_path = city.output_root / "blender_ready" / f"{city.city_id}_glb_offset.json"
    epsg = city.out_epsg or 32617
    print(f"  tiles: {len(tiles)}")
    print(f"  city GLB target: {city_glb} (optional — skipped if oversize)")

    if not require_execute(args):
        print(f"  would merge {len(tiles)} tile(s) and write city manifest")
        return 0

    # ── Optional city-wide GLB ────────────────────────────────────────────────

    obj_paths = [
        t.tile_dir / "masses" / f"{t.tile_id}_LOD0_convexhull.obj"
        for t in tiles
        if (t.tile_dir / "masses" / f"{t.tile_id}_LOD0_convexhull.obj").exists()
    ]
    shift = mesh_shift_from_vertices(obj_paths)
    meshes: list[dict] = []

    all_verts, all_faces, all_normals = [], [], []
    vbase = 0
    for path in obj_paths:
        verts, faces, normals = obj_to_flat_triangles(path, shift)
        if len(verts):
            all_verts.append(verts)
            all_faces.append(faces + vbase)
            all_normals.append(normals)
            vbase += len(verts)
    if all_verts:
        meshes.append({
            "name": "buildings",
            "vertices": np.concatenate(all_verts),
            "faces": np.concatenate(all_faces),
            "normals": np.concatenate(all_normals),
        })

    terrain_chunks, vegetation_chunks = [], []
    for tile in tiles:
        ground = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_ground_1m.ply"
        veg = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_vegetation_1m.ply"
        if ground.exists():
            terrain_chunks.append(read_ply_xyz(ground))
        if veg.exists():
            vegetation_chunks.append(read_ply_xyz(veg))
    if terrain_chunks:
        t_mesh = _points_mesh("terrain", np.concatenate(terrain_chunks), shift, [0.55, 0.50, 0.42, 1.0])
        if t_mesh:
            meshes.append(t_mesh)
    if vegetation_chunks:
        v_mesh = _points_mesh("vegetation", np.concatenate(vegetation_chunks), shift, [0.0, 0.65, 0.18, 1.0])
        if v_mesh:
            meshes.append(v_mesh)

    city_glb_status, city_glb_error = _try_pack_city_glb(
        city_glb, offset_path, meshes, shift, epsg
    )
    viewer_load_strategy = "city_glb" if city_glb_status == "written" else "tile_glbs"
    if city_glb_status == "written":
        print(f"  city GLB written: {city_glb}")
    else:
        msg = f"  city GLB skipped: {city_glb_status}"
        if city_glb_error:
            msg += f" ({city_glb_error[:120]})"
        print(msg)

    # ── structures_enriched.geojson ───────────────────────────────────────────

    features = _aggregate_structures(tiles, epsg)
    city.metadata_dir.mkdir(parents=True, exist_ok=True)
    city.structures_enriched.write_text(
        json.dumps({
            "type": "FeatureCollection",
            "name": f"{city.city_id}_structures_enriched",
            "crs": crs_tag(city),
            "features": features,
        }),
        encoding="utf-8",
    )
    print(f"  structures_enriched: {len(features)} building(s) → {city.structures_enriched}")

    # ── Tile GLB index ────────────────────────────────────────────────────────

    tile_index = _tile_glb_index(tiles)
    tile_glb_count = sum(1 for t in tile_index if t["glb_exists"])
    print(f"  per-tile GLBs: {tile_glb_count} / {len(tiles)}")

    # ── City manifest ─────────────────────────────────────────────────────────

    warnings: list[str] = []
    if city_glb_status != "written":
        warnings.append(
            f"City-wide GLB not written ({city_glb_status}). "
            f"Viewer should load {tile_glb_count} per-tile GLBs."
        )
    addr_source = city.address_source or {}
    addr_path = str(addr_source.get("path", "not_configured"))

    city_manifest: dict[str, Any] = {
        "schema_version": "1.1",
        "pipeline": "GlitchOS city pipeline",
        "city_id": city.city_id,
        "display_name": city.display_name,
        "CRS": f"EPSG:{epsg}",
        "bounds_4326": city.bbox_4326,
        "generated_at": utc_now(),
        "preserve_raw_laz": city.preserve_raw_laz,
        "package_status": "complete",
        "totals": {
            "tiles_attempted": len(tiles),
            "tiles_with_glb": tile_glb_count,
            "buildings_lod0": len(features),
        },
        "city_glb_status": city_glb_status,
        "city_glb_required": False,
        "viewer_load_strategy": viewer_load_strategy,
        "assets": {
            "structures_enriched": str(city.structures_enriched),
            "tiles_root": str(city.tiles_root),
        },
        "city_assets": (
            {"city_glb": str(city_glb), "city_glb_offset": str(offset_path)}
            if city_glb_status == "written" else {}
        ),
        "address_enrichment": {
            "required": city.require_addresses,
            "source": addr_path,
            "status": "not_run",
            "note": "Run address enrichment phase separately if address data is available.",
        },
        "tiles": {t["tile_id"]: {k: v for k, v in t.items() if k != "tile_id"} for t in tile_index},
        "warnings": warnings,
    }
    if city_glb_error:
        city_manifest["city_glb_error"] = city_glb_error[:256]

    city.city_manifest.write_text(
        json.dumps(city_manifest, indent=2),
        encoding="utf-8",
    )
    print(f"  city manifest: {city.city_manifest}")

    outputs = [city.structures_enriched, city.city_manifest]
    if city_glb_status == "written":
        outputs.extend([city_glb, offset_path])

    details: dict[str, Any] = {
        "tiles": len(tiles),
        "obj_files": len(obj_paths),
        "buildings_lod0": len(features),
        "tile_glbs": tile_glb_count,
        "city_glb_status": city_glb_status,
        "viewer_load_strategy": viewer_load_strategy,
        "warnings": warnings,
    }
    return output_summary(city, PHASE_ID, "complete", details, outputs)


if __name__ == "__main__":
    sys.exit(main())
