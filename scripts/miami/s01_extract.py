"""
s01_extract.py  [Project Bikini — GlitchOS.io]

Extract building-candidate and ground points from the 16 Bikini LAZ tiles.

The FL_MiamiDade_D23 2024 dataset does NOT classify buildings as class 6.
All elevated structures are class 1 (Unclassified). Buildings are extracted
via height-above-ground (HAG) filtering:

  For each tile independently:
    1. Reproject to UTM 17N (EPSG:32617)
    2. Compute HeightAboveGround via filters.hag_nn (class 2 as ground reference)
    3. Keep class 1 points with HAG in [HAG_MIN_M, HAG_MAX_M] → building candidates
       OR keep class 2 points → ground reference
  Then accumulate all per-tile filtered arrays and write a single PLY output.

Processing tiles one at a time avoids the 43 GB peak caused by filters.merge
loading all 16 raw tiles simultaneously.

Outputs (data_processed/miami/bikini/pointcloud/):
  bikini_building_32617_0p25m.ply   HAG-filtered class 1, 0.25 m — height estimation
  bikini_building_32617_1m.ply      HAG-filtered class 1, 1.0 m  — DBSCAN clustering
  bikini_ground_32617_1m.ply        class 2, 1.0 m               — ground elevation

Usage:
    python scripts/miami/s01_extract.py
    python scripts/miami/s01_extract.py building025
    python scripts/miami/s01_extract.py building1
    python scripts/miami/s01_extract.py ground
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG
from metric_normalization_v1 import (
    MiamiMetricNormalizationConfig,
    SourceUnitError,
    build_profile_z_normalization_step,
    inspect_sources,
    write_provenance_envelope,
)

import numpy as np

# ── extraction targets ─────────────────────────────────────────────────────────

EXTRACTIONS = {
    "building025": {
        "mode":      "building",
        "spacing_m": 0.25,
        "out":       "bikini_building_32617_0p25m.ply",
        "dims":      "X,Y,Z,Intensity,HeightAboveGround",
        "note":      "class 1 HAG-filtered, 0.25 m — for height estimation",
    },
    "building1": {
        "mode":      "building",
        "spacing_m": 1.0,
        "out":       "bikini_building_32617_1m.ply",
        "dims":      "X,Y,Z,Intensity,HeightAboveGround",
        "note":      "class 1 HAG-filtered, 1.0 m — for DBSCAN clustering",
    },
    "ground": {
        "mode":      "ground",
        "spacing_m": 1.0,
        "out":       "bikini_ground_32617_1m.ply",
        "dims":      "X,Y,Z,Intensity,Classification",
        "note":      "class 2 ground, 1.0 m — for ground elevation reference",
    },
}

# PLY type map: PDAL dimension name → (PLY type string, numpy dtype)
_PLY_TYPES: dict[str, tuple[str, str]] = {
    "X":                 ("double", "<f8"),
    "Y":                 ("double", "<f8"),
    "Z":                 ("double", "<f8"),
    "Intensity":         ("uint16", "<u2"),
    "HeightAboveGround": ("double", "<f8"),
    "Classification":    ("uint8",  "u1"),
}

_UNIT_PROFILE: dict | None = None


# ── tile helpers ───────────────────────────────────────────────────────────────

def check_tiles() -> list[Path]:
    found, missing = [], []
    for fname in CFG.LAZ_TILES:
        p = CFG.LAZ_DIR / fname
        if p.exists():
            found.append(p)
        else:
            missing.append(fname)
    if missing:
        print(f"WARNING: {len(missing)} tile(s) not on disk — processing {len(found)} available:")
        for m in missing:
            print(f"  MISSING  {m}")
    if not found:
        print(f"ERROR: no LAZ tiles found under {CFG.LAZ_DIR}")
        print("  Run: python scripts/miami/download_bikini_tiles.py")
        sys.exit(1)
    return found


def inspect_source_units(tile_paths: list[Path]) -> dict:
    """Inspect LAZ CRS/units and return the vertical Z conversion profile."""
    config = MiamiMetricNormalizationConfig(
        enabled=bool(CFG.NORMALIZE_SOURCE_Z_TO_METERS),
        source_vertical_unit=CFG.METRIC_NORMALIZATION_CONFIG["source_vertical_unit"],
        target_vertical_unit=CFG.METRIC_NORMALIZATION_CONFIG["target_vertical_unit"],
        conversion_factor=CFG.METRIC_NORMALIZATION_CONFIG["conversion_factor"],
        normalization_version=CFG.METRIC_NORMALIZATION_CONFIG["normalization_version"],
        expected_source_horizontal_crs=CFG.METRIC_NORMALIZATION_CONFIG["expected_source_horizontal_crs"],
        expected_source_vertical_crs=CFG.METRIC_NORMALIZATION_CONFIG["expected_source_vertical_crs"],
    )
    return inspect_sources(tile_paths, config)


def _metric_normalization_step() -> list[dict]:
    if not CFG.NORMALIZE_SOURCE_Z_TO_METERS:
        return []
    if _UNIT_PROFILE is None:
        raise RuntimeError("unit profile was not initialized before building PDAL steps")
    return build_profile_z_normalization_step(_UNIT_PROFILE)


def _fixture_crop_step() -> list[dict]:
    bounds = getattr(CFG, "FIXTURE_CROP_BOUNDS_32617", None)
    if not bounds:
        return []
    return [{"type": "filters.crop", "bounds": bounds, "a_srs": f"EPSG:{CFG.OUT_EPSG}"}]


# ── single-tile PDAL pipelines (no writer — returns numpy array) ───────────────

def _building_steps(tile_path: Path, spacing_m: float) -> list[dict]:
    return [
        {"type": "readers.las", "filename": str(tile_path)},
        {"type": "filters.reprojection", "out_srs": f"EPSG:{CFG.OUT_EPSG}"},
        *_metric_normalization_step(),
        *_fixture_crop_step(),
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


def _ground_steps(tile_path: Path, spacing_m: float) -> list[dict]:
    return [
        {"type": "readers.las", "filename": str(tile_path)},
        {"type": "filters.reprojection", "out_srs": f"EPSG:{CFG.OUT_EPSG}"},
        *_metric_normalization_step(),
        *_fixture_crop_step(),
        {"type": "filters.range", "limits": f"Classification[{CFG.GROUND_CLASS}:{CFG.GROUND_CLASS}]"},
        {"type": "filters.sample", "radius": spacing_m},
    ]


def process_tile(tile_path: Path, mode: str, spacing_m: float) -> np.ndarray | None:
    """Run extraction pipeline on one tile. Returns filtered numpy array or None."""
    if mode == "building":
        steps = _building_steps(tile_path, spacing_m)
    else:
        steps = _ground_steps(tile_path, spacing_m)

    try:
        import pdal

        pipeline = pdal.Pipeline(json.dumps({"pipeline": steps}))
        n = pipeline.execute()
    except Exception as exc:
        print(f"    WARN: tile failed ({tile_path.name}): {exc}")
        return None

    if n == 0:
        return None
    return pipeline.arrays[0]


# ── PLY writer ─────────────────────────────────────────────────────────────────

def write_ply(arr: np.ndarray, out_path: Path, dims: str) -> int:
    """Write a PDAL numpy structured array to a binary-little-endian PLY file."""
    dim_list = [d.strip() for d in dims.split(",")]
    n = len(arr)

    header_lines = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {n}",
    ]
    for dim in dim_list:
        ply_type = _PLY_TYPES[dim][0]
        header_lines.append(f"property {ply_type} {dim}")
    header_lines.append("end_header")
    header = "\n".join(header_lines) + "\n"

    # Pack only the requested dimensions into a compact contiguous array
    dtype = [(dim, _PLY_TYPES[dim][1]) for dim in dim_list]
    packed = np.empty(n, dtype=dtype)
    for dim in dim_list:
        packed[dim] = arr[dim]

    with out_path.open("wb") as f:
        f.write(header.encode("ascii"))
        packed.tofile(f)

    return n


# ── runner ─────────────────────────────────────────────────────────────────────

def run_extraction(key: str, cfg: dict, tile_paths: list[Path]) -> int:
    out_path = CFG.PC_DIR / cfg["out"]
    mode     = cfg["mode"]
    spacing  = cfg["spacing_m"]

    print(f"\n[{key}]  {cfg['note']}")
    if mode == "building":
        print(f"  strategy: class {CFG.BUILDING_SOURCE_CLASS} + HAG [{CFG.HAG_MIN_M}m – {CFG.HAG_MAX_M}m]")
    else:
        print(f"  strategy: class {CFG.GROUND_CLASS} (ground)")
    print(f"  tiles: {len(tile_paths)}  ->  {out_path.name}")

    t0 = time.time()
    arrays: list[np.ndarray] = []
    total_raw = 0

    for i, tile in enumerate(tile_paths, 1):
        t1 = time.time()
        arr = process_tile(tile, mode, spacing)
        elapsed = time.time() - t1
        count = len(arr) if arr is not None else 0
        total_raw += count
        tag = f"({count:,} pts, {elapsed:.1f}s)"
        print(f"  [{i:2d}/{len(tile_paths)}] {tile.name}  {tag}")
        if arr is not None:
            arrays.append(arr)

    if not arrays:
        print(f"  WARNING: 0 points from all tiles — nothing written")
        return 0

    combined = np.concatenate(arrays)
    n_written = write_ply(combined, out_path, cfg["dims"])

    elapsed_total = time.time() - t0
    print(f"  wrote  {n_written:,} points  ({elapsed_total/60:.1f} min)")
    return n_written


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    global _UNIT_PROFILE
    tile_paths = check_tiles()
    if CFG.NORMALIZE_SOURCE_Z_TO_METERS:
        try:
            _UNIT_PROFILE = inspect_source_units(tile_paths)
        except (RuntimeError, SourceUnitError) as exc:
            print(f"ERROR: source unit inspection failed: {exc}")
            return 1
        CFG.SOURCE_Z_TO_METERS_FACTOR = float(_UNIT_PROFILE["z_to_meters_factor"])
        print("source units:")
        print(f"  horizontal: {_UNIT_PROFILE['source_horizontal_units']} -> metre via EPSG:{CFG.OUT_EPSG}")
        print(f"  vertical:   {_UNIT_PROFILE['source_vertical_unit']} -> metre")
        print(f"  z factor:   {_UNIT_PROFILE['z_to_meters_factor']}")
        print(f"  assign:     {_UNIT_PROFILE['pdal_assign_syntax']}")

    CFG.PC_DIR.mkdir(parents=True, exist_ok=True)
    CFG.META_DIR.mkdir(parents=True, exist_ok=True)
    CFG.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:]
    if args:
        targets = [a for a in args if a in EXTRACTIONS]
        unknown = [a for a in args if a not in EXTRACTIONS]
        if unknown:
            print(f"Unknown target(s): {unknown}  Valid: {list(EXTRACTIONS)}")
            return 1
    else:
        targets = list(EXTRACTIONS)

    log_lines = [
        "# s01_extract.py run log",
        f"# tiles: {len(tile_paths)}",
        f"# strategy: class {CFG.BUILDING_SOURCE_CLASS} + HAG [{CFG.HAG_MIN_M}–{CFG.HAG_MAX_M}m]",
        f"# ground class: {CFG.GROUND_CLASS}",
        f"# laz_dir: {CFG.LAZ_DIR}",
        f"# normalize_z_to_meters: {CFG.NORMALIZE_SOURCE_Z_TO_METERS}",
        f"# fixture_crop_bounds_32617: {getattr(CFG, 'FIXTURE_CROP_BOUNDS_32617', None)}",
    ]
    if _UNIT_PROFILE is not None:
        log_lines.extend([
            f"# source_horizontal_units: {_UNIT_PROFILE['source_horizontal_units']}",
            f"# source_vertical_unit: {_UNIT_PROFILE['source_vertical_unit']}",
            f"# target_horizontal_unit: {_UNIT_PROFILE['target_horizontal_unit']}",
            f"# target_vertical_unit: {_UNIT_PROFILE['target_vertical_unit']}",
            f"# z_to_meters_factor: {_UNIT_PROFILE['z_to_meters_factor']}",
            f"# pdal_assign_syntax: {_UNIT_PROFILE['pdal_assign_syntax']}",
        ])
        unit_path = CFG.META_DIR / "source_unit_profile.json"
        unit_path.write_text(json.dumps(_UNIT_PROFILE, indent=2), encoding="utf-8")
        log_lines.append(f"# source_unit_profile: {unit_path}")
        if CFG.NORMALIZE_SOURCE_Z_TO_METERS:
            provenance_path = CFG.META_DIR / "normalization_provenance.json"
            write_provenance_envelope(
                provenance_path,
                source_profile=_UNIT_PROFILE,
                laz_paths=tile_paths,
                repo_root=Path(__file__).resolve().parents[2],
                output_root=CFG.OUT_ROOT,
                config=MiamiMetricNormalizationConfig(
                    enabled=True,
                    source_vertical_unit=CFG.METRIC_NORMALIZATION_CONFIG["source_vertical_unit"],
                    target_vertical_unit=CFG.METRIC_NORMALIZATION_CONFIG["target_vertical_unit"],
                    conversion_factor=CFG.METRIC_NORMALIZATION_CONFIG["conversion_factor"],
                    normalization_version=CFG.METRIC_NORMALIZATION_CONFIG["normalization_version"],
                    expected_source_horizontal_crs=CFG.METRIC_NORMALIZATION_CONFIG["expected_source_horizontal_crs"],
                    expected_source_vertical_crs=CFG.METRIC_NORMALIZATION_CONFIG["expected_source_vertical_crs"],
                ),
            )
            log_lines.append(f"# normalization_provenance: {provenance_path}")
    total_t0 = time.time()

    for key in targets:
        n = run_extraction(key, EXTRACTIONS[key], tile_paths)
        log_lines.append(f"{key}: {n} points")

    elapsed_total = time.time() - total_t0
    log_lines.append(f"total_elapsed_min: {elapsed_total/60:.1f}")

    log_path = CFG.NOTES_DIR / "_s01_run.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"\nLog -> {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
