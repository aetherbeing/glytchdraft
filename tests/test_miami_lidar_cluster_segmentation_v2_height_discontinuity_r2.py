import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2_height_discontinuity_r1 as r1
from scripts.diagnostics import miami_lidar_cluster_segmentation_v2_height_discontinuity_r2 as r2


def _counts(cluster_18=2, cluster_34=1):
    counts = {pid: 1 for pid in r2.EXPECTED_PARENT_IDS}
    counts[18] = cluster_18
    counts[34] = cluster_34
    return counts


def test_height_r2_sole_scientific_delta():
    r1_constants = r1.frozen_constants_block()
    r2_constants = r2.frozen_constants_block()
    assert r1_constants["VERTICAL_STEP_THRESHOLD_M"] == 2.0
    assert r2_constants["VERTICAL_STEP_THRESHOLD_M"] == 3.0
    comparable = set(r1_constants) - {"VERTICAL_STEP_THRESHOLD_M", "RUN_STATUS", "BLOCKED_STATUS", "FAILED_STATUS"}
    for key in comparable:
        assert r2_constants[key] == r1_constants[key]
    assert r2.METHOD_IDENTITY.endswith("_height_discontinuity_r2")
    assert r2.assert_frozen_constants() is None


@pytest.mark.parametrize(
    ("c18", "c34", "expected"),
    [
        (0, 1, "INVALID_RUN"),
        (1, 1, "LOST_SEVERING"),
        (2, 1, "CANDIDATE"),
        (12, 1, "CANDIDATE"),
        (13, 1, "INTERMEDIATE"),
        (99, 1, "INTERMEDIATE"),
        (100, 1, "EXHAUSTED"),
        (520, 1, "EXHAUSTED"),
        (2, 2, "EXHAUSTED"),
        (18, 2, "EXHAUSTED"),
    ],
)
def test_height_r2_decision_boundaries(c18, c34, expected):
    decision = r2.classify_height_r2_decision(_counts(c18, c34))
    assert decision["height_r2_decision"] == expected
    if expected != "INVALID_RUN":
        assert decision["invalid_reasons"] == []


@pytest.mark.parametrize(
    "bad_counts",
    [
        None,
        {pid: 1 for pid in r2.EXPECTED_PARENT_IDS if pid != 18},
        {**{pid: 1 for pid in r2.EXPECTED_PARENT_IDS}, 999: 1},
        [(pid, 1) for pid in r2.EXPECTED_PARENT_IDS] + [(18, 1)],
        {**{pid: 1 for pid in r2.EXPECTED_PARENT_IDS}, 18: -1},
        {**{pid: 1 for pid in r2.EXPECTED_PARENT_IDS}, 18: 1.5},
        {**{pid: 1 for pid in r2.EXPECTED_PARENT_IDS}, 34: 0},
    ],
)
def test_height_r2_invalid_parent_tables_route_to_invalid_run(bad_counts):
    decision = r2.classify_height_r2_decision(bad_counts)
    assert decision["height_r2_decision"] == "INVALID_RUN"
    assert decision["invalid_reasons"]


def test_height_r2_invalid_run_precedence():
    decision = r2.classify_height_r2_decision(_counts(2, 1), run_valid=False)
    assert decision["height_r2_decision"] == "INVALID_RUN"
    assert "run validity gate failed" in decision["invalid_reasons"]


def test_height_r2_dose_response_schema_and_bins():
    payload = r2.build_r1_r2_dose_response(_counts(cluster_18=12, cluster_34=1))
    assert payload["parent_count"] == 34
    assert payload["parent_order"] == r2.EXPECTED_PARENT_IDS
    assert payload["zero_denominator_policy"] == "INVALID_RUN"
    assert payload["r1_bins"] == {"exactly_1": 20, "2_9": 9, "10_99": 1, "100_or_more": 4}
    row18 = next(row for row in payload["rows"] if row["parent_id"] == 18)
    assert row18["r1_child_count"] == 520
    assert row18["r2_child_count"] == 12
    assert row18["absolute_delta"] == -508
    assert row18["percentage_delta"] == pytest.approx(-97.692307692)
    assert row18["r2_divided_by_r1_ratio"] == pytest.approx(0.023076923)
    assert set(payload["callout_parent_ids"]) == {0, 1, 6, 18, 29, 34}
    row34 = next(row for row in payload["rows"] if row["parent_id"] == 34)
    assert row34["r2_false_split_status"] == "CLUSTER_34_HELD_AT_1"


def test_height_r2_success_and_blocked_inventory_contract(tmp_path):
    assert len(r2.OUTPUT_CONTENT_FILES) == 32
    assert len(set(r2.OUTPUT_CONTENT_FILES)) == 32
    assert "deterministic_replay_report.json" in r2.OUTPUT_CONTENT_FILES
    assert "r1_r2_dose_response.csv" in r2.OUTPUT_CONTENT_FILES
    assert r2.BLOCKED_CONTENT_FILES == [
        "command.txt",
        "command_stdout_stderr.log",
        "family_decision.json",
        "gate_report.json",
        "run.log",
    ]
    out = tmp_path / "blocked"
    out.mkdir()
    r2._write_blocked_evidence(out, "G-SYNTH", "synthetic failure", "cmd --x")
    (out / "command_stdout_stderr.log").write_text("", encoding="utf-8")
    assert sorted(path.name for path in out.iterdir()) == sorted(r2.BLOCKED_CONTENT_FILES)
    assert json.loads((out / "family_decision.json").read_text())["production_adoption_authorized"] is False


def test_height_r2_fresh_output_root_semantics(tmp_path):
    out = tmp_path / "new_root"
    r2.require_fresh_output_root(out)
    assert out.is_dir()
    with pytest.raises(r2.SegmentationInputError):
        r2.require_fresh_output_root(out)


def test_height_r2_mount_metadata_parser():
    mountinfo = "1 0 8:1 / / rw,relatime - ext4 /dev/sda1 rw,errors=remount-ro\n"
    metadata = r2.build_mount_metadata(
        Path("/tmp"),
        mountinfo_text=mountinfo,
        mount_namespace_identity="mnt:[synthetic]",
        timestamp_utc="2026-07-09T00:00:00Z",
    )
    assert metadata["rw_present"] is True
    assert metadata["ro_present"] is False
    assert metadata["filesystem_type"] == "ext4"
    assert metadata["mount_source"] == "/dev/sda1"


def test_height_r2_execution_surface_rejects_root_and_namespace_mismatch():
    report = r2.assert_execution_surface(
        user_id=0,
        sudo_user=None,
        shell_name="bash",
        readiness_mount_namespace="mnt:[1]",
        invocation_mount_namespace="mnt:[2]",
    )
    assert report["verdict"] == "NO_GO"
    assert any("root" in failure for failure in report["failures"])
    assert any("mount namespace mismatch" in failure for failure in report["failures"])


def test_height_r2_disposable_sibling_probe(tmp_path):
    output_parent = tmp_path
    future = output_parent / "future_scientific_root"
    result = r2.run_disposable_sibling_probe(
        output_parent,
        future,
        utc_token="20260709T000000Z",
        pid=123,
        nonce_hex="a" * 32,
    )
    assert result["verdict"] == "GO"
    assert result["probe_mkdir_parents"] is False
    assert result["probe_mkdir_exist_ok"] is False
    assert not future.exists()
    assert not (output_parent / (".height_r2_parent_probe_20260709T000000Z_123_" + "a" * 32)).exists()


def test_height_r2_replay_scratch_lifecycle(tmp_path):
    scratch = r2.create_replay_scratch_root(
        scratch_parent=tmp_path,
        utc_token="20260709T000000Z",
        pid=456,
        nonce_hex="b" * 32,
    )
    assert scratch.name == "height_r2_replay_20260709T000000Z_456_" + "b" * 32
    (scratch / "payload" / "artifact.json").write_text('{"ok": true}\n', encoding="utf-8")
    (scratch / "logs" / "replay_run.log").write_text("ok\n", encoding="utf-8")
    manifest = r2.write_replay_manifest(scratch / "payload")
    assert manifest.name == "REPLAY_FREEZE_MANIFEST.sha256"
    inventory = r2.inventory_tree(scratch)
    assert any(row["relative_path"] == "payload/artifact.json" for row in inventory)
    cleanup = r2.cleanup_replay_scratch_root(scratch)
    assert cleanup["cleanup_status"] == "CLEANED"
    assert not scratch.exists()


def test_height_r2_production_and_receipt_locks_false():
    payload = r2.authorization_false_payload()
    assert payload["production_adoption_authorized"] is False
    assert payload["child_level_receipts_authorized"] is False
    assert payload["downstream_building_identity_claims_authorized"] is False
