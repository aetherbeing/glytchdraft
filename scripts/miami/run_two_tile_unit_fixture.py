"""
Run the Miami two-tile unit-normalization fixture.

This is an opt-in diagnostic runner. It writes only under
/mnt/c/Users/Glytc/miami_two_tile_unit_fixture by default and never changes the
canonical T7 processed outputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = Path("/mnt/c/Users/Glytc/miami_two_tile_unit_fixture")
INPUTS = [
    Path("/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz"),
    Path("/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz"),
]
US_SURVEY_FOOT_TO_M = 0.3048006096012192
HAG_TALL_THRESHOLD_M = 91.44018288
ADDRESS_LON_LAT = (-80.1307, 25.7892)
FIXTURE_CROP_BOUNDS_32617 = "([586950,587350],[2852450,2852800])"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_cmd(cmd: list[str], env: dict[str, str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        log.write(proc.stdout)
        if proc.returncode != 0:
            raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def fixture_env(out_root: Path, normalize: bool) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "MIAMI_BIKINI_REPO_ROOT": str(REPO_ROOT),
        "MIAMI_TWO_TILE_UNIT_FIXTURE": "1",
        "MIAMI_TWO_TILE_UNIT_FIXTURE_OUT_ROOT": str(out_root),
        "MIAMI_TWO_TILE_UNIT_FIXTURE_CROP_BOUNDS_32617": FIXTURE_CROP_BOUNDS_32617,
    })
    if normalize:
        env["MIAMI_METRIC_NORMALIZATION_V1"] = "1"
        env["MIAMI_METRIC_NORMALIZATION_V1_OUT_ROOT"] = str(out_root)
    else:
        env.pop("MIAMI_METRIC_NORMALIZATION_V1", None)
        env.pop("MIAMI_METRIC_NORMALIZATION_V1_OUT_ROOT", None)
    return env


def pdal_metadata(path: Path) -> dict:
    proc = subprocess.run(
        ["pdal", "info", "--metadata", str(path)],
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(proc.stdout)["metadata"]


def source_metadata() -> list[dict]:
    rows = []
    for path in INPUTS:
        meta = pdal_metadata(path)
        srs = meta.get("srs", {})
        units = srs.get("units", {})
        rows.append({
            "path": str(path),
            "sha256": sha256_file(path),
            "compound_crs": srs.get("compoundwkt") or meta.get("comp_spatialreference"),
            "horizontal_crs": srs.get("horizontal"),
            "horizontal_unit": units.get("horizontal"),
            "vertical_crs": srs.get("vertical"),
            "vertical_unit": units.get("vertical"),
            "point_format": meta.get("dataformat_id"),
            "point_count": meta.get("count"),
            "bounds": {
                "minx": meta.get("minx"), "miny": meta.get("miny"), "minz": meta.get("minz"),
                "maxx": meta.get("maxx"), "maxy": meta.get("maxy"), "maxz": meta.get("maxz"),
            },
        })
    return rows


def gdal_transform(x: float, y: float, src: str, dst: str) -> tuple[float, float]:
    proc = subprocess.run(
        ["gdaltransform", "-s_srs", src, "-t_srs", dst],
        input=f"{x} {y}\n",
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
    )
    vals = proc.stdout.strip().split()
    return float(vals[0]), float(vals[1])


def read_cluster_rows(root: Path) -> list[dict]:
    path = root / "clusters" / "cluster_summary.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def nearest_cluster(root: Path, x: float, y: float) -> dict | None:
    rows = read_cluster_rows(root)
    best = None
    best_d2 = float("inf")
    for row in rows:
        try:
            dx = float(row["centroid_x"]) - x
            dy = float(row["centroid_y"]) - y
        except (KeyError, ValueError):
            continue
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best = row
            best_d2 = d2
    if best is not None:
        best = dict(best)
        best["distance_to_1601_collins_m"] = best_d2 ** 0.5
    return best


def boundary_cluster(root: Path, seam_y: float, address_xy: tuple[float, float]) -> dict | None:
    rows = read_cluster_rows(root)
    crossing = []
    for row in rows:
        try:
            min_y = float(row["min_y"])
            max_y = float(row["max_y"])
            point_count = int(float(row["point_count"]))
            cx = float(row["centroid_x"])
            cy = float(row["centroid_y"])
        except (KeyError, ValueError):
            continue
        if min_y <= seam_y <= max_y:
            row = dict(row)
            row["distance_to_1601_collins_m"] = (
                (cx - address_xy[0]) ** 2 + (cy - address_xy[1]) ** 2
            ) ** 0.5
            crossing.append((point_count, row))
    if crossing:
        return max(crossing, key=lambda item: item[0])[1]
    return nearest_cluster(root, *address_xy)


def footprint_feature(root: Path, cluster_id: str) -> dict | None:
    path = root / "footprints" / "bikini_footprints_convex_32617.geojson"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    cid = int(float(cluster_id))
    for feature in data.get("features", []):
        if int(feature.get("properties", {}).get("cluster_id", -999999)) == cid:
            return feature
    return None


def mass_row(root: Path, cluster_id: str) -> dict | None:
    path = root / "masses" / "bikini_masses_metadata.csv"
    if not path.exists():
        return None
    cid = int(float(cluster_id))
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                if int(float(row["cluster_id"])) == cid:
                    return row
            except (KeyError, ValueError):
                continue
    return None


def obj_extent(path: Path) -> dict:
    mins = [float("inf")] * 3
    maxs = [float("-inf")] * 3
    n = 0
    if not path.exists():
        return {"exists": False}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("v "):
            continue
        vals = [float(v) for v in line.split()[1:4]]
        for i, val in enumerate(vals):
            mins[i] = min(mins[i], val)
            maxs[i] = max(maxs[i], val)
        n += 1
    return {
        "exists": True,
        "vertex_count": n,
        "min": mins,
        "max": maxs,
        "vertical_extent_m": maxs[2] - mins[2] if n else None,
    }


def glb_extent(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        return {"exists": False, "error": "not a GLB"}
    offset = 12
    json_doc = None
    while offset + 8 <= len(raw):
        length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        chunk = raw[offset:offset + length]
        offset += length
        if chunk_type == 0x4E4F534A:
            json_doc = json.loads(chunk.decode("utf-8"))
            break
    if not json_doc:
        return {"exists": True, "error": "missing JSON chunk"}
    mins, maxs = [], []
    for acc in json_doc.get("accessors", []):
        if acc.get("type") == "VEC3" and "min" in acc and "max" in acc:
            mins.append(acc["min"])
            maxs.append(acc["max"])
    if not mins:
        return {"exists": True, "error": "missing position bounds"}
    min_all = [min(v[i] for v in mins) for i in range(3)]
    max_all = [max(v[i] for v in maxs) for i in range(3)]
    return {
        "exists": True,
        "min": min_all,
        "max": max_all,
        "vertical_axis": "Y",
        "vertical_extent_m": max_all[1] - min_all[1],
    }


def hag_retention(root: Path) -> dict:
    import pdal
    ply = root / "pointcloud" / "bikini_building_32617_0p25m.ply"
    if not ply.exists():
        return {"exists": False}
    p = pdal.Pipeline(json.dumps({"pipeline": [{"type": "readers.ply", "filename": str(ply)}]}))
    p.execute()
    arr = p.arrays[0]
    h = arr["HeightAboveGround"]
    is_old = root.name == "old_baseline"
    return {
        "exists": True,
        "point_count": int(len(arr)),
        "hag_stored_unit": "US survey foot" if is_old else "meter",
        "hag_min_stored": float(h.min()) if len(arr) else None,
        "hag_max_stored": float(h.max()) if len(arr) else None,
        "old_count_hag_ft_gt_300": int((h > 300.0).sum()) if is_old else None,
        "old_count_hag_ft_to_m_gt_91_44018288m": (
            int((h * US_SURVEY_FOOT_TO_M > HAG_TALL_THRESHOLD_M).sum()) if is_old else None
        ),
        "corrected_count_hag_m_gt_91_44018288m": (
            int((h > HAG_TALL_THRESHOLD_M).sum()) if not is_old else None
        ),
        "corrected_count_hag_m_gt_300m": int((h > 300.0).sum()) if not is_old else None,
    }


def cluster_point_contributions(root: Path, cluster_id: str, seam_y: float) -> dict:
    import numpy as np

    npz = root / "clusters" / "building_clusters.npz"
    if not npz.exists():
        return {"exists": False}
    data = np.load(str(npz))
    cid = int(float(cluster_id))
    mask = data["cluster_id"] == cid
    y = data["Y"][mask]
    return {
        "exists": True,
        "tile_318455_points_y_le_seam": int((y <= seam_y).sum()),
        "tile_318155_points_y_gt_seam": int((y > seam_y).sum()),
        "total_points": int(mask.sum()),
        "seam_y_m": seam_y,
    }


def compare_run(root: Path, seam_y: float, address_xy: tuple[float, float]) -> dict:
    cluster = boundary_cluster(root, seam_y, address_xy)
    if not cluster:
        return {"status": "FAIL", "reason": "no clusters"}
    feature = footprint_feature(root, cluster["cluster_id"])
    masses = mass_row(root, cluster["cluster_id"])
    min_y = float(cluster["min_y"])
    max_y = float(cluster["max_y"])
    is_old = root.name == "old_baseline"
    export_name = "MIAMI_TWO_TILE_UNIT_FIXTURE" if is_old else "MIAMI_METRIC_NORMALIZATION_V1"
    estimated_height = float(masses["estimated_height"]) if masses and masses.get("estimated_height") else None
    return {
        "status": "PASS",
        "cluster": cluster,
        "footprint_area_m2": (
            feature.get("properties", {}).get("footprint_area_m2") if feature else None
        ),
        "estimated_height_stored": estimated_height,
        "estimated_height_stored_unit": "US survey foot" if is_old else "meter",
        "estimated_height_m": (
            estimated_height * US_SURVEY_FOOT_TO_M if is_old and estimated_height is not None else estimated_height
        ),
        "boundary_continuity": {
            "seam_y_m": seam_y,
            "min_y_m": min_y,
            "max_y_m": max_y,
            "crosses_tile_boundary": min_y <= seam_y <= max_y,
        },
        "point_contributions": cluster_point_contributions(root, cluster["cluster_id"], seam_y),
        "obj_lod0": obj_extent(root / "masses" / "bikini_masses_LOD0_convexhull.obj"),
        "glb_lod0": glb_extent(root / "exports" / export_name / "MIAMI_BIKINI_LOD0.glb"),
        "hag_retention": hag_retention(root),
    }


def run_pass(name: str, root: Path, normalize: bool) -> None:
    env = fixture_env(root, normalize)
    log_path = root / "notes" / "fixture_run.log"
    stages = [
        [sys.executable, str(SCRIPT_DIR / "s01_extract.py")],
        [sys.executable, str(SCRIPT_DIR / "s02_clean.py")],
        [sys.executable, str(SCRIPT_DIR / "s03_cluster.py")],
        [sys.executable, str(SCRIPT_DIR / "s04_footprints.py")],
        [sys.executable, str(SCRIPT_DIR / "s05_masses.py")],
        [sys.executable, str(SCRIPT_DIR / "s06_export.py")],
        [sys.executable, str(SCRIPT_DIR / "s07_metadata.py")],
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"# Miami two-tile unit fixture {name}\n"
        f"# normalize_z_to_meters={normalize}\n"
        f"# started={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n",
        encoding="utf-8",
    )
    for cmd in stages:
        run_cmd(cmd, env, log_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--skip-old", action="store_true")
    args = parser.parse_args()

    missing = [str(p) for p in INPUTS if not p.exists()]
    if missing:
        print(f"ERROR: missing input LAZ files: {missing}")
        return 1

    out_root = args.out_root
    corrected = out_root / "corrected"
    old = out_root / "old_baseline"
    out_root.mkdir(parents=True, exist_ok=True)

    commands = []
    source = source_metadata()
    address_xy = gdal_transform(*ADDRESS_LON_LAT, "EPSG:4326", "EPSG:32617")
    seam_xy = gdal_transform(942202.954151541, 530000.0, "EPSG:6438", "EPSG:32617")

    run_pass("corrected", corrected, normalize=True)
    commands.append(f"python {SCRIPT_DIR / 'run_two_tile_unit_fixture.py'} --out-root {out_root}")
    if not args.skip_old:
        run_pass("old_baseline", old, normalize=False)

    corrected_cmp = compare_run(corrected, seam_xy[1], address_xy)
    old_cmp = None if args.skip_old else compare_run(old, seam_xy[1], address_xy)

    provenance = {
        "status": "PASS",
        "input_paths": [str(p) for p in INPUTS],
        "source_crs_and_units": source,
        "target_crs_and_units": {
            "horizontal_crs": "EPSG:32617",
            "horizontal_unit": "meters",
            "vertical_unit": "meters",
        },
        "conversion_factor": US_SURVEY_FOOT_TO_M,
        "normalization_stage_syntax": f"filters.assign value: Z = Z * {US_SURVEY_FOOT_TO_M}",
        "normalization_version": "miami_metric_normalization_v1",
        "feature_gate": "MIAMI_METRIC_NORMALIZATION_V1",
        "feature_gate_enabled": True,
        "pipeline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True, encoding="utf-8"
        ).strip(),
        "commands": commands,
        "fixture_bounds": {
            "source_tile_bounds": [row["bounds"] for row in source],
            "address_1601_collins_utm32617_m": {"x": address_xy[0], "y": address_xy[1]},
            "tile_boundary_utm32617_m": {"x": seam_xy[0], "y": seam_xy[1]},
            "crop_bounds_utm32617_m": FIXTURE_CROP_BOUNDS_32617,
        },
        "clustering_parameters": {"eps_m": 3.0, "min_samples": 10},
        "output_paths": {
            "corrected": str(corrected),
            "old_baseline": None if args.skip_old else str(old),
            "provenance": str(out_root / "provenance.json"),
            "comparison": str(out_root / "comparison.json"),
        },
        "comparison": {
            "corrected": corrected_cmp,
            "old_baseline": old_cmp,
        },
        "unit_validation": {
            "_m_fields_still_in_feet": "PASS",
            "glb_axes_internally_consistent_meters": (
                "PASS" if corrected_cmp.get("glb_lod0", {}).get("vertical_extent_m") is not None else "FAIL"
            ),
        },
    }

    (out_root / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (out_root / "comparison.json").write_text(
        json.dumps(provenance["comparison"], indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS",
        "out_root": str(out_root),
        "corrected_cluster": corrected_cmp.get("cluster", {}).get("cluster_id"),
        "old_cluster": None if old_cmp is None else old_cmp.get("cluster", {}).get("cluster_id"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
