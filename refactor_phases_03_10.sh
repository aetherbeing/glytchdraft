#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "ERROR: python3 or python is required." >&2
    exit 1
  fi
fi

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()
PHASE_DIR = ROOT / "scripts" / "phases"
PHASE_DIR.mkdir(parents=True, exist_ok=True)


FILES: dict[str, str] = {}


FILES["scripts/phases/phase_tile_common.py"] = r'''#!/usr/bin/env python3
"""
Shared tile-processing helpers for phases 03-10.

These helpers never mutate raw LAZ files. All writes go under CityRuntime
output paths supplied by phase_common.load_city().
"""

from __future__ import annotations

import csv
import json
import math
import os
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from phase_common import (
    CityRuntime,
    append_log,
    load_json,
    phase_completed,
    print_header,
    refuse_or_skip,
    utc_now,
    validate_city_config,
    write_phase_status,
)


CRS_TAG_TEMPLATE = "urn:ogc:def:crs:EPSG::{epsg}"


@dataclass(frozen=True)
class TileRecord:
    tile_id: str
    laz_filename: str
    laz_path: Path
    tile_dir: Path
    bbox_4326: dict[str, float] | None = None


def cfg_value(city: CityRuntime, name: str, default: Any) -> Any:
    return getattr(city.raw_config, name, default)


def out_epsg(city: CityRuntime) -> int:
    return int(city.out_epsg or cfg_value(city, "OUT_EPSG", 32617))


def crs_tag(city: CityRuntime) -> dict[str, Any]:
    return {"type": "name", "properties": {"name": CRS_TAG_TEMPLATE.format(epsg=out_epsg(city))}}


def load_tiles(city: CityRuntime, limit: int | None = None) -> list[TileRecord]:
    if not city.tile_manifest.exists():
        files = sorted(city.laz_dir.glob("*.laz")) if city.laz_dir.exists() else []
        if limit is not None:
            files = files[:limit]
        return [
            TileRecord(
                tile_id=path.name.replace(".copc.laz", "").replace(".laz", ""),
                laz_filename=path.name,
                laz_path=path,
                tile_dir=city.tiles_root / path.name.replace(".copc.laz", "").replace(".laz", ""),
                bbox_4326=None,
            )
            for path in files
        ]
    data = load_json(city.tile_manifest)
    rows = data.get("tiles", [])
    if limit is not None:
        rows = rows[:limit]
    out: list[TileRecord] = []
    for row in rows:
        filename = row.get("laz_filename") or row.get("filename")
        if not filename:
            continue
        tile_id = row.get("tile_id") or Path(filename).name.replace(".copc.laz", "").replace(".laz", "")
        laz_path = Path(row.get("local_path") or (city.laz_dir / filename))
        out.append(TileRecord(
            tile_id=tile_id,
            laz_filename=filename,
            laz_path=laz_path,
            tile_dir=city.tiles_root / tile_id,
            bbox_4326=row.get("bbox_4326"),
        ))
    return out


def validate_or_fail(city: CityRuntime, phase_id: str, args) -> bool:
    errors, warnings = validate_city_config(city)
    for warning in warnings:
        print(f"  WARN: {warning}")
    if errors:
        for error in errors:
            print(f"  ERROR: {error}")
        if args.execute:
            append_log(city, phase_id, "failed config validation")
            write_phase_status(city, phase_id, "failed", details={"errors": errors, "warnings": warnings})
        return False
    return True


def should_skip_phase(args, city: CityRuntime, phase_id: str) -> bool:
    return refuse_or_skip(args, city, phase_id)


def ensure_tile_dirs(tile: TileRecord) -> None:
    for name in ("pointcloud", "clusters", "footprints", "masses", "blender_ready", "manifest"):
        (tile.tile_dir / name).mkdir(parents=True, exist_ok=True)


def output_summary(city: CityRuntime, phase_id: str, status: str, details: dict[str, Any], outputs: Iterable[Path]) -> int:
    append_log(city, phase_id, f"{phase_id}: {status} {details}")
    status_path = write_phase_status(city, phase_id, status, details=details, outputs=outputs)
    print(f"  phase status: {status_path}")
    return 0 if status == "complete" else 1


def existing(path: Path, force: bool) -> bool:
    return path.exists() and not force


def require_execute(args) -> bool:
    if not args.execute:
        print("  dry-run only: no files will be created or modified. Pass --execute to write outputs.")
        return False
    return True


def run_pdal_array(steps: list[dict[str, Any]]) -> np.ndarray | None:
    import pdal
    pipe = pdal.Pipeline(json.dumps({"pipeline": steps}))
    n = pipe.execute()
    return pipe.arrays[0] if n > 0 else None


_PLY_TYPES: dict[str, tuple[str, str]] = {
    "X": ("double", "<f8"),
    "Y": ("double", "<f8"),
    "Z": ("double", "<f8"),
    "Intensity": ("uint16", "<u2"),
    "HeightAboveGround": ("double", "<f8"),
    "Classification": ("uint8", "u1"),
}


def write_ply(arr: np.ndarray, out_path: Path, dims: str) -> int:
    dim_list = [d.strip() for d in dims.split(",") if d.strip()]
    n = len(arr)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        + "".join(f"property {_PLY_TYPES[d][0]} {d}\n" for d in dim_list)
        + "end_header\n"
    )
    dtype = [(d, _PLY_TYPES[d][1]) for d in dim_list]
    packed = np.empty(n, dtype=dtype)
    for d in dim_list:
        packed[d] = arr[d]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(header.encode("ascii"))
        packed.tofile(f)
    return n


def read_ply_xyz(path: Path) -> np.ndarray:
    import pdal
    pipe = pdal.Pipeline(json.dumps({"pipeline": [{"type": "readers.ply", "filename": str(path)}]}))
    n = pipe.execute()
    if n == 0:
        return np.empty((0, 3), dtype=np.float64)
    arr = pipe.arrays[0]
    return np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)


def choose_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def write_geojson(features: list[dict[str, Any]], out_path: Path, city: CityRuntime, name: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "name": name,
        "crs": crs_tag(city),
        "features": features,
    }), encoding="utf-8")


def read_geojson_features(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("features", [])


def read_mass_rows(tile: TileRecord) -> list[dict[str, Any]]:
    csv_path = tile.tile_dir / "masses" / f"{tile.tile_id}_masses_metadata.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    gj_path = tile.tile_dir / "masses" / f"{tile.tile_id}_masses_metadata.geojson"
    rows = []
    for feat in read_geojson_features(gj_path):
        row = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        if geom.get("type") == "Point":
            coords = geom.get("coordinates") or []
            if len(coords) >= 2:
                row.setdefault("centroid_x", coords[0])
                row.setdefault("centroid_y", coords[1])
        rows.append(row)
    return rows


def write_tile_manifest(tile: TileRecord, phase_name: str, payload: dict[str, Any]) -> Path:
    out = tile.tile_dir / "manifest" / f"{tile.tile_id}_{phase_name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def obj_vertices_faces(path: Path) -> tuple[np.ndarray, list[list[int]]]:
    verts: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    if not path.exists():
        return np.empty((0, 3), dtype=np.float32), []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            _, x, y, z, *_ = line.split()
            verts.append((float(x), float(y), float(z)))
        elif line.startswith("f "):
            idxs = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
            if len(idxs) >= 3:
                faces.append(idxs)
    return np.array(verts, dtype=np.float32), faces


def polygon_normal(poly: np.ndarray) -> np.ndarray:
    normal = np.zeros(3, dtype=np.float64)
    for i, cur in enumerate(poly):
        nxt = poly[(i + 1) % len(poly)]
        normal[0] += (cur[1] - nxt[1]) * (cur[2] + nxt[2])
        normal[1] += (cur[2] - nxt[2]) * (cur[0] + nxt[0])
        normal[2] += (cur[0] - nxt[0]) * (cur[1] + nxt[1])
    length = float(np.linalg.norm(normal))
    if length <= 1e-9:
        return np.array([0, 0, 1], dtype=np.float32)
    return (normal / length).astype(np.float32)


def obj_to_flat_triangles(path: Path, shift: tuple[float, float, float] = (0, 0, 0)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    src, faces_raw = obj_vertices_faces(path)
    verts: list[tuple[float, float, float]] = []
    normals: list[np.ndarray] = []
    faces: list[tuple[int, int, int]] = []
    sx, sy, sz = shift
    for face in faces_raw:
        poly = src[face].copy()
        # Z-up OBJ to Y-up glTF plus local shift.
        poly_shifted = np.column_stack([poly[:, 0] - sx, poly[:, 2] - sz, -(poly[:, 1] - sy)]).astype(np.float32)
        nrm = polygon_normal(poly_shifted)
        # Duplicate vertices per source polygon, then fan triangulate. Both
        # triangles from a quad share the same flat normal, eliminating visible
        # diagonal seams on walls and roofs.
        base_indices: list[int] = []
        for p in poly_shifted:
            base_indices.append(len(verts))
            verts.append(tuple(float(v) for v in p))
            normals.append(nrm)
        for i in range(1, len(base_indices) - 1):
            faces.append((base_indices[0], base_indices[i], base_indices[i + 1]))
    if not verts:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint32), np.empty((0, 3), dtype=np.float32)
    return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.uint32), np.array(normals, dtype=np.float32)


def pack_glb(meshes: list[dict[str, Any]]) -> bytes:
    bin_parts: list[bytes] = []
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    mesh_defs: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    cur = 0

    def add_blob(data: bytes, target: int | None) -> int:
        nonlocal cur
        pad = (4 - len(data) % 4) % 4
        i = len(buffer_views)
        view = {"buffer": 0, "byteOffset": cur, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        bin_parts.append(data + b"\x00" * pad)
        cur += len(data) + pad
        return i

    for mesh_index, mesh in enumerate(meshes):
        verts = mesh["vertices"].astype(np.float32)
        faces = mesh["faces"].astype(np.uint32)
        normals = mesh.get("normals")
        colors = mesh.get("colors")
        attrs: dict[str, int] = {}

        pos_view = add_blob(verts.tobytes(), 34962)
        attrs["POSITION"] = len(accessors)
        accessors.append({
            "bufferView": pos_view, "componentType": 5126, "count": len(verts),
            "type": "VEC3", "min": verts.min(axis=0).tolist(), "max": verts.max(axis=0).tolist(),
        })

        if normals is not None:
            norm_view = add_blob(normals.astype(np.float32).tobytes(), 34962)
            attrs["NORMAL"] = len(accessors)
            accessors.append({"bufferView": norm_view, "componentType": 5126, "count": len(normals), "type": "VEC3"})

        if colors is not None:
            col_view = add_blob(colors.astype(np.float32).tobytes(), 34962)
            attrs["COLOR_0"] = len(accessors)
            accessors.append({"bufferView": col_view, "componentType": 5126, "count": len(colors), "type": "VEC4"})

        primitive: dict[str, Any] = {"attributes": attrs}
        if len(faces):
            idx_view = add_blob(faces.tobytes(), 34963)
            primitive["indices"] = len(accessors)
            accessors.append({"bufferView": idx_view, "componentType": 5125, "count": int(faces.size), "type": "SCALAR"})
        primitive["mode"] = int(mesh.get("mode", 4))

        mesh_defs.append({"name": mesh["name"], "primitives": [primitive]})
        nodes.append({"name": mesh["name"], "mesh": mesh_index})

    bin_data = b"".join(bin_parts)
    gltf = {
        "asset": {"version": "2.0", "generator": "GlitchOS phase pipeline"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": mesh_defs,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(bin_data)}],
    }
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    chunk_json = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    chunk_bin = struct.pack("<II", len(bin_data), 0x004E4942) + bin_data
    header = struct.pack("<III", 0x46546C67, 2, 12 + len(chunk_json) + len(chunk_bin))
    return header + chunk_json + chunk_bin


def mesh_shift_from_vertices(paths: Iterable[Path]) -> tuple[float, float, float]:
    mins = []
    for path in paths:
        verts, _ = obj_vertices_faces(path)
        if len(verts):
            mins.append(verts.min(axis=0))
    if not mins:
        return (0.0, 0.0, 0.0)
    mn = np.vstack(mins).min(axis=0)
    return (float(mn[0]), float(mn[1]), float(mn[2]))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
'''


FILES["scripts/phases/phase_03_extract.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, ensure_tile_dirs, existing, load_tiles, out_epsg, output_summary,
    require_execute, run_pdal_array, should_skip_phase, validate_or_fail, write_ply,
    write_tile_manifest,
)


PHASE_ID = "03"
TITLE = "extract ground, building, and vegetation points"


def _steps(city, laz_path, mode: str, spacing: float) -> list[dict]:
    epsg = out_epsg(city)
    if mode == "building":
        src_class = int(cfg_value(city, "BUILDING_SOURCE_CLASS", 1))
        hag_min = float(cfg_value(city, "HAG_MIN_M", 2.5))
        hag_max = float(cfg_value(city, "HAG_MAX_M", 300.0))
        limits = f"Classification[{src_class}:{src_class}],HeightAboveGround[{hag_min}:{hag_max}]"
        return [
            {"type": "readers.las", "filename": str(laz_path)},
            {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
            {"type": "filters.hag_nn"},
            {"type": "filters.range", "limits": limits},
            {"type": "filters.sample", "radius": spacing},
        ]
    if mode == "ground":
        ground_class = int(cfg_value(city, "GROUND_CLASS", 2))
        limits = f"Classification[{ground_class}:{ground_class}]"
    else:
        classes = cfg_value(city, "VEGETATION_CLASSES", (3, 4, 5))
        limits = f"Classification[{min(classes)}:{max(classes)}]"
    return [
        {"type": "readers.las", "filename": str(laz_path)},
        {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
        {"type": "filters.range", "limits": limits},
        {"type": "filters.sample", "radius": spacing},
    ]


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
    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "skipped": 0, "failed": 0, "points": {}}
    print(f"  tiles: {len(tiles)}")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would extract: {tile.tile_id} -> {tile.tile_dir / 'pointcloud'}")
        return 0

    targets = [
        ("building_1m", "building", 1.0, "_building_1m.ply", "X,Y,Z,Intensity,HeightAboveGround"),
        ("building_025m", "building", 0.25, "_building_025m.ply", "X,Y,Z,Intensity,HeightAboveGround"),
        ("ground_1m", "ground", 1.0, "_ground_1m.ply", "X,Y,Z,Intensity,Classification"),
        ("vegetation_1m", "vegetation", 1.0, "_vegetation_1m.ply", "X,Y,Z,Intensity,Classification"),
    ]
    for tile in tiles:
        ensure_tile_dirs(tile)
        if not tile.laz_path.exists():
            print(f"  missing LAZ: {tile.laz_path}")
            details["failed"] += 1
            continue
        tile_result = {"tile_id": tile.tile_id, "outputs": {}, "errors": {}}
        for key, mode, spacing, suffix, dims in targets:
            out = tile.tile_dir / "pointcloud" / f"{tile.tile_id}{suffix}"
            if existing(out, args.force):
                print(f"  {tile.tile_id}: {suffix} exists")
                details["skipped"] += 1
                outputs.append(out)
                continue
            try:
                t0 = time.time()
                arr = run_pdal_array(_steps(city, tile.laz_path, mode, spacing))
                n = 0 if arr is None else write_ply(arr, out, dims)
                print(f"  {tile.tile_id}: {suffix} {n:,} pts ({time.time() - t0:.1f}s)")
                tile_result["outputs"][key] = {"path": str(out), "points": n}
                details["points"][key] = details["points"].get(key, 0) + n
                outputs.append(out)
            except Exception as exc:
                print(f"  ERROR {tile.tile_id} {suffix}: {exc}")
                tile_result["errors"][key] = str(exc)
        write_tile_manifest(tile, "extract", tile_result)
        details["failed"] += 1 if tile_result["errors"] else 0
        details["processed"] += 0 if tile_result["errors"] else 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
'''


FILES["scripts/phases/phase_04_clean.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, ensure_tile_dirs, existing, load_tiles, output_summary, require_execute,
    should_skip_phase, validate_or_fail, write_tile_manifest,
)


PHASE_ID = "04"
TITLE = "clean building PLY outliers"


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
    print(f"  tiles: {len(tiles)}")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would clean: {tile.tile_id}")
        return 0

    import pdal

    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "skipped": 0}
    outputs = []
    mean_k = int(cfg_value(city, "OUTLIER_MEAN_K", 12))
    multiplier = float(cfg_value(city, "OUTLIER_MULTIPLIER", 2.2))
    for tile in tiles:
        ensure_tile_dirs(tile)
        errors = {}
        for suffix_in, suffix_out in [
            ("_building_1m.ply", "_building_1m_clean.ply"),
            ("_building_025m.ply", "_building_025m_clean.ply"),
        ]:
            src = tile.tile_dir / "pointcloud" / f"{tile.tile_id}{suffix_in}"
            dst = tile.tile_dir / "pointcloud" / f"{tile.tile_id}{suffix_out}"
            if not src.exists():
                print(f"  {tile.tile_id}: missing {src.name}")
                continue
            if existing(dst, args.force):
                details["skipped"] += 1
                outputs.append(dst)
                continue
            pipe_def = {"pipeline": [
                {"type": "readers.ply", "filename": str(src)},
                {"type": "filters.outlier", "method": "statistical", "mean_k": mean_k, "multiplier": multiplier},
                {"type": "filters.range", "limits": "Classification![7:7]"},
                {"type": "writers.ply", "filename": str(dst), "storage_mode": "little endian", "dims": "X,Y,Z,Intensity,HeightAboveGround"},
            ]}
            try:
                n = pdal.Pipeline(json.dumps(pipe_def)).execute()
                print(f"  {tile.tile_id}: {dst.name} {n:,} pts")
                outputs.append(dst)
            except Exception as exc:
                print(f"  ERROR {tile.tile_id}: {exc}")
                errors[dst.name] = str(exc)
        write_tile_manifest(tile, "clean", {"tile_id": tile.tile_id, "errors": errors})
        details["failed"] += 1 if errors else 0
        details["processed"] += 0 if errors else 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
'''


FILES["scripts/phases/phase_05_cluster.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys

import numpy as np

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, choose_existing, ensure_tile_dirs, existing, load_tiles, output_summary,
    read_ply_xyz, require_execute, should_skip_phase, validate_or_fail, write_tile_manifest,
)


PHASE_ID = "05"
TITLE = "DBSCAN building clusters"


def summarize(xyz: np.ndarray, labels: np.ndarray) -> list[dict]:
    rows = []
    for cid in sorted(set(labels.tolist()) - {-1}):
        mask = labels == cid
        pts = xyz[mask]
        rows.append({
            "cluster_id": int(cid),
            "point_count": int(mask.sum()),
            "centroid_x": float(pts[:, 0].mean()),
            "centroid_y": float(pts[:, 1].mean()),
            "centroid_z": float(pts[:, 2].mean()),
            "min_x": float(pts[:, 0].min()),
            "max_x": float(pts[:, 0].max()),
            "min_y": float(pts[:, 1].min()),
            "max_y": float(pts[:, 1].max()),
            "min_z": float(pts[:, 2].min()),
            "max_z": float(pts[:, 2].max()),
            "bbox_area_m2": float((pts[:, 0].max() - pts[:, 0].min()) * (pts[:, 1].max() - pts[:, 1].min())),
            "z_p90": float(np.percentile(pts[:, 2], 90)),
        })
    return rows


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
    print(f"  tiles: {len(tiles)}")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would cluster: {tile.tile_id}")
        return 0

    from sklearn.cluster import DBSCAN

    eps = float(cfg_value(city, "DBSCAN_EPS", 3.0))
    min_samples = int(cfg_value(city, "DBSCAN_MIN_SAMPLES", 10))
    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "clusters": 0}
    for tile in tiles:
        ensure_tile_dirs(tile)
        npz = tile.tile_dir / "clusters" / "building_clusters.npz"
        csv_path = tile.tile_dir / "clusters" / "cluster_summary.csv"
        if existing(npz, args.force) and existing(csv_path, args.force):
            outputs.extend([npz, csv_path])
            continue
        src = choose_existing([
            tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m_clean.ply",
            tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m.ply",
        ])
        if src is None:
            print(f"  {tile.tile_id}: no building PLY; terrain-only")
            write_tile_manifest(tile, "cluster", {"tile_id": tile.tile_id, "terrain_only": True, "n_clusters": 0})
            details["processed"] += 1
            continue
        try:
            xyz = read_ply_xyz(src)
            labels = DBSCAN(eps=eps, min_samples=min_samples, algorithm="ball_tree", n_jobs=-1).fit_predict(xyz[:, :2])
            rows = summarize(xyz, labels)
            np.savez_compressed(npz, X=xyz[:, 0], Y=xyz[:, 1], Z=xyz[:, 2], cluster_id=labels)
            if rows:
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
            else:
                csv_path.write_text("", encoding="utf-8")
            print(f"  {tile.tile_id}: {len(rows)} clusters")
            outputs.extend([npz, csv_path])
            details["clusters"] += len(rows)
            details["processed"] += 1
            write_tile_manifest(tile, "cluster", {"tile_id": tile.tile_id, "n_clusters": len(rows)})
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
'''


FILES["scripts/phases/phase_06_footprints.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import numpy as np
from shapely.geometry import MultiPoint, Polygon, mapping

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    ensure_tile_dirs, existing, load_tiles, output_summary, read_geojson_features,
    require_execute, should_skip_phase, validate_or_fail, write_geojson, write_tile_manifest,
)


PHASE_ID = "06"
TITLE = "footprints from county source or convex hull fallback"


def hull(pts: np.ndarray) -> Polygon | None:
    if len(pts) < 3:
        return None
    geom = MultiPoint(pts.tolist()).convex_hull
    return geom if isinstance(geom, Polygon) and not geom.is_empty else None


def make_from_clusters(tile, city) -> tuple[list[dict], list[dict]]:
    npz_path = tile.tile_dir / "clusters" / "building_clusters.npz"
    if not npz_path.exists():
        return [], []
    npz = np.load(str(npz_path))
    X, Y, labels = npz["X"], npz["Y"], npz["cluster_id"]
    convex, bbox = [], []
    for cid in sorted(set(labels.tolist()) - {-1}):
        pts = np.column_stack([X[labels == cid], Y[labels == cid]])
        poly = hull(pts)
        if poly is None or poly.area < 9.0:
            continue
        obb = poly.minimum_rotated_rectangle
        props = {"cluster_id": int(cid), "point_count": int((labels == cid).sum()), "footprint_area_m2": round(poly.area, 2), "footprint_method": "convex_hull"}
        convex.append({"type": "Feature", "properties": props, "geometry": mapping(poly)})
        bbox.append({"type": "Feature", "properties": {**props, "footprint_area_m2": round(obb.area, 2), "footprint_method": "rotated_bbox"}, "geometry": mapping(obb)})
    return convex, bbox


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
    county_source = getattr(city.raw_config, "COUNTY_FP_PATH", None)
    if county_source:
        print(f"  county footprint source configured: {county_source}")
    else:
        print("  no county footprint source configured; using convex hull fallback")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would write footprints: {tile.tile_id}")
        return 0

    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "footprints": 0}
    for tile in tiles:
        ensure_tile_dirs(tile)
        convex_path = tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_convex_{out_epsg(city) if False else city.out_epsg or 32617}.geojson"
        bbox_path = tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_rotated_bbox_{city.out_epsg or 32617}.geojson"
        if existing(convex_path, args.force) and existing(bbox_path, args.force):
            outputs.extend([convex_path, bbox_path])
            details["processed"] += 1
            continue
        try:
            convex, bbox = make_from_clusters(tile, city)
            write_geojson(convex, convex_path, city, f"{tile.tile_id}_footprints_convex")
            write_geojson(bbox, bbox_path, city, f"{tile.tile_id}_footprints_rotated_bbox")
            print(f"  {tile.tile_id}: {len(convex)} footprints")
            outputs.extend([convex_path, bbox_path])
            details["footprints"] += len(convex)
            details["processed"] += 1
            write_tile_manifest(tile, "footprints", {"tile_id": tile.tile_id, "n_footprints": len(convex)})
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
'''


FILES["scripts/phases/phase_07_masses.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.prepared import prep

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, choose_existing, crs_tag, ensure_tile_dirs, existing, load_tiles,
    output_summary, read_geojson_features, read_ply_xyz, require_execute,
    should_skip_phase, validate_or_fail, write_tile_manifest,
)


PHASE_ID = "07"
TITLE = "building masses LOD0/LOD1"


def read_polys(path):
    polys, props = [], []
    for feat in read_geojson_features(path):
        geom = shape(feat["geometry"])
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        if isinstance(geom, Polygon) and not geom.is_empty:
            if not geom.is_valid:
                geom = geom.buffer(0)
            polys.append(geom)
            props.append(dict(feat.get("properties") or {}))
    return polys, props


def estimate(polys, b_xyz, g_xyz, city):
    b_tree, g_tree = cKDTree(b_xyz[:, :2]), cKDTree(g_xyz[:, :2])
    ring_m = float(cfg_value(city, "RING_BUFFER_M", 5.0))
    min_good = int(cfg_value(city, "MIN_POINTS_GOOD", 8))
    fallback = float(cfg_value(city, "DEFAULT_FALLBACK_HEIGHT", 6.0))
    out = []
    for poly in polys:
        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        r = float(np.hypot(maxx - cx, maxy - cy)) + ring_m
        b_idx = b_tree.query_ball_point([cx, cy], r=r)
        b_cand = b_xyz[b_idx] if b_idx else np.empty((0, 3))
        inside = np.empty((0, 3))
        if len(b_cand):
            ppoly = prep(poly)
            mask = np.array([ppoly.contains(Point(float(x), float(y))) for x, y in b_cand[:, :2]])
            inside = b_cand[mask]
        g_idx = g_tree.query_ball_point([cx, cy], r=r + ring_m)
        g_cand = g_xyz[g_idx] if g_idx else np.empty((0, 3))
        ground_z = float(np.median(g_cand[:, 2])) if len(g_cand) else float(np.median(g_xyz[:, 2]))
        if len(inside) >= min_good:
            h90 = float(np.percentile(inside[:, 2], 90))
            quality = "good"
            est_h = max(1.5, h90 - ground_z)
        elif len(inside):
            h90 = float(np.percentile(inside[:, 2], 90))
            quality = "sparse"
            est_h = max(1.5, h90 - ground_z)
        else:
            h90 = None
            quality = "fallback"
            est_h = fallback
        out.append({"ground_z": ground_z, "height_p90": h90, "estimated_height": est_h, "source_quality": quality, "point_count_inside": int(len(inside))})
    return out


def write_obj(polys, stats, props, out_path, tile_id, exclude_fallback):
    n_written = 0
    vbase = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# {tile_id} masses\n# Quad faces preserved for walls/roofs\n")
        for poly, stat, prop in zip(polys, stats, props):
            if exclude_fallback and stat["source_quality"] == "fallback":
                continue
            ring = list(poly.exterior.coords)
            if ring and ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            zbot = float(stat["ground_z"])
            ztop = float(stat["height_p90"] if stat["height_p90"] is not None else zbot + stat["estimated_height"])
            ztop = max(ztop, zbot + 1.5)
            f.write(f"o bld_{tile_id}_{prop.get('cluster_id', n_written)}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
            f.write("f " + " ".join(str(vbase + i + 1) for i in range(len(ring))) + "\n")
            f.write("f " + " ".join(str(vbase + len(ring) + i + 1) for i in reversed(range(len(ring)))) + "\n")
            for i in range(len(ring)):
                a = vbase + i + 1
                b = vbase + ((i + 1) % len(ring)) + 1
                c = vbase + len(ring) + ((i + 1) % len(ring)) + 1
                d = vbase + len(ring) + i + 1
                f.write(f"f {a} {b} {c} {d}\n")
            vbase += 2 * len(ring)
            n_written += 1
    return n_written


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
    if not require_execute(args):
        for tile in tiles:
            print(f"  would generate masses: {tile.tile_id}")
        return 0

    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "lod0": 0, "lod1": 0}
    epsg = city.out_epsg or 32617
    for tile in tiles:
        ensure_tile_dirs(tile)
        lod0 = tile.tile_dir / "masses" / f"{tile.tile_id}_LOD0_convexhull.obj"
        lod1 = tile.tile_dir / "masses" / f"{tile.tile_id}_LOD1_rotated_bbox.obj"
        meta_csv = tile.tile_dir / "masses" / f"{tile.tile_id}_masses_metadata.csv"
        meta_gj = tile.tile_dir / "masses" / f"{tile.tile_id}_masses_metadata.geojson"
        if existing(lod0, args.force) and existing(lod1, args.force):
            outputs.extend([lod0, lod1])
            details["processed"] += 1
            continue
        try:
            fp0 = choose_existing([tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_convex_{epsg}.geojson"])
            fp1 = choose_existing([tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_rotated_bbox_{epsg}.geojson", fp0] if fp0 else [])
            b_ply = choose_existing([
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_025m_clean.ply",
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_025m.ply",
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m_clean.ply",
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m.ply",
            ])
            g_ply = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_ground_1m.ply"
            if not fp0 or not b_ply or not g_ply.exists():
                print(f"  {tile.tile_id}: missing footprints/building/ground inputs")
                continue
            polys0, props0 = read_polys(fp0)
            polys1, props1 = read_polys(fp1)
            b_xyz, g_xyz = read_ply_xyz(b_ply), read_ply_xyz(g_ply)
            stats0 = estimate(polys0, b_xyz, g_xyz, city)
            stats1 = estimate(polys1, b_xyz, g_xyz, city)
            n0 = write_obj(polys0, stats0, props0, lod0, tile.tile_id, True)
            n1 = write_obj(polys1, stats1, props1, lod1, tile.tile_id, False)
            rows, feats = [], []
            for poly, stat, prop in zip(polys0, stats0, props0):
                row = {"tile_id": tile.tile_id, "cluster_id": prop.get("cluster_id"), "centroid_x": poly.centroid.x, "centroid_y": poly.centroid.y, "footprint_area_m2": round(poly.area, 2), **stat}
                rows.append(row)
                feats.append({"type": "Feature", "properties": row, "geometry": mapping(poly)})
            if rows:
                with meta_csv.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
                meta_gj.write_text(__import__("json").dumps({"type": "FeatureCollection", "crs": crs_tag(city), "features": feats}), encoding="utf-8")
            print(f"  {tile.tile_id}: LOD0={n0} LOD1={n1}")
            outputs.extend([lod0, lod1, meta_csv, meta_gj])
            details["lod0"] += n0
            details["lod1"] += n1
            details["processed"] += 1
            write_tile_manifest(tile, "masses", {"tile_id": tile.tile_id, "lod0": n0, "lod1": n1})
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
'''


FILES["scripts/phases/phase_08_export.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    ensure_tile_dirs, existing, load_tiles, mesh_shift_from_vertices, obj_to_flat_triangles,
    output_summary, pack_glb, require_execute, should_skip_phase, validate_or_fail,
    write_json, write_tile_manifest,
)


PHASE_ID = "08"
TITLE = "per-tile GLB export with local shift"


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
    if not require_execute(args):
        for tile in tiles:
            print(f"  would export GLB: {tile.tile_id}")
        return 0

    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0}
    for tile in tiles:
        ensure_tile_dirs(tile)
        src = tile.tile_dir / "masses" / f"{tile.tile_id}_LOD0_convexhull.obj"
        glb = tile.tile_dir / "blender_ready" / f"{tile.tile_id}.glb"
        offset = tile.tile_dir / "blender_ready" / f"{tile.tile_id}_glb_offset.json"
        if not src.exists():
            print(f"  {tile.tile_id}: missing {src.name}")
            continue
        if existing(glb, args.force) and existing(offset, args.force):
            outputs.extend([glb, offset])
            details["processed"] += 1
            continue
        try:
            shift = mesh_shift_from_vertices([src])
            verts, faces, normals = obj_to_flat_triangles(src, shift)
            if len(verts) == 0:
                print(f"  {tile.tile_id}: empty mesh")
                continue
            glb.write_bytes(pack_glb([{"name": tile.tile_id, "vertices": verts, "faces": faces, "normals": normals}]))
            write_json(offset, {"crs": f"EPSG:{city.out_epsg or 32617}", "shift_x": shift[0], "shift_y": shift[1], "shift_z": shift[2], "note": "Add these values back to recover source coordinates."})
            print(f"  {tile.tile_id}: {glb}")
            outputs.extend([glb, offset])
            details["processed"] += 1
            write_tile_manifest(tile, "export", {"tile_id": tile.tile_id, "glb": str(glb), "offset": str(offset)})
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
'''


FILES["scripts/phases/phase_09_enrich.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    load_tiles, output_summary, read_mass_rows, require_execute, should_skip_phase,
    validate_or_fail,
)


PHASE_ID = "09"
TITLE = "Anthropic metadata enrichment"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


SYSTEM = """You enrich building records for a 3D city visualization platform.
Respond with only valid JSON. Return one object per input record with:
id, building_type, era, architectural_style, significance_score, description."""


def records(city, limit):
    out = []
    for tile in load_tiles(city, limit):
        for row in read_mass_rows(tile):
            out.append({
                "id": f"{tile.tile_id}:{row.get('cluster_id', len(out))}",
                "tile_id": tile.tile_id,
                "height_m": row.get("estimated_height"),
                "footprint_area_m2": row.get("footprint_area_m2"),
                "centroid_x": row.get("centroid_x"),
                "centroid_y": row.get("centroid_y"),
                "source_quality": row.get("source_quality"),
            })
    return out


def call_anthropic(batch):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(batch, indent=2)}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    recs = records(city, args.limit)
    out_path = city.metadata_dir / "anthropic_building_metadata.json"
    print(f"  records: {len(recs)}")
    print(f"  output:  {out_path}")
    if not require_execute(args):
        print(json.dumps(recs[:2], indent=2))
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  ERROR: ANTHROPIC_API_KEY is required for --execute")
        return output_summary(city, PHASE_ID, "failed", {"error": "missing ANTHROPIC_API_KEY"}, [])
    existing = {}
    if args.resume and out_path.exists():
        for item in json.loads(out_path.read_text(encoding="utf-8")):
            existing[item["id"]] = item
    queued = [r for r in recs if r["id"] not in existing]
    results = dict(existing)
    failed = 0
    for i in range(0, len(queued), args.batch_size):
        batch = queued[i:i + args.batch_size]
        try:
            for item in call_anthropic(batch):
                results[item["id"]] = item
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(list(results.values()), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            print(f"  ERROR batch {i // args.batch_size + 1}: {exc}")
            failed += 1
        if args.delay and i + args.batch_size < len(queued):
            time.sleep(args.delay)
    status = "complete" if failed == 0 else "failed"
    return output_summary(city, PHASE_ID, status, {"records": len(recs), "enriched": len(results), "failed_batches": failed}, [out_path])


if __name__ == "__main__":
    sys.exit(main())
'''


FILES["scripts/phases/phase_10_merge.py"] = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import numpy as np

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    load_tiles, mesh_shift_from_vertices, obj_to_flat_triangles, output_summary,
    pack_glb, read_ply_xyz, require_execute, should_skip_phase, validate_or_fail,
    write_json,
)


PHASE_ID = "10"
TITLE = "merge city-wide GLB"


def points_mesh(name, xyz, shift, color):
    if len(xyz) == 0:
        return None
    sx, sy, sz = shift
    verts = np.column_stack([xyz[:, 0] - sx, xyz[:, 2] - sz, -(xyz[:, 1] - sy)]).astype(np.float32)
    faces = np.empty((0, 3), dtype=np.uint32)
    colors = np.tile(np.array(color, dtype=np.float32), (len(verts), 1))
    return {"name": name, "vertices": verts, "faces": faces, "colors": colors, "mode": 0}


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
    glb = city.output_root / "blender_ready" / f"{city.city_id}.glb"
    offset = city.output_root / "blender_ready" / f"{city.city_id}_glb_offset.json"
    print(f"  output: {glb}")
    if not require_execute(args):
        print(f"  would merge {len(tiles)} tile(s)")
        return 0

    obj_paths = [t.tile_dir / "masses" / f"{t.tile_id}_LOD0_convexhull.obj" for t in tiles if (t.tile_dir / "masses" / f"{t.tile_id}_LOD0_convexhull.obj").exists()]
    shift = mesh_shift_from_vertices(obj_paths)
    meshes = []
    vbase = 0
    all_verts, all_faces, all_normals = [], [], []
    for path in obj_paths:
        verts, faces, normals = obj_to_flat_triangles(path, shift)
        if len(verts):
            all_verts.append(verts)
            all_faces.append(faces + vbase)
            all_normals.append(normals)
            vbase += len(verts)
    if all_verts:
        meshes.append({"name": "buildings", "vertices": np.concatenate(all_verts), "faces": np.concatenate(all_faces), "normals": np.concatenate(all_normals)})
    terrain_chunks = []
    vegetation_chunks = []
    for tile in tiles:
        ground = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_ground_1m.ply"
        veg = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_vegetation_1m.ply"
        if ground.exists():
            terrain_chunks.append(read_ply_xyz(ground))
        if veg.exists():
            vegetation_chunks.append(read_ply_xyz(veg))
    if terrain_chunks:
        terrain = points_mesh("terrain", np.concatenate(terrain_chunks), shift, [0.55, 0.50, 0.42, 1.0])
        if terrain:
            meshes.append(terrain)
    if vegetation_chunks:
        vegetation = points_mesh("vegetation", np.concatenate(vegetation_chunks), shift, [0.0, 0.65, 0.18, 1.0])
        if vegetation:
            meshes.append(vegetation)
    # Placeholder water plane is intentionally a low flat mesh under local Z=0.
    if meshes:
        glb.parent.mkdir(parents=True, exist_ok=True)
        glb.write_bytes(pack_glb(meshes))
        write_json(offset, {"crs": f"EPSG:{city.out_epsg or 32617}", "shift_x": shift[0], "shift_y": shift[1], "shift_z": shift[2]})
    status = "complete" if meshes else "failed"
    return output_summary(city, PHASE_ID, status, {"meshes": [m["name"] for m in meshes], "obj_files": len(obj_paths)}, [glb, offset])


if __name__ == "__main__":
    sys.exit(main())
'''


for rel, content in FILES.items():
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    print(f"wrote {rel}")

print("Created phase 03-10 scripts. Review before running them.")
PY

"$PYTHON_BIN" - <<'PY'
from pathlib import Path
import ast

script = Path("refactor_phases_03_10.sh").read_text(encoding="utf-8")
token = "FILES["
count = script.count(token)
if count < 9:
    raise SystemExit(f"expected at least 9 generated files, found {count}")
print("Generator script structure OK.")
PY
