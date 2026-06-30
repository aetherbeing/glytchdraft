"""
run_tile_miami.py  [GlitchOS city pipeline — Miami per-tile]

Self-contained per-tile pipeline for the City of Miami 3DEP dataset.
Called as a subprocess by run_miami_city.py for each LAZ tile.

Stages (run in order):
  extract    PDAL HAG filtering — building candidate + ground PLY
  clean      Statistical outlier removal
  cluster    DBSCAN building isolation
  footprints Convex-hull + rotated-bbox polygons from clusters
  masses     Height estimation + OBJ extrusion (LOD0 + LOD1)

Output tree (per tile):
  <out>/
    pointcloud/  <tile>_building_1m.ply   <tile>_building_025m.ply   <tile>_ground_1m.ply
                 <tile>_building_1m_clean.ply   <tile>_building_025m_clean.ply
    clusters/    building_clusters.npz    cluster_summary.csv
    footprints/  <tile>_footprints_convex_32617.geojson
                 <tile>_footprints_rotated_bbox_32617.geojson
    masses/      <tile>_LOD0_convexhull.obj   <tile>_LOD1_rotated_bbox.obj
                 <tile>_masses_metadata.csv
    manifest/    <tile>_manifest.json

Usage:
    python scripts/miami/run_tile_miami.py --laz /mnt/e/miami/data_raw/laz/<tile>.laz \\
                                           --out /mnt/t7/miami/data_processed/miami_city/tiles/<tile>/
    python scripts/miami/run_tile_miami.py --laz ... --out ... --stages extract clean cluster
    python scripts/miami/run_tile_miami.py --laz ... --out ... --resume  # skip completed stages

Exit codes:
    0  all stages OK
    1  one or more stages failed
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import miami_city_config as CFG

import numpy as np
import pdal
from scipy.spatial import cKDTree
from shapely.geometry import mapping
from shapely.geometry import MultiPolygon, Polygon
from shapely.prepared import prep as prepared_prep
from sklearn.cluster import DBSCAN

try:
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

ALL_STAGES = ["extract", "clean", "cluster", "footprints", "masses", "vegetation"]

# PRESERVE_RAW_LAZ guard — enforced at module load time (rule 3)
# The pipeline reads LAZ files via PDAL but NEVER writes to CFG.LAZ_DIR.
# If this assertion fails, stop immediately — something has misconfigured the pipeline.
assert CFG.PRESERVE_RAW_LAZ, (
    "CFG.PRESERVE_RAW_LAZ is False. Set it to True in miami_city_config.py before running."
)

CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}

# ── Z normalization source contract ──────────────────────────────────────────
# EPSG:6438 horizontal, EPSG:6360 vertical, US survey foot.
# XY reprojection to EPSG:32617 corrects horizontal coordinates only.
# Z must be converted explicitly before HAG and all metric height semantics.
_MIAMI_SOURCE_HORIZONTAL_CRS: str = CFG.SOURCE_HORIZONTAL_CRS
_MIAMI_SOURCE_VERTICAL_CRS: str   = CFG.SOURCE_VERTICAL_CRS
_MIAMI_SOURCE_Z_UNITS: str        = CFG.SOURCE_Z_UNITS
_Z_TO_METERS_FACTOR: float        = CFG.Z_TO_METERS_FACTOR

# Fail closed if the constant has been corrupted
assert _Z_TO_METERS_FACTOR == 0.3048006096012192, (
    f"Z_TO_METERS_FACTOR mismatch: {_Z_TO_METERS_FACTOR!r}. "
    "Miami source contract requires exactly 0.3048006096012192 "
    "(US survey foot to metres, EPSG:6360)."
)


def _validate_source_contract(
    source_horizontal_crs: str,
    source_vertical_crs: str,
    source_z_units: str,
    z_to_meters_factor: float,
) -> None:
    """Validate Miami LAZ source contract fields. Raises RuntimeError on mismatch."""
    if source_horizontal_crs != "EPSG:6438":
        raise RuntimeError(
            f"Incorrect source horizontal CRS: {source_horizontal_crs!r}; "
            "Miami LAZ requires EPSG:6438."
        )
    if source_vertical_crs != "EPSG:6360":
        raise RuntimeError(
            f"Incorrect source vertical CRS: {source_vertical_crs!r}; "
            "Miami LAZ requires EPSG:6360."
        )
    if source_z_units != "US survey foot":
        raise RuntimeError(
            f"Incorrect source Z units: {source_z_units!r}; "
            "Miami LAZ requires 'US survey foot'."
        )
    if abs(z_to_meters_factor - 0.3048006096012192) > 1e-15:
        raise RuntimeError(
            f"Incorrect Z conversion factor: {z_to_meters_factor!r}; "
            "Miami source contract requires exactly 0.3048006096012192."
        )


def _z_normalization_steps() -> list[dict]:
    """Return the Z-conversion PDAL stage for Miami LAZ source.

    Converts Z from US survey feet to metres exactly once per pipeline,
    after filters.reprojection and before filters.hag_nn and metric filters.range.
    Source: EPSG:6438/6360, US survey foot. Factor: 0.3048006096012192.
    """
    return [{"type": "filters.assign", "value": f"Z = Z * {_Z_TO_METERS_FACTOR}"}]


def _validate_pipeline_z_normalization(steps: list[dict]) -> None:
    """Raise RuntimeError if Z normalization is absent, duplicated, mispositioned, or has wrong factor."""
    types = [s["type"] for s in steps]
    assign_count = sum(1 for t in types if t == "filters.assign")
    if assign_count == 0:
        raise RuntimeError(
            "Z normalization stage (filters.assign) missing from Miami pipeline. "
            "Source Z is in US survey feet; all metric operations will be incorrect."
        )
    if assign_count > 1:
        raise RuntimeError(
            f"Duplicate Z normalization stages ({assign_count}) in Miami pipeline. "
            "Z must be converted exactly once."
        )
    assign_idx = types.index("filters.assign")
    if "filters.reprojection" in types:
        reproj_idx = types.index("filters.reprojection")
        if reproj_idx >= assign_idx:
            raise RuntimeError(
                "Z normalization must appear after filters.reprojection "
                "(XY reprojection does not normalize Z)."
            )
    if "filters.hag_nn" in types:
        hag_idx = types.index("filters.hag_nn")
        if assign_idx >= hag_idx:
            raise RuntimeError(
                "Z normalization must appear before filters.hag_nn "
                "(HAG computation requires metric Z values)."
            )
    assign_step = steps[assign_idx]
    value = assign_step.get("value", "")
    expected_value = f"Z = Z * {_Z_TO_METERS_FACTOR}"
    if value != expected_value:
        raise RuntimeError(
            f"Z normalization value mismatch: expected {expected_value!r}, "
            f"found {value!r}."
        )


_PLY_TYPES: dict[str, tuple[str, str]] = {
    "X":                 ("double", "<f8"),
    "Y":                 ("double", "<f8"),
    "Z":                 ("double", "<f8"),
    "Intensity":         ("uint16", "<u2"),
    "HeightAboveGround": ("double", "<f8"),
    "Classification":    ("uint8",  "u1"),
}


# ── Stage 1: Extract ───────────────────────────────────────────────────────────

def _building_steps(laz_path: Path, spacing_m: float) -> list[dict]:
    return [
        {"type": "readers.las", "filename": str(laz_path)},
        {"type": "filters.reprojection", "out_srs": f"EPSG:{CFG.OUT_EPSG}"},
        *_z_normalization_steps(),
        {"type": "filters.hag_nn"},
        {
            "type":   "filters.range",
            "limits": (
                f"Classification[{CFG.BUILDING_SOURCE_CLASS}:{CFG.BUILDING_SOURCE_CLASS}],"
                f"HeightAboveGround[{CFG.HAG_MIN_M}:{CFG.HAG_MAX_M}]"
            ),
        },
        {"type": "filters.sample", "radius": spacing_m},
    ]


def _ground_steps(laz_path: Path, spacing_m: float) -> list[dict]:
    return [
        {"type": "readers.las", "filename": str(laz_path)},
        {"type": "filters.reprojection", "out_srs": f"EPSG:{CFG.OUT_EPSG}"},
        *_z_normalization_steps(),
        {"type": "filters.range", "limits": f"Classification[{CFG.GROUND_CLASS}:{CFG.GROUND_CLASS}]"},
        {"type": "filters.sample", "radius": spacing_m},
    ]


def _vegetation_steps(laz_path: Path, spacing_m: float) -> list[dict]:
    vmin, vmax = min(CFG.VEGETATION_CLASSES), max(CFG.VEGETATION_CLASSES)
    return [
        {"type": "readers.las", "filename": str(laz_path)},
        {"type": "filters.reprojection", "out_srs": f"EPSG:{CFG.OUT_EPSG}"},
        *_z_normalization_steps(),
        {"type": "filters.range", "limits": f"Classification[{vmin}:{vmax}]"},
        {"type": "filters.sample", "radius": spacing_m},
    ]


def _run_pdal(steps: list[dict]) -> np.ndarray | None:
    try:
        pipe = pdal.Pipeline(json.dumps({"pipeline": steps}))
        n = pipe.execute()
        return pipe.arrays[0] if n > 0 else None
    except Exception as exc:
        print(f"  PDAL error: {exc}", file=sys.stderr)
        return None


def _write_ply(arr: np.ndarray, out_path: Path, dims: str) -> int:
    dim_list = [d.strip() for d in dims.split(",")]
    n = len(arr)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        + "".join(f"property {_PLY_TYPES[d][0]} {d}\n" for d in dim_list)
        + "end_header\n"
    )
    dtype  = [(d, _PLY_TYPES[d][1]) for d in dim_list]
    packed = np.empty(n, dtype=dtype)
    for d in dim_list:
        packed[d] = arr[d]
    with out_path.open("wb") as f:
        f.write(header.encode("ascii"))
        packed.tofile(f)
    return n


def stage_extract(laz_path: Path, out: Path, tile_id: str) -> dict:
    pc_dir = out / "pointcloud"
    pc_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, int] = {}
    t0 = time.time()

    for spacing, suffix, dims, mode in [
        (1.0,  "_building_1m.ply",   "X,Y,Z,Intensity,HeightAboveGround", "building"),
        (0.25, "_building_025m.ply", "X,Y,Z,Intensity,HeightAboveGround", "building"),
        (1.0,  "_ground_1m.ply",     "X,Y,Z,Intensity,Classification",    "ground"),
    ]:
        out_path = pc_dir / f"{tile_id}{suffix}"
        if out_path.exists():
            print(f"  [extract] {suffix} exists, skip")
            results[suffix] = out_path.stat().st_size
            continue

        steps = _building_steps(laz_path, spacing) if mode == "building" \
                else _ground_steps(laz_path, spacing)
        arr = _run_pdal(steps)
        if arr is None or len(arr) == 0:
            print(f"  [extract] {suffix}: 0 points")
            results[suffix] = 0
            continue

        n = _write_ply(arr, out_path, dims)
        results[suffix] = n
        print(f"  [extract] {suffix}: {n:,} pts ({time.time()-t0:.1f}s)")
        t0 = time.time()

    return {"ok": True, "results": results}


# ── Stage 2: Clean ─────────────────────────────────────────────────────────────

def stage_clean(out: Path, tile_id: str) -> dict:
    pc_dir = out / "pointcloud"
    ok = True

    for suffix_in, suffix_out in [
        ("_building_1m.ply",   "_building_1m_clean.ply"),
        ("_building_025m.ply", "_building_025m_clean.ply"),
    ]:
        in_path  = pc_dir / f"{tile_id}{suffix_in}"
        out_path = pc_dir / f"{tile_id}{suffix_out}"

        if out_path.exists():
            print(f"  [clean] {suffix_out} exists, skip")
            continue
        if not in_path.exists():
            print(f"  [clean] SKIP: {suffix_in} not found")
            continue

        pipe_def = {
            "pipeline": [
                {"type": "readers.ply", "filename": str(in_path)},
                {"type": "filters.outlier", "method": "statistical",
                 "mean_k": CFG.OUTLIER_MEAN_K, "multiplier": CFG.OUTLIER_MULTIPLIER},
                {"type": "filters.range", "limits": "Classification![7:7]"},
                {"type": "writers.ply", "filename": str(out_path),
                 "storage_mode": "little endian",
                 "dims": "X,Y,Z,Intensity,HeightAboveGround"},
            ]
        }
        try:
            n = pdal.Pipeline(json.dumps(pipe_def)).execute()
            print(f"  [clean] {suffix_out}: {n:,} pts")
        except Exception as exc:
            print(f"  [clean] ERROR {suffix_out}: {exc}", file=sys.stderr)
            ok = False

    return {"ok": ok}


# ── Stage 3: Cluster ───────────────────────────────────────────────────────────

def _read_ply_xyz(path: Path) -> np.ndarray:
    pipe = pdal.Pipeline(json.dumps({"pipeline": [{"type": "readers.ply", "filename": str(path)}]}))
    pipe.execute()
    arr = pipe.arrays[0]
    return np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)


def _cluster(xyz: np.ndarray) -> np.ndarray:
    print(f"  [cluster] DBSCAN eps={CFG.DBSCAN_EPS} min_samples={CFG.DBSCAN_MIN_SAMPLES} "
          f"pts={len(xyz):,}")
    t0 = time.time()
    db = DBSCAN(eps=CFG.DBSCAN_EPS, min_samples=CFG.DBSCAN_MIN_SAMPLES,
                algorithm="ball_tree", n_jobs=-1)
    labels = db.fit_predict(xyz[:, :2])
    n_clusters = int(labels.max()) + 1 if labels.max() >= 0 else 0
    print(f"  [cluster] {n_clusters} clusters  noise={int((labels==-1).sum()):,}  "
          f"({time.time()-t0:.1f}s)")
    return labels


def _build_cluster_summary(xyz: np.ndarray, labels: np.ndarray) -> list[dict]:
    rows = []
    for cid in sorted(set(labels) - {-1}):
        mask = labels == cid
        pts  = xyz[mask]
        rows.append({
            "cluster_id":   int(cid),
            "point_count":  int(mask.sum()),
            "centroid_x":   float(pts[:, 0].mean()),
            "centroid_y":   float(pts[:, 1].mean()),
            "centroid_z":   float(pts[:, 2].mean()),
            "min_x": float(pts[:, 0].min()), "max_x": float(pts[:, 0].max()),
            "min_y": float(pts[:, 1].min()), "max_y": float(pts[:, 1].max()),
            "min_z": float(pts[:, 2].min()), "max_z": float(pts[:, 2].max()),
            "bbox_area_m2": float(
                (pts[:, 0].max() - pts[:, 0].min()) *
                (pts[:, 1].max() - pts[:, 1].min())
            ),
            "z_range": float(pts[:, 2].max() - pts[:, 2].min()),
            "z_p90":   float(np.percentile(pts[:, 2], 90)),
        })
    return rows


def stage_cluster(out: Path, tile_id: str) -> dict:
    pc_dir      = out / "pointcloud"
    cluster_dir = out / "clusters"
    cluster_dir.mkdir(parents=True, exist_ok=True)

    npz_path = cluster_dir / "building_clusters.npz"
    csv_path = cluster_dir / "cluster_summary.csv"

    if npz_path.exists():
        print("  [cluster] building_clusters.npz exists, skip")
        summary = []
        if csv_path.exists():
            with csv_path.open(encoding="utf-8") as f:
                summary = list(csv.DictReader(f))
        return {"ok": True, "n_clusters": len(summary)}

    # Prefer clean PLY, fall back to raw
    in_path = pc_dir / f"{tile_id}_building_1m_clean.ply"
    if not in_path.exists():
        in_path = pc_dir / f"{tile_id}_building_1m.ply"
    if not in_path.exists():
        print(f"  [cluster] SKIP: no building 1m PLY found")
        return {"ok": True, "n_clusters": 0, "terrain_only": True}

    xyz    = _read_ply_xyz(in_path)
    labels = _cluster(xyz)
    n_clusters = int(labels.max()) + 1 if labels.max() >= 0 else 0

    np.savez_compressed(str(npz_path),
                        X=xyz[:, 0], Y=xyz[:, 1], Z=xyz[:, 2], cluster_id=labels)

    summary = _build_cluster_summary(xyz, labels)
    if summary:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            writer.writeheader()
            writer.writerows(summary)
    print(f"  [cluster] {n_clusters} clusters -> {npz_path.name}")

    return {"ok": True, "n_clusters": n_clusters, "terrain_only": n_clusters == 0}


# ── Stage 4: Footprints ────────────────────────────────────────────────────────

def _convex_hull_polygon(pts_xy: np.ndarray) -> Polygon | None:
    if len(pts_xy) < 3:
        return None
    try:
        from shapely.geometry import MultiPoint
        hull = MultiPoint(pts_xy.tolist()).convex_hull
        return hull if isinstance(hull, Polygon) and not hull.is_empty else None
    except Exception:
        return None


def _rotated_bbox_polygon(pts_xy: np.ndarray) -> Polygon | None:
    hull = _convex_hull_polygon(pts_xy)
    if hull is None:
        return None
    try:
        obb = hull.minimum_rotated_rectangle
        return obb if isinstance(obb, Polygon) and not obb.is_empty else None
    except Exception:
        return hull


def _cluster_quality(bbox_area: float) -> str:
    if bbox_area < 4.0:
        return "noise"
    if bbox_area > 200_000:
        return "oversized"
    return "ok"


def stage_footprints(out: Path, tile_id: str) -> dict:
    cluster_dir = out / "clusters"
    fp_dir      = out / "footprints"
    fp_dir.mkdir(parents=True, exist_ok=True)

    convex_path = fp_dir / f"{tile_id}_footprints_convex_32617.geojson"
    bbox_path   = fp_dir / f"{tile_id}_footprints_rotated_bbox_32617.geojson"

    if convex_path.exists() and bbox_path.exists():
        n = sum(1 for _ in json.loads(convex_path.read_text()).get("features", []))
        print(f"  [footprints] already done ({n} features), skip")
        return {"ok": True, "n_footprints": n}

    npz_path = cluster_dir / "building_clusters.npz"
    if not npz_path.exists():
        print("  [footprints] SKIP: no cluster data")
        return {"ok": True, "n_footprints": 0}

    npz = np.load(str(npz_path))
    X, Y, Z, labels = npz["X"], npz["Y"], npz["Z"], npz["cluster_id"]
    unique_ids = sorted(set(labels.tolist()) - {-1})

    convex_feats, bbox_feats = [], []

    for cid in unique_ids:
        mask   = labels == cid
        pts_xy = np.stack([X[mask], Y[mask]], axis=1)
        n_pts  = int(mask.sum())
        bbox_area = (
            float(pts_xy[:, 0].max() - pts_xy[:, 0].min()) *
            float(pts_xy[:, 1].max() - pts_xy[:, 1].min())
        )
        if _cluster_quality(bbox_area) == "noise":
            continue

        props_base = {
            "cluster_id":        int(cid),
            "point_count":       n_pts,
            "bbox_area_m2":      round(float(bbox_area), 2),
        }

        hull = _convex_hull_polygon(pts_xy)
        if hull:
            convex_feats.append({
                "type": "Feature",
                "properties": {**props_base,
                               "footprint_area_m2": round(hull.area, 2),
                               "footprint_method": "convex_hull"},
                "geometry": mapping(hull),
            })

        obb = _rotated_bbox_polygon(pts_xy)
        if obb:
            bbox_feats.append({
                "type": "Feature",
                "properties": {**props_base,
                               "footprint_area_m2": round(obb.area, 2),
                               "footprint_method": "rotated_bbox"},
                "geometry": mapping(obb),
            })

    def _write_gj(feats, path, name):
        path.write_text(json.dumps(
            {"type": "FeatureCollection", "name": name, "crs": CRS_TAG, "features": feats}
        ), encoding="utf-8")

    _write_gj(convex_feats, convex_path, f"{tile_id}_footprints_convex")
    _write_gj(bbox_feats,   bbox_path,   f"{tile_id}_footprints_rotated_bbox")
    n = len(convex_feats)
    print(f"  [footprints] {n} footprints -> {fp_dir.name}/")
    return {"ok": True, "n_footprints": n}


# ── Stage 5: Masses ────────────────────────────────────────────────────────────

def _shapely_pt(x, y):
    from shapely.geometry import Point
    return Point(float(x), float(y))


def _read_footprints(path: Path) -> tuple[list[Polygon], list[dict]]:
    if not path.exists():
        return [], []
    polys, props = [], []
    for feat in json.loads(path.read_text(encoding="utf-8")).get("features", []):
        from shapely.geometry import shape
        geom = shape(feat["geometry"])
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)
        if not isinstance(geom, Polygon) or geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        polys.append(geom)
        props.append(feat.get("properties", {}))
    return polys, props


def _estimate_heights(polys: list[Polygon], b_xyz: np.ndarray, g_xyz: np.ndarray) -> list[dict]:
    b_tree = cKDTree(b_xyz[:, :2])
    g_tree = cKDTree(g_xyz[:, :2])
    stats  = []

    for i, poly in enumerate(polys):
        if (i + 1) % 500 == 0:
            print(f"    heights {i+1}/{len(polys)}")

        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        r = float(np.hypot(maxx - cx, maxy - cy)) + CFG.RING_BUFFER_M

        b_idx = b_tree.query_ball_point([cx, cy], r=r)
        if b_idx:
            b_cand = b_xyz[b_idx]
            prep   = prepared_prep(poly)
            mask   = np.array([prep.contains_properly(_shapely_pt(x, y))
                               for x, y in b_cand[:, :2]])
            inside = b_cand[mask]
        else:
            inside = np.empty((0, 3))

        ring  = poly.buffer(CFG.RING_BUFFER_M).difference(poly)
        g_idx = g_tree.query_ball_point([cx, cy], r=r + CFG.RING_BUFFER_M)
        if g_idx:
            g_cand    = g_xyz[g_idx]
            prep_ring = prepared_prep(ring)
            g_mask    = np.array([prep_ring.contains(_shapely_pt(x, y))
                                  for x, y in g_cand[:, :2]])
            g_inside  = g_cand[g_mask]
        else:
            g_inside = np.empty((0, 3))

        if len(g_inside):
            ground_z = float(np.median(g_inside[:, 2]))
        else:
            _, ni = g_tree.query([cx, cy], k=min(8, len(g_xyz)))
            ground_z = float(np.median(g_xyz[np.atleast_1d(ni), 2]))

        if len(inside) >= CFG.MIN_POINTS_GOOD:
            zs = inside[:, 2]
            h90  = float(np.percentile(zs, 90))
            h95  = float(np.percentile(zs, 95))
            hmax = float(zs.max())
            est_h   = max(0.0, h90 - ground_z)
            quality = "good"
        elif len(inside):
            zs = inside[:, 2]
            h90  = float(np.percentile(zs, 90))
            h95  = float(np.percentile(zs, 95))
            hmax = float(zs.max())
            est_h   = max(0.0, h90 - ground_z)
            quality = "sparse"
        else:
            h90 = h95 = hmax = None
            est_h   = CFG.DEFAULT_FALLBACK_HEIGHT
            quality = "fallback"

        stats.append({
            "point_count_inside": int(len(inside)),
            "height_p90":         h90,
            "height_p95":         h95,
            "height_max":         hmax,
            "ground_z":           ground_z,
            "estimated_height":   est_h,
            "source_quality":     quality,
        })

    return stats


def _extrude_to_obj(f, vbase: int, ring, ztop: float, zbot: float, name: str) -> int:
    n = len(ring)
    if n < 3:
        return vbase
    ztop = max(ztop, zbot + 1.5)
    f.write(f"o {name}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
    f.write(f"f {' '.join(str(vbase+i+1) for i in range(n))}\n")
    f.write(f"f {' '.join(str(vbase+n+i+1) for i in reversed(range(n)))}\n")
    for i in range(n):
        a = vbase+i+1; b = vbase+((i+1)%n)+1
        c = vbase+n+((i+1)%n)+1; d = vbase+n+i+1
        f.write(f"f {a} {b} {c} {d}\n")
    return vbase + 2 * n


def _write_lod_obj(polys, stats, props, out_path: Path, lod_name: str,
                   tile_id: str, exclude_fallback: bool = True) -> int:
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# {lod_name}\n# tile: {tile_id}\n"
                "# CRS: EPSG:32617 (UTM 17N, meters)\n"
                "# source: USGS 3DEP FL_MiamiDade_D23 2024 (public domain)\n")
        vbase = 0
        for poly, s, p in zip(polys, stats, props):
            if exclude_fallback and s["source_quality"] in ("empty", "fallback"):
                continue
            ring = list(poly.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            gnd  = s["ground_z"] if s["ground_z"] is not None else 0.0
            ztop = s["height_p90"] if s["height_p90"] is not None else gnd + s["estimated_height"]
            cid  = p.get("cluster_id", n)
            vbase = _extrude_to_obj(f, vbase, ring, ztop, gnd, f"bld_{tile_id}_{cid}")
            n += 1
    return n


def stage_masses(out: Path, tile_id: str) -> dict:
    pc_dir   = out / "pointcloud"
    fp_dir   = out / "footprints"
    mass_dir = out / "masses"
    mass_dir.mkdir(parents=True, exist_ok=True)

    lod0_path = mass_dir / f"{tile_id}_LOD0_convexhull.obj"
    lod1_path = mass_dir / f"{tile_id}_LOD1_rotated_bbox.obj"

    if lod0_path.exists() and lod1_path.exists():
        print("  [masses] OBJ files exist, skip")
        return {"ok": True}

    convex_path = fp_dir / f"{tile_id}_footprints_convex_32617.geojson"
    bbox_path   = fp_dir / f"{tile_id}_footprints_rotated_bbox_32617.geojson"

    polys_cv, props_cv = _read_footprints(convex_path)
    polys_bb, props_bb = _read_footprints(bbox_path)

    if not polys_cv:
        print("  [masses] SKIP: no footprints found")
        return {"ok": True, "lod0": 0, "lod1": 0}

    # Building points (0.25m preferred for height accuracy)
    b_ply = pc_dir / f"{tile_id}_building_025m_clean.ply"
    if not b_ply.exists():
        b_ply = pc_dir / f"{tile_id}_building_025m.ply"
    if not b_ply.exists():
        b_ply = pc_dir / f"{tile_id}_building_1m_clean.ply"
    if not b_ply.exists():
        b_ply = pc_dir / f"{tile_id}_building_1m.ply"

    g_ply = pc_dir / f"{tile_id}_ground_1m.ply"

    if not b_ply.exists() or not g_ply.exists():
        print("  [masses] SKIP: PLY files missing")
        return {"ok": False}

    print(f"  [masses] reading PLY files…")
    b_xyz = _read_ply_xyz(b_ply)
    g_xyz = _read_ply_xyz(g_ply)

    print(f"  [masses] estimating heights for {len(polys_cv)} footprints…")
    stats_cv = _estimate_heights(polys_cv, b_xyz, g_xyz)

    # LOD1 (rotated bbox) uses the same height stats keyed by cluster_id
    stats_map = {s["source_quality"]: s for s in stats_cv}  # simple fallback
    cid_to_stats = {}
    for poly, s, p in zip(polys_cv, stats_cv, props_cv):
        cid = p.get("cluster_id")
        if cid is not None:
            cid_to_stats[int(cid)] = s
    stats_bb = []
    for p in props_bb:
        cid = p.get("cluster_id")
        stats_bb.append(cid_to_stats.get(int(cid), stats_cv[0] if stats_cv else {
            "source_quality": "fallback",
            "ground_z": 0.0,
            "height_p90": None,
            "estimated_height": CFG.DEFAULT_FALLBACK_HEIGHT,
        }))

    n_lod0 = _write_lod_obj(polys_cv, stats_cv, props_cv, lod0_path,
                             f"{tile_id}_LOD0_convexhull", tile_id, exclude_fallback=True)
    n_lod1 = _write_lod_obj(polys_bb, stats_bb, props_bb, lod1_path,
                             f"{tile_id}_LOD1_rotated_bbox", tile_id, exclude_fallback=False)

    # CSV metadata
    meta_csv = mass_dir / f"{tile_id}_masses_metadata.csv"
    if stats_cv and props_cv:
        rows = []
        for poly, s, p in zip(polys_cv, stats_cv, props_cv):
            cx, cy = poly.centroid.x, poly.centroid.y
            rows.append({
                "tile_id":            tile_id,
                "cluster_id":         p.get("cluster_id"),
                "centroid_x":         round(cx, 3),
                "centroid_y":         round(cy, 3),
                "footprint_area_m2":  round(poly.area, 2),
                "bbox_area_m2":       p.get("bbox_area_m2"),
                "ground_z":           s.get("ground_z"),
                "height_p90":         s.get("height_p90"),
                "estimated_height":   s.get("estimated_height"),
                "source_quality":     s.get("source_quality"),
                "lod0_included":      s.get("source_quality") not in ("empty", "fallback"),
                "lod1_included":      s.get("source_quality") not in ("empty",),
            })
        with meta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print(f"  [masses] LOD0={n_lod0}  LOD1={n_lod1} -> {mass_dir.name}/")
    return {"ok": True, "lod0": n_lod0, "lod1": n_lod1}


# ── Stage 6: Vegetation ────────────────────────────────────────────────────────

def stage_vegetation(laz_path: Path, out: Path, tile_id: str) -> dict:
    """Extract LiDAR vegetation classes (3/4/5) at 1 m spacing to PLY."""
    if not CFG.VEGETATION_ENABLED:
        return {"ok": True, "skipped": True, "n_pts": 0}

    pc_dir = out / "pointcloud"
    pc_dir.mkdir(parents=True, exist_ok=True)
    out_path = pc_dir / f"{tile_id}_vegetation_1m.ply"

    if out_path.exists():
        pts = out_path.stat().st_size // 28  # rough estimate (header + 3 doubles + int16 + uint8)
        print(f"  [vegetation] exists, skip")
        return {"ok": True, "n_pts": pts}

    arr = _run_pdal(_vegetation_steps(laz_path, 1.0))
    if arr is None or len(arr) == 0:
        print(f"  [vegetation] 0 points (no classes {CFG.VEGETATION_CLASSES} in tile)")
        return {"ok": True, "n_pts": 0}

    n = _write_ply(arr, out_path, "X,Y,Z,Intensity,Classification")
    print(f"  [vegetation] {n:,} pts → {out_path.name}")
    return {"ok": True, "n_pts": n}


# ── manifest ───────────────────────────────────────────────────────────────────

def _write_manifest(tile_id: str, out: Path, stage_results: dict, elapsed: float, errors: dict):
    manifest_dir = out / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{tile_id}_manifest.json"

    cluster_result = stage_results.get("cluster", {})
    mass_result    = stage_results.get("masses", {})

    veg_result = stage_results.get("vegetation", {})
    manifest = {
        "schema_version":  CFG.PIPELINE_VERSION,
        "pipeline":        "GlitchOS.io Miami city pipeline",
        "tile_id":         tile_id,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "elapsed_s":       round(elapsed, 1),
        "all_stages_passed": not errors,
        "terrain_only":    cluster_result.get("terrain_only", False),
        "building_mass_lod0":  mass_result.get("lod0"),
        "building_mass_lod1":  mass_result.get("lod1"),
        "n_clusters":      cluster_result.get("n_clusters", 0),
        "n_footprints":    stage_results.get("footprints", {}).get("n_footprints", 0),
        "n_vegetation_pts": veg_result.get("n_pts", 0),
        "vegetation_enabled": CFG.VEGETATION_ENABLED,
        "stages":          {k: ("ok" if v.get("ok") else "failed")
                            for k, v in stage_results.items()},
        "errors":          errors,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


# ── runner ─────────────────────────────────────────────────────────────────────

def run_tile(laz_path: Path, out: Path, stages: list[str], resume: bool = False) -> int:
    tile_id = laz_path.stem
    print(f"\n[tile] {tile_id}")
    print(f"  laz: {laz_path}")
    print(f"  out: {out}")

    out.mkdir(parents=True, exist_ok=True)
    stage_results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    t0_total = time.time()

    stage_fns = {
        "extract":    lambda: stage_extract(laz_path, out, tile_id),
        "clean":      lambda: stage_clean(out, tile_id),
        "cluster":    lambda: stage_cluster(out, tile_id),
        "footprints": lambda: stage_footprints(out, tile_id),
        "masses":     lambda: stage_masses(out, tile_id),
        "vegetation": lambda: stage_vegetation(laz_path, out, tile_id),
    }

    for stage_name in stages:
        fn = stage_fns.get(stage_name)
        if fn is None:
            continue

        # Resume: skip if manifest says this stage already passed
        if resume:
            manifest_path = out / "manifest" / f"{tile_id}_manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("stages", {}).get(stage_name) == "ok":
                    print(f"  [resume] {stage_name} already passed, skip")
                    stage_results[stage_name] = {"ok": True}
                    continue

        t0 = time.time()
        try:
            result = fn()
        except Exception as exc:
            import traceback
            result = {"ok": False}
            errors[stage_name] = str(exc)
            print(f"  [{stage_name}] ERROR: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

        stage_results[stage_name] = result
        if not result.get("ok", True):
            errors[stage_name] = errors.get(stage_name, "stage returned ok=False")

        elapsed_stage = time.time() - t0
        status = "OK" if result.get("ok", True) else "FAIL"
        print(f"  [{stage_name}] {status} ({elapsed_stage:.1f}s)")

    elapsed_total = time.time() - t0_total
    manifest_path = _write_manifest(tile_id, out, stage_results, elapsed_total, errors)
    print(f"  manifest -> {manifest_path}")
    print(f"  total: {elapsed_total/60:.1f} min  {'OK' if not errors else 'ERRORS: '+str(list(errors))}")

    return 0 if not errors else 1


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]

    laz_path = out_dir = None
    stages   = ALL_STAGES[:]
    resume   = "--resume" in args

    i = 0
    while i < len(args):
        if args[i] == "--laz" and i + 1 < len(args):
            laz_path = Path(args[i + 1]); i += 2
        elif args[i] == "--out" and i + 1 < len(args):
            out_dir = Path(args[i + 1]); i += 2
        elif args[i] == "--stages" and i + 1 < len(args):
            stages = []
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                stages.append(args[i]); i += 1
        else:
            i += 1

    if not laz_path or not out_dir:
        print("Usage: run_tile_miami.py --laz <path> --out <dir> [--stages ...] [--resume]")
        return 1
    if not laz_path.exists():
        print(f"ERROR: LAZ not found: {laz_path}", file=sys.stderr)
        return 1

    return run_tile(laz_path, out_dir, stages, resume=resume)


if __name__ == "__main__":
    sys.exit(main())
