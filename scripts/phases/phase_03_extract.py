#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time

from phase_common import (
    CityRuntime,
    MIAMI_Z_TO_METERS_FACTOR,
    add_phase_args,
    load_city,
    print_header,
    resolve_mode,
)
from phase_tile_common import (
    cfg_value, ensure_tile_dirs, existing, load_tiles, out_epsg, output_summary,
    require_execute, run_pdal_array, should_skip_phase, validate_or_fail, write_ply,
    write_empty_ply, write_tile_manifest,
)


PHASE_ID = "03"
TITLE = "extract ground, building, and vegetation points"

# Cities with a source-contract requiring explicit Z normalization before metric
# operations. A city in this set must carry a valid laz_source_contract;
# falling back silently to an ungoverned pipeline without normalization is refused.
_GOVERNED_CITY_IDS: frozenset[str] = frozenset({"miami", "miami_city"})


def _laz_source_contract(city: CityRuntime) -> dict | None:
    """Return the laz_source_contract dict from city runtime, or None if absent."""
    return getattr(city.raw_config, "LAZ_SOURCE_CONTRACT", None)


def _is_governed(city: CityRuntime) -> bool:
    """Return True when the city carries a Z normalization contract with required=true."""
    contract = _laz_source_contract(city)
    if not isinstance(contract, dict):
        return False
    z_conv = contract.get("z_conversion")
    return isinstance(z_conv, dict) and z_conv.get("required") is True


def _validate_governed_contract(city: CityRuntime) -> None:
    """
    Validate city-level source contract fields for governed processing.
    Raises RuntimeError on any violation; always fail-closed.
    """
    contract = _laz_source_contract(city)
    if not isinstance(contract, dict):
        raise RuntimeError(
            f"City {city.city_id!r} requires a governed Z normalization contract "
            "but laz_source_contract is missing or not a dict."
        )

    # Reject the address CRS (EPSG:3857) being used as the LiDAR source CRS.
    src_crs = contract.get("source_horizontal_crs")
    if src_crs == "EPSG:3857":
        raise RuntimeError(
            f"Governed city {city.city_id!r}: source_horizontal_crs is EPSG:3857 "
            "(address CRS / Web Mercator), not the LiDAR source CRS. "
            "Miami LiDAR horizontal source is EPSG:6438."
        )

    xy_units = contract.get("source_xy_units")
    if xy_units != "US survey foot":
        raise RuntimeError(
            f"Governed city {city.city_id!r}: source_xy_units={xy_units!r}; "
            "expected 'US survey foot'."
        )

    z_units = contract.get("source_z_units")
    if z_units != "US survey foot":
        raise RuntimeError(
            f"Governed city {city.city_id!r}: source_z_units={z_units!r}; "
            "expected 'US survey foot'."
        )

    factor = contract.get("z_to_meters_factor")
    if factor is None:
        raise RuntimeError(
            f"Governed city {city.city_id!r}: z_to_meters_factor is missing."
        )
    if factor != MIAMI_Z_TO_METERS_FACTOR:
        raise RuntimeError(
            f"Governed city {city.city_id!r}: z_to_meters_factor={factor!r}; "
            f"expected {MIAMI_Z_TO_METERS_FACTOR!r}."
        )

    z_conv = contract.get("z_conversion")
    if not isinstance(z_conv, dict):
        raise RuntimeError(
            f"Governed city {city.city_id!r}: z_conversion block is missing or not a dict."
        )
    stage = z_conv.get("stage")
    if stage != "filters.assign":
        raise RuntimeError(
            f"Governed city {city.city_id!r}: z_conversion.stage={stage!r}; "
            "expected 'filters.assign'."
        )
    expected_value = f"Z = Z * {MIAMI_Z_TO_METERS_FACTOR}"
    stage_value = z_conv.get("stage_value")
    if stage_value != expected_value:
        raise RuntimeError(
            f"Governed city {city.city_id!r}: z_conversion.stage_value={stage_value!r}; "
            f"expected {expected_value!r}."
        )


def _validate_governed_pipeline_steps(city: CityRuntime, steps: list[dict]) -> None:
    """
    Validate pipeline step ordering for governed Z normalization.
    Raises RuntimeError on absence, duplication, wrong factor, or wrong position.
    """
    types = [s["type"] for s in steps]
    assign_count = sum(1 for t in types if t == "filters.assign")

    if assign_count == 0:
        raise RuntimeError(
            f"Z normalization stage (filters.assign) missing from governed "
            f"{city.city_id!r} pipeline. Source Z is in US survey feet; "
            "all metric operations will be incorrect."
        )
    if assign_count > 1:
        raise RuntimeError(
            f"Duplicate Z normalization stages ({assign_count}) in governed "
            f"{city.city_id!r} pipeline. Z must be converted exactly once."
        )

    assign_idx = types.index("filters.assign")

    if "filters.reprojection" not in types:
        raise RuntimeError(
            f"filters.reprojection missing from governed {city.city_id!r} pipeline."
        )
    reproj_idx = types.index("filters.reprojection")
    if reproj_idx >= assign_idx:
        raise RuntimeError(
            f"Z normalization must appear after filters.reprojection in governed "
            f"{city.city_id!r} pipeline (XY reprojection does not normalize Z)."
        )

    if "filters.hag_nn" in types:
        hag_idx = types.index("filters.hag_nn")
        if assign_idx >= hag_idx:
            raise RuntimeError(
                f"Z normalization must appear before filters.hag_nn in governed "
                f"{city.city_id!r} pipeline (HAG computation requires metric Z)."
            )

    if "filters.range" in types:
        range_idx = types.index("filters.range")
        if assign_idx >= range_idx:
            raise RuntimeError(
                f"Z normalization must appear before filters.range in governed "
                f"{city.city_id!r} pipeline (metric range filtering requires metric Z)."
            )

    contract = _laz_source_contract(city)
    if isinstance(contract, dict):
        z_conv = contract.get("z_conversion") or {}
        expected_value = z_conv.get("stage_value") or f"Z = Z * {MIAMI_Z_TO_METERS_FACTOR}"
    else:
        expected_value = f"Z = Z * {MIAMI_Z_TO_METERS_FACTOR}"

    actual_value = steps[assign_idx].get("value", "")
    if actual_value != expected_value:
        raise RuntimeError(
            f"Z normalization value mismatch in governed {city.city_id!r} pipeline: "
            f"expected {expected_value!r}, found {actual_value!r}."
        )


def _steps(city, laz_path, mode: str, spacing: float) -> list[dict]:
    # Refuse governed city IDs that are missing a valid contract before building
    # any pipeline. This prevents silent fallback to un-normalized processing.
    if city.city_id in _GOVERNED_CITY_IDS and not _is_governed(city):
        raise RuntimeError(
            f"City {city.city_id!r} is a governed city but has no valid "
            "laz_source_contract with z_conversion.required=true. "
            "Refusing to fall back to an ungoverned pipeline."
        )

    epsg = out_epsg(city)
    governed = _is_governed(city)

    if governed:
        _validate_governed_contract(city)
        contract = _laz_source_contract(city)
        factor = contract["z_to_meters_factor"]
        z_norm_step: list[dict] = [{"type": "filters.assign", "value": f"Z = Z * {factor}"}]
    else:
        z_norm_step = []

    if mode == "building":
        src_class = int(cfg_value(city, "BUILDING_SOURCE_CLASS", 1))
        hag_min = float(cfg_value(city, "HAG_MIN_M", 2.5))
        hag_max = float(cfg_value(city, "HAG_MAX_M", 300.0))
        limits = f"Classification[{src_class}:{src_class}],HeightAboveGround[{hag_min}:{hag_max}]"
        steps = [
            {"type": "readers.las", "filename": str(laz_path)},
            {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
            *z_norm_step,
            {"type": "filters.hag_nn"},
            {"type": "filters.range", "limits": limits},
            {"type": "filters.sample", "radius": spacing},
        ]
    elif mode == "ground":
        ground_class = int(cfg_value(city, "GROUND_CLASS", 2))
        limits = f"Classification[{ground_class}:{ground_class}]"
        steps = [
            {"type": "readers.las", "filename": str(laz_path)},
            {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
            *z_norm_step,
            {"type": "filters.range", "limits": limits},
            {"type": "filters.sample", "radius": spacing},
        ]
    else:  # vegetation
        classes = cfg_value(city, "VEGETATION_CLASSES", (3, 4, 5))
        limits = f"Classification[{min(classes)}:{max(classes)}]"
        steps = [
            {"type": "readers.las", "filename": str(laz_path)},
            {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
            *z_norm_step,
            {"type": "filters.range", "limits": limits},
            {"type": "filters.sample", "radius": spacing},
        ]

    if governed:
        _validate_governed_pipeline_steps(city, steps)

    return steps


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
    vegetation_enabled = bool(cfg_value(city, "VEGETATION_ENABLED", True))
    if not require_execute(args):
        for tile in tiles:
            print(f"  {tile.tile_id}: vegetation_enabled={vegetation_enabled}")
            print(f"  would extract: {tile.tile_id} -> {tile.tile_dir / 'pointcloud'}")
        return 0

    targets = [
        ("building_1m", "building", 1.0, "_building_1m.ply", "X,Y,Z,Intensity,HeightAboveGround"),
        ("building_025m", "building", 0.25, "_building_025m.ply", "X,Y,Z,Intensity,HeightAboveGround"),
        ("ground_1m", "ground", 1.0, "_ground_1m.ply", "X,Y,Z,Intensity,Classification"),
    ]
    if vegetation_enabled:
        targets.append(("vegetation_1m", "vegetation", 1.0, "_vegetation_1m.ply", "X,Y,Z,Intensity,Classification"))
    else:
        print("  vegetation extraction disabled by VEGETATION_ENABLED")
    for tile in tiles:
        ensure_tile_dirs(tile)
        print(f"  {tile.tile_id}: vegetation_enabled={vegetation_enabled}")
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
                if mode == "vegetation":
                    classes = cfg_value(city, "VEGETATION_CLASSES", (3, 4, 5))
                    print(f"  {tile.tile_id}: running vegetation extraction classes={tuple(classes)} -> {out.name}")
                arr = run_pdal_array(_steps(city, tile.laz_path, mode, spacing))
                n = write_empty_ply(out, dims) if arr is None else write_ply(arr, out, dims)
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
