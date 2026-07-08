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
import re
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
        if name in {"command.txt", "command_stdout_stderr.log", "run.log"}:
            # command.txt/run.log are the declared-volatile I5 artifacts (run.log now carries
            # UTC timestamps per B13); run.log content is checked for format, not byte equality,
            # by test_run_log_is_utc_timestamped_text_with_required_content below.
            continue
        content_a = (out_root_a / name).read_bytes()
        content_b = (out_root_b / name).read_bytes()
        if name == "experiment_parameters.json":
            # The embedded full CLI echo (`command`) legitimately varies with --out-root, exactly
            # like command.txt already does; `resolved_arguments.out_root` (D4) legitimately
            # varies for the same reason. Every other field must be identical.
            params_a = json.loads(content_a)
            params_b = json.loads(content_b)
            assert params_a.pop("command") != params_b.pop("command")
            ra_a = params_a.pop("resolved_arguments")
            ra_b = params_b.pop("resolved_arguments")
            assert ra_a.pop("out_root") != ra_b.pop("out_root")
            assert ra_a == ra_b
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

    # --- every frozen_constants value (D1: exactly the 14-key experiment_contract.json block,
    # exact contract key names and frozen values) ---
    assert params["frozen_constants"] == {
        "VERTICAL_STEP_THRESHOLD_M": 2.0,
        "CELL_SIZE_M": 1.0,
        "CLOSING_RADIUS_CELLS": 1,
        "REPRESENTATIVE_Z_STATISTIC": "median",
        "MIN_POINTS_PER_CELL_FOR_Z": 1,
        "NO_DATA_EDGE_RULE": "preserve",
        "EQUALITY_RULE": "preserve",
        "EDGE_CONNECTIVITY": 4,
        "COMPONENT_CONNECTIVITY": 4,
        "SERIALIZATION_DECIMAL_PLACES": 9,
        "Z_UNIT_RELIEF_BAND_M": [10.0, 350.0],
        "RUN_STATUS": h.RUN_STATUS,
        "BLOCKED_STATUS": h.BLOCKED_STATUS,
        "FAILED_STATUS": h.FAILED_STATUS,
    }
    assert len(params["frozen_constants"]) == 14

    # --- full CLI echo embedded in the file itself, not merely in command.txt ---
    command_txt = (out_root / "command.txt").read_text(encoding="utf-8").strip()
    assert params["command"] == command_txt
    assert params["command"].split()[0] == SCRIPT_PATH.name
    for token in argv:
        assert token in params["command"]

    # --- D4: resolved_arguments is a separate, deterministic, fixed-key-set record of the
    # parser-effective typed values (paths resolved absolute), distinct from the exact `command`
    # echo above (both are mandatory and must not be conflated). ---
    resolved = params["resolved_arguments"]
    assert set(resolved) == {
        "source_run", "out_root", "canonical_v0", "frozen_r1_root", "frozen_r2_root",
        "z_unit_attestation", "expected_r1_freeze_manifest_sha256", "expected_r2_freeze_manifest_sha256",
        "expected_npz_sha256", "expected_v0_sha256", "expected_metadata_csv_sha256",
        "expected_z_unit_attestation_sha256", "implementation_sha",
        "readiness_audit_only", "readiness_audit_only_is_default",
    }
    assert resolved["source_run"] == str(fixture["source_run"].resolve())
    assert resolved["out_root"] == str(out_root.resolve())
    assert resolved["canonical_v0"] == str(fixture["canonical_v0"].resolve())
    assert resolved["implementation_sha"] == implementation_sha
    assert resolved["readiness_audit_only"] is False
    assert resolved["readiness_audit_only_is_default"] is True

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

    # --- D3: cell-count semantics use the finite, canonical, post-exclusion Stage A population
    # (raw per-parent occupancy grids), not the support-filtered population reported inside
    # height_discontinuity_diagnostics.json (a genuinely different, smaller population once
    # largest-component selection / covers() exclusion has removed cells). The binding invariant
    # is one_point_cell_count + multi_point_cell_count == occupied_cell_count. ---
    assert readiness["one_point_cell_count"] + readiness["multi_point_cell_count"] == readiness["occupied_cell_count"]
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
    ra_a = params_a.pop("resolved_arguments")
    ra_b = params_b.pop("resolved_arguments")
    assert ra_a.pop("out_root") != ra_b.pop("out_root")
    assert ra_a == ra_b
    assert params_a == params_b


def test_b1_segmented_children_geometry_is_georeferenced_not_index_space(tmp_path):
    """B1: child (and parent-support) geometry must serialize in absolute EPSG:32617 meters,
    matching the parent's real UTM-scale origin, never collapsing to raster-index space near
    (0, 0). The fixture's canonical features use origins 500000+/900000 (UTM-scale), so
    index-space output is unmistakable from real output."""
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr

    from shapely.geometry import shape as shapely_shape

    geojson = json.loads((out_root / "segmented_children.geojson").read_text(encoding="utf-8"))
    assert geojson["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::32617"
    canonical = json.loads(fixture["canonical_v0"].read_text(encoding="utf-8"))
    canonical_bounds_by_parent = {}
    for feature in canonical["features"]:
        geom = shapely_shape(feature["geometry"])
        canonical_bounds_by_parent[int(feature["properties"]["cluster_id"])] = geom.bounds

    assert len(geojson["features"]) > 0
    for feature in geojson["features"]:
        pid = int(feature["properties"]["parent_cluster_id"])
        child_geom = shapely_shape(feature["geometry"])
        minx, miny, maxx, maxy = child_geom.bounds
        # Never collapsed near raster-index space.
        assert minx > 1000.0
        assert miny > 1000.0
        # Every child centroid must fall within (a small buffer of) the parent's canonical bounds.
        pminx, pminy, pmaxx, pmaxy = canonical_bounds_by_parent[pid]
        centroid = child_geom.centroid
        assert (pminx - 5.0) <= centroid.x <= (pmaxx + 5.0)
        assert (pminy - 5.0) <= centroid.y <= (pmaxy + 5.0)

    # Round-trip: re-parsing the written file preserves the same absolute frame.
    reread = json.loads((out_root / "segmented_children.geojson").read_text(encoding="utf-8"))
    assert reread == geojson


def test_b2_gi2_dimension_f_rows_are_independent_and_detect_altered_geometry(tmp_path):
    """B2: dimension_f_invariance.json rows must be built from two genuinely independent
    sources (disk-reread child union vs re-hashed canonical v0), never a self-comparison. Proves
    both the nominal pass and that a deliberately altered second geometry is detected."""
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr

    invariance = json.loads((out_root / "dimension_f_invariance.json").read_text(encoding="utf-8"))
    assert invariance["verdict"] == "DIMENSION_F_INVARIANCE_PASSED"
    assert "review_caveat" not in invariance
    rows = invariance["dimension_f_rows"]
    assert [row["parent_cluster_id"] for row in rows] == h.EXPECTED_PARENT_IDS
    for row in rows:
        assert set(row) == {
            "parent_cluster_id", "union_area_m2", "canonical_area_m2", "area_error_m2",
            "symmetric_difference_area_m2", "iou", "centroid_distance_m", "hausdorff_distance_m",
            "side_a_wkb_sha256", "side_b_wkb_sha256",
        }
        assert len(row["side_a_wkb_sha256"]) == 64
        assert len(row["side_b_wkb_sha256"]) == 64
        int(row["side_a_wkb_sha256"], 16)
        int(row["side_b_wkb_sha256"], 16)
        assert row["symmetric_difference_area_m2"] <= 1e-6

    # canonical_area_m2 must equal the canonical file geometry's own area, recomputed in-test
    # directly from the fixture file (independent of the module's own re-parse).
    from shapely.geometry import shape as shapely_shape_for_check

    canonical_payload = json.loads(fixture["canonical_v0"].read_text(encoding="utf-8"))
    canonical_area_by_parent = {
        int(feature["properties"]["cluster_id"]): shapely_shape_for_check(feature["geometry"]).area
        for feature in canonical_payload["features"]
    }
    for row in rows:
        assert abs(row["canonical_area_m2"] - canonical_area_by_parent[row["parent_cluster_id"]]) <= 1e-6

    # Adversarial probe: corrupt one child's geometry on disk (bytes only, independent of any
    # in-memory object) and rebuild the GI2 rows directly — this must detect the divergence.
    geojson_path = out_root / "segmented_children.geojson"
    payload = json.loads(geojson_path.read_text(encoding="utf-8"))
    target_pid = payload["features"][0]["properties"]["parent_cluster_id"]
    from shapely.affinity import translate
    from shapely.geometry import mapping as shapely_mapping
    from shapely.geometry import shape as shapely_shape

    for feature in payload["features"]:
        if feature["properties"]["parent_cluster_id"] == target_pid:
            moved = translate(shapely_shape(feature["geometry"]), xoff=250.0, yoff=250.0)
            feature["geometry"] = shapely_mapping(moved)
    geojson_path.write_text(json.dumps(payload), encoding="utf-8")

    corrupted_rows = h.build_gi2_dimension_f_rows(
        out_root, fixture["canonical_v0"], fixture["expected_v0_sha256"], h.EXPECTED_PARENT_IDS
    )
    corrupted_row = [row for row in corrupted_rows if row["parent_cluster_id"] == target_pid][0]
    assert corrupted_row["symmetric_difference_area_m2"] > 1e-6


def test_b3_conservation_summary_has_per_parent_c4_rows(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    conservation = json.loads((out_root / "conservation_summary.json").read_text(encoding="utf-8"))
    rows = conservation["parents"]
    assert [row["parent_cluster_id"] for row in rows] == h.EXPECTED_PARENT_IDS
    for row in rows:
        assert set(row) == {
            "parent_cluster_id", "child_union_area_m2", "canonical_area_m2",
            "conservation_residual_m2", "child_overlap_area_m2",
            "area_outside_parent_support_m2", "no_data_cell_count", "support_cell_count",
        }
        assert abs(row["child_union_area_m2"] - row["canonical_area_m2"]) <= 2e-6
    assert "global_conservation_residual_sum_of_abs_m2" in conservation


def test_b4_parent_segmentation_summary_has_inherited_neck_r1_fields(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    rows = json.loads((out_root / "parent_segmentation_summary.json").read_text(encoding="utf-8"))
    required_new_fields = {
        "coverage", "parent_hole_count", "child_hole_count_sum", "benchmark_minimum",
        "benchmark_minimum_met", "area_min_m2", "area_median_m2", "area_max_m2",
        "parent_validity_state", "parent_pre_selection_component_count",
        "orphan_fragment_count", "outside_parent_support_tile_counts",
        "algorithm_version", "source_run", "source_npz_sha256", "canonical_v0_sha256",
    }
    for row in rows:
        assert required_new_fields.issubset(set(row))
        assert row["coverage"] == 1.0
        assert row["parent_validity_state"] in {"valid", "repaired_make_valid", "repaired_buffer0"}
        assert row["area_min_m2"] <= row["area_median_m2"] <= row["area_max_m2"]
    benchmarked = [row for row in rows if row["parent_cluster_id"] in h.BENCHMARK_MINIMA]
    assert len(benchmarked) == len(h.BENCHMARK_MINIMA)
    for row in benchmarked:
        assert row["benchmark_minimum"] == h.BENCHMARK_MINIMA[row["parent_cluster_id"]]
        assert row["benchmark_minimum_met"] == (row["child_count"] >= row["benchmark_minimum"])


def test_b5_point_assignment_summary_has_per_parent_and_tile_rows(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    point_summary = json.loads((out_root / "point_assignment_summary.json").read_text(encoding="utf-8"))
    rows = point_summary["parents"]
    assert [row["parent_cluster_id"] for row in rows] == h.EXPECTED_PARENT_IDS
    for row in rows:
        assert set(row) == {
            "parent_cluster_id", "source_point_count", "assigned_child_point_count",
            "outside_parent_support_point_count", "assigned_child_tile_counts",
            "outside_parent_support_tile_counts",
        }
        assert row["assigned_child_point_count"] + row["outside_parent_support_point_count"] == row["source_point_count"]
        if row["assigned_child_point_count"] > 0:
            assert sum(row["assigned_child_tile_counts"].values()) == row["assigned_child_point_count"]


def test_b6_source_tile_ids_populated_from_fixture_provenance(tmp_path):
    """B6: source_tile_ids must be populated from actual point provenance (never silently
    empty on the real route); the fixture's Y coordinates (~900000) are all on the
    TILE_318455 side of the frozen seam (2852621.18647587), so every non-empty child must
    report exactly that tile."""
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    child_summaries = json.loads((out_root / "child_segmentation_summary.json").read_text(encoding="utf-8"))
    assert len(child_summaries) > 0
    saw_nonempty = False
    for child in child_summaries:
        if child["source_point_count"] > 0:
            saw_nonempty = True
            assert child["source_tile_ids"] == [h.TILE_318455]
    assert saw_nonempty


def test_b7_height_discontinuity_diagnostics_has_e2_fields(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    diagnostics = json.loads((out_root / "height_discontinuity_diagnostics.json").read_text(encoding="utf-8"))
    for row in diagnostics["parents"]:
        assert set(row) == {
            "parent_cluster_id", "support_cell_count", "data_cell_count", "no_data_cell_count",
            "no_data_cell_fraction", "histogram", "tested_edge_count", "no_data_edge_count",
            "cut_edge_count", "one_point_cell_count", "multi_point_cell_count",
            "min_rep_z_m", "median_rep_z_m", "max_rep_z_m",
        }
        assert row["data_cell_count"] + row["no_data_cell_count"] == row["support_cell_count"]
    csv_text = (out_root / "height_discontinuity_diagnostics.csv").read_text(encoding="utf-8")
    header = csv_text.splitlines()[0]
    for field in ("support_cell_count", "data_cell_count", "no_data_cell_count", "no_data_cell_fraction"):
        assert field in header


def test_b8_b9_benchmark_and_baseline_schema(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr

    benchmark = json.loads((out_root / "benchmark_minimum_comparison.json").read_text(encoding="utf-8"))
    assert benchmark["benchmark_caveat"] == h.BENCHMARK_CAVEAT
    assert [row["parent_cluster_id"] for row in benchmark["parents"]] == sorted(h.BENCHMARK_MINIMA)
    for row in benchmark["parents"]:
        assert set(row) == {
            "parent_cluster_id", "frozen_scalar_minimum", "height_r1_child_count",
            "height_fraction_of_minimum", "height_minimum_met",
        }
    benchmark_md = (out_root / "benchmark_minimum_comparison.md").read_text(encoding="utf-8")
    assert h.BENCHMARK_CAVEAT in benchmark_md

    baseline = json.loads((out_root / "baseline_comparison.json").read_text(encoding="utf-8"))
    baseline_by_parent = {row["parent_cluster_id"]: row for row in baseline}
    for row in benchmark["parents"]:
        b = baseline_by_parent[row["parent_cluster_id"]]
        assert b["frozen_scalar_minimum"] == row["frozen_scalar_minimum"]
        assert b["height_r1_child_count"] == row["height_r1_child_count"]
        assert b["height_fraction_of_minimum"] == row["height_fraction_of_minimum"]
        assert b["height_minimum_met"] == row["height_minimum_met"]

    baseline_md = (out_root / "baseline_comparison.md").read_text(encoding="utf-8")
    assert h.BENCHMARK_CAVEAT in baseline_md
    for pid in h.COHORT_REPORT_IDS:
        assert str(pid) in baseline_md
    assert "total" in baseline_md.lower()


def test_b10_prediction_scorecard_has_registered_p1_through_p6(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    scorecard = json.loads((out_root / "prediction_scorecard.json").read_text(encoding="utf-8"))
    predictions = scorecard["predictions"]
    assert [row["id"] for row in predictions] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    for row in predictions:
        assert row["result"] in {"MET", "NOT_MET"}
        assert isinstance(row["observed"], int)
    p4 = [row for row in predictions if row["id"] == "P4"][0]
    assert p4["pre_declared_miss_framing"] == h.P4_PRE_DECLARED_MISS_FRAMING
    scorecard_md = (out_root / "prediction_scorecard.md").read_text(encoding="utf-8")
    assert h.P4_PRE_DECLARED_MISS_FRAMING in scorecard_md


def test_b11_family_decision_embeds_canonical_rule_text(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    decision = json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))
    assert decision["family_decision_rule"] == h.FAMILY_DECISION_RULE_TEXT
    decision_md = (out_root / "family_decision.md").read_text(encoding="utf-8")
    assert h.FAMILY_DECISION_RULE_TEXT in decision_md


def test_b12_b13_contact_sheet_and_run_log_content(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr

    contact = (out_root / "contact_sheet.svg").read_text(encoding="utf-8")
    assert "cut_edges=" in contact
    assert "no_data_fraction=" in contact

    run_log = (out_root / "run.log").read_text(encoding="utf-8")
    lines = [line for line in run_log.splitlines() if line.strip()]
    assert len(lines) > 0
    for line in lines:
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z ", line), line
    assert any("gate G-P0" in line for line in lines)
    assert any("gate G-I1" in line for line in lines)
    assert any("gate G-E1" in line for line in lines)
    assert any("gate G-Z1/G-Z2" in line for line in lines)
    parent_lines = [line for line in lines if re.search(r"parent \d{4}: processed", line)]
    assert len(parent_lines) == len(h.EXPECTED_PARENT_IDS)
    assert any("invariant HB1" in line for line in lines)
    assert any("invariant HB11" in line for line in lines)
    assert any(f"run_status: {h.RUN_STATUS}" in line for line in lines)
    assert any("determinism_double_run: byte_identical=True" in line for line in lines)


def test_b14_determinism_double_run_recorded_before_manifest(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    run_log = (out_root / "run.log").read_text(encoding="utf-8")
    assert "determinism_double_run: byte_identical=True differing_files=[]" in run_log
    # FREEZE_MANIFEST.sha256 hashes the FINAL run.log content (with the determinism line).
    manifest_lines = (out_root / "FREEZE_MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    manifest_by_name = {line.split("  ", 2)[2]: line.split("  ", 2)[0] for line in manifest_lines}
    actual_sha = hashlib.sha256((out_root / "run.log").read_bytes()).hexdigest()
    assert manifest_by_name["run.log"] == actual_sha


def test_d2_z_gate_blocked_run_emits_exactly_five_files(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    attestation_payload = json.loads(fixture["attestation_path"].read_text(encoding="utf-8"))
    attestation_payload["target_unit"] = "feet"
    fixture["attestation_path"].write_text(json.dumps(attestation_payload, sort_keys=True) + "\n", encoding="utf-8")
    fixture["expected_z_unit_attestation_sha256"] = _sha256_path(fixture["attestation_path"])
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 2
    on_disk = {p.name for p in out_root.iterdir()}
    assert on_disk == {"z_unit_gate.json", "family_decision.json", "command.txt", "run.log", "command_stdout_stderr.log"}
    assert len(on_disk) == 5
    assert not (out_root / "FREEZE_MANIFEST.sha256").exists()
    decision = json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))
    gate = json.loads((out_root / "z_unit_gate.json").read_text(encoding="utf-8"))
    assert decision["run_validity"] == gate["run_validity"] == "RUN_BLOCKED"


def test_d2_pre_z_gate_blocked_run_emits_exactly_five_files(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    argv = _full_argv(fixture, out_root)
    npz_index = argv.index("--expected-npz-sha256") + 1
    argv[npz_index] = "0" * 64
    proc = _run_cli(argv)
    assert proc.returncode == 2
    on_disk = {p.name for p in out_root.iterdir()}
    assert on_disk == {"gate_report.json", "family_decision.json", "command.txt", "run.log", "command_stdout_stderr.log"}
    assert len(on_disk) == 5
    assert not (out_root / "FREEZE_MANIFEST.sha256").exists()
    gate_report = json.loads((out_root / "gate_report.json").read_text(encoding="utf-8"))
    assert gate_report["verdict"] == "RUN_BLOCKED"
    decision = json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))
    assert decision["run_validity"] == "RUN_BLOCKED"
    assert decision["height_mechanism_productive"] == "NOT_EVALUABLE"


def test_run_valid_inventory_is_exactly_25_content_files_plus_manifest(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out"
    proc = _run_cli(_full_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    on_disk = sorted(p.name for p in out_root.iterdir())
    assert on_disk == sorted([*h.OUTPUT_CONTENT_FILES, "FREEZE_MANIFEST.sha256"])
    assert len(h.OUTPUT_CONTENT_FILES) == 25
    assert len(on_disk) == 26
    assert "gate_report.json" not in on_disk
    assert "z_unit_gate.json" not in on_disk


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
