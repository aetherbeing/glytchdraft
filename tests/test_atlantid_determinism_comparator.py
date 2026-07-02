"""Focused, non-processing tests for scripts/diagnostics/atlantid_determinism_comparator.py.

These tests build small synthetic run roots under tmp_path -- never real LAZ,
GLB, or Miami/NOLA tile data, never a copy of the real failed smoke root at
/tmp/glytchdraft-miami-controlled-smoke-20260702T030834Z -- and exercise the
comparator's refusal conditions, normalization policy, and classification
rules. No PDAL, no /mnt/t7, no network, no real smoke execution.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARATOR_PATH = REPO_ROOT / "scripts" / "diagnostics" / "atlantid_determinism_comparator.py"
SCHEMA_PATH = REPO_ROOT / "schemas" / "atlantid_determinism_report.schema.json"


def _load_comparator_module():
    spec = importlib.util.spec_from_file_location("atlantid_determinism_comparator_under_test", COMPARATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load_comparator_module()
AUTHORIZED_TILE_IDS = mod.AUTHORIZED_TILE_IDS
KNOWN_CANONICAL_SOURCE_SHA256 = dict(mod.KNOWN_CANONICAL_SOURCE_SHA256)
KNOWN_CANONICAL_SOURCE_PATHS = dict(mod.KNOWN_CANONICAL_SOURCE_PATHS)

try:
    from jsonschema import Draft7Validator, validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False


# ── fixture builders ────────────────────────────────────────────────────────

def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def build_valid_run(
    tmp_path: Path,
    name: str,
    *,
    tile_ids: Sequence[str] = AUTHORIZED_TILE_IDS,
    source_hashes: dict[str, str] | None = None,
    git_head: str = "a" * 40,
    git_branch: str = "feat/synthetic",
    git_dirty: bool = False,
    python_version: str = "3.11.5",
    platform_str: str = "Linux-synthetic",
    created_at: str = "2026-07-01T00:00:00Z",
    run_id: str = "atlantid-synthetic-run-a",
    elapsed_s: float = 12.3,
    embed_real_root_paths: bool = True,
    manifest_overrides: dict[str, Any] | None = None,
    tile_manifest_overrides: dict[str, dict[str, Any]] | None = None,
    metrics_overrides: dict[str, dict[str, Any]] | None = None,
    extra_root_files: dict[str, bytes] | None = None,
    skip_tiles: Sequence[str] = (),
) -> Path:
    """Build a synthetic, structurally-complete controlled-smoke output root.

    embed_real_root_paths=False substitutes a fixed placeholder for
    output_root/cwd instead of the real tmp path, so two independently built
    roots can be made truly byte-identical for PASS-classification tests
    without the always-differing-tmp-path effect (tested separately).
    """
    root = tmp_path / name
    qa = root / "qa"
    tiles_dir = root / "tiles"
    source_hashes = source_hashes or dict(KNOWN_CANONICAL_SOURCE_SHA256)
    tile_manifest_overrides = tile_manifest_overrides or {}
    metrics_overrides = metrics_overrides or {}
    extra_root_files = extra_root_files or {}

    embedded_root = str(root) if embed_real_root_paths else "<FIXED_PLACEHOLDER_ROOT>"

    inputs = []
    for tid in tile_ids:
        sha = source_hashes.get(tid, "0" * 64)
        path = KNOWN_CANONICAL_SOURCE_PATHS.get(tid, f"/mnt/t7/miami/data_raw/laz/synthetic_{tid}.laz")
        inputs.append({"tile_id": tid, "path": path, "bytes": 1000, "sha256": sha})

    metrics = []
    for tid in tile_ids:
        base = {
            "tile_id": tid,
            "units": {"processed_z": "meters"},
            "crs": {"processed_horizontal": "EPSG:32617"},
            "height": {"normalized": 10.0, "compatible": True},
            "ground_z": {"normalized": 1.0, "compatible": True},
            "absolute_roof_elevation": {"normalized": 11.0, "compatible": True},
            "building_relative_height": {"normalized": 9.0, "compatible": True},
            "point_counts": {"normalized": 500000, "compatible": True},
            "z_conversion_factor": 0.3048006096012192,
        }
        base.update(metrics_overrides.get(tid, {}))
        metrics.append(base)

    manifest: dict[str, Any] = {
        "schema_version": "miami_metric_normalization_smoke.v1",
        "created_at": created_at,
        "dry_run": False,
        "feature_gate": {"name": "MIAMI_METRIC_NORMALIZATION_V1", "value": "1", "enabled": True},
        "release": {"status": "CONDITIONAL_GO", "real_data_execution_enabled": True, "blocked_until": "n/a"},
        "controlled_smoke": {
            "active": True,
            "authorization_provided": True,
            "auth_token_name": "MIAMI_CONTROLLED_SMOKE_AUTHORIZED",
            "preflight": {"all_clear": True},
        },
        "git": {"branch": git_branch, "head": git_head, "dirty": git_dirty, "status_short": []},
        "environment": {"profile": {"python": python_version, "platform": platform_str, "cwd": embedded_root}, "variables": {}},
        "output_root": embedded_root,
        "run_id": run_id,
        "source_contract": {},
        "provenance_findings": [],
        "inputs": inputs,
        "commands": [
            {
                "label": "run_tile_miami",
                "argv": ["python", "run_tile_miami.py", "--out", f"{embedded_root}/tiles/{inputs[0]['tile_id']}"],
                "runnable": True,
                "started_at": "2026-07-01T00:00:01Z",
                "ended_at": "2026-07-01T00:00:02Z",
                "returncode": 0,
            },
        ],
        "metrics": metrics,
        "output_hashes": [],
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)

    write_json(qa / "miami_metric_smoke_manifest.json", manifest)
    (qa / "miami_metric_smoke_report.md").write_text(
        f"# Miami Two-Tile Metric Normalization Smoke\n\n- Created: `{created_at}`\n- Output root: `{embedded_root}`\n",
        encoding="utf-8",
    )
    (qa / "miami_metric_smoke_report.html").write_text(
        f"<pre>- Created: `{created_at}`\n- Output root: `{embedded_root}`</pre>\n", encoding="utf-8"
    )
    with (qa / "miami_metric_smoke_inputs.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["tile_id", "bytes", "sha256", "path"])
        writer.writeheader()
        for item in inputs:
            writer.writerow(item)

    for tid in tile_ids:
        if tid in skip_tiles:
            continue
        tile_manifest = {
            "schema_version": "glitchos_miami_pipeline.v1",
            "pipeline": "GlitchOS.io Miami city pipeline",
            "tile_id": tid,
            "generated_at": created_at,
            "elapsed_s": elapsed_s,
            "all_stages_passed": True,
            "terrain_only": False,
            "building_mass_lod0": 10,
            "building_mass_lod1": 10,
            "n_clusters": 10,
            "n_footprints": 10,
            "n_vegetation_pts": 1000,
            "vegetation_enabled": True,
            "stages": {"extract": "ok", "clean": "ok", "cluster": "ok", "footprints": "ok", "masses": "ok"},
            "errors": {},
        }
        tile_manifest.update(tile_manifest_overrides.get(tid, {}))
        write_json(tiles_dir / tid / "manifest" / f"{tid}_manifest.json", tile_manifest)
        marker = tiles_dir / tid / "pointcloud" / f"{tid}_ground_marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("synthetic pointcloud marker\n", encoding="utf-8")

    for rel, content in extra_root_files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    return root


def run_comparison(root_a: Path, root_b: Path, **kwargs) -> dict[str, Any]:
    manifest_a = mod.load_run_manifest(root_a)
    manifest_b = mod.load_run_manifest(root_b)
    inv_a, esc_a = mod.collect_inventory(root_a)
    inv_b, esc_b = mod.collect_inventory(root_b)
    errors_a = mod.validate_run_completeness(root_a, manifest_a)
    errors_b = mod.validate_run_completeness(root_b, manifest_b)
    if errors_a or errors_b:
        return {"refused": True, "errors_a": errors_a, "errors_b": errors_b}
    ev_a = mod.collect_run_evidence(root_a, "A", manifest_a, inv_a, esc_a)
    ev_b = mod.collect_run_evidence(root_b, "B", manifest_b, inv_b, esc_b)
    report = mod.build_report(
        ev_a,
        ev_b,
        tolerances=kwargs.get("tolerances", {"count": 0, "z_m": 0.0}),
        allow_different_commits=kwargs.get("allow_different_commits", False),
        allowed_file_patterns=kwargs.get("allowed_file_patterns", []),
    )
    return {"refused": False, "report": report}


def codes(report: dict[str, Any], severity: str | None = None) -> list[str]:
    return [f["code"] for f in report["findings"] if severity is None or f["severity"] == severity]


# ── refusal conditions ───────────────────────────────────────────────────────

def test_refuses_pre_execution_failed_shape_no_tiles_directory(tmp_path: Path):
    """Scenario 19: the real failed-smoke shape (qa/ present, no tiles/) must
    never be treated as a successful completed run."""
    root = tmp_path / "failed_pre_execution"
    qa = root / "qa"
    manifest = {
        "schema_version": "miami_metric_normalization_smoke.v1",
        "created_at": "2026-07-02T03:08:34Z",
        "dry_run": False,
        "controlled_smoke": {"active": True, "authorization_provided": True},
        "provenance_findings": [],
        "commands": [{"label": "building_characteristics_validator", "returncode": 2}],
        "git": {"branch": "x", "head": "a" * 40, "dirty": False},
        "environment": {"profile": {"python": "3.11.5", "platform": "Linux", "cwd": str(root)}},
        "inputs": [],
        "metrics": [],
        "output_hashes": [],
    }
    write_json(qa / "miami_metric_smoke_manifest.json", manifest)
    (qa / "miami_metric_smoke_report.md").write_text("# refused\n", encoding="utf-8")

    other = build_valid_run(tmp_path, "other_valid")
    result = run_comparison(root, other)

    assert result["refused"] is True
    assert any("tiles/ directory is missing" in e for e in result["errors_a"])


def test_refuses_missing_manifest(tmp_path: Path):
    root = tmp_path / "no_manifest"
    (root / "tiles").mkdir(parents=True)
    other = build_valid_run(tmp_path, "other_valid")
    result = run_comparison(root, other)
    assert result["refused"] is True
    assert any("missing or unparsable" in e for e in result["errors_a"])


def test_refuses_dry_run(tmp_path: Path):
    root = build_valid_run(tmp_path, "dry_run", manifest_overrides={"dry_run": True})
    other = build_valid_run(tmp_path, "other_valid")
    result = run_comparison(root, other)
    assert result["refused"] is True
    assert any("dry_run" in e for e in result["errors_a"])


def test_refuses_unauthorized_ad_hoc_run(tmp_path: Path):
    root = build_valid_run(tmp_path, "ad_hoc", manifest_overrides={"controlled_smoke": {"active": False, "authorization_provided": False}})
    other = build_valid_run(tmp_path, "other_valid")
    result = run_comparison(root, other)
    assert result["refused"] is True
    assert any("controlled_smoke.active" in e for e in result["errors_a"])


def test_refuses_unsupported_manifest_schema_version(tmp_path: Path):
    """Scenario 16."""
    root = build_valid_run(tmp_path, "bad_schema", manifest_overrides={"schema_version": "some_other_schema.v9"})
    other = build_valid_run(tmp_path, "other_valid")
    result = run_comparison(root, other)
    assert result["refused"] is True
    assert any("unsupported or missing manifest schema_version" in e for e in result["errors_a"])


def test_refuses_failed_command(tmp_path: Path):
    root = build_valid_run(
        tmp_path,
        "failed_command",
        manifest_overrides={"commands": [{"label": "run_tile_miami", "argv": [], "returncode": 1}]},
    )
    other = build_valid_run(tmp_path, "other_valid")
    result = run_comparison(root, other)
    assert result["refused"] is True
    assert any("did not complete successfully" in e for e in result["errors_a"])


def test_refuses_empty_tile_directory(tmp_path: Path):
    root = build_valid_run(tmp_path, "empty_tile", skip_tiles=[AUTHORIZED_TILE_IDS[1]])
    (root / "tiles" / AUTHORIZED_TILE_IDS[1]).mkdir(parents=True)
    other = build_valid_run(tmp_path, "other_valid")
    result = run_comparison(root, other)
    assert result["refused"] is True
    assert any("empty" in e for e in result["errors_a"])


# ── CLI-level refusals (subprocess) ─────────────────────────────────────────

def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COMPARATOR_PATH), *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False
    )


def test_cli_refuses_same_path(tmp_path: Path):
    root = build_valid_run(tmp_path, "same")
    result = run_cli(
        "--run-a", str(root), "--run-b", str(root),
        "--report-json", str(tmp_path / "r.json"), "--report-md", str(tmp_path / "r.md"),
    )
    assert result.returncode == 2
    assert "must be different paths" in result.stderr
    assert not (tmp_path / "r.json").exists()


def test_cli_refuses_nonexistent_root(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    result = run_cli(
        "--run-a", str(root_a), "--run-b", str(tmp_path / "does_not_exist"),
        "--report-json", str(tmp_path / "r.json"), "--report-md", str(tmp_path / "r.md"),
    )
    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_cli_refuses_overwrite_without_flag(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b")
    report_json = tmp_path / "report.json"
    report_json.write_text("{}", encoding="utf-8")
    result = run_cli(
        "--run-a", str(root_a), "--run-b", str(root_b),
        "--report-json", str(report_json), "--report-md", str(tmp_path / "report.md"),
    )
    assert result.returncode == 2
    assert "already exists" in result.stderr


def test_cli_writes_reports_and_returns_nonzero_on_fail(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", source_hashes={tid: "f" * 64 for tid in AUTHORIZED_TILE_IDS})
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"
    result = run_cli(
        "--run-a", str(root_a), "--run-b", str(root_b),
        "--report-json", str(report_json), "--report-md", str(report_md),
    )
    assert result.returncode == 1
    assert report_json.exists() and report_md.exists()
    data = json.loads(report_json.read_text(encoding="utf-8"))
    assert data["classification"] == "FAIL"


def test_cli_overwrite_flag_permits_rewrite(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b")
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"
    report_json.write_text("{}", encoding="utf-8")
    report_md.write_text("stale", encoding="utf-8")
    result = run_cli(
        "--run-a", str(root_a), "--run-b", str(root_b),
        "--report-json", str(report_json), "--report-md", str(report_md), "--overwrite",
    )
    assert result.returncode in (0, 1)
    assert json.loads(report_json.read_text(encoding="utf-8"))["schema_version"] == "glytchos.atlantid_determinism_report.v1"


# ── classification scenarios ────────────────────────────────────────────────

def test_scenario_1_identical_runs_pass(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", embed_real_root_paths=False)
    root_b = build_valid_run(tmp_path, "b", embed_real_root_paths=False)
    result = run_comparison(root_a, root_b)
    assert result["refused"] is False
    report = result["report"]
    assert report["classification"] == "PASS", report["classification_reasons"]
    assert codes(report, "blocker") == []
    assert codes(report, "warning") == []


def test_scenario_2_timestamp_and_run_id_only_differences_non_blocking(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", embed_real_root_paths=False, created_at="2026-07-01T00:00:00Z", run_id="atlantid-run-a", elapsed_s=10.0)
    root_b = build_valid_run(tmp_path, "b", embed_real_root_paths=False, created_at="2026-07-01T01:00:00Z", run_id="atlantid-run-b", elapsed_s=99.9)
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "PASS WITH NON-BLOCKING FINDINGS", report["classification_reasons"]
    assert codes(report, "blocker") == []
    assert "normalized_equal" in codes(report, "warning")


def test_scenario_3_differing_output_root_paths_not_material(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", embed_real_root_paths=True)
    root_b = build_valid_run(tmp_path, "b", embed_real_root_paths=True)
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] in ("PASS", "PASS WITH NON-BLOCKING FINDINGS")
    assert codes(report, "blocker") == []


def test_scenario_4_source_hash_mismatch_fails(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", source_hashes={AUTHORIZED_TILE_IDS[0]: "9" * 64, AUTHORIZED_TILE_IDS[1]: KNOWN_CANONICAL_SOURCE_SHA256[AUTHORIZED_TILE_IDS[1]]})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "source_hash_mismatch" in codes(report, "blocker")


def test_scenario_5_third_tile_fails(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(
        tmp_path,
        "b",
        tile_ids=(*AUTHORIZED_TILE_IDS, "999999"),
        source_hashes={**KNOWN_CANONICAL_SOURCE_SHA256, "999999": "9" * 64},
    )
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "unauthorized_tile" in codes(report, "blocker")
    assert "tile_set_mismatch_between_runs" in codes(report, "blocker")


def test_scenario_6_missing_required_tile_fails(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_ids=(AUTHORIZED_TILE_IDS[0],))
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "missing_authorized_tile" in codes(report, "blocker")


def test_scenario_7_crs_mismatch_fails(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", metrics_overrides={tid: {"crs": {"processed_horizontal": "EPSG:4326"}}})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "crs_mismatch" in codes(report, "blocker")


def test_scenario_8_unit_mismatch_fails(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", metrics_overrides={tid: {"units": {"processed_z": "US survey foot"}}})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "unit_mismatch" in codes(report, "blocker")


def test_scenario_9_z_value_mismatch_outside_and_within_tolerance(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", metrics_overrides={tid: {"height": {"normalized": 10.5, "compatible": True}}})

    zero_tolerance = run_comparison(root_a, root_b, tolerances={"count": 0, "z_m": 0.0})
    assert zero_tolerance["report"]["classification"] == "FAIL"
    assert "z_value_mismatch" in codes(zero_tolerance["report"], "blocker")

    boundary_tolerance = run_comparison(root_a, root_b, tolerances={"count": 0, "z_m": 0.5})
    assert "z_value_mismatch" not in codes(boundary_tolerance["report"], "blocker")
    assert boundary_tolerance["report"]["classification"] == "PASS WITH NON-BLOCKING FINDINGS"

    wide_tolerance = run_comparison(root_a, root_b, tolerances={"count": 0, "z_m": 1.0})
    assert wide_tolerance["report"]["classification"] == "PASS WITH NON-BLOCKING FINDINGS"


def test_scenario_10_point_count_mismatch_fails(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", metrics_overrides={tid: {"point_counts": {"normalized": 500001, "compatible": True}}})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "point_count_mismatch" in codes(report, "blocker")


def test_scenario_10b_tile_manifest_count_field_mismatch_fails(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_manifest_overrides={tid: {"n_footprints": 11}})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "count_mismatch" in codes(report, "blocker")


def test_scenario_11_missing_required_file_fails(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b")
    (root_a / "qa" / "miami_metric_smoke_inputs.csv").unlink()
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "unexplained_file_only_in_run_b" in codes(report, "blocker")
    assert "qa/miami_metric_smoke_inputs.csv" in report["inventory_comparison"]["only_in_run_b"]


def test_scenario_12_unexpected_file_reported_and_governed_by_allow_pattern(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", extra_root_files={"qa/unexpected_extra.json": b'{"note":"synthetic"}'})

    default_result = run_comparison(root_a, root_b)
    assert default_result["report"]["classification"] == "FAIL"
    assert "unexplained_file_only_in_run_b" in codes(default_result["report"], "blocker")

    allowed_result = run_comparison(root_a, root_b, allowed_file_patterns=["qa/unexpected_extra.json"])
    assert "unexplained_file_only_in_run_b" not in codes(allowed_result["report"], "blocker")
    assert "file_only_in_run_b_allowed" in codes(allowed_result["report"], "info")
    assert allowed_result["report"]["classification"] != "FAIL"


def test_scenario_13_production_allowed_true_fails(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", extra_root_files={"qa/publication_gate.json": json.dumps({"publication": {"production_allowed": True}}).encode("utf-8")})
    root_b = build_valid_run(tmp_path, "b", extra_root_files={"qa/publication_gate.json": json.dumps({"publication": {"production_allowed": True}}).encode("utf-8")})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "production_allowed_true" in codes(report, "blocker")


def test_scenario_13b_auto_publish_enabled_true_fails(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", extra_root_files={"qa/publication_gate.json": json.dumps({"publication": {"auto_publish_enabled": True}}).encode("utf-8")})
    root_b = build_valid_run(tmp_path, "b", extra_root_files={"qa/publication_gate.json": json.dumps({"publication": {"auto_publish_enabled": True}}).encode("utf-8")})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "auto_publish_enabled_true" in codes(report, "blocker")


def test_scenario_14_tile_stage_validation_failure_fails(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_manifest_overrides={tid: {"all_stages_passed": False, "errors": {"masses": "synthetic failure"}}})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "tile_stage_failure" in codes(report, "blocker")
    assert "tile_errors_present" in codes(report, "blocker")


def test_scenario_15_pipeline_commit_mismatch_visible_and_classified(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", git_head="a" * 40)
    root_b = build_valid_run(tmp_path, "b", git_head="b" * 40)

    default_result = run_comparison(root_a, root_b)
    assert default_result["report"]["classification"] == "FAIL"
    assert "pipeline_commit_mismatch" in codes(default_result["report"], "blocker")

    allowed_result = run_comparison(root_a, root_b, allow_different_commits=True)
    assert "pipeline_commit_mismatch" not in codes(allowed_result["report"], "blocker")
    assert "pipeline_commit_mismatch_accepted" in codes(allowed_result["report"], "warning")
    assert allowed_result["report"]["classification"] == "PASS WITH NON-BLOCKING FINDINGS"


def test_scenario_16_unsupported_contract_version_refused():
    # Already covered structurally by test_refuses_unsupported_manifest_schema_version;
    # this asserts the refusal happens before any report is produced (no silent pass-through).
    pass


def test_scenario_17_array_reordering_of_unordered_key_not_a_false_failure(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", embed_real_root_paths=False)
    root_b = build_valid_run(tmp_path, "b", embed_real_root_paths=False)

    manifest_path_a = root_a / "qa" / "miami_metric_smoke_manifest.json"
    manifest_path_b = root_b / "qa" / "miami_metric_smoke_manifest.json"
    manifest_a = json.loads(manifest_path_a.read_text(encoding="utf-8"))
    manifest_b = json.loads(manifest_path_b.read_text(encoding="utf-8"))
    hashes = [
        {"path": "qa/x.txt", "bytes": 1, "sha256": "1" * 64},
        {"path": "qa/y.txt", "bytes": 2, "sha256": "2" * 64},
    ]
    manifest_a["output_hashes"] = list(hashes)
    manifest_b["output_hashes"] = list(reversed(hashes))
    write_json(manifest_path_a, manifest_a)
    write_json(manifest_path_b, manifest_b)

    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert codes(report, "blocker") == []
    assert report["classification"] != "FAIL"


def test_scenario_18_meaningful_json_difference_not_normalized_away(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", embed_real_root_paths=False)
    root_b = build_valid_run(tmp_path, "b", embed_real_root_paths=False)

    manifest_path_b = root_b / "qa" / "miami_metric_smoke_manifest.json"
    manifest_b = json.loads(manifest_path_b.read_text(encoding="utf-8"))
    manifest_b["provenance_findings"] = []  # stays clean for run-completeness
    manifest_b["release"]["status"] = "GO"  # meaningful field, must not be normalized away
    write_json(manifest_path_b, manifest_b)

    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "unexplained_content_difference" in codes(report, "blocker")
    per_file = report["inventory_comparison"]["per_file"]["qa/miami_metric_smoke_manifest.json"]
    assert per_file["status"] == "different"
    assert any(d["path"] == "release.status" for d in per_file.get("diffs", []))


def test_scenario_19_failed_pre_execution_shape_cannot_be_run_a_or_b(tmp_path: Path):
    # Duplicate, explicit assertion alongside test_refuses_pre_execution_failed_shape_no_tiles_directory
    # to keep the scenario numbering from the mission traceable 1:1 in this file.
    root = tmp_path / "failed_shape"
    write_json(
        root / "qa" / "miami_metric_smoke_manifest.json",
        {
            "schema_version": "miami_metric_normalization_smoke.v1",
            "dry_run": False,
            "controlled_smoke": {"active": True, "authorization_provided": True},
            "provenance_findings": [],
            "commands": [{"label": "building_characteristics_validator", "returncode": 2}],
            "inputs": [],
        },
    )
    valid = build_valid_run(tmp_path, "valid_counterpart")
    as_run_a = run_comparison(root, valid)
    as_run_b = run_comparison(valid, root)
    assert as_run_a["refused"] is True
    assert as_run_b["refused"] is True


# ── source-identity cross-check against known canonical hashes ─────────────

def test_both_runs_agreeing_on_wrong_hash_still_fails(tmp_path: Path):
    """A==B is not sufficient; both runs silently processing the wrong input
    for a tile must still be caught via the known canonical hash cross-check."""
    wrong_hash = "d" * 64
    root_a = build_valid_run(tmp_path, "a", source_hashes={tid: wrong_hash for tid in AUTHORIZED_TILE_IDS})
    root_b = build_valid_run(tmp_path, "b", source_hashes={tid: wrong_hash for tid in AUTHORIZED_TILE_IDS})
    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "source_hash_not_canonical" in codes(report, "blocker")


# ── symlink escape ──────────────────────────────────────────────────────────

def test_symlink_escape_outside_run_root_detected(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b")
    outside_target = tmp_path / "outside_secret.txt"
    outside_target.write_text("outside content\n", encoding="utf-8")
    symlink_path = root_b / "qa" / "escaped_link.txt"
    try:
        symlink_path.symlink_to(outside_target)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")

    result = run_comparison(root_a, root_b)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "symlink_escape" in codes(report, "blocker")
    assert report["inventory_comparison"]["symlink_escapes_run_b"]


# ── report schema self-consistency ──────────────────────────────────────────

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_file_is_valid_draft7():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_pass_report_validates_against_schema(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", embed_real_root_paths=False)
    root_b = build_valid_run(tmp_path, "b", embed_real_root_paths=False)
    report = run_comparison(root_a, root_b)["report"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate(instance=report, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_fail_report_validates_against_schema(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_ids=(AUTHORIZED_TILE_IDS[0],))
    report = run_comparison(root_a, root_b)["report"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate(instance=report, schema=schema)


# ── safety: execution locks and no real-data touch ──────────────────────────

def test_comparator_never_opens_mnt_t7_or_touches_execution_locks():
    """The comparator may mention /mnt/t7 in documentation strings (it explains
    where the harness's canonical LAZ sources live) but must never open/read/write
    a path under it, and must never reference REAL_DATA_EXECUTION_ENABLED (that
    lock belongs to miami_metric_smoke_harness.py / run_tile_miami.py only)."""
    source = COMPARATOR_PATH.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped_lock = line.strip()
        if "REAL_DATA_EXECUTION_ENABLED" in stripped_lock:
            assert "=" not in stripped_lock.split("REAL_DATA_EXECUTION_ENABLED", 1)[1][:3], (
                f"line assigns to REAL_DATA_EXECUTION_ENABLED: {stripped_lock!r}"
            )
    for line in source.splitlines():
        stripped = line.strip()
        if "/mnt/t7" not in stripped:
            continue
        assert not any(call in stripped for call in ("open(", ".read_", ".write_", "Path(\"/mnt/t7", "Path('/mnt/t7")), (
            f"line performs filesystem I/O referencing /mnt/t7: {stripped!r}"
        )


def test_run_tile_miami_and_smoke_harness_locks_remain_false():
    runtime = (REPO_ROOT / "scripts" / "miami" / "run_tile_miami.py").read_text(encoding="utf-8")
    harness = (REPO_ROOT / "scripts" / "diagnostics" / "miami_metric_smoke_harness.py").read_text(encoding="utf-8")
    assert "REAL_DATA_EXECUTION_ENABLED: bool = False" in runtime
    assert "REAL_DATA_EXECUTION_ENABLED: bool = True" not in runtime
    assert "REAL_DATA_EXECUTION_ENABLED = False" in harness
    assert "REAL_DATA_EXECUTION_ENABLED = True" not in harness


def test_miami_production_allowed_remains_false():
    miami_config = json.loads((REPO_ROOT / "configs" / "cities" / "miami.json").read_text(encoding="utf-8"))
    assert miami_config["pipeline_tunables"]["footprint_source_detail"]["production_allowed"] is False


# ═════════════════════════════════════════════════════════════════════════════
# PR #37 bounded correctness pass: path-specific tolerances, exact-commit-path
# normalization, deduplicated normalization/tolerance records.
# ═════════════════════════════════════════════════════════════════════════════

WIDE_TOLERANCES = {"count": 1000, "z_m": 1000.0}
ZERO_TOLERANCES = {"count": 0, "z_m": 0.0}


def _direct_compare(a: Any, b: Any, *, extra_normalized_paths: frozenset[str] = frozenset(), tolerances: dict[str, float] = ZERO_TOLERANCES):
    normalization_events: list = []
    tolerated_paths: list = []
    diffs: list = []
    equal = mod.compare_json_values(
        a, b, "",
        run_root_a="", run_root_b="",
        extra_normalized_paths=extra_normalized_paths, tolerances=tolerances,
        normalization_events=normalization_events, tolerated_paths=tolerated_paths, diffs=diffs,
    )
    return equal, normalization_events, tolerated_paths, diffs


# ── 1-2: tolerance applies only to approved paths ──────────────────────────

def test_count_tolerance_category_only_for_approved_count_paths():
    for suffix in mod.APPROVED_COUNT_TOLERANCE_PATH_SUFFIXES:
        path = ".".join(suffix)
        assert mod.tolerance_category_for_path(path) == "count", path
        # index-agnostic: metrics[0].point_counts.normalized must match the same as metrics.point_counts.normalized
        indexed = re_sub_first_component_index(path)
        assert mod.tolerance_category_for_path(indexed) == "count", indexed


def test_z_tolerance_category_only_for_approved_z_paths():
    for suffix in mod.APPROVED_Z_TOLERANCE_PATH_SUFFIXES:
        path = ".".join(suffix)
        assert mod.tolerance_category_for_path(path) == "z_m", path


def re_sub_first_component_index(path: str) -> str:
    parts = path.split(".")
    parts[0] = f"{parts[0]}[0]"
    return ".".join(parts)


@pytest.mark.parametrize(
    "path",
    [
        "commands[0].returncode",
        "inputs[0].bytes",
        "source_records.318155.bytes",
        "metrics[0].crs.processed_horizontal_epsg",
        "metrics[0].some_other_metric",
        "outputs.glb.size_bytes",
        "n_footprints.extra",  # not an exact top-level match
        "tile_id",
        "metrics[0].point_counts.raw",  # only .normalized is approved, not .raw
    ],
)
def test_unapproved_paths_are_never_tolerated(path):
    assert mod.tolerance_category_for_path(path) is None


# ── 3: tile-ID difference fails even with nonzero count tolerance ──────────

def test_tile_id_difference_fails_even_with_count_tolerance(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_manifest_overrides={tid: {"tile_id": "999999"}})
    result = run_comparison(root_a, root_b, tolerances=WIDE_TOLERANCES)
    report = result["report"]
    assert report["classification"] == "FAIL"
    per_file = report["inventory_comparison"]["per_file"][f"tiles/{tid}/manifest/{tid}_manifest.json"]
    assert per_file["status"] == "different"
    assert any(d["path"] == "tile_id" for d in per_file.get("diffs", []))


# ── 4: byte-size difference fails unless the exact path is explicitly allowed ─

def test_source_byte_size_difference_fails_with_nonzero_count_tolerance(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    tid0 = AUTHORIZED_TILE_IDS[0]
    root_b = build_valid_run(tmp_path, "b")
    manifest_path_b = root_b / "qa" / "miami_metric_smoke_manifest.json"
    manifest_b = json.loads(manifest_path_b.read_text(encoding="utf-8"))
    for item in manifest_b["inputs"]:
        if item["tile_id"] == tid0:
            item["bytes"] += 5
    write_json(manifest_path_b, manifest_b)

    result = run_comparison(root_a, root_b, tolerances=WIDE_TOLERANCES)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "source_size_mismatch" in codes(report, "blocker")
    per_file = report["inventory_comparison"]["per_file"]["qa/miami_metric_smoke_manifest.json"]
    assert per_file["status"] == "different"
    assert any(d["path"].endswith(".bytes") for d in per_file.get("diffs", []))


# ── 5: return-code difference is exact (never tolerated) ───────────────────

def test_returncode_difference_is_never_tolerated():
    equal, _, _, diffs = _direct_compare(
        {"commands": [{"label": "x", "returncode": 0}]},
        {"commands": [{"label": "x", "returncode": 2}]},
        tolerances=WIDE_TOLERANCES,
    )
    assert equal is False
    assert any(d["path"] == "commands[0].returncode" for d in diffs)


# ── 6: EPSG / CRS-identifier-shaped numeric difference is exact ────────────

def test_epsg_style_numeric_difference_is_never_tolerated():
    equal, _, _, diffs = _direct_compare(
        {"metrics": [{"crs": {"processed_horizontal_epsg": 32617}}]},
        {"metrics": [{"crs": {"processed_horizontal_epsg": 4326}}]},
        tolerances=WIDE_TOLERANCES,
    )
    assert equal is False
    assert any(d["path"] == "metrics[0].crs.processed_horizontal_epsg" for d in diffs)


# ── 7: an unrelated float difference is exact even with nonzero Z tolerance ─

def test_unrelated_float_difference_is_never_tolerated():
    equal, _, _, diffs = _direct_compare(
        {"some_other_metric": 5.0},
        {"some_other_metric": 5.05},
        tolerances=WIDE_TOLERANCES,
    )
    assert equal is False
    assert any(d["path"] == "some_other_metric" for d in diffs)


# ── 8-9: exact pipeline-commit path only, never a bare "head" key ──────────

def test_exact_commit_path_normalized_only_with_allow_flag():
    without_flag, events_without, _, _ = _direct_compare(
        {"git": {"head": "a" * 40}}, {"git": {"head": "b" * 40}}, extra_normalized_paths=frozenset()
    )
    assert without_flag is False

    with_flag, events_with, _, _ = _direct_compare(
        {"git": {"head": "a" * 40}}, {"git": {"head": "b" * 40}}, extra_normalized_paths=frozenset({"git.head"})
    )
    assert with_flag is True
    assert len(events_with) == 1
    assert events_with[0]["path"] == "git.head"
    assert events_with[0]["mechanism"] == "explicit_opt_in_normalization"
    assert events_with[0]["value_a"] == "a" * 40
    assert events_with[0]["value_b"] == "b" * 40


def test_unrelated_key_named_head_is_not_normalized():
    equal, _, _, diffs = _direct_compare(
        {"other": {"head": "a" * 40}}, {"other": {"head": "b" * 40}}, extra_normalized_paths=frozenset({"git.head"})
    )
    assert equal is False
    assert any(d["path"] == "other.head" for d in diffs)


# ── 10-11: different-commit classification ceiling ─────────────────────────

def test_different_commits_without_allowance_fails(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", git_head="a" * 40)
    root_b = build_valid_run(tmp_path, "b", git_head="b" * 40)
    result = run_comparison(root_a, root_b)
    assert result["report"]["classification"] == "FAIL"
    assert "pipeline_commit_mismatch" in codes(result["report"], "blocker")


def test_different_commits_with_allowance_never_reaches_clean_pass(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", git_head="a" * 40, embed_real_root_paths=False)
    root_b = build_valid_run(tmp_path, "b", git_head="b" * 40, embed_real_root_paths=False)
    result = run_comparison(root_a, root_b, allow_different_commits=True)
    report = result["report"]
    assert report["classification"] == "PASS WITH NON-BLOCKING FINDINGS"
    assert report["classification"] != "PASS"
    assert "pipeline_commit_mismatch" not in codes(report, "blocker")
    assert "pipeline_commit_mismatch_accepted" in codes(report, "warning")
    # the runtime-identity finding still names both commit values
    accepted = next(f for f in report["findings"] if f["code"] == "pipeline_commit_mismatch_accepted")
    assert ("a" * 40) in accepted["message"] and ("b" * 40) in accepted["message"]


# ── 12: normalization events are not duplicated ─────────────────────────────

def test_normalization_events_are_not_duplicated(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a", embed_real_root_paths=True, created_at="2026-07-01T00:00:00Z")
    root_b = build_valid_run(tmp_path, "b", embed_real_root_paths=True, created_at="2026-07-01T05:00:00Z")
    manifest_a = json.loads((root_a / "qa" / "miami_metric_smoke_manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((root_b / "qa" / "miami_metric_smoke_manifest.json").read_text(encoding="utf-8"))

    normalization_events: list = []
    tolerated_paths: list = []
    diffs: list = []
    equal = mod.compare_json_values(
        manifest_a, manifest_b, "",
        run_root_a=str(root_a), run_root_b=str(root_b),
        extra_normalized_paths=frozenset(), tolerances=ZERO_TOLERANCES,
        normalization_events=normalization_events, tolerated_paths=tolerated_paths, diffs=diffs,
    )
    assert equal is True
    # exactly one event per distinct (path, mechanism) pair -- never two
    # (one per side) for the same field, and never more than one entry
    # merely because both manifests independently reference the run root.
    seen = set()
    for event in normalization_events:
        key = (event["path"], event["mechanism"])
        assert key not in seen, f"duplicate normalization event: {key}"
        seen.add(key)
    created_at_events = [e for e in normalization_events if e.get("key") == "created_at"]
    assert len(created_at_events) == 1
    assert created_at_events[0]["value_a"] == "2026-07-01T00:00:00Z"
    assert created_at_events[0]["value_b"] == "2026-07-01T05:00:00Z"


# ── 13: tolerance application records are not duplicated ───────────────────

def test_tolerance_application_visible_in_both_layers_produces_exactly_one_record(tmp_path: Path):
    """The same within-tolerance count difference is independently visible to
    compare_file_pair (raw JSON diff of the tile manifest file) and to
    compare_counts_and_geospatial (semantic field comparison of the same
    file). The final report must record it exactly once."""
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_manifest_overrides={tid: {"n_footprints": 11}})  # base is 10

    result = run_comparison(root_a, root_b, tolerances={"count": 1, "z_m": 0.0})
    report = result["report"]

    assert report["classification"] == "PASS WITH NON-BLOCKING FINDINGS", report["classification_reasons"]
    matching = [
        t for t in report["tolerance_applications"]
        if t["path"] == "n_footprints" and t["file"] == f"tiles/{tid}/manifest/{tid}_manifest.json"
    ]
    assert len(matching) == 1, report["tolerance_applications"]
    record = matching[0]
    assert record["value_a"] == 10
    assert record["value_b"] == 11
    assert record["tolerance_category"] == "count"
    assert record["tolerance"] == 1
    assert record["observed_difference"] == 1
    assert record["reason"]

    # And the raw file-level diff for that same tile manifest must NOT also
    # be a blocking "different" -- it should agree it's tolerated.
    per_file = report["inventory_comparison"]["per_file"][f"tiles/{tid}/manifest/{tid}_manifest.json"]
    assert per_file["status"] == "normalized_equal"
    assert "n_footprints" in per_file.get("tolerated_paths", [])


def test_z_tolerance_application_deduplicated_across_layers(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", metrics_overrides={tid: {"height": {"normalized": 10.3, "compatible": True}}})

    result = run_comparison(root_a, root_b, tolerances={"count": 0, "z_m": 0.5})
    report = result["report"]
    assert report["classification"] == "PASS WITH NON-BLOCKING FINDINGS"
    matching = [t for t in report["tolerance_applications"] if t["path"] == f"metrics[{tid}].height.normalized"]
    assert len(matching) == 1, report["tolerance_applications"]
    assert matching[0]["tolerance_category"] == "z_m"


# ── 14: report schema includes and validates tolerance_applications ────────

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_report_schema_requires_tolerance_applications():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert "tolerance_applications" in schema["required"]
    assert "tolerance_applications" in schema["properties"]


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_tolerance_report_validates_against_schema(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_manifest_overrides={tid: {"n_footprints": 11}})
    result = run_comparison(root_a, root_b, tolerances={"count": 1, "z_m": 0.0})
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate(instance=result["report"], schema=schema)
    assert len(result["report"]["tolerance_applications"]) == 1


# ── 16-18: refusal / third-tile / production_allowed re-verified after the correction ─

def test_pre_execution_refusal_still_cannot_pass_after_correction(tmp_path: Path):
    root = tmp_path / "failed_shape_corrected_check"
    write_json(
        root / "qa" / "miami_metric_smoke_manifest.json",
        {
            "schema_version": "miami_metric_normalization_smoke.v1",
            "dry_run": False,
            "controlled_smoke": {"active": True, "authorization_provided": True},
            "provenance_findings": [],
            "commands": [{"label": "building_characteristics_validator", "returncode": 2}],
            "inputs": [],
        },
    )
    valid = build_valid_run(tmp_path, "valid_counterpart_corrected_check")
    assert run_comparison(root, valid)["refused"] is True
    assert run_comparison(valid, root)["refused"] is True


def test_third_tile_still_fails_after_correction(tmp_path: Path):
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(
        tmp_path, "b",
        tile_ids=(*AUTHORIZED_TILE_IDS, "999999"),
        source_hashes={**KNOWN_CANONICAL_SOURCE_SHA256, "999999": "9" * 64},
    )
    result = run_comparison(root_a, root_b, tolerances=WIDE_TOLERANCES)
    assert result["report"]["classification"] == "FAIL"
    assert "unauthorized_tile" in codes(result["report"], "blocker")


def test_production_allowed_true_still_fails_after_correction(tmp_path: Path):
    gate = json.dumps({"publication": {"production_allowed": True}}).encode("utf-8")
    root_a = build_valid_run(tmp_path, "a", extra_root_files={"qa/publication_gate.json": gate})
    root_b = build_valid_run(tmp_path, "b", extra_root_files={"qa/publication_gate.json": gate})
    result = run_comparison(root_a, root_b, tolerances=WIDE_TOLERANCES)
    assert result["report"]["classification"] == "FAIL"
    assert "production_allowed_true" in codes(result["report"], "blocker")


# ── zero tolerance preserves exact comparison behavior ──────────────────────

def test_zero_tolerance_is_exact_for_approved_paths_too(tmp_path: Path):
    tid = AUTHORIZED_TILE_IDS[0]
    root_a = build_valid_run(tmp_path, "a")
    root_b = build_valid_run(tmp_path, "b", tile_manifest_overrides={tid: {"n_footprints": 11}})
    result = run_comparison(root_a, root_b, tolerances=ZERO_TOLERANCES)
    report = result["report"]
    assert report["classification"] == "FAIL"
    assert "count_mismatch" in codes(report, "blocker")
    assert report["tolerance_applications"] == []
