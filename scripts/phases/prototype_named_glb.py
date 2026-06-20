#!/usr/bin/env python3
"""
Prototype: per-building named-node GLB export for a single tile.

Reads the LOD0 OBJ (produced by phase_07) and re-exports it as a GLB where
each building `o bld_...` group becomes its own named glTF mesh+node.

Outputs (all in the prototype artifact directory):
  {out_dir}/viewer_manifest.json  — §18.3-compliant single-tile manifest
  {out_dir}/building_metadata.json — array of §18.4-compliant records

Also writes the GLB to:
  {tiles_root}/{tile_id}/blender_ready/prototypes/{tile_id}_named_clean.glb

The canonical blender_ready/{tile_id}.glb is NEVER touched.

Usage (from scripts/phases/):
    python prototype_named_glb.py \\
        --tile-id USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901 \\
        --tiles-root /mnt/e/miami/data_processed/miami_city/tiles \\
        --out-dir /mnt/e/miami/data_processed/prototypes/318455_0901 \\
        --glb-viewer-url /models/local_prototype.glb \\
        --metadata-viewer-url /metadata/local_prototype.json \\
        --enriched /mnt/e/miami/data_processed/miami_city/metadata/structures_enriched.geojson
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from phase_tile_common import pack_glb, polygon_normal


# ── OBJ parsing ───────────────────────────────────────────────────────────────

def parse_obj_per_object(
    path: Path,
) -> list[tuple[str, np.ndarray, list[list[int]]]]:
    """Parse OBJ preserving per-`o`-group boundaries.

    Returns list of (name, global_vert_subset, face_index_lists) where
    face indices are 0-based and local to this object's vertex subset.
    """
    global_verts: list[tuple[float, float, float]] = []
    objects: list[tuple[str, list[list[int]]]] = []
    cur_name: str | None = None
    cur_faces: list[list[int]] = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            p = line.split()
            global_verts.append((float(p[1]), float(p[2]), float(p[3])))
        elif line.startswith("o "):
            if cur_name is not None:
                objects.append((cur_name, cur_faces))
            cur_name = line.split(None, 1)[1].strip()
            cur_faces = []
        elif line.startswith("f "):
            idxs = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            if len(idxs) >= 3 and cur_name is not None:
                cur_faces.append(idxs)

    if cur_name is not None:
        objects.append((cur_name, cur_faces))

    gv = np.array(global_verts, dtype=np.float64) if global_verts else np.empty((0, 3))

    result: list[tuple[str, np.ndarray, list[list[int]]]] = []
    for name, faces in objects:
        used = sorted({idx for face in faces for idx in face})
        if not used or not faces:
            continue
        remap = {old: new for new, old in enumerate(used)}
        local_verts = gv[used]
        local_faces = [[remap[i] for i in face] for face in faces]
        result.append((name, local_verts, local_faces))

    return result


def compute_shift(objects: list[tuple[str, np.ndarray, list[list[int]]]]) -> tuple[float, float, float]:
    all_mins = [verts.min(axis=0) for _, verts, _ in objects if len(verts)]
    if not all_mins:
        return (0.0, 0.0, 0.0)
    mn = np.vstack(all_mins).min(axis=0)
    return (float(mn[0]), float(mn[1]), float(mn[2]))


# ── Per-building GLB geometry ─────────────────────────────────────────────────

def triangulate_object(
    name: str,
    local_verts: np.ndarray,
    local_faces: list[list[int]],
    shift: tuple[float, float, float],
) -> dict:
    """Convert one OBJ object to a pack_glb-compatible mesh dict (Y-up, shifted).

    Returns {} if the mesh produces no triangles.
    """
    sx, sy, sz = shift
    out_verts: list[tuple[float, float, float]] = []
    out_norms: list[np.ndarray] = []
    out_faces: list[tuple[int, int, int]] = []

    for face in local_faces:
        poly = local_verts[face].astype(np.float64)
        poly_shifted = np.column_stack([
            poly[:, 0] - sx,
            poly[:, 2] - sz,
            -(poly[:, 1] - sy),
        ]).astype(np.float32)

        nrm = polygon_normal(poly_shifted)

        for i in range(1, len(poly_shifted) - 1):
            tri: list[int] = []
            for p in (poly_shifted[0], poly_shifted[i], poly_shifted[i + 1]):
                tri.append(len(out_verts))
                out_verts.append(tuple(float(v) for v in p))
                out_norms.append(nrm)
            out_faces.append((tri[0], tri[1], tri[2]))

    if not out_verts:
        return {}

    return {
        "name": name,
        "vertices": np.array(out_verts, dtype=np.float32),
        "faces": np.array(out_faces, dtype=np.uint32),
        "normals": np.array(out_norms, dtype=np.float32),
    }


# ── GLB post-parse: extract per-building bbox from POSITION accessors ─────────

def extract_glb_building_bounds(
    glb_path: Path,
) -> dict[str, dict[str, list[float]]]:
    """Parse the GLB JSON chunk and return per-node bbox and centroid.

    Returns {node_name: {min: [x,y,z], max: [x,y,z], centroid: [x,y,z]}}.
    """
    data = glb_path.read_bytes()
    json_len, _ = struct.unpack_from("<II", data, 12)
    gltf = json.loads(data[20 : 20 + json_len])

    meshes = gltf.get("meshes", [])
    nodes  = gltf.get("nodes", [])
    accs   = gltf.get("accessors", [])

    out: dict[str, dict[str, list[float]]] = {}
    for node in nodes:
        name = node.get("name", "")
        mesh_idx = node.get("mesh")
        if mesh_idx is None or not name:
            continue
        mesh = meshes[mesh_idx]
        prims = mesh.get("primitives", [])
        if not prims:
            continue
        pos_acc_idx = prims[0]["attributes"].get("POSITION")
        if pos_acc_idx is None:
            continue
        acc = accs[pos_acc_idx]
        mn = acc.get("min", [0.0, 0.0, 0.0])
        mx = acc.get("max", [0.0, 0.0, 0.0])
        centroid = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
        out[name] = {"min": mn, "max": mx, "centroid": centroid}

    return out


# ── Enrichment join ───────────────────────────────────────────────────────────

def load_enriched_by_cluster(
    enriched_path: Path | None,
    tile_id: str,
) -> dict[int, dict]:
    """Load structures_enriched.geojson filtered to tile_id, keyed by cluster_id."""
    if not enriched_path or not enriched_path.exists():
        return {}
    try:
        data = json.loads(enriched_path.read_bytes())
    except Exception:
        return {}
    result: dict[int, dict] = {}
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        if props.get("tile_id") != tile_id:
            continue
        cid = props.get("cluster_id")
        if cid is None:
            continue
        result[int(cid)] = props
    return result


def cluster_id_from_name(name: str) -> int | None:
    """Extract integer cluster_id from node name `bld_{tile_id}_{cluster_id}`."""
    try:
        return int(name.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return None


# ── §18.4-compliant metadata record assembly ──────────────────────────────────

def build_metadata_record(
    name: str,
    tile_id: str,
    bounds: dict[str, list[float]],
    enriched: dict[int, dict],
) -> dict:
    """Build one §18.4-compliant record.

    Centroid and bbox come from the GLB accessor bounds (authoritative geometry).
    Semantic fields (address, height_m, footprint_area_m2) come from
    structures_enriched.geojson when a cluster_id match exists.
    Unmatched fields are absent (not substituted with fallbacks).
    """
    cid = cluster_id_from_name(name)
    enriched_props = enriched.get(cid, {}) if cid is not None else {}

    # Required geometry fields from GLB bounds
    centroid = bounds["centroid"]
    bbox_min = bounds["min"]
    bbox_max = bounds["max"]

    record: dict = {
        "building_id": name,
        "tile_id": tile_id,
        "centroid": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
        "bbox": {
            "min": bbox_min,
            "max": bbox_max,
        },
        "source": {
            "lidar_tile": tile_id,
            "footprint_id": str(cid) if cid is not None else None,
            "address_id": None,
        },
    }

    # Optional semantic fields — only included when data exists
    if enriched_props:
        addr = enriched_props.get("full_address")
        if addr:
            record["address"] = addr
        h = enriched_props.get("estimated_height")
        if h is not None:
            try:
                record["height_m"] = float(h)
            except (TypeError, ValueError):
                pass
        area = enriched_props.get("footprint_area_m2")
        if area is not None:
            try:
                record["footprint_area_m2"] = float(area)
            except (TypeError, ValueError):
                pass

    return record


# ── §18.3-compliant viewer manifest ──────────────────────────────────────────

def build_viewer_manifest(
    tile_id: str,
    shift: tuple[float, float, float],
    scene_bbox_min: list[float],
    scene_bbox_max: list[float],
    building_count: int,
    glb_viewer_url: str,
    metadata_viewer_url: str,
    crs: str,
    provenance_lidar: str | None = None,
    provenance_footprints: str | None = None,
    provenance_addresses: str | None = None,
) -> dict:
    """Build a §18.3-compliant single-tile prototype viewer manifest.

    city_id uses a safe identifier for the prototype artifact — no uppercase,
    no hyphens, no special chars, matching ^[a-z0-9_]+$.

    The label clearly identifies this as a non-canonical prototype artifact.
    Origin is the CRS coordinates of the GLB local origin (tile min vertex).
    """
    safe_city_id = "prototype_" + tile_id.lower().replace("-", "_").replace(".", "_")
    if len(safe_city_id) > 64:
        safe_city_id = "prototype_tile_" + tile_id[-20:].lower().replace("-", "_")

    origin_x, origin_y_north, origin_z_elev = shift

    tile_entry: dict = {
        "tile_id": tile_id,
        "label": f"[PROTOTYPE] {tile_id} — {building_count} selectable named buildings",
        "glb_url": glb_viewer_url,
        "metadata_url": metadata_viewer_url,
        "bbox": {
            "min": scene_bbox_min,
            "max": scene_bbox_max,
        },
        "building_count": building_count,
        "selectable": True,
    }
    prov: dict = {}
    if provenance_lidar:
        prov["lidar"] = provenance_lidar
    if provenance_footprints:
        prov["footprints"] = provenance_footprints
    if provenance_addresses:
        prov["addresses"] = provenance_addresses
    if prov:
        tile_entry["provenance"] = prov

    return {
        "schema_version": "glytchos.viewer_manifest.v1",
        "city_id": safe_city_id,
        "city_name": f"[PROTOTYPE] {tile_id} — named-node export, not canonical T7",
        "crs": crs,
        "units": "meters",
        "origin": {
            "x": float(origin_x),
            "y": float(origin_y_north),
            "z": float(origin_z_elev),
        },
        "reveal_radius_m": 3000.0,
        "tiles": [tile_entry],
    }


# ── Schema validation ─────────────────────────────────────────────────────────

def _load_schema(name: str) -> dict | None:
    schema_path = Path(__file__).parent.parent.parent / "schemas" / f"{name}.schema.json"
    if schema_path.exists():
        try:
            return json.loads(schema_path.read_text())
        except Exception:
            pass
    return None


def validate_against_schema(instance: dict | list, schema_name: str) -> list[str]:
    """Validate instance against schema using jsonschema if available."""
    schema = _load_schema(schema_name)
    if schema is None:
        return [f"schema {schema_name}.schema.json not found — skipping validation"]
    try:
        import jsonschema  # type: ignore
        errors: list[str] = []
        # For a list of records, validate each item against the schema
        if isinstance(instance, list):
            for i, item in enumerate(instance):
                for err in jsonschema.Draft7Validator(schema).iter_errors(item):
                    errors.append(f"record[{i}]: {err.message}")
        else:
            for err in jsonschema.Draft7Validator(schema).iter_errors(instance):
                errors.append(err.message)
        return errors
    except ImportError:
        return ["jsonschema not installed — skipping schema validation"]
    except Exception as e:
        return [f"validation error: {e}"]


# ── Machine-absolute path guard ───────────────────────────────────────────────

def _is_machine_absolute(url: str) -> bool:
    """Return True if url begins with a machine-local filesystem prefix."""
    if any(url.startswith(p) for p in ("/mnt/", "/home/", "/Users/")):
        return True
    # Windows drive letter paths: X:\ or X:/ for any letter A-Z
    return len(url) >= 3 and url[1] == ":" and url[2] in ("\\", "/")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a spec-compliant prototype artifact bundle for a single tile"
    )
    parser.add_argument("--tile-id", required=True)
    parser.add_argument("--tiles-root", required=True, help="Directory containing per-tile subdirs")
    parser.add_argument("--out-dir", required=True, help="Output directory for prototype manifest + metadata")
    parser.add_argument("--glb-viewer-url", default="/models/local_prototype.glb",
                        help="Portable viewer URL for the named-node GLB (no machine path)")
    parser.add_argument("--metadata-viewer-url", default="/metadata/local_prototype.json",
                        help="Portable viewer URL for the metadata JSON (no machine path)")
    parser.add_argument("--enriched", default=None,
                        help="Path to structures_enriched.geojson for semantic enrichment")
    parser.add_argument("--force", action="store_true", help="Overwrite existing GLB")
    parser.add_argument("--crs", required=True,
                        help="CRS of the source geometry (e.g. EPSG:32617 for Miami, EPSG:32615 for NOLA)")
    parser.add_argument("--provenance-lidar", default=None,
                        help="LiDAR source label for the viewer manifest provenance block")
    parser.add_argument("--provenance-footprints", default=None,
                        help="Footprint source label for the viewer manifest provenance block")
    parser.add_argument("--provenance-addresses", default=None,
                        help="Address source label for the viewer manifest provenance block")
    args = parser.parse_args(argv)

    for _flag, _url in (("--glb-viewer-url", args.glb_viewer_url), ("--metadata-viewer-url", args.metadata_viewer_url)):
        if _is_machine_absolute(_url):
            print(f"ERROR: {_flag} is a machine-absolute path: {_url!r}")
            print("       Pass a portable viewer URL (e.g. /models/tile.glb).")
            return 1

    tile_id   = args.tile_id
    tile_dir  = Path(args.tiles_root) / tile_id
    out_dir   = Path(args.out_dir)
    src_obj   = tile_dir / "masses" / f"{tile_id}_LOD0_convexhull.obj"
    proto_dir = tile_dir / "blender_ready" / "prototypes"
    out_glb   = proto_dir / f"{tile_id}_named_clean.glb"
    canonical = tile_dir / "blender_ready" / f"{tile_id}.glb"
    enriched_path = Path(args.enriched) if args.enriched else None

    print(f"tile:         {tile_id}")
    print(f"source OBJ:   {src_obj}")
    print(f"prototype GLB:{out_glb}")
    print(f"canonical:    {canonical} (will NOT be touched)")
    print(f"output dir:   {out_dir}")
    print(f"glb URL:      {args.glb_viewer_url}")
    print(f"meta URL:     {args.metadata_viewer_url}")

    if not src_obj.exists():
        print(f"ERROR: source OBJ not found: {src_obj}")
        return 1

    # ── Step 1: Parse OBJ ────────────────────────────────────────────────────
    print("\n[1] Parsing OBJ per-object groups...")
    objects = parse_obj_per_object(src_obj)
    print(f"    {len(objects)} building objects")

    shift = compute_shift(objects)
    print(f"    shift: ({shift[0]:.3f}, {shift[1]:.3f}, {shift[2]:.3f})")

    # ── Step 2: Generate named-node GLB (skip if exists and --force not set) ─
    print("\n[2] Generating named-node GLB...")
    if out_glb.exists() and not args.force:
        print(f"    exists — skipping (use --force to regenerate)")
    else:
        proto_dir.mkdir(parents=True, exist_ok=True)
        meshes = []
        empty_count = 0
        for name, local_verts, local_faces in objects:
            m = triangulate_object(name, local_verts, local_faces, shift)
            if m:
                meshes.append(m)
            else:
                empty_count += 1

        if not meshes:
            print("ERROR: no meshes produced")
            return 1

        glb_bytes = pack_glb(meshes)
        out_glb.write_bytes(glb_bytes)
        print(f"    wrote {len(meshes)} meshes, {empty_count} skipped → {out_glb} ({len(glb_bytes):,} bytes)")

        if canonical.exists() and glb_bytes == canonical.read_bytes():
            print("ERROR: prototype identical to canonical — something is wrong")
            return 1

    # ── Step 3: Extract per-building bbox from GLB POSITION accessors ────────
    print("\n[3] Extracting per-building bounds from GLB...")
    building_bounds = extract_glb_building_bounds(out_glb)
    print(f"    {len(building_bounds)} buildings with bounds")

    # Compute scene-level bbox (union of all accessor bounds)
    all_mins = np.array([b["min"] for b in building_bounds.values()])
    all_maxs = np.array([b["max"] for b in building_bounds.values()])
    scene_min = all_mins.min(axis=0).tolist()
    scene_max = all_maxs.max(axis=0).tolist()
    print(f"    scene bbox: min={[round(v,1) for v in scene_min]} max={[round(v,1) for v in scene_max]}")

    # ── Step 4: Load enrichment ───────────────────────────────────────────────
    print("\n[4] Loading enrichment from structures_enriched.geojson...")
    enriched = load_enriched_by_cluster(enriched_path, tile_id)
    print(f"    {len(enriched)} enriched features for this tile")

    # ── Step 5: Build §18.4-compliant metadata records ────────────────────────
    print("\n[5] Building metadata records...")
    records: list[dict] = []
    matched = unmatched = missing_enriched = 0

    for name in building_bounds:
        cid = cluster_id_from_name(name)
        if cid is not None and cid in enriched:
            matched += 1
        elif cid is not None:
            missing_enriched += 1
        else:
            unmatched += 1

        rec = build_metadata_record(name, tile_id, building_bounds[name], enriched)
        records.append(rec)

    print(f"    {len(records)} records total")
    print(f"    enrichment: {matched} matched, {missing_enriched} cluster_id not in enriched, {unmatched} no cluster_id")

    # Validate metadata records against schema
    print("\n[5a] Validating metadata records against building_metadata.schema.json...")
    meta_errors = validate_against_schema(records, "building_metadata")
    if meta_errors:
        for e in meta_errors[:10]:
            print(f"    SCHEMA ERROR: {e}")
        if len(meta_errors) > 10:
            print(f"    ... {len(meta_errors) - 10} more errors")
    else:
        print(f"    schema validation PASSED ({len(records)} records)")

    # ── Step 6: Build §18.3-compliant viewer manifest ─────────────────────────
    print("\n[6] Building viewer manifest...")
    manifest = build_viewer_manifest(
        tile_id=tile_id,
        shift=shift,
        scene_bbox_min=scene_min,
        scene_bbox_max=scene_max,
        building_count=len(records),
        glb_viewer_url=args.glb_viewer_url,
        metadata_viewer_url=args.metadata_viewer_url,
        crs=args.crs,
        provenance_lidar=args.provenance_lidar,
        provenance_footprints=args.provenance_footprints,
        provenance_addresses=args.provenance_addresses,
    )

    print(f"    city_id: {manifest['city_id']}")
    print(f"    origin: {manifest['origin']}")
    print(f"    tiles: {len(manifest['tiles'])}, selectable: {manifest['tiles'][0]['selectable']}")

    # Validate manifest against schema
    print("\n[6a] Validating manifest against viewer_manifest.schema.json...")
    manifest_errors = validate_against_schema(manifest, "viewer_manifest")
    if manifest_errors:
        for e in manifest_errors:
            print(f"    SCHEMA ERROR: {e}")
    else:
        print("    schema validation PASSED")

    # ── Step 7: Write outputs ─────────────────────────────────────────────────
    print("\n[7] Writing prototype artifact bundle...")
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_path = out_dir / "building_metadata.json"
    meta_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"    metadata → {meta_path} ({len(records)} records, {meta_path.stat().st_size:,} bytes)")

    manifest_path = out_dir / "viewer_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"    manifest → {manifest_path} ({manifest_path.stat().st_size:,} bytes)")

    # ── Step 8: Cross-validate node names ↔ metadata building_ids ────────────
    print("\n[8] Cross-validating GLB node names ↔ metadata building_ids...")
    meta_ids   = {r["building_id"] for r in records}
    glb_names  = set(building_bounds.keys())
    only_meta  = meta_ids - glb_names
    only_glb   = glb_names - meta_ids
    both       = meta_ids & glb_names
    print(f"    in both:        {len(both)}")
    print(f"    only in meta:   {len(only_meta)} (no GLB node — should be 0)")
    print(f"    only in GLB:    {len(only_glb)} (no metadata — should be 0)")
    if only_meta or only_glb:
        print("    WARNING: mismatch detected")
        for n in sorted(only_meta)[:3]:
            print(f"      meta-only: {n}")
        for n in sorted(only_glb)[:3]:
            print(f"      glb-only:  {n}")
    else:
        print("    cross-validation PASSED — 1:1 correspondence")

    # ── Step 9: Check no machine-absolute paths in manifest URLs ─────────────
    print("\n[9] Checking manifest for machine-absolute paths...")
    manifest_text = manifest_path.read_text()
    if re.search(r'/mnt/|/home/|/Users/|[A-Za-z]:[/\\]', manifest_text):
        print("    WARNING: machine-absolute paths found in manifest")
    else:
        print("    PASSED — no machine-absolute paths in manifest")

    print("\n=== DONE ===")
    print(f"  GLB:      {out_glb}")
    print(f"  Metadata: {meta_path}")
    print(f"  Manifest: {manifest_path}")
    if meta_errors or manifest_errors:
        print("  SCHEMA ERRORS PRESENT — review before using in viewer")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
