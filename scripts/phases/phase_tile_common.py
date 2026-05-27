#!/usr/bin/env python3
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
    resolve_cross_platform_path,
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
        laz_path = resolve_cross_platform_path(Path(row.get("local_path") or (city.laz_dir / filename)))
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


def write_empty_ply(out_path: Path, dims: str) -> int:
    dim_list = [d.strip() for d in dims.split(",") if d.strip()]
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "element vertex 0\n"
        + "".join(f"property {_PLY_TYPES[d][0]} {d}\n" for d in dim_list)
        + "end_header\n"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(header.encode("ascii"))
    return 0


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
        # glTF stores polygon meshes as triangles. Keep each OBJ quad/ngon as a
        # flat source face by duplicating the vertices per emitted triangle and
        # assigning the same face normal to every emitted vertex. Nothing is
        # shared across the internal diagonal, so walls and roofs render as one
        # continuous flat face instead of exposing a lighting seam.
        for i in range(1, len(poly_shifted) - 1):
            tri_indices: list[int] = []
            for p in (poly_shifted[0], poly_shifted[i], poly_shifted[i + 1]):
                tri_indices.append(len(verts))
                verts.append(tuple(float(v) for v in p))
                normals.append(nrm)
            faces.append((tri_indices[0], tri_indices[1], tri_indices[2]))
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

        primitive: dict[str, Any] = {"attributes": attrs, "material": 0}
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
        "materials": [{"name": "massing_flat_quads", "doubleSided": True, "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}}],
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
