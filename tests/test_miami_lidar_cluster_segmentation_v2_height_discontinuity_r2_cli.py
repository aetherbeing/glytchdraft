from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2_height_discontinuity_r2 as r2
from tests.test_miami_lidar_cluster_segmentation_v2_height_discontinuity_r1_cli import (
    REPO_ROOT,
    build_fixture,
    _full_argv,
    _sha256_path,
)

SCRIPT_PATH = REPO_ROOT / "scripts" / "diagnostics" / "miami_lidar_cluster_segmentation_v2_height_discontinuity_r2.py"


def _git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(REPO_ROOT), text=True).strip()


def _augment_r2_fixture(fixture: dict, tmp_path: Path) -> dict:
    for key in ("r1_independent_review", "r1_post_run_closeout", "r1_fragmentation_forensics"):
        path = tmp_path / f"{key}.md"
        path.write_text(f"synthetic {key}\n", encoding="utf-8")
        fixture[key] = path
        fixture[f"expected_{key}_sha256"] = _sha256_path(path)
    fixture["design_v3_root"] = Path(
        "/home/gytchdrafter/ATLANTID_SPRINT_20260704/designs/"
        "height_r2_dose_response_design_v3_20260709T023520Z"
    )
    fixture["expected_design_v3_manifest_sha256"] = r2.HEIGHT_R2_DESIGN_MANIFEST_SHA256
    fixture["evidence_artifact_parent"] = tmp_path
    fixture["expected_head_sha"] = _git_value("rev-parse", "HEAD")
    fixture["expected_origin_master_sha"] = _git_value("rev-parse", "origin/master")
    return fixture


def _full_r2_argv(fixture: dict, out_root: Path) -> list[str]:
    return [
        *_full_argv(fixture, out_root),
        "--r1-independent-review", str(fixture["r1_independent_review"]),
        "--expected-r1-independent-review-sha256", fixture["expected_r1_independent_review_sha256"],
        "--r1-post-run-closeout", str(fixture["r1_post_run_closeout"]),
        "--expected-r1-post-run-closeout-sha256", fixture["expected_r1_post_run_closeout_sha256"],
        "--r1-fragmentation-forensics", str(fixture["r1_fragmentation_forensics"]),
        "--expected-r1-fragmentation-forensics-sha256", fixture["expected_r1_fragmentation_forensics_sha256"],
        "--design-v3-root", str(fixture["design_v3_root"]),
        "--expected-design-v3-manifest-sha256", fixture["expected_design_v3_manifest_sha256"],
        "--expected-head-sha", fixture["expected_head_sha"],
        "--expected-origin-master-sha", fixture["expected_origin_master_sha"],
        "--evidence-artifact-parent", str(fixture["evidence_artifact_parent"]),
    ]


def _run_cli(argv: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *argv],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def _tree_hashes(root: Path) -> dict[str, tuple[str, str | None]]:
    rows: dict[str, tuple[str, str | None]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            rows[rel + "/"] = ("dir", None)
        elif path.is_symlink():
            rows[rel] = ("symlink", os.readlink(path))
        else:
            rows[rel] = ("file", _sha256_path(path))
    return rows


def test_height_r2_full_synthetic_cli_success_inventory_and_manifest(tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    out_root = tmp_path / "out_r2"
    proc = _run_cli(_full_r2_argv(fixture, out_root))
    assert proc.returncode == 0, proc.stderr
    names = sorted(path.name for path in out_root.iterdir())
    assert names == sorted([*r2.OUTPUT_CONTENT_FILES, "FREEZE_MANIFEST.sha256"])
    assert json.loads((out_root / "experiment_parameters.json").read_text())["vertical_step_threshold_m"] == 3.0
    decision = json.loads((out_root / "height_r2_decision.json").read_text())
    assert decision["height_r2_decision"] in {
        "CANDIDATE",
        "EXHAUSTED",
        "INTERMEDIATE",
        "LOST_SEVERING",
    }
    dose = json.loads((out_root / "r1_r2_dose_response.json").read_text())
    assert dose["parent_count"] == 34
    replay = json.loads((out_root / "deterministic_replay_report.json").read_text())
    assert replay["disposition"] == r2.DETERMINISTIC_REPLAY_SCRATCH_DISPOSITION
    assert replay["cleanup"]["cleanup_status"] == "CLEANED"
    assert replay["automatic_retry_triggered"] is False
    assert replay["replay_manifest"]["verification"]["verified"] is True
    assert replay["child_identifier_comparison"]["matched"] is True
    assert replay["segmented_geometry_comparison"]["matched"] is True
    assert not Path(replay["scratch_root"]).exists()
    params = json.loads((out_root / "experiment_parameters.json").read_text())
    assert params["execution_surface_preflight"]["preflight_verdict"] == "GO"
    assert params["provenance_evidence"]["repository_identity"]["head_sha"] == fixture["expected_head_sha"]


def test_height_r2_cli_invalid_z_gate_exact_blocked_inventory(tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    payload = json.loads(fixture["attestation_path"].read_text(encoding="utf-8"))
    payload["target_unit"] = "feet"
    fixture["attestation_path"].write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    fixture["expected_z_unit_attestation_sha256"] = _sha256_path(fixture["attestation_path"])
    out_root = tmp_path / "blocked_r2"
    proc = _run_cli(_full_r2_argv(fixture, out_root))
    assert proc.returncode == 2
    assert sorted(path.name for path in out_root.iterdir()) == sorted(r2.BLOCKED_CONTENT_FILES)
    gate = json.loads((out_root / "gate_report.json").read_text())
    assert gate["gate"] == "G-Z1/G-Z2"
    assert not (out_root / "FREEZE_MANIFEST.sha256").exists()
    assert not (out_root / "z_unit_gate.json").exists()


def test_height_r2_cli_rejects_t7_without_opening_inputs(tmp_path):
    out_root = tmp_path / "t7_block"
    proc = _run_cli(["--source-run", "/mnt/t7/forbidden", "--out-root", str(out_root)])
    assert proc.returncode == 2
    assert "/mnt/t7 access is forbidden" in proc.stderr
    assert not out_root.exists()


def test_height_r2_cli_missing_arguments_writes_exact_blocked_inventory(tmp_path):
    out_root = tmp_path / "missing_args"
    proc = _run_cli(["--source-run", str(tmp_path / "src"), "--out-root", str(out_root)])
    assert proc.returncode == 2
    assert sorted(path.name for path in out_root.iterdir()) == sorted(r2.BLOCKED_CONTENT_FILES)
    assert not (out_root / "FREEZE_MANIFEST.sha256").exists()


def test_height_r2_cli_existing_empty_root_is_rejected_without_reuse(tmp_path):
    out_root = tmp_path / "existing_empty"
    out_root.mkdir()
    before = _tree_hashes(out_root)
    proc = _run_cli(["--source-run", str(tmp_path / "src"), "--out-root", str(out_root)])
    assert proc.returncode == 2
    assert "already exists" in proc.stderr
    assert _tree_hashes(out_root) == before
    assert list(out_root.iterdir()) == []


def test_height_r2_cli_existing_nonempty_nested_root_preserves_hashes(tmp_path):
    out_root = tmp_path / "existing_nonempty"
    nested = out_root / "nested" / "deeper"
    nested.mkdir(parents=True)
    (out_root / "sentinel.txt").write_text("keep me\n", encoding="utf-8")
    (nested / "payload.bin").write_bytes(b"do not touch")
    before = _tree_hashes(out_root)
    proc = _run_cli(["--source-run", str(tmp_path / "src"), "--out-root", str(out_root)])
    assert proc.returncode == 2
    assert _tree_hashes(out_root) == before
    assert not any((out_root / name).exists() for name in r2.BLOCKED_CONTENT_FILES)


def test_height_r2_cli_existing_symlink_root_is_rejected_without_target_write(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "sentinel.txt").write_text("target remains\n", encoding="utf-8")
    out_root = tmp_path / "linked_root"
    out_root.symlink_to(target, target_is_directory=True)
    before = _tree_hashes(target)
    proc = _run_cli(["--source-run", str(tmp_path / "src"), "--out-root", str(out_root)])
    assert proc.returncode == 2
    assert _tree_hashes(target) == before
    assert sorted(path.name for path in target.iterdir()) == ["sentinel.txt"]


def test_height_r2_cli_preflight_failure_blocks_before_inputs(monkeypatch, tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    out_root = tmp_path / "preflight_block"
    monkeypatch.setattr(r2, "perform_execution_surface_preflight", lambda args: (_ for _ in ()).throw(r2.SegmentationInputError("forced preflight failure")))
    code = r2.main(_full_r2_argv(fixture, out_root))
    assert code == 2
    assert sorted(path.name for path in out_root.iterdir()) == sorted(r2.BLOCKED_CONTENT_FILES)
    gate = json.loads((out_root / "gate_report.json").read_text())
    assert gate["inputs_opened"] is False


def test_height_r2_cli_existing_root_preflight_failure_does_not_delete_empty_or_nonempty(monkeypatch, tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    for name, populate in (("empty", False), ("nonempty", True)):
        out_root = tmp_path / f"preexisting_{name}"
        out_root.mkdir()
        if populate:
            (out_root / "sentinel.txt").write_text("preserve\n", encoding="utf-8")
            (out_root / "nested").mkdir()
            (out_root / "nested" / "payload.txt").write_text("nested preserve\n", encoding="utf-8")
        before = _tree_hashes(out_root)
        monkeypatch.setattr(
            r2,
            "perform_execution_surface_preflight",
            lambda args: (_ for _ in ()).throw(r2.SegmentationInputError("forced preflight failure")),
        )
        code = r2.main(_full_r2_argv(fixture, out_root))
        assert code == 2
        assert _tree_hashes(out_root) == before
        assert not any((out_root / blocked).exists() for blocked in r2.BLOCKED_CONTENT_FILES)


def test_height_r2_cli_real_path_invokes_strict_preflight(monkeypatch, tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    out_root = tmp_path / "strict_preflight"
    called = {"preflight": False}

    def abbreviated_preflight(args):
        called["preflight"] = True
        probe = {"verdict": "GO"}
        r2.validate_disposable_sibling_probe_evidence(probe)

    monkeypatch.setattr(r2, "perform_execution_surface_preflight", abbreviated_preflight)
    code = r2.main(_full_r2_argv(fixture, out_root))
    assert code == 2
    assert called["preflight"] is True
    assert sorted(path.name for path in out_root.iterdir()) == sorted(r2.BLOCKED_CONTENT_FILES)
    gate = json.loads((out_root / "gate_report.json").read_text())
    assert "schema" in gate["reason"] or "evidence" in gate["reason"]


def test_height_r2_cli_failure_cleanup_never_targets_requested_root(monkeypatch, tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    out_root = tmp_path / "cleanup_guard"
    touched = []
    original_rmtree = shutil.rmtree

    def recording_rmtree(path, *args, **kwargs):
        touched.append(Path(path).resolve())
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(r2.shutil, "rmtree", recording_rmtree)
    monkeypatch.setattr(r2, "run_determinism_double_check", lambda *args, **kwargs: {"byte_identical": False, "differing_files": ["x"]})
    code = r2.main(_full_r2_argv(fixture, out_root))
    assert code == 2
    assert out_root.resolve() not in touched
    assert sorted(path.name for path in out_root.iterdir()) == sorted(r2.BLOCKED_CONTENT_FILES)


def test_height_r2_final_root_absent_until_replay_success(monkeypatch, tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    out_root = tmp_path / "stage_probe"
    observed = {}
    def inspect_replay(args, command, primary_root, **kwargs):
        observed["final_exists_at_replay"] = out_root.exists()
        observed["primary_file_count"] = len(list(primary_root.iterdir()))
        return {
            "byte_identical": True,
            "differing_files": [],
            "cleanup": {"cleanup_status": "CLEANED"},
            "automatic_retry_triggered": False,
            "disposition": r2.DETERMINISTIC_REPLAY_SCRATCH_DISPOSITION,
            "replay_manifest": {"verification": {"verified": True}},
            "child_identifier_comparison": {"matched": True},
            "segmented_geometry_comparison": {"matched": True},
            "final_replay_verdict": "PASS",
        }
    monkeypatch.setattr(r2, "run_determinism_double_check", inspect_replay)
    code = r2.main(_full_r2_argv(fixture, out_root))
    assert code == 0
    assert observed["final_exists_at_replay"] is False
    assert observed["primary_file_count"] == 32
    assert (out_root / "FREEZE_MANIFEST.sha256").exists()


def test_height_r2_replay_disagreement_invalidates_without_manifest(monkeypatch, tmp_path):
    fixture = _augment_r2_fixture(build_fixture(tmp_path, productive=True), tmp_path)
    out_root = tmp_path / "replay_disagree"
    def disagree(*args, **kwargs):
        return {"byte_identical": False, "differing_files": ["segmented_children.geojson"]}
    monkeypatch.setattr(r2, "run_determinism_double_check", disagree)
    code = r2.main(_full_r2_argv(fixture, out_root))
    assert code == 2
    assert sorted(path.name for path in out_root.iterdir()) == sorted(r2.BLOCKED_CONTENT_FILES)
    assert not (out_root / "FREEZE_MANIFEST.sha256").exists()
