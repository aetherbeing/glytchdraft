"""Bounded synthetic CLI-contract tests for the Height-Discontinuity R1 real-execution route.

Every fixture here is fully synthetic (generated arrays, tmp_path, synthetic attestations and
synthetic frozen-evidence roots). No real Atlantid NPZ, canonical-v0, metadata CSV, or Z-unit
attestation is ever opened by this file. Tests exercise the real parser and main() entry point,
mostly via subprocess, so the exact CLI-wiring defect (unconditional real-route rejection) is
what is actually being tested.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2_height_discontinuity_r1 as h

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "diagnostics" / "miami_lidar_cluster_segmentation_v2_height_discontinuity_r1.py"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _parent_shape_cells(parent_id: int, productive: bool) -> list[tuple[int, int, float]]:
    """Returns (col, row, z) cells for one parent's synthetic occupied footprint."""
    if parent_id == 18 and productive:
        cells = []
        for band, z in enumerate((10.0, 14.0, 18.0)):
            for row in range(3):
                for col in range(3):
                    cells.append((col, band * 3 + row, z))
        return cells
    return [(0, 0, 10.0)]


def _build_parent_points(parent_id: int, productive: bool, target_count: int, origin_x: float, origin_y: float):
    cells = _parent_shape_cells(parent_id, productive)
    points = []
    idx = 0
    while len(points) < target_count:
        col, row, z = cells[idx % len(cells)]
        points.append((origin_x + col + 0.5, origin_y + row + 0.5, z))
        idx += 1
    return points


def _derive_canonical_properties(points_xy: np.ndarray, source_point_count: int, parent_id: int):
    grid, origin_x, origin_y = h._occupancy_grid(points_xy, h.DEFAULT_CELL_SIZE_M)
    closed = h._morphological_closing(grid, h.DEFAULT_CLOSING_RADIUS_CELLS)
    geom = h._polygonize_cells(closed, origin_x, origin_y, h.DEFAULT_CELL_SIZE_M)
    geom, _ = h._valid_polygonal(geom)
    geom, _ = h._largest_valid_component(geom)
    return {
        "cluster_id": parent_id,
        "source_point_count": source_point_count,
        "occupancy_cell_count": int(grid.sum()),
        "closed_cell_count": int(closed.sum()),
    }, geom


def build_fixture(tmp_path: Path, *, productive: bool = True, corrupt_parent_id: int | None = None) -> dict:
    source_run = tmp_path / "source_run"
    corrected = source_run / "corrected"
    (corrected / "clusters").mkdir(parents=True)
    (corrected / "masses").mkdir(parents=True)
    (corrected / "metadata").mkdir(parents=True)

    parent_count = len(h.EXPECTED_PARENT_IDS)
    base = h.EXPECTED_PARENT_ROWS // parent_count
    remainder = h.EXPECTED_PARENT_ROWS - base * parent_count
    parent_targets = {
        pid: base + (1 if i < remainder else 0) for i, pid in enumerate(h.EXPECTED_PARENT_IDS)
    }

    excluded = h.EXPECTED_EXCLUDED_LABELS
    ebase = h.EXPECTED_EXCLUDED_ROWS // len(excluded)
    eremainder = h.EXPECTED_EXCLUDED_ROWS - ebase * len(excluded)
    excluded_targets = {lbl: ebase + (1 if i < eremainder else 0) for i, lbl in enumerate(excluded)}

    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    cluster_ids: list[int] = []

    canonical_features = []
    for i, parent_id in enumerate(h.EXPECTED_PARENT_IDS):
        origin_x = 500000.0 + i * 200.0
        origin_y = 900000.0
        target = parent_targets[parent_id]
        points = _build_parent_points(parent_id, productive, target, origin_x, origin_y)
        points_xy = np.array([[px, py] for px, py, _ in points], dtype=np.float64)
        props, geom = _derive_canonical_properties(points_xy, target, parent_id)
        if corrupt_parent_id is not None and parent_id == corrupt_parent_id:
            minx, miny, maxx, maxy = geom.bounds
            from shapely.geometry import box as shapely_box

            geom = shapely_box(minx, miny, maxx + 25.0, maxy + 25.0)
        canonical_features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": json.loads(json.dumps(_mapping(geom))),
            }
        )
        for px, py, pz in points:
            xs.append(px)
            ys.append(py)
            zs.append(pz)
            cluster_ids.append(parent_id)

    for i, label in enumerate(excluded):
        for j in range(excluded_targets[label]):
            xs.append(1_000_000.0 + i * 10.0 + j)
            ys.append(2_000_000.0)
            zs.append(5.0)
            cluster_ids.append(label)

    for j in range(h.EXPECTED_NOISE_ROWS):
        xs.append(3_000_000.0 + j)
        ys.append(4_000_000.0)
        # Fixed regardless of `productive` so the global Z-relief gate (G-Z2) always
        # sees a [10, 350] m spread, whether or not parent 18's multi-band shape is used.
        zs.append(0.0 if j < h.EXPECTED_NOISE_ROWS - 1 else 20.0)
        cluster_ids.append(-1)

    npz_path = corrected / "clusters" / "building_clusters.npz"
    np.savez(
        npz_path,
        X=np.asarray(xs, dtype=np.float64),
        Y=np.asarray(ys, dtype=np.float64),
        Z=np.asarray(zs, dtype=np.float64),
        cluster_id=np.asarray(cluster_ids, dtype=np.int64),
    )
    # np.savez appends .npz; ensure the exact expected filename exists.
    if not npz_path.exists() and npz_path.with_suffix(npz_path.suffix + ".npz").exists():
        npz_path.with_suffix(npz_path.suffix + ".npz").rename(npz_path)

    canonical_v0 = tmp_path / "lidar_footprints_v0.geojson"
    canonical_payload = {
        "type": "FeatureCollection",
        "crs": h.CRS_TAG,
        "features": canonical_features,
    }
    canonical_v0.write_text(json.dumps(canonical_payload, sort_keys=True) + "\n", encoding="utf-8")

    metadata_csv = corrected / "masses" / "bikini_masses_metadata.csv"
    with metadata_csv.open("w", encoding="utf-8", newline="") as handle:
        handle.write("cluster_id\n")
        for pid in h.EXPECTED_PARENT_IDS:
            handle.write(f"{pid}\n")

    attestation_path = corrected / "metadata" / "normalization_provenance.json"
    attestation_payload = {
        "normalization_version": "miami_metric_normalization_v1",
        "feature_gate_enabled": True,
        "target_unit": "meters",
        "output_root": str(npz_path.parent.resolve()),
    }
    attestation_path.write_text(json.dumps(attestation_payload, sort_keys=True) + "\n", encoding="utf-8")

    frozen_r1_root = tmp_path / "frozen_r1"
    frozen_r2_root = tmp_path / "frozen_r2"
    r1_manifest_sha = _build_evidence_root(frozen_r1_root, {pid: 2 for pid in h.EXPECTED_PARENT_IDS})
    r2_manifest_sha = _build_evidence_root(frozen_r2_root, {pid: 3 for pid in h.EXPECTED_PARENT_IDS})

    return {
        "source_run": source_run,
        "npz_path": npz_path,
        "canonical_v0": canonical_v0,
        "metadata_csv": metadata_csv,
        "attestation_path": attestation_path,
        "frozen_r1_root": frozen_r1_root,
        "frozen_r2_root": frozen_r2_root,
        "expected_npz_sha256": _sha256_path(npz_path),
        "expected_v0_sha256": _sha256_path(canonical_v0),
        "expected_metadata_csv_sha256": _sha256_path(metadata_csv),
        "expected_z_unit_attestation_sha256": _sha256_path(attestation_path),
        "expected_r1_freeze_manifest_sha256": r1_manifest_sha,
        "expected_r2_freeze_manifest_sha256": r2_manifest_sha,
    }


def _mapping(geom):
    from shapely.geometry import mapping

    return mapping(geom)


def _build_evidence_root(root: Path, child_counts: dict[int, int]) -> str:
    root.mkdir(parents=True)
    parent_rows = [{"parent_cluster_id": pid, "child_count": count} for pid, count in sorted(child_counts.items())]
    contents: dict[str, bytes] = {
        "parent_segmentation_summary.json": (json.dumps(parent_rows, sort_keys=True) + "\n").encode("utf-8"),
    }
    for name in h.FROZEN_EVIDENCE_REQUIRED_FILES:
        if name == "parent_segmentation_summary.json":
            continue
        contents[name] = f"synthetic frozen evidence: {name}\n".encode("utf-8")
    for name, data in contents.items():
        (root / name).write_bytes(data)
    lines = []
    for name in sorted(contents):
        data = (root / name).read_bytes()
        lines.append(f"{_sha256_bytes(data)}  {len(data)}  {name}")
    manifest = root / "FREEZE_MANIFEST.sha256"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _sha256_path(manifest)


def _full_argv(fixture: dict, out_root: Path, *, implementation_sha: str = "0" * 40) -> list[str]:
    return [
        "--source-run", str(fixture["source_run"]),
        "--canonical-v0", str(fixture["canonical_v0"]),
        "--frozen-r1-root", str(fixture["frozen_r1_root"]),
        "--expected-r1-freeze-manifest-sha256", fixture["expected_r1_freeze_manifest_sha256"],
        "--frozen-r2-root", str(fixture["frozen_r2_root"]),
        "--expected-r2-freeze-manifest-sha256", fixture["expected_r2_freeze_manifest_sha256"],
        "--out-root", str(out_root),
        "--expected-npz-sha256", fixture["expected_npz_sha256"],
        "--expected-v0-sha256", fixture["expected_v0_sha256"],
        "--expected-metadata-csv-sha256", fixture["expected_metadata_csv_sha256"],
        "--z-unit-attestation", str(fixture["attestation_path"]),
        "--expected-z-unit-attestation-sha256", fixture["expected_z_unit_attestation_sha256"],
        "--implementation-sha", implementation_sha,
    ]


def _run_cli(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *argv],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_full_authorized_cli_reaches_synthetic_segmentation(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    assert (out_root / "FREEZE_MANIFEST.sha256").exists()
    decision = json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))
    assert decision["run_validity"] == "RUN_VALID"
    assert decision["height_mechanism_productive"] is True
    for name in h.OUTPUT_CONTENT_FILES:
        assert (out_root / name).exists(), name


def test_missing_authorization_blocks_before_load(tmp_path):
    out_root = tmp_path / "out"
    proc = _run_cli(["--source-run", str(tmp_path / "nonexistent_source"), "--out-root", str(out_root)])
    assert proc.returncode == 2
    assert "missing" in proc.stderr
    assert not (out_root / "segmented_children.geojson").exists()
    assert not any((out_root).glob("*")) or list((out_root).iterdir()) == []


def test_invalid_authorization_blocks_before_load(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    argv = _full_argv(fixture, out_root)
    npz_index = argv.index("--expected-npz-sha256") + 1
    argv[npz_index] = "0" * 64
    proc = _run_cli(argv)
    assert proc.returncode == 2
    decision = json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))
    assert decision["run_validity"] == "RUN_BLOCKED"
    assert decision["height_mechanism_productive"] == "NOT_EVALUABLE"
    assert not (out_root / "segmented_children.geojson").exists()
    assert not (out_root / "FREEZE_MANIFEST.sha256").exists()


def test_readiness_only_mode_does_not_segment(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli([
        "--source-run", str(fixture["source_run"]),
        "--out-root", str(out_root),
        "--readiness-audit-only",
    ])
    assert proc.returncode == 0, proc.stderr
    assert (out_root / "run.log").exists()
    assert list(out_root.iterdir()) == [out_root / "run.log"]
    assert not (out_root / "segmented_children.geojson").exists()


def test_existing_output_root_is_rejected(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    out_root.mkdir()
    (out_root / "preexisting.txt").write_text("hello\n", encoding="utf-8")
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 2
    assert "must not exist or must be empty" in proc.stderr
    assert not (out_root / "segmented_children.geojson").exists()


def test_prior_run_evidence_is_rejected(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    first = _run_cli(_full_argv(fixture, out_root))
    assert first.returncode == 0, first.stderr
    second = _run_cli(_full_argv(fixture, out_root))
    assert second.returncode == 2
    assert "must not exist or must be empty" in second.stderr


def test_invalid_z_unit_attestation_blocks_without_segmentation(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    attestation_payload = json.loads(fixture["attestation_path"].read_text(encoding="utf-8"))
    attestation_payload["target_unit"] = "feet"
    fixture["attestation_path"].write_text(json.dumps(attestation_payload, sort_keys=True) + "\n", encoding="utf-8")
    fixture["expected_z_unit_attestation_sha256"] = _sha256_path(fixture["attestation_path"])
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 2
    decision = json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))
    assert decision["run_validity"] == "RUN_BLOCKED"
    assert decision["height_mechanism_productive"] == "NOT_EVALUABLE"
    assert not (out_root / "segmented_children.geojson").exists()
    z_gate = json.loads((out_root / "z_unit_gate.json").read_text(encoding="utf-8"))
    assert z_gate["segmentation_entered"] is False


def test_valid_synthetic_execution_produces_required_artifacts(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    manifest_lines = (out_root / "FREEZE_MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    names = {line.split("  ", 2)[2] for line in manifest_lines}
    assert names == set(h.OUTPUT_CONTENT_FILES)


def test_valid_unfavorable_result_remains_run_valid(tmp_path):
    fixture = build_fixture(tmp_path, productive=False)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    decision = json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))
    assert decision["run_validity"] == "RUN_VALID"
    assert decision["height_mechanism_productive"] is False
    assert (out_root / "FREEZE_MANIFEST.sha256").exists()


def test_hard_stop_violation_produces_run_failed(tmp_path):
    fixture = build_fixture(tmp_path, productive=True, corrupt_parent_id=0)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 2
    run_log = json.loads((out_root / "run.log").read_text(encoding="utf-8"))
    assert run_log["run_validity"] == "RUN_FAILED"
    assert run_log["height_mechanism_productive"] == "NOT_EVALUABLE"
    assert not (out_root / "FREEZE_MANIFEST.sha256").exists()


def test_no_production_path_written(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    prohibited_root = REPO_ROOT / "viewer" / "_height_r1_cli_test_should_not_exist"
    argv = _full_argv(fixture, prohibited_root)
    proc = _run_cli(argv)
    assert proc.returncode == 2
    assert "not an authorized external diagnostic root" in proc.stderr
    assert not prohibited_root.exists()


def test_cli_output_is_deterministic_for_identical_synthetic_inputs(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root_a = tmp_path / "out_a"
    out_root_b = tmp_path / "out_b"
    proc_a = _run_cli(_full_argv(fixture, out_root_a))
    proc_b = _run_cli(_full_argv(fixture, out_root_b))
    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    for name in h.OUTPUT_CONTENT_FILES:
        if name in {"command.txt", "command_stdout_stderr.log"}:
            continue
        content_a = (out_root_a / name).read_bytes()
        content_b = (out_root_b / name).read_bytes()
        if name == "experiment_parameters.json":
            # The embedded full CLI echo (`command`) legitimately varies with --out-root,
            # exactly like command.txt already does; every other field must be identical.
            params_a = json.loads(content_a)
            params_b = json.loads(content_b)
            assert params_a.pop("command") != params_b.pop("command")
            assert params_a == params_b
            continue
        assert content_a == content_b, name


def test_experiment_parameters_json_satisfies_o3_schema(tmp_path):
    """Frozen §O3 (output_package_contract.md) schema coverage for experiment_parameters.json:
    every frozen_constants value, all six input hashes, the full CLI echo, environment capture,
    the z_unit_gate record, run_status, the nine isolation booleans, the input-readiness evidence
    block, and the per-parent Stage A diagnostics — parsed and asserted exactly, not keyword-
    searched."""
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    implementation_sha = "a" * 40
    argv = _full_argv(fixture, out_root, implementation_sha=implementation_sha)
    proc = _run_cli(argv)
    assert proc.returncode == 0, proc.stderr

    manifest_lines = (out_root / "FREEZE_MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    manifest_names = sorted(line.split("  ", 2)[2] for line in manifest_lines)
    assert manifest_names == sorted(h.OUTPUT_CONTENT_FILES)
    assert len(h.OUTPUT_CONTENT_FILES) == 25
    on_disk = sorted(p.name for p in out_root.iterdir())
    assert on_disk == sorted([*h.OUTPUT_CONTENT_FILES, "FREEZE_MANIFEST.sha256"])
    assert len(on_disk) == 26

    params = json.loads((out_root / "experiment_parameters.json").read_text(encoding="utf-8"))

    # --- environment capture: exact five fields, meaningful (non-empty, real) values ---
    assert params["python_version"] == platform.python_version()
    assert params["numpy_version"] == np.__version__
    assert params["shapely_version"] == shapely.__version__
    assert params["validity_repair_backend"] in {"shapely.validation.make_valid", "geometry.buffer(0)"}
    assert params["implementation_sha"] == implementation_sha

    # --- every frozen_constants value (exactly 8 keys, exact frozen values) ---
    assert params["frozen_constants"] == {
        "VERTICAL_STEP_THRESHOLD_M": 2.0,
        "DEFAULT_CELL_SIZE_M": 1.0,
        "DEFAULT_CLOSING_RADIUS_CELLS": 1,
        "REPRESENTATIVE_Z_STATISTIC": "median",
        "MIN_POINTS_PER_CELL_FOR_Z": 1,
        "EDGE_CONNECTIVITY": 4,
        "COMPONENT_CONNECTIVITY": 4,
        "SERIALIZATION_DECIMAL_PLACES": 9,
    }

    # --- full CLI echo embedded in the file itself, not merely in command.txt ---
    command_txt = (out_root / "command.txt").read_text(encoding="utf-8").strip()
    assert params["command"] == command_txt
    assert params["command"].split()[0] == SCRIPT_PATH.name
    for token in argv:
        assert token in params["command"]

    # --- all six input hashes, exact keys and values ---
    assert params["input_hashes"] == {
        "npz": fixture["expected_npz_sha256"],
        "canonical_v0": fixture["expected_v0_sha256"],
        "metadata_csv": fixture["expected_metadata_csv_sha256"],
        "frozen_r1_manifest": fixture["expected_r1_freeze_manifest_sha256"],
        "frozen_r2_manifest": fixture["expected_r2_freeze_manifest_sha256"],
        "z_unit_attestation": fixture["expected_z_unit_attestation_sha256"],
    }

    # --- z_unit_gate record: attestation path + SHA-256 + attested facts + observed relief ---
    gate = params["z_unit_gate"]
    assert gate["attestation_path"] == str(fixture["attestation_path"])
    assert gate["attestation_sha256"] == fixture["expected_z_unit_attestation_sha256"]
    assert gate["attested_facts"]["normalization_version"] == "miami_metric_normalization_v1"
    assert gate["attested_facts"]["feature_gate_enabled"] is True
    assert gate["attested_facts"]["target_unit"] == "meters"
    assert isinstance(gate["observed_relief_m"], float)
    assert 10.0 <= gate["observed_relief_m"] <= 350.0

    # --- run_status ---
    assert params["run_status"] == h.RUN_STATUS

    # --- the nine isolation booleans, exact keys, all false ---
    for key in (
        "county_geometry_read", "county_objectid_used", "featureserver_accessed", "t7_accessed",
        "buffer_used", "morphology_used", "alpha_shape_used", "eave_offset_used", "regularization_used",
    ):
        assert params[key] is False

    # --- input-readiness evidence block: census, cell counts, all-finite confirmation ---
    readiness = params["input_readiness_evidence"]
    census = readiness["census"]
    assert census["canonical_rows"] == h.EXPECTED_PARENT_ROWS
    assert census["excluded_noncanonical_rows"] == h.EXPECTED_EXCLUDED_ROWS
    assert census["noise_rows"] == h.EXPECTED_NOISE_ROWS
    assert census["total_rows"] == h.EXPECTED_NPZ_ROWS
    assert census["reconciliation"] == (
        f"{h.EXPECTED_PARENT_ROWS} + {h.EXPECTED_EXCLUDED_ROWS} + {h.EXPECTED_NOISE_ROWS} = {h.EXPECTED_NPZ_ROWS}"
    )
    assert set(census["excluded_label_counts"]) == {str(label) for label in h.EXPECTED_EXCLUDED_LABELS}
    assert sum(census["excluded_label_counts"].values()) == h.EXPECTED_EXCLUDED_ROWS
    assert readiness["all_input_values_finite"] is True

    diagnostics = json.loads((out_root / "height_discontinuity_diagnostics.json").read_text(encoding="utf-8"))
    assert readiness["one_point_cell_count"] == sum(
        row["one_point_cell_count"] for row in diagnostics["parents"]
    )
    assert readiness["multi_point_cell_count"] == sum(
        row["multi_point_cell_count"] for row in diagnostics["parents"]
    )
    assert readiness["occupied_cell_count"] == sum(row["occupancy_cell_count"] for row in params["stage_a"])

    # --- per-parent Stage A diagnostics: deterministic parent ordering, exact field set ---
    stage_a = params["stage_a"]
    assert [row["parent_cluster_id"] for row in stage_a] == h.EXPECTED_PARENT_IDS
    for row in stage_a:
        assert set(row) == {
            "parent_cluster_id", "occupancy_cell_count", "closed_cell_count",
            "validity_result", "canonical_area_m2", "reproduced_area_m2",
        }
        assert row["occupancy_cell_count"] >= 1
        assert row["closed_cell_count"] >= 1
        assert row["validity_result"] in {"valid", "repaired_make_valid", "repaired_buffer0"}

    # --- the eleven authorization booleans, all false ---
    assert len(h.AUTHORIZATION_FALSE_FIELDS) == 11
    for field in h.AUTHORIZATION_FALSE_FIELDS:
        assert params[field] is False


def test_experiment_parameters_json_identical_across_runs_except_permitted_fields(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root_a = tmp_path / "out_a"
    out_root_b = tmp_path / "out_b"
    proc_a = _run_cli(_full_argv(fixture, out_root_a))
    proc_b = _run_cli(_full_argv(fixture, out_root_b))
    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    params_a = json.loads((out_root_a / "experiment_parameters.json").read_text(encoding="utf-8"))
    params_b = json.loads((out_root_b / "experiment_parameters.json").read_text(encoding="utf-8"))
    command_a = params_a.pop("command")
    command_b = params_b.pop("command")
    assert command_a != command_b
    assert params_a == params_b


def test_scientific_suite_still_collects_exactly_33(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "tests/test_miami_lidar_cluster_segmentation_v2_height_discontinuity_r1.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "33 passed" in proc.stdout

    collect = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only",
         "tests/test_miami_lidar_cluster_segmentation_v2_height_discontinuity_r1.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert "33 tests collected" in collect.stdout
