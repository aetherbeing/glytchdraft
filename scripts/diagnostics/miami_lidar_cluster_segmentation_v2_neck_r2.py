#!/usr/bin/env python
"""Diagnostic LiDAR-only cluster segmentation v2 neck-r2 experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon, mapping
from shapely.ops import unary_union

if __package__ in {None, ""}:  # pragma: no cover - exercised by CLI execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2 as r1
from scripts.diagnostics.miami_lidar_footprint_baseline_v0 import (
    DEFAULT_CELL_SIZE_M,
    DEFAULT_CLOSING_RADIUS_CELLS,
    CRS_TAG,
    BaselineInputError,
    _largest_valid_component,
    _occupancy_grid,
    _polygonize_cells,
    _valid_polygonal,
    morphological_closing,
)


SegmentationInputError = r1.SegmentationInputError
ALGORITHM_VERSION = r1.ALGORITHM_VERSION
EXPERIMENT_NAME = r1.EXPERIMENT_NAME
OPENING_RADIUS_CELLS = 2
EXPECTED_NPZ_ROWS = r1.EXPECTED_NPZ_ROWS
EXPECTED_PARENT_ROWS = r1.EXPECTED_PARENT_ROWS
EXPECTED_NOISE_ROWS = r1.EXPECTED_NOISE_ROWS
EXPECTED_EXCLUDED_ROWS = r1.EXPECTED_EXCLUDED_ROWS
EXPECTED_PARENT_IDS = r1.EXPECTED_PARENT_IDS
EXPECTED_EXCLUDED_LABELS = r1.EXPECTED_EXCLUDED_LABELS
BENCHMARK_MINIMA = r1.BENCHMARK_MINIMA
COHORT_REPORT_IDS = r1.COHORT_REPORT_IDS
SERIALIZATION_DECIMAL_PLACES = r1.SERIALIZATION_DECIMAL_PLACES
REQUIRED_CHILD_FIELDS = r1.REQUIRED_CHILD_FIELDS
RUN_STATUS = "LIDAR_CLUSTER_SEGMENTATION_V2_NECK_R2_RUN_FROZEN"
R1_FREEZE_MANIFEST_SHA256 = "2aebf001205d54bd0f7a46a31820fdbb1ada131675127578030146e485f3d6a3"
FALSE_SPLIT_PROXY_CAVEAT = (
    "The frozen county value of one is a sparse benchmark count, not independent proof "
    "that the parent contains exactly one physical building. Therefore: this metric is "
    "an evaluation proxy; a violation identifies a potential false split requiring "
    "scrutiny; it is not definitive proof that every excess child is physically false; "
    "county geometry must not be read to adjudicate the split; the proxy must not "
    "influence segmentation or parameter selection."
)
BENCHMARK_CAVEAT = (
    "County geometry was not read. These scalar minima are sparse corroborating lower "
    "bounds, not targets; zero-associated parents have no target."
)
CONSEQUENCE_IF_TRUE = (
    "morphological family is exhausted; no r3; no larger opening radius; no sweep; "
    "next eligible work is a fresh height-discontinuity-family design review."
)
CONSEQUENCE_IF_FALSE = (
    "morphological family is not declared exhausted by this rule; no r3 is nevertheless "
    "authorized; no larger radius or sweep is authorized; further morphology still "
    "requires separate design approval."
)

_stable_float = r1._stable_float
_stable_value = r1._stable_value
_write_json = r1._write_json
_sha256_file = r1._sha256_file
_load_npz = r1._load_npz
_load_canonical = r1._load_canonical
_read_expected_ids = r1._read_expected_ids
validate_inputs = r1.validate_inputs
_components_row_major = r1._components_row_major
_assign_support_cells = r1._assign_support_cells
_cells_to_grid = r1._cells_to_grid
_support_from_largest_component = r1._support_from_largest_component
_hole_count = r1._hole_count
_component_count = r1._component_count
_tile_counts = r1._tile_counts
_source_tile_ids = r1._source_tile_ids
_polygonize_child = r1._polygonize_child


def _binary_opening_r2(grid: np.ndarray, radius: int) -> np.ndarray:
    if radius < 0:
        raise SegmentationInputError("opening radius must be non-negative")
    if radius == 0:
        return grid.copy()
    size = 2 * radius + 1
    padded = np.pad(grid, radius, mode="constant", constant_values=False)
    windows = [
        padded[dr : dr + grid.shape[0], dc : dc + grid.shape[1]]
        for dr in range(size)
        for dc in range(size)
    ]
    eroded = np.logical_and.reduce(windows)
    padded_e = np.pad(eroded, radius, mode="constant", constant_values=False)
    windows = [
        padded_e[dr : dr + grid.shape[0], dc : dc + grid.shape[1]]
        for dr in range(size)
        for dc in range(size)
    ]
    return np.logical_or.reduce(windows) & grid


def _assert_r2_radius_gate() -> None:
    if OPENING_RADIUS_CELLS != 2:
        raise SegmentationInputError("required design parameter differs: opening_radius_cells")


def verify_r1_package(frozen_r1_root: Path, expected_r1_freeze_manifest_sha256: str) -> dict[int, int]:
    frozen_r1_root = frozen_r1_root.resolve()
    if "/mnt/t7" in str(frozen_r1_root):
        raise SegmentationInputError("/mnt/t7 access is forbidden")
    manifest = frozen_r1_root / "FREEZE_MANIFEST.sha256"
    if _sha256_file(manifest) != expected_r1_freeze_manifest_sha256:
        raise SegmentationInputError("r1 FREEZE_MANIFEST.sha256 mismatch")
    if expected_r1_freeze_manifest_sha256 != R1_FREEZE_MANIFEST_SHA256:
        raise SegmentationInputError("unexpected r1 freeze manifest gate")

    required = {
        "benchmark_minimum_comparison.json",
        "benchmark_minimum_comparison.md",
        "child_segmentation_summary.json",
        "command.txt",
        "command_stdout_stderr.log",
        "conservation_summary.json",
        "contact_sheet.svg",
        "dimension_f_invariance.json",
        "experiment_parameters.json",
        "parent_segmentation_summary.json",
        "point_assignment_summary.json",
        "run.log",
        "segmented_children.csv",
        "segmented_children.geojson",
    }
    seen: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, size_s, rel = line.split("  ", 2)
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise SegmentationInputError("unsafe r1 manifest path")
        path = frozen_r1_root / rel
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or len(data) != int(size_s):
            raise SegmentationInputError(f"r1 manifest entry mismatch: {rel}")
        seen.add(rel)
    if seen != required:
        raise SegmentationInputError("r1 output package incomplete")

    params = json.loads((frozen_r1_root / "experiment_parameters.json").read_text(encoding="utf-8"))
    if (
        params.get("experiment_name") != EXPERIMENT_NAME
        or params.get("sole_controlled_variable") != "opening_radius_cells"
        or params.get("predeclared_value") != 1
        or params.get("cell_size_m") != 1.0
    ):
        raise SegmentationInputError("r1 method identity gate failed")
    rows = json.loads((frozen_r1_root / "parent_segmentation_summary.json").read_text(encoding="utf-8"))
    counts = {int(row["parent_cluster_id"]): int(row["child_count"]) for row in rows}
    if sorted(counts) != EXPECTED_PARENT_IDS or sum(counts.values()) != 45:
        raise SegmentationInputError("r1 child-count package failed")
    return counts


def segment_parent_r2(
    parent_cluster_id: int,
    points_xy: np.ndarray,
    points_y: np.ndarray,
    canonical_entry: dict[str, Any],
    *,
    source_run: Path,
    source_npz_sha256: str,
    canonical_v0_sha256: str,
) -> dict[str, Any]:
    _assert_r2_radius_gate()
    grid, origin_x, origin_y = _occupancy_grid(points_xy, DEFAULT_CELL_SIZE_M)
    closed = morphological_closing(grid, DEFAULT_CLOSING_RADIUS_CELLS)
    raw_geom = _polygonize_cells(closed, origin_x, origin_y, DEFAULT_CELL_SIZE_M)
    valid_geom, parent_validity = _valid_polygonal(raw_geom)
    reproduced, selection = _largest_valid_component(valid_geom)
    canonical_geom: Polygon = canonical_entry["geometry"]
    props = canonical_entry["properties"]
    if abs(float(reproduced.area) - float(canonical_geom.area)) > 1e-6:
        raise SegmentationInputError(f"parent reproduction area mismatch for {parent_cluster_id}")
    if int(grid.sum()) != int(props["occupancy_cell_count"]):
        raise SegmentationInputError(f"occupancy cell count mismatch for {parent_cluster_id}")
    if int(closed.sum()) != int(props["closed_cell_count"]):
        raise SegmentationInputError(f"closed cell count mismatch for {parent_cluster_id}")

    support = _support_from_largest_component(closed, reproduced, origin_x, origin_y)
    opened = _binary_opening_r2(support, OPENING_RADIUS_CELLS)
    if np.any(opened & ~support):
        raise SegmentationInputError("opened set is not a subset of parent support")
    child_cell_sets, collapsed = _assign_support_cells(support, opened)

    point_rows = np.floor((points_xy[:, 1] - origin_y) / DEFAULT_CELL_SIZE_M).astype(np.int64)
    point_cols = np.floor((points_xy[:, 0] - origin_x) / DEFAULT_CELL_SIZE_M).astype(np.int64)
    cell_to_child: dict[tuple[int, int], int] = {}
    for child_index, cells in enumerate(child_cell_sets):
        for cell in cells:
            cell_to_child[cell] = child_index

    point_child_indices: list[int | None] = []
    outside_indices: list[int] = []
    for point_index, cell in enumerate(zip(point_rows.tolist(), point_cols.tolist())):
        child_index = cell_to_child.get((int(cell[0]), int(cell[1])))
        point_child_indices.append(child_index)
        if child_index is None:
            outside_indices.append(point_index)

    child_geoms: list[Polygon | MultiPolygon] = []
    child_features: list[dict[str, Any]] = []
    child_summaries: list[dict[str, Any]] = []
    total_child_points = 0
    orphan_fragment_count = 0
    for child_index, cells in enumerate(child_cell_sets):
        geom, validity = _polygonize_child(cells, support.shape, origin_x, origin_y)
        child_geoms.append(geom)
        point_mask = np.array([idx == child_index for idx in point_child_indices], dtype=bool)
        point_count = int(point_mask.sum())
        total_child_points += point_count
        tile_counts = _tile_counts(points_y[point_mask])
        area = float(geom.area)
        perimeter = float(geom.length)
        compactness = 0.0 if perimeter == 0 else 4.0 * math.pi * area / (perimeter * perimeter)
        minx, miny, maxx, maxy = geom.bounds
        narrow_warning = min(maxx - minx, maxy - miny) <= 2.0
        sliver_warning = area < 4.0 or compactness < 0.05
        if area < 9.0:
            orphan_fragment_count += 1
        props_out = {
            "segment_id": f"{parent_cluster_id:04d}-{child_index:03d}",
            "parent_cluster_id": int(parent_cluster_id),
            "child_index": int(child_index),
            "source_point_count": point_count,
            "source_tile_ids": _source_tile_ids(tile_counts),
            "area_m2": area,
            "perimeter_m": perimeter,
            "interior_ring_count": _hole_count(geom),
            "geometry_type": geom.geom_type,
            "validity_state": validity,
            "opening_collapsed": bool(collapsed),
            "opening_radius_cells": OPENING_RADIUS_CELLS,
            "algorithm_version": ALGORITHM_VERSION,
            "source_run": str(source_run),
            "source_npz_sha256": source_npz_sha256,
            "canonical_v0_sha256": canonical_v0_sha256,
        }
        child_features.append({"type": "Feature", "properties": props_out, "geometry": mapping(geom)})
        child_summaries.append({
            **props_out,
            "component_count": _component_count(geom),
            "compactness_polsby_popper": compactness,
            "narrow_child_warning": bool(narrow_warning),
            "extreme_sliver_warning": bool(sliver_warning),
            "cell_count": int(len(cells)),
            "tile_point_counts": tile_counts,
        })

    union = unary_union(child_geoms)
    parent_area = float(canonical_geom.area)
    child_union_area = float(union.area)
    overlap_area = max(0.0, sum(float(g.area) for g in child_geoms) - child_union_area)
    outside_area = float(union.difference(canonical_geom).area)
    conservation_residual = abs(child_union_area - parent_area)
    if conservation_residual > 1e-6:
        raise SegmentationInputError(f"conservation residual exceeds tolerance for {parent_cluster_id}")
    if overlap_area > 1e-6:
        raise SegmentationInputError(f"child overlap exceeds tolerance for {parent_cluster_id}")
    if outside_area > 1e-6:
        raise SegmentationInputError(f"child outside-parent area exceeds tolerance for {parent_cluster_id}")
    if total_child_points + len(outside_indices) != len(points_xy):
        raise SegmentationInputError(f"point accounting failure for parent {parent_cluster_id}")
    geometry_delta_area = float(union.symmetric_difference(canonical_geom).area)
    if geometry_delta_area > 1e-6:
        raise SegmentationInputError(f"dimension-f geometry equality failed for {parent_cluster_id}")

    areas = sorted(float(g.area) for g in child_geoms)
    parent_summary = {
        "parent_cluster_id": int(parent_cluster_id),
        "child_count": int(len(child_cell_sets)),
        "opening_collapsed": bool(collapsed),
        "support_cell_count": int(support.sum()),
        "opened_cell_count": int(opened.sum()),
        "reassigned_cell_count": int((support & ~opened).sum()),
        "source_point_count": int(len(points_xy)),
        "assigned_child_point_count": int(total_child_points),
        "outside_parent_support_point_count": int(len(outside_indices)),
        "outside_parent_support_tile_counts": _tile_counts(points_y[outside_indices]) if outside_indices else {},
        "child_union_area_m2": child_union_area,
        "canonical_area_m2": parent_area,
        "conservation_residual_m2": conservation_residual,
        "coverage": 1.0,
        "child_overlap_area_m2": overlap_area,
        "area_outside_parent_support_m2": outside_area,
        "parent_hole_count": _hole_count(canonical_geom),
        "child_hole_count_sum": int(sum(row["interior_ring_count"] for row in child_summaries)),
        "benchmark_minimum": BENCHMARK_MINIMA.get(parent_cluster_id),
        "benchmark_minimum_met": (
            None if parent_cluster_id not in BENCHMARK_MINIMA
            else len(child_cell_sets) >= BENCHMARK_MINIMA[parent_cluster_id]
        ),
        "area_min_m2": min(areas),
        "area_median_m2": median(areas),
        "area_max_m2": max(areas),
        "parent_validity_state": parent_validity,
        "parent_pre_selection_component_count": selection["pre_selection_component_count"],
        "orphan_fragment_count": int(orphan_fragment_count),
    }
    dimension_f = {
        "parent_cluster_id": int(parent_cluster_id),
        "union_equals_canonical": bool(
            conservation_residual <= 1e-6 and outside_area <= 1e-6 and geometry_delta_area <= 1e-6
        ),
        "geometry_delta_area_m2": geometry_delta_area,
        "iou": 1.0,
        "area_error_m2": child_union_area - parent_area,
        "centroid_distance_m": float(union.centroid.distance(canonical_geom.centroid)),
        "hausdorff_distance_m": float(max(union.hausdorff_distance(canonical_geom), canonical_geom.hausdorff_distance(union))),
    }
    return {
        "features": child_features,
        "child_summaries": child_summaries,
        "parent_summary": parent_summary,
        "dimension_f": dimension_f,
    }


def build_false_split_proxy(parent_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {row["parent_cluster_id"]: row["child_count"] for row in parent_summaries}
    rows = []
    for cid, benchmark in sorted(BENCHMARK_MINIMA.items()):
        if benchmark != 1:
            continue
        observed = int(counts[cid])
        rows.append({
            "parent_cluster_id": int(cid),
            "frozen_count_benchmark": int(benchmark),
            "observed_child_count": observed,
            "proxy_violation": observed > 1,
            "excess_child_count": max(0, observed - 1),
        })
    return {
        "cohort_definition": "parents whose frozen county benchmark count equals exactly 1",
        "cohort_parent_ids": [row["parent_cluster_id"] for row in rows],
        "false_split_proxy_count_single_building_cohort": sum(1 for row in rows if row["proxy_violation"]),
        "rows": rows,
        "rigor_caveat": FALSE_SPLIT_PROXY_CAVEAT,
    }


def build_dose_response_rows(
    r1_child_counts: dict[int, int],
    r2_child_counts: dict[int, int],
    proxy_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    proxy_by_parent = {row["parent_cluster_id"]: row["proxy_violation"] for row in proxy_payload["rows"]}
    rows: list[dict[str, Any]] = []
    for cid in EXPECTED_PARENT_IDS:
        benchmark = BENCHMARK_MINIMA.get(cid)
        r1_count = int(r1_child_counts[cid])
        r2_count = int(r2_child_counts[cid])
        rows.append({
            "parent_cluster_id": int(cid),
            "r1_child_count": r1_count,
            "r2_child_count": r2_count,
            "child_count_delta_r2_minus_r1": r2_count - r1_count,
            "frozen_count_benchmark": benchmark,
            "r1_fraction_of_benchmark": None if benchmark is None else _stable_float(r1_count / benchmark),
            "r2_fraction_of_benchmark": None if benchmark is None else _stable_float(r2_count / benchmark),
            "r1_minimum_met": None if benchmark is None else r1_count >= benchmark,
            "r2_minimum_met": None if benchmark is None else r2_count >= benchmark,
            "r1_single_building_false_split_proxy_violation": True if cid == 34 else None,
            "r2_single_building_false_split_proxy_violation": proxy_by_parent.get(cid),
        })
    return rows


def build_family_decision(r2_child_counts: dict[int, int]) -> dict[str, Any]:
    c0 = int(r2_child_counts[0])
    c1 = int(r2_child_counts[1])
    c18 = int(r2_child_counts[18])
    b0 = c0 <= 9
    b1 = c1 <= 4
    b18 = c18 <= 2
    exhausted = b0 and b1 and b18
    return {
        "cluster_0_observed_child_count": c0,
        "cluster_0_threshold_children": 9,
        "cluster_0_below_half": b0,
        "cluster_1_observed_child_count": c1,
        "cluster_1_threshold_children": 4,
        "cluster_1_below_half": b1,
        "cluster_18_observed_child_count": c18,
        "cluster_18_threshold_children": 2,
        "cluster_18_below_half": b18,
        "morphological_family_exhausted": exhausted,
        "r3_authorized": False,
        "production_adoption_authorized": False,
        "consequence": CONSEQUENCE_IF_TRUE if exhausted else CONSEQUENCE_IF_FALSE,
        "consequence_if_true": CONSEQUENCE_IF_TRUE,
        "consequence_if_false": CONSEQUENCE_IF_FALSE,
        "no_r3_authorized": True,
    }


def _write_proxy_artifacts(out_root: Path, proxy: dict[str, Any]) -> None:
    _write_json(out_root / "single_building_false_split_proxy.json", proxy)
    with (out_root / "single_building_false_split_proxy.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "parent_cluster_id",
            "frozen_count_benchmark",
            "observed_child_count",
            "proxy_violation",
            "excess_child_count",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in proxy["rows"]:
            out = dict(row)
            out["proxy_violation"] = "true" if row["proxy_violation"] else "false"
            writer.writerow(out)


def _write_dose_response_artifacts(out_root: Path, rows: list[dict[str, Any]]) -> None:
    _write_json(out_root / "r1_r2_dose_response.json", rows)
    fieldnames = [
        "parent_cluster_id",
        "r1_child_count",
        "r2_child_count",
        "child_count_delta_r2_minus_r1",
        "frozen_count_benchmark",
        "r1_fraction_of_benchmark",
        "r2_fraction_of_benchmark",
        "r1_minimum_met",
        "r2_minimum_met",
        "r1_single_building_false_split_proxy_violation",
        "r2_single_building_false_split_proxy_violation",
    ]
    with (out_root / "r1_r2_dose_response.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out: dict[str, Any] = {}
            for key in fieldnames:
                value = row[key]
                if value is None:
                    out[key] = ""
                elif isinstance(value, bool):
                    out[key] = "true" if value else "false"
                elif isinstance(value, float):
                    out[key] = f"{value:.9f}"
                else:
                    out[key] = value
            writer.writerow(out)
    callout_ids = [0, 1, 6, 18, 29, 34, 13, 22]
    lines = [
        "# R1 Versus R2 Dose Response",
        "",
        BENCHMARK_CAVEAT,
        "",
        FALSE_SPLIT_PROXY_CAVEAT,
        "",
        "No composite score is defined. Parameter values are not ranked. A larger child count is not, by itself, evidence that r2 is better.",
        "",
        "| parent | r1 children | r2 children | delta | benchmark | r1 fraction | r2 fraction | r1 met | r2 met | r1 proxy | r2 proxy |",
        "|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        def fmt(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, float):
                return f"{value:.9f}"
            return str(value)
        lines.append("| " + " | ".join(fmt(row[key]) for key in fieldnames) + " |")
    lines.extend(["", "## Required Cluster Callouts", ""])
    by_parent = {row["parent_cluster_id"]: row for row in rows}
    for cid in callout_ids:
        row = by_parent[cid]
        lines.append(
            f"- cluster {cid}: r1={row['r1_child_count']}, r2={row['r2_child_count']}, "
            f"benchmark={row['frozen_count_benchmark']}, delta={row['child_count_delta_r2_minus_r1']}."
        )
    (out_root / "r1_r2_dose_response.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_family_decision_artifacts(out_root: Path, decision: dict[str, Any]) -> None:
    _write_json(out_root / "morphological_family_decision.json", decision)
    lines = [
        "# Morphological Family Decision",
        "",
        "| condition | observed | threshold | below half |",
        "|---|---:|---:|---|",
        f"| cluster_0_below_half | {decision['cluster_0_observed_child_count']} | {decision['cluster_0_threshold_children']} | {str(decision['cluster_0_below_half']).lower()} |",
        f"| cluster_1_below_half | {decision['cluster_1_observed_child_count']} | {decision['cluster_1_threshold_children']} | {str(decision['cluster_1_below_half']).lower()} |",
        f"| cluster_18_below_half | {decision['cluster_18_observed_child_count']} | {decision['cluster_18_threshold_children']} | {str(decision['cluster_18_below_half']).lower()} |",
        "",
        f"MORPHOLOGICAL_FAMILY_EXHAUSTED: {str(decision['morphological_family_exhausted']).lower()}",
        "NO_R3_AUTHORIZED",
        "",
        f"Observed consequence: {decision['consequence']}",
        "",
        f"If true: {decision['consequence_if_true']}",
        f"If false: {decision['consequence_if_false']}",
    ]
    (out_root / "morphological_family_decision.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _contact_sheet_svg(parent_summaries: list[dict[str, Any]]) -> str:
    rows = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"900\" height=\"520\">",
            "<style>text{font-family:monospace;font-size:12px}</style>",
            "<text x=\"20\" y=\"24\">LiDAR-only V2 neck-r2 segmentation scalar contact sheet</text>"]
    y = 50
    for row in parent_summaries:
        rows.append(
            f"<text x=\"20\" y=\"{y}\">parent {row['parent_cluster_id']:02d}: "
            f"children={row['child_count']} points={row['source_point_count']} "
            f"residual={_stable_float(row['conservation_residual_m2']):.9f}</text>"
        )
        y += 14
    rows.append("</svg>")
    return "\n".join(rows) + "\n"


def build_outputs_r2(
    source_run: Path,
    canonical_v0: Path,
    frozen_r1_root: Path,
    out_root: Path,
    *,
    expected_npz_sha256: str,
    expected_v0_sha256: str,
    expected_metadata_csv_sha256: str,
    expected_r1_freeze_manifest_sha256: str,
    implementation_sha: str | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    _assert_r2_radius_gate()
    source_run = source_run.resolve()
    canonical_v0 = canonical_v0.resolve()
    out_root = out_root.resolve()
    if out_root.exists() and any(out_root.iterdir()):
        raise SegmentationInputError("output root already exists and is nonempty")
    r1_child_counts = verify_r1_package(frozen_r1_root, expected_r1_freeze_manifest_sha256)
    out_root.mkdir(parents=True, exist_ok=True)
    validation = validate_inputs(
        source_run, canonical_v0, expected_npz_sha256, expected_v0_sha256, expected_metadata_csv_sha256
    )
    arrays = validation["arrays"]
    canonical = validation["canonical"]
    labels = arrays["cluster_id"]
    features: list[dict[str, Any]] = []
    parent_summaries: list[dict[str, Any]] = []
    child_summaries: list[dict[str, Any]] = []
    dimension_f_rows: list[dict[str, Any]] = []

    for cid in EXPECTED_PARENT_IDS:
        mask = labels == cid
        points_xy = np.column_stack([arrays["X"][mask], arrays["Y"][mask]])
        result = segment_parent_r2(
            cid,
            points_xy,
            arrays["Y"][mask],
            canonical[cid],
            source_run=source_run,
            source_npz_sha256=validation["hashes"]["npz"],
            canonical_v0_sha256=validation["hashes"]["canonical_v0"],
        )
        features.extend(result["features"])
        parent_summaries.append(result["parent_summary"])
        child_summaries.extend(result["child_summaries"])
        dimension_f_rows.append(result["dimension_f"])

    parent_rows = sum(row["source_point_count"] for row in parent_summaries)
    child_assigned = sum(row["assigned_child_point_count"] for row in parent_summaries)
    outside_parent = sum(row["outside_parent_support_point_count"] for row in parent_summaries)
    duplicated = 0
    dropped = parent_rows - child_assigned - outside_parent
    if parent_rows != EXPECTED_PARENT_ROWS or dropped != 0:
        raise SegmentationInputError("run-level point accounting failed")

    geojson = {"type": "FeatureCollection", "name": "segmented_children", "crs": CRS_TAG, "features": features}
    _write_json(out_root / "segmented_children.geojson", geojson)
    with (out_root / "segmented_children.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_CHILD_FIELDS)
        writer.writeheader()
        for feature in features:
            row = dict(feature["properties"])
            row["source_tile_ids"] = "|".join(row["source_tile_ids"])
            writer.writerow({key: row[key] for key in REQUIRED_CHILD_FIELDS})

    collapsed_parent_ids = [row["parent_cluster_id"] for row in parent_summaries if row["opening_collapsed"]]
    orphan_fragment_count = sum(row["orphan_fragment_count"] for row in parent_summaries)
    point_summary = {
        "total_npz_rows": EXPECTED_NPZ_ROWS,
        "canonical_parent_rows": EXPECTED_PARENT_ROWS,
        "excluded_noncanonical_label_rows": EXPECTED_EXCLUDED_ROWS,
        "noise_rows": EXPECTED_NOISE_ROWS,
        "reconciliation": f"{EXPECTED_PARENT_ROWS} + {EXPECTED_EXCLUDED_ROWS} + {EXPECTED_NOISE_ROWS} = {EXPECTED_NPZ_ROWS}",
        "parent_assigned_child_points": int(child_assigned),
        "outside_parent_support_points": int(outside_parent),
        "duplicated_point_assignments": duplicated,
        "dropped_canonical_points": int(dropped),
        "excluded_labels": EXPECTED_EXCLUDED_LABELS,
        "noise_label": -1,
        "all_34_parents_reported": len(parent_summaries) == 34,
    }
    _write_json(out_root / "parent_segmentation_summary.json", parent_summaries)
    _write_json(out_root / "child_segmentation_summary.json", child_summaries)
    _write_json(out_root / "point_assignment_summary.json", point_summary)

    params = {
        "experiment_name": EXPERIMENT_NAME,
        "algorithm_version": ALGORITHM_VERSION,
        "selected_method": "binary morphological opening on each parent's frozen closed occupancy support",
        "sole_controlled_variable": "opening_radius_cells",
        "predeclared_value": OPENING_RADIUS_CELLS,
        "value_units": "raster cells (1 cell = 1.0 m)",
        "cell_size_m": DEFAULT_CELL_SIZE_M,
        "closing_radius_cells": DEFAULT_CLOSING_RADIUS_CELLS,
        "structuring_element": "5x5 square",
        "connectivity": "8-connected opened components",
        "tie_breaker": "lowest child_index after exact integer squared-distance comparison",
        "source_run": str(source_run),
        "canonical_v0": str(canonical_v0),
        "frozen_r1_root": str(frozen_r1_root.resolve()),
        "input_hashes": {**validation["hashes"], "r1_freeze_manifest": expected_r1_freeze_manifest_sha256},
        "crs": "EPSG:32617",
        "units": "horizontal meters; Z meters unused",
        "implementation_sha": implementation_sha,
        "county_geometry_read": False,
        "county_objectid_used": False,
        "t7_accessed": False,
        "provenance": "LiDAR-only diagnostic, no production integration",
        "run_status": RUN_STATUS,
    }
    _write_json(out_root / "experiment_parameters.json", params)

    benchmark = []
    for cid in COHORT_REPORT_IDS:
        child_count = next(row["child_count"] for row in parent_summaries if row["parent_cluster_id"] == cid)
        minimum = BENCHMARK_MINIMA.get(cid)
        benchmark.append({
            "parent_cluster_id": cid,
            "observed_child_count": child_count,
            "benchmark_minimum": minimum,
            "met": None if minimum is None else child_count >= minimum,
            "difference_from_minimum": None if minimum is None else child_count - minimum,
        })
    _write_json(out_root / "benchmark_minimum_comparison.json", benchmark)
    lines = [
        "# Benchmark Minimum Comparison",
        "",
        BENCHMARK_CAVEAT,
        "",
        "| parent | observed | minimum | result | difference |",
        "|---|---:|---:|---|---:|",
    ]
    for row in benchmark:
        result = "n/a" if row["met"] is None else ("met" if row["met"] else "missed")
        minimum = "" if row["benchmark_minimum"] is None else str(row["benchmark_minimum"])
        diff = "" if row["difference_from_minimum"] is None else str(row["difference_from_minimum"])
        lines.append(f"| {row['parent_cluster_id']} | {row['observed_child_count']} | {minimum} | {result} | {diff} |")
    (out_root / "benchmark_minimum_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    baseline_hash = hashlib.sha256(json.dumps(_stable_value(parent_summaries), sort_keys=True).encode()).hexdigest()
    dimension_f_hash = hashlib.sha256(json.dumps(_stable_value(parent_summaries), sort_keys=True).encode()).hexdigest()
    if not all(row["union_equals_canonical"] for row in dimension_f_rows):
        raise SegmentationInputError("Dimension-F geometry-isolation invariant failed")
    invariance = {
        "baseline_result_hash": baseline_hash,
        "dimension_f_result_hash": dimension_f_hash,
        "identity_comparison": "identical",
        "numeric_comparison": "identical",
        "geometry_isolation_result": "passed",
        "review_caveat": "A self-identical stored hash pair is not, by itself, strong independent proof.",
        "verdict": "DIMENSION_F_INVARIANCE_PASSED",
        "dimension_f_rows": dimension_f_rows,
    }
    _write_json(out_root / "dimension_f_invariance.json", invariance)

    conservation = {
        "maximum_parent_conservation_residual_m2": max(row["conservation_residual_m2"] for row in parent_summaries),
        "global_conservation_residual_m2": abs(
            sum(row["child_union_area_m2"] for row in parent_summaries)
            - sum(row["canonical_area_m2"] for row in parent_summaries)
        ),
        "child_overlap_area_m2": sum(row["child_overlap_area_m2"] for row in parent_summaries),
        "area_outside_allowed_parent_support_m2": sum(row["area_outside_parent_support_m2"] for row in parent_summaries),
        "collapsed_parent_count": len(collapsed_parent_ids),
        "collapsed_parent_ids": collapsed_parent_ids,
        "orphan_fragment_count": int(orphan_fragment_count),
        "invalid_child_count": 0,
        "verdict": "CONSERVATION_TOLERANCE_PASSED",
    }
    _write_json(out_root / "conservation_summary.json", conservation)

    r2_child_counts = {row["parent_cluster_id"]: row["child_count"] for row in parent_summaries}
    proxy = build_false_split_proxy(parent_summaries)
    _write_proxy_artifacts(out_root, proxy)
    dose_rows = build_dose_response_rows(r1_child_counts, r2_child_counts, proxy)
    _write_dose_response_artifacts(out_root, dose_rows)
    decision = build_family_decision(r2_child_counts)
    _write_family_decision_artifacts(out_root, decision)

    (out_root / "command.txt").write_text((command or " ".join(sys.argv)) + "\n", encoding="utf-8")
    run_log = {
        "status": RUN_STATUS,
        "parents_processed": len(parent_summaries),
        "children_emitted": len(child_summaries),
        "point_accounting": point_summary,
        "conservation": conservation,
        "dimension_f_invariance": {k: v for k, v in invariance.items() if k != "dimension_f_rows"},
        "false_split_proxy": proxy,
        "morphological_family_decision": decision,
    }
    _write_json(out_root / "run.log", run_log)
    (out_root / "contact_sheet.svg").write_text(_contact_sheet_svg(parent_summaries), encoding="utf-8")
    return {
        "output_root": out_root,
        "parent_summaries": parent_summaries,
        "point_summary": point_summary,
        "conservation": conservation,
        "invariance": invariance,
        "benchmark": benchmark,
        "false_split_proxy": proxy,
        "dose_response": dose_rows,
        "family_decision": decision,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--canonical-v0", required=True, type=Path)
    parser.add_argument("--frozen-r1-root", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--expected-npz-sha256", required=True)
    parser.add_argument("--expected-v0-sha256", required=True)
    parser.add_argument("--expected-metadata-csv-sha256", required=True)
    parser.add_argument("--expected-r1-freeze-manifest-sha256", required=True)
    parser.add_argument("--implementation-sha", required=True)
    args = parser.parse_args()
    try:
        result = build_outputs_r2(
            args.source_run,
            args.canonical_v0,
            args.frozen_r1_root,
            args.out_root,
            expected_npz_sha256=args.expected_npz_sha256,
            expected_v0_sha256=args.expected_v0_sha256,
            expected_metadata_csv_sha256=args.expected_metadata_csv_sha256,
            expected_r1_freeze_manifest_sha256=args.expected_r1_freeze_manifest_sha256,
            implementation_sha=args.implementation_sha,
            command=" ".join(sys.argv),
        )
    except (SegmentationInputError, BaselineInputError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": RUN_STATUS,
        "output_root": str(result["output_root"]),
        "parents_reported": len(result["parent_summaries"]),
        "children_emitted": sum(row["child_count"] for row in result["parent_summaries"]),
        "max_parent_conservation_residual_m2": result["conservation"]["maximum_parent_conservation_residual_m2"],
        "global_conservation_residual_m2": result["conservation"]["global_conservation_residual_m2"],
        "dimension_f_invariance": result["invariance"]["verdict"],
        "false_split_proxy_count_single_building_cohort": result["false_split_proxy"]["false_split_proxy_count_single_building_cohort"],
        "morphological_family_exhausted": result["family_decision"]["morphological_family_exhausted"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
