from __future__ import annotations

import json
import subprocess
import sys
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


def _run_cli(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *argv],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_height_r2_full_synthetic_cli_success_inventory_and_manifest(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    out_root = tmp_path / "out_r2"
    proc = _run_cli(_full_argv(fixture, out_root))
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
    assert not Path(replay["scratch_root"]).exists()


def test_height_r2_cli_invalid_z_gate_exact_blocked_inventory(tmp_path):
    fixture = build_fixture(tmp_path, productive=True)
    payload = json.loads(fixture["attestation_path"].read_text(encoding="utf-8"))
    payload["target_unit"] = "feet"
    fixture["attestation_path"].write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    fixture["expected_z_unit_attestation_sha256"] = _sha256_path(fixture["attestation_path"])
    out_root = tmp_path / "blocked_r2"
    proc = _run_cli(_full_argv(fixture, out_root))
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
