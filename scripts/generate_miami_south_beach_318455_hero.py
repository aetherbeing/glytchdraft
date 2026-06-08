"""
generate_miami_south_beach_318455_hero.py

Generate a per-building South Beach / Ocean Drive hero tile GLB + metadata
from tile USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.

Source geometry: per-building named objects in LOD0_convexhull.obj
    Object names: bld_USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901_<cluster_id>
    Node names in output GLB: sb_318455_<cluster_id>

Coordinate transform
--------------------
    OBJ coords are absolute EPSG:32617 (metres).
    glb_offset.json gives the per-tile shift from absolute to local scene space:
        local_x = abs_x - shift_x
        local_y = abs_y - shift_y
        local_z = abs_z - shift_z
    Z-up OBJ → Y-up glTF:
        gltf_X =  local_x
        gltf_Y =  local_z   (OBJ Z becomes glTF Y)
        gltf_Z = -local_y   (OBJ -Y becomes glTF Z)

Address join
------------
    centroid_x / centroid_y in masses_metadata.csv are absolute EPSG:32617.
    KDTree nearest-neighbour to address_points.geojson (same CRS).
    Radius: JOIN_RADIUS_M = 30 m.

Outputs
-------
    exports/miami_south_beach_318455_hero/
        miami_south_beach_318455_hero.glb
        miami_south_beach_318455_hero_metadata.json
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

import ijson
import numpy as np
from scipy.spatial import cKDTree

# -- import pack_glb and polygon_normal from the shared phase utilities
_PHASES = Path(__file__).resolve().parents[1] / "scripts" / "phases"
sys.path.insert(0, str(_PHASES))
from phase_tile_common import pack_glb, polygon_normal  # noqa: E402

# ── Paths ──────────────────────────────────────────────────────────────────────

TILE_ID   = "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901"
ROOT      = Path(__file__).resolve().parents[1]
TILE_BASE = Path("/mnt/e/miami/data_processed/miami_city/tiles") / TILE_ID

OBJ_PATH    = TILE_BASE / "masses" / f"{TILE_ID}_LOD0_convexhull.obj"
CSV_PATH    = TILE_BASE / "masses" / f"{TILE_ID}_masses_metadata.csv"
OFFSET_PATH = TILE_BASE / "blender_ready" / f"{TILE_ID}_glb_offset.json"
ADDR_PATH   = Path("/mnt/e/miami/data_processed/miami_city/metadata/address_points.geojson")

OUT_DIR  = ROOT / "exports/miami_south_beach_318455_hero"
OUT_GLB  = OUT_DIR / "miami_south_beach_318455_hero.glb"
OUT_META = OUT_DIR / "miami_south_beach_318455_hero_metadata.json"

NODE_PREFIX    = "sb_318455"
JOIN_RADIUS_M  = 30.0
ADDR_BUFFER_M  = 300.0


# ── OBJ parsing ────────────────────────────────────────────────────────────────

def parse_obj_per_building(
    path: Path,
) -> tuple[np.ndarray, dict[int, list[list[int]]]]:
    """
    Parse OBJ with named per-building objects.
    Returns (global_verts [N,3] float64, {cluster_id: [[vi,vj,vk,...], ...]}).
    Object name format: bld_..._<cluster_id>
    """
    global_verts: list[tuple[float, float, float]] = []
    buildings: dict[int, list[list[int]]] = {}
    current_id: int | None = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                global_verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("o "):
                name = line.split()[1].strip()
                suffix = name.rsplit("_", 1)[-1]
                try:
                    current_id = int(suffix)
                    buildings[current_id] = []
                except ValueError:
                    current_id = None
            elif line.startswith("f ") and current_id is not None:
                idxs = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
                if len(idxs) >= 3:
                    buildings[current_id].append(idxs)

    return np.array(global_verts, dtype=np.float64), buildings


# ── Per-building geometry ──────────────────────────────────────────────────────

def build_building_mesh(
    global_verts: np.ndarray,
    face_lists: list[list[int]],
    shift_x: float,
    shift_y: float,
    shift_z: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract one building's geometry from the global vertex array, apply
    coordinate shift + Z-up→Y-up transform, return triangulated mesh arrays.
    Matches the same transform used in phase_tile_common.obj_to_flat_triangles.
    """
    verts_out: list[tuple[float, float, float]] = []
    norms_out: list[np.ndarray] = []
    faces_out: list[tuple[int, int, int]] = []

    for face in face_lists:
        poly_abs = global_verts[face]  # (N, 3) absolute EPSG:32617
        poly_local = np.column_stack([
            poly_abs[:, 0] - shift_x,   # gltf X
            poly_abs[:, 2] - shift_z,   # gltf Y  (OBJ Z)
            -(poly_abs[:, 1] - shift_y), # gltf Z  (-OBJ Y)
        ]).astype(np.float32)

        nrm = polygon_normal(poly_local)

        # Fan triangulation — duplicate vertices per triangle so each
        # face gets a flat normal with no shared-vertex lighting seam.
        for i in range(1, len(poly_local) - 1):
            tri: list[int] = []
            for p in (poly_local[0], poly_local[i], poly_local[i + 1]):
                tri.append(len(verts_out))
                verts_out.append(tuple(float(v) for v in p))
                norms_out.append(nrm)
            faces_out.append((tri[0], tri[1], tri[2]))

    if not verts_out:
        return (
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, 3), dtype=np.uint32),
            np.empty((0, 3), dtype=np.float32),
        )
    return (
        np.array(verts_out, dtype=np.float32),
        np.array(faces_out, dtype=np.uint32),
        np.array(norms_out, dtype=np.float32),
    )


# ── Metadata loading ───────────────────────────────────────────────────────────

def load_csv_metadata(path: Path) -> dict[int, dict]:
    """Load masses_metadata.csv → {cluster_id: row_dict}."""
    rows: dict[int, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                cid = int(row["cluster_id"])
                rows[cid] = row
            except (KeyError, ValueError):
                pass
    return rows


# ── Address enrichment ─────────────────────────────────────────────────────────

def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_addr(props: dict) -> dict:
    full = props.get("full_address") or ""
    parts = [p.strip() for p in full.split(",")]
    return {
        "x":            float(props["x"]),
        "y":            float(props["y"]),
        "full_address": full or None,
        "city":         parts[1] if len(parts) >= 2 else None,
        "zip":          parts[2].strip() if len(parts) >= 3 else None,
        "source":       props.get("source"),
        "lat":          _to_float(props.get("lat")),
        "lon":          _to_float(props.get("lon")),
    }


def stream_addresses(path: Path, min_x: float, max_x: float, min_y: float, max_y: float) -> list[dict]:
    """Stream address_points.geojson filtered to tile bbox + buffer."""
    addrs: list[dict] = []
    bmin_x = min_x - ADDR_BUFFER_M
    bmax_x = max_x + ADDR_BUFFER_M
    bmin_y = min_y - ADDR_BUFFER_M
    bmax_y = max_y + ADDR_BUFFER_M
    with open(path, "rb") as f:
        for feat in ijson.items(f, "features.item"):
            p = feat.get("properties") or {}
            x, y = p.get("x"), p.get("y")
            if x is None or y is None:
                continue
            fx, fy = float(x), float(y)
            if bmin_x <= fx <= bmax_x and bmin_y <= fy <= bmax_y:
                try:
                    addrs.append(_parse_addr(p))
                except (KeyError, TypeError, ValueError):
                    pass
    return addrs


def join_addresses(buildings: list[dict], addrs: list[dict]) -> list[dict]:
    """Nearest-neighbour address join. Uses centroid_x/y (absolute EPSG:32617)."""
    addr_xy = np.array([[a["x"], a["y"]] for a in addrs], dtype=np.float64)
    tree    = cKDTree(addr_xy)

    bld_xy = np.array(
        [[float(b["centroid_x"]), float(b["centroid_y"])] for b in buildings],
        dtype=np.float64,
    )
    dists, idxs = tree.query(bld_xy, k=1, distance_upper_bound=JOIN_RADIUS_M)

    enriched: list[dict] = []
    for i, b in enumerate(buildings):
        dist = float(dists[i])
        idx  = int(idxs[i])
        rec  = dict(b)
        if dist <= JOIN_RADIUS_M and idx < len(addrs):
            ap = addrs[idx]
            rec["address"]            = ap["full_address"]
            rec["address_full"]       = ap["full_address"]
            rec["address_distance_m"] = round(dist, 2)
            rec["address_source"]     = ap["source"]
            rec["address_city"]       = ap["city"]
            rec["address_zip"]        = ap["zip"]
        else:
            rec["address"]            = None
            rec["address_full"]       = None
            rec["address_distance_m"] = None
            rec["address_source"]     = None
            rec["address_city"]       = None
            rec["address_zip"]        = None
        enriched.append(rec)
    return enriched


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(
    meta_records: list[dict],
    glb_path: Path,
    meta_path: Path,
    glb_node_names: set[str],
) -> None:
    total = len(meta_records)
    matched = [r for r in meta_records if r["address"]]
    coverage_pct = 100.0 * len(matched) / total if total else 0.0

    heights = sorted(
        [float(r["estimated_height"]) for r in meta_records if r.get("estimated_height")],
        reverse=True,
    )
    n = len(heights)

    meta_mesh_names = {r["mesh_name"] for r in meta_records}
    node_no_meta = glb_node_names - meta_mesh_names
    meta_no_node = meta_mesh_names - glb_node_names

    print("\n" + "=" * 60)
    print("ARTIFACT REPORT — miami_south_beach_318455_hero")
    print("=" * 60)
    print(f"\nGLB path      : {glb_path}")
    print(f"GLB size      : {glb_path.stat().st_size / 1e6:.2f} MB")
    print(f"Metadata path : {meta_path}")
    print(f"Metadata size : {meta_path.stat().st_size / 1e6:.2f} MB")
    print(f"\nBuilding count         : {total}")
    print(f"GLB nodes              : {len(glb_node_names)}")
    print(f"Addresses joined       : {len(matched)} / {total}  ({coverage_pct:.1f}%)")

    if heights:
        print(f"\nHeight profile:")
        print(f"  max={heights[0]:.1f}m   p50={heights[n // 2]:.1f}m   min={heights[-1]:.1f}m")
        print(f"  > 40m: {sum(1 for h in heights if h > 40)}")
        print(f"  > 20m: {sum(1 for h in heights if h > 20)}")
        print(f"  > 10m: {sum(1 for h in heights if h > 10)}")

    q_count = Counter(r.get("source_quality", "?") for r in meta_records)
    print(f"\nSource quality         : {dict(q_count)}")

    print(f"\nNode ↔ metadata check:")
    print(f"  GLB nodes with no metadata : {len(node_no_meta)}")
    print(f"  Metadata with no GLB node  : {len(meta_no_node)}")
    if node_no_meta:
        print(f"  (sample nodes missing meta : {sorted(node_no_meta)[:5]})")
    if meta_no_node:
        print(f"  (sample meta missing nodes : {sorted(meta_no_node)[:5]})")

    print(f"\n10 sample addresses:")
    for r in matched[:10]:
        h = r.get("estimated_height")
        h_s = f"{float(h):.1f}m" if h else "  ?m"
        d_s = f"{float(r['address_distance_m']):.1f}m" if r.get("address_distance_m") else " ?m"
        print(f"  {r['mesh_name']:<22}  h={h_s:>7}  dist={d_s:>6}  {r['address']!r}")

    print(f"\nReady to copy into glytchOS as hidden candidate:")
    ready = (
        len(node_no_meta) == 0
        and len(meta_no_node) <= 3       # up to 3 degenerate buildings OK
        and coverage_pct >= 80.0
    )
    print(f"  {'YES' if ready else 'NOT YET — see mismatches above'}")
    print("=" * 60)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=== Miami South Beach 318455 hero tile generator ===\n")

    # Validate inputs
    for label, path in [("OBJ", OBJ_PATH), ("CSV", CSV_PATH), ("offset", OFFSET_PATH), ("addresses", ADDR_PATH)]:
        if not path.exists():
            print(f"ERROR: {label} not found: {path}")
            return 1
        print(f"  {label:10}: {path}  ({path.stat().st_size / 1e3:.1f} KB)")

    # Load coordinate shift
    offset = json.loads(OFFSET_PATH.read_text())
    shift_x = float(offset["shift_x"])
    shift_y = float(offset["shift_y"])
    shift_z = float(offset["shift_z"])
    print(f"\nCoordinate shift: x={shift_x:.3f}  y={shift_y:.3f}  z={shift_z:.3f}")

    # Load CSV metadata
    print("\nLoading masses metadata CSV ...")
    csv_meta = load_csv_metadata(CSV_PATH)
    print(f"  {len(csv_meta)} buildings loaded")

    # Parse OBJ — global vertices + per-building faces
    print("\nParsing OBJ per-building objects ...")
    t0 = time.time()
    global_verts, buildings_faces = parse_obj_per_building(OBJ_PATH)
    print(f"  global vertices : {len(global_verts):,}")
    print(f"  building objects: {len(buildings_faces)}  ({time.time() - t0:.1f}s)")

    # Build per-building GLB meshes
    print("\nBuilding per-building meshes ...")
    t0 = time.time()
    mesh_dicts: list[dict] = []
    skipped_empty = 0
    skipped_no_meta = 0

    for cluster_id in sorted(buildings_faces.keys()):
        face_lists = buildings_faces[cluster_id]
        node_name  = f"{NODE_PREFIX}_{cluster_id}"

        if not face_lists:
            skipped_empty += 1
            continue

        verts, faces, norms = build_building_mesh(
            global_verts, face_lists, shift_x, shift_y, shift_z
        )

        if len(verts) == 0:
            skipped_empty += 1
            continue

        if cluster_id not in csv_meta:
            skipped_no_meta += 1
            continue

        mesh_dicts.append({
            "name":     node_name,
            "vertices": verts,
            "faces":    faces,
            "normals":  norms,
        })

    print(f"  meshes built    : {len(mesh_dicts)}")
    print(f"  skipped (empty) : {skipped_empty}")
    print(f"  skipped (no meta): {skipped_no_meta}  ({time.time() - t0:.1f}s)")

    if not mesh_dicts:
        print("ERROR: no meshes to pack")
        return 1

    # Pack GLB
    print("\nPacking GLB ...")
    t0 = time.time()
    glb_bytes = pack_glb(mesh_dicts)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_GLB.write_bytes(glb_bytes)
    print(f"  {OUT_GLB}  ({OUT_GLB.stat().st_size / 1e6:.2f} MB)  ({time.time() - t0:.1f}s)")

    glb_node_names = {m["name"] for m in mesh_dicts}

    # Build base metadata records (before address join)
    print("\nBuilding metadata records ...")
    base_records: list[dict] = []
    for cluster_id in sorted(csv_meta.keys()):
        node_name = f"{NODE_PREFIX}_{cluster_id}"
        row = csv_meta[cluster_id]
        base_records.append({
            "mesh_name":        node_name,
            "tile_id":          TILE_ID,
            "cluster_id":       cluster_id,
            "centroid_x":       float(row["centroid_x"]),
            "centroid_y":       float(row["centroid_y"]),
            "estimated_height": float(row["estimated_height"]) if row.get("estimated_height") else None,
            "footprint_area_m2": float(row["footprint_area_m2"]) if row.get("footprint_area_m2") else None,
            "ground_z":         float(row["ground_z"]) if row.get("ground_z") else None,
            "source_quality":   row.get("source_quality"),
            "point_count_inside": int(row["point_count_inside"]) if row.get("point_count_inside") else None,
            "has_glb_node":     node_name in glb_node_names,
        })
    print(f"  {len(base_records)} metadata records (all CSV buildings, incl degenerate)")

    # Compute tile bbox for address streaming
    cxs = [r["centroid_x"] for r in base_records]
    cys = [r["centroid_y"] for r in base_records]
    tile_min_x, tile_max_x = min(cxs), max(cxs)
    tile_min_y, tile_max_y = min(cys), max(cys)
    print(f"\nTile bbox (absolute EPSG:32617):")
    print(f"  x=[{tile_min_x:.1f}, {tile_max_x:.1f}]  y=[{tile_min_y:.1f}, {tile_max_y:.1f}]")

    # Stream address points
    print(f"\nStreaming address points (radius {ADDR_BUFFER_M}m buffer) ...")
    t0 = time.time()
    addrs = stream_addresses(ADDR_PATH, tile_min_x, tile_max_x, tile_min_y, tile_max_y)
    print(f"  {len(addrs)} address points in tile area  ({time.time() - t0:.1f}s)")

    if not addrs:
        print("ERROR: no address points found — check /mnt/e mount")
        return 1

    # Join addresses
    print("\nJoining addresses ...")
    t0 = time.time()
    enriched = join_addresses(base_records, addrs)
    print(f"  done  ({time.time() - t0:.2f}s)")

    # Write metadata JSON
    payload = {
        "schema_version":   "1.0",
        "tile":             "miami_south_beach_318455_hero_v001",
        "source_tile_id":   TILE_ID,
        "primary_key":      "mesh_name",
        "node_prefix":      NODE_PREFIX,
        "coordinate_frame": {
            "crs":     "EPSG:32617",
            "shift_x": shift_x,
            "shift_y": shift_y,
            "shift_z": shift_z,
            "note":    "Subtract shift from absolute EPSG:32617 to get scene-local coords",
        },
        "building_count":   len(enriched),
        "address_enrichment": {
            "source":       "Miami-Dade GeoAddress (gis-mdc.opendata.arcgis.com)",
            "join_method":  "cKDTree nearest-neighbour",
            "join_radius_m": JOIN_RADIUS_M,
            "crs":          "EPSG:32617",
        },
        "buildings": enriched,
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"\nWrote metadata : {OUT_META}  ({OUT_META.stat().st_size / 1e6:.2f} MB)")

    # Print artifact report
    print_report(enriched, OUT_GLB, OUT_META, glb_node_names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
