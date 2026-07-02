"""
Controlled two-tile smoke tests for miami_metric_smoke_harness.

Covers exactly tiles 318155 and 318455 against their canonical paths and
SHA-256 hashes.  No real T7 LAZ files are accessed; all inputs are synthetic.
No PDAL processing occurs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAG_DIR = REPO_ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAG_DIR))

import miami_metric_smoke_harness as harness  # noqa: E402


# ─── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, body: bytes = b"placeholder") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _make_allowlist(tmp_path: Path, bodies: dict[str, bytes] | None = None) -> tuple[dict[str, dict], dict[str, str]]:
    """
    Create synthetic canonical files in tmp_path and return an allowlist override
    plus a matching hash dict suitable for write_contract().
    """
    default_bodies = {
        "318155": b"synthetic_tile_318155",
        "318455": b"synthetic_tile_318455",
    }
    tile_bodies = bodies if bodies is not None else default_bodies
    canon_dir = tmp_path / "canonical_laz"
    canon_dir.mkdir(exist_ok=True)

    allowlist: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    for tile_id, body in tile_bodies.items():
        canon = canon_dir / f"USGS_LPC_FL_MiamiDade_D23_LID2024_{tile_id}_0901.laz"
        canon.write_bytes(body)
        sha = harness.sha256_file(canon)
        allowlist[tile_id] = {"canonical_path": canon, "sha256": sha}
        hashes[tile_id] = sha
    return allowlist, hashes


def _tile_flags(allowlist: dict[str, dict]) -> list[str]:
    """--tile flags pointing at canonical paths in the allowlist."""
    flags: list[str] = []
    for tile_id, entry in sorted(allowlist.items()):
        flags += ["--tile", f"{tile_id}={entry['canonical_path']}"]
    return flags


def _write_contract(path: Path, hashes: dict[str, str], **overrides) -> Path:
    payload = {
        "source_contract_status": "CONDITIONAL_GO",
        "source_horizontal_crs": "EPSG:6438",
        "source_vertical_crs": "EPSG:6360",
        "source_horizontal_unit": "US survey foot",
        "source_vertical_unit": "US survey foot",
        "processed_horizontal_crs": "EPSG:32617",
        "processed_vertical_datum": None,
        "processed_z_unit": "metre",
        "xy_reprojection_stage": "synthetic_xy_reprojection_stage",
        "z_conversion_stage": "synthetic_z_conversion_stage",
        "z_conversion_factor": 0.3048006096012192,
        "normalization_provenance": "synthetic unit-test contract; not real Miami evidence",
        "z_not_already_converted_evidence": "synthetic evidence that Z is still ftUS before filters.assign",
        "xy_reprojection_converts_z": False,
        "canonical_input_hashes": hashes,
        "possible_double_conversion": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest_at(output_root: Path) -> dict:
    return json.loads(
        (output_root / "qa" / "miami_metric_smoke_manifest.json").read_text(encoding="utf-8")
    )


def _t7_ro_mock(**kw):
    """Mock check_t7_read_only to return read-only (no errors)."""
    return []


# ─── approved tiles (dry-run / preflight) ─────────────────────────────────────

def test_controlled_smoke_318155_approved_dry_run(tmp_path, monkeypatch):
    """Tile 318155 in allowlist with canonical path and matching hash passes dry-run."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out-155"

    code = harness.main(["--controlled-smoke", "--output-root", str(out), *_tile_flags(allowlist)])

    assert code == 0
    m = _manifest_at(out)
    assert m["dry_run"] is True
    assert m["controlled_smoke"]["active"] is True
    assert m["controlled_smoke"]["preflight"]["input_errors"] == []
    tile_ids = {item["tile_id"] for item in m["inputs"]}
    assert "318155" in tile_ids


def test_controlled_smoke_318455_approved_dry_run(tmp_path, monkeypatch):
    """Tile 318455 in allowlist with canonical path and matching hash passes dry-run."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out-455"

    code = harness.main(["--controlled-smoke", "--output-root", str(out), *_tile_flags(allowlist)])

    assert code == 0
    m = _manifest_at(out)
    assert m["dry_run"] is True
    assert m["controlled_smoke"]["active"] is True
    assert m["controlled_smoke"]["preflight"]["input_errors"] == []
    tile_ids = {item["tile_id"] for item in m["inputs"]}
    assert "318455" in tile_ids


# ─── allowlist rejection ──────────────────────────────────────────────────────

def test_controlled_smoke_wrong_tile_rejected(tmp_path, monkeypatch):
    """A tile ID not in the allowlist is rejected even in dry-run."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    wrong = _write(tmp_path / "inputs" / "USGS_LPC_FL_MiamiDade_D23_LID2024_999999_0901.laz")
    canon_155 = allowlist["318155"]["canonical_path"]

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={canon_155}",
        "--tile", f"999999={wrong}",
    ])

    assert code == 2


def test_controlled_smoke_wrong_path_rejected(tmp_path, monkeypatch):
    """Allowlisted tile ID at a non-canonical path is rejected."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    wrong_155 = _write(
        tmp_path / "wrong" / "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz",
        b"synthetic_tile_318155",
    )
    canon_455 = allowlist["318455"]["canonical_path"]

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={wrong_155}",
        "--tile", f"318455={canon_455}",
    ])

    assert code == 2


def test_controlled_smoke_symlink_path_escape_rejected(tmp_path, monkeypatch):
    """A symlink to the canonical file is rejected; direct path required."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    canon_155 = allowlist["318155"]["canonical_path"]
    canon_455 = allowlist["318455"]["canonical_path"]
    sym = tmp_path / "sym_to_318155.laz"
    sym.symlink_to(canon_155)

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={sym}",
        "--tile", f"318455={canon_455}",
    ])

    assert code == 2


# ─── component-level symlink rejection ────────────────────────────────────────

def test_controlled_smoke_symlink_final_file_rejected(tmp_path, monkeypatch):
    """Final path component is a symlink: rejected."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    canon_155 = allowlist["318155"]["canonical_path"]
    canon_455 = allowlist["318455"]["canonical_path"]
    sym = tmp_path / "sym_file.laz"
    sym.symlink_to(canon_155)

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={sym}",
        "--tile", f"318455={canon_455}",
    ])

    assert code == 2


def test_controlled_smoke_symlink_parent_dir_rejected(tmp_path, monkeypatch):
    """Parent directory is a symlink: rejected even if it resolves to canonical location."""
    real_dir = tmp_path / "real_laz_dir"
    real_dir.mkdir()

    # Build an allowlist whose canonical path lives in real_dir
    canon_155_path = real_dir / "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz"
    canon_155_path.write_bytes(b"synthetic_tile_318155")
    canon_455_path = real_dir / "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz"
    canon_455_path.write_bytes(b"synthetic_tile_318455")

    test_allowlist = {
        "318155": {"canonical_path": canon_155_path, "sha256": harness.sha256_file(canon_155_path)},
        "318455": {"canonical_path": canon_455_path, "sha256": harness.sha256_file(canon_455_path)},
    }
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", test_allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    # Symlink parent → real_dir; caller provides sym_parent/filename
    sym_parent = tmp_path / "sym_parent_dir"
    sym_parent.symlink_to(real_dir)
    sym_path_155 = sym_parent / canon_155_path.name

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={sym_path_155}",
        "--tile", f"318455={canon_455_path}",
    ])

    assert code == 2


def test_controlled_smoke_nested_parent_symlink_rejected(tmp_path, monkeypatch):
    """A symlink at a nested parent component (a/b_link/c/file) is rejected."""
    deep_real = tmp_path / "a" / "b" / "c"
    deep_real.mkdir(parents=True)

    canon_155_path = deep_real / "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz"
    canon_155_path.write_bytes(b"synthetic_tile_318155")
    canon_455_path = (tmp_path / "canonical_laz")
    canon_455_path.mkdir(exist_ok=True)
    canon_455_path = canon_455_path / "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz"
    canon_455_path.write_bytes(b"synthetic_tile_318455")

    test_allowlist = {
        "318155": {"canonical_path": canon_155_path, "sha256": harness.sha256_file(canon_155_path)},
        "318455": {"canonical_path": canon_455_path, "sha256": harness.sha256_file(canon_455_path)},
    }
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", test_allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    # Symlink at middle level: a/b_link → a/b
    sym_middle = tmp_path / "a" / "b_link"
    sym_middle.symlink_to(tmp_path / "a" / "b")
    nested_sym = sym_middle / "c" / canon_155_path.name  # a/b_link/c/filename

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={nested_sym}",
        "--tile", f"318455={canon_455_path}",
    ])

    assert code == 2


def test_controlled_smoke_direct_canonical_path_accepted(tmp_path, monkeypatch):
    """Direct canonical path with no symlinks in any component is accepted."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 0
    m = _manifest_at(out)
    assert m["controlled_smoke"]["preflight"]["input_errors"] == []


def test_controlled_smoke_hash_mismatch_rejected(tmp_path, monkeypatch):
    """Canonical path is correct but file content (hash) does not match allowlist entry."""
    allowlist, _ = _make_allowlist(tmp_path)
    # Overwrite canonical 318155 with different content AFTER computing the allowlist hash
    allowlist["318155"]["canonical_path"].write_bytes(b"CORRUPTED_CONTENT")
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2


# ─── T7 mount checks ──────────────────────────────────────────────────────────

def test_check_t7_read_only_rejects_missing_mount(tmp_path):
    """Missing T7 mount point returns an error."""
    errors = harness.check_t7_read_only(t7_mount=tmp_path / "nonexistent_t7")
    assert errors
    assert any("not present" in e.lower() for e in errors)


def test_check_t7_read_only_rejects_writable_mount(tmp_path):
    """Writable T7 mount returns an error."""
    t7 = tmp_path / "t7"
    t7.mkdir()
    proc_mounts = tmp_path / "proc_mounts"
    proc_mounts.write_text(f"ext4 {t7} ext4 rw,relatime 0 0\n", encoding="utf-8")

    errors = harness.check_t7_read_only(t7_mount=t7, _proc_mounts=proc_mounts)

    assert errors
    assert any("not read-only" in e.lower() or "writable" in e.lower() for e in errors)


def test_check_t7_read_only_accepts_ro_mount(tmp_path):
    """Read-only T7 mount returns no errors."""
    t7 = tmp_path / "t7"
    t7.mkdir()
    proc_mounts = tmp_path / "proc_mounts"
    proc_mounts.write_text(f"ext4 {t7} ext4 ro,relatime 0 0\n", encoding="utf-8")

    errors = harness.check_t7_read_only(t7_mount=t7, _proc_mounts=proc_mounts)

    assert errors == []


def test_controlled_smoke_writable_t7_blocks_execution(tmp_path, monkeypatch):
    """Writable T7 mount blocks execution even with auth token and valid contract."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", lambda **kw: ["T7 mount is not read-only (rw,relatime)"])
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "contract.json", hashes)
    validator = _write(tmp_path / "validator.py", b"")
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--building-characteristics-validator", str(validator),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    assert m["controlled_smoke"]["preflight"]["t7_errors"]


# ─── output isolation ─────────────────────────────────────────────────────────

def test_controlled_smoke_output_under_t7_rejected(tmp_path, monkeypatch):
    """Output root under /mnt/t7 is rejected by path safety check."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)

    code = harness.main([
        "--controlled-smoke",
        "--output-root", "/mnt/t7/miami/smoke_output",
        *_tile_flags(allowlist),
    ])

    assert code == 2


def test_controlled_smoke_output_under_production_dir_rejected(tmp_path, monkeypatch):
    """Output root under a canonical production directory is rejected."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)

    production_output = harness.REPO_ROOT / "viewer" / "smoke_output"
    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(production_output),
        *_tile_flags(allowlist),
    ])

    assert code == 2


def test_controlled_smoke_nonempty_output_dir_rejected(tmp_path, monkeypatch):
    """Pre-existing non-empty output directory is rejected."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    pre = tmp_path / "pre-existing"
    pre.mkdir()
    (pre / "existing_file.txt").write_text("already here")

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(pre),
        *_tile_flags(allowlist),
    ])

    assert code == 2


# ─── source contract value validation ─────────────────────────────────────────

def test_controlled_smoke_wrong_crs_rejected(tmp_path, monkeypatch):
    """Wrong source_horizontal_crs triggers a blocker finding that blocks execution."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes, source_horizontal_crs="EPSG:4326")
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    finding_codes = {f["code"] for f in m["provenance_findings"]}
    assert "wrong_source_horizontal_crs" in finding_codes


def test_controlled_smoke_wrong_units_rejected(tmp_path, monkeypatch):
    """Wrong source_vertical_unit triggers a blocker finding that blocks execution."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes, source_vertical_unit="metre")
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    finding_codes = {f["code"] for f in m["provenance_findings"]}
    assert "wrong_source_vertical_unit" in finding_codes


def test_controlled_smoke_wrong_z_factor_rejected(tmp_path, monkeypatch):
    """Wrong z_conversion_factor triggers a blocker finding that blocks execution."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes, z_conversion_factor=0.3048)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    finding_codes = {f["code"] for f in m["provenance_findings"]}
    assert "wrong_z_conversion_factor" in finding_codes


def test_controlled_smoke_missing_z_conversion_rejected(tmp_path, monkeypatch):
    """Missing z_conversion_stage triggers a blocker finding that blocks execution."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes, z_conversion_stage=None)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    finding_codes = {f["code"] for f in m["provenance_findings"]}
    assert "missing_provenance" in finding_codes
    # Verify the missing field is z_conversion_stage specifically
    missing_fields = {f["field"] for f in m["provenance_findings"] if f["code"] == "missing_provenance"}
    assert "z_conversion_stage" in missing_fields


def test_controlled_smoke_duplicate_z_conversion_rejected(tmp_path, monkeypatch):
    """possible_double_conversion=True triggers a blocker finding that blocks execution."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes, possible_double_conversion=True)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    finding_codes = {f["code"] for f in m["provenance_findings"]}
    assert "possible_double_conversion" in finding_codes


# ─── authorization gate ───────────────────────────────────────────────────────

def test_execute_without_controlled_smoke_authorization_rejected(tmp_path, monkeypatch):
    """--execute in controlled smoke mode without the authorization token is rejected."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        # deliberately omit --controlled-smoke-authorization
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    assert m["controlled_smoke"]["active"] is True
    assert m["controlled_smoke"]["authorization_provided"] is False
    assert all(cmd["returncode"] is None for cmd in m["commands"])


def test_execute_with_wrong_authorization_token_rejected(tmp_path, monkeypatch):
    """--execute with an incorrect authorization token is rejected."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", "WRONG_TOKEN",
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    assert m["controlled_smoke"]["authorization_provided"] is False


# ─── REAL_DATA_EXECUTION_ENABLED safety ───────────────────────────────────────

def test_real_data_execution_enabled_false_remains_governed_in_controlled_smoke(tmp_path, monkeypatch):
    """REAL_DATA_EXECUTION_ENABLED=False is the final gate even when all other conditions pass."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    contract = _write_contract(tmp_path / "c.json", hashes)
    validator = _write(tmp_path / "validator.py", b"")
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--building-characteristics-validator", str(validator),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    assert m["release"]["real_data_execution_enabled"] is False
    assert all(cmd["returncode"] is None for cmd in m["commands"])
    assert m["controlled_smoke"]["authorization_provided"] is True
    assert not m["controlled_smoke"]["preflight"]["input_errors"]


# ─── provenance manifest structure ────────────────────────────────────────────

def test_controlled_smoke_manifest_records_complete_provenance(tmp_path, monkeypatch):
    """Dry-run manifest contains all required provenance fields."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    contract = _write_contract(tmp_path / "c.json", hashes)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke",
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 0
    m = _manifest_at(out)

    # Allowlist IDs recorded
    assert sorted(m["controlled_smoke"]["preflight"]["allowlist_tile_ids"]) == ["318155", "318455"]

    # Source contract CRS and units
    sc = m["source_contract"]
    assert sc["source_horizontal_crs"] == "EPSG:6438"
    assert sc["source_vertical_crs"] == "EPSG:6360"
    assert sc["source_horizontal_unit"] == "US survey foot"
    assert sc["source_vertical_unit"] == "US survey foot"
    assert sc["processed_horizontal_crs"] == "EPSG:32617"
    assert sc["z_conversion_factor"] == 0.3048006096012192

    # Exactly two inputs
    assert len(m["inputs"]) == 2
    tile_ids = {item["tile_id"] for item in m["inputs"]}
    assert tile_ids == {"318155", "318455"}

    # Input hashes recorded
    for item in m["inputs"]:
        assert len(item["sha256"]) == 64

    # No provenance findings
    assert m["provenance_findings"] == []

    # Commands are not runnable in dry-run
    assert all(cmd["returncode"] is None for cmd in m["commands"])

    # Execution gate state
    assert m["release"]["real_data_execution_enabled"] is False
    assert m["controlled_smoke"]["active"] is True
    assert m["controlled_smoke"]["authorization_provided"] is False


def test_controlled_smoke_allowlist_canonical_paths_recorded_in_manifest(tmp_path, monkeypatch):
    """Manifest records the canonical paths from the allowlist."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out"

    harness.main(["--controlled-smoke", "--output-root", str(out), *_tile_flags(allowlist)])

    m = _manifest_at(out)
    recorded = m["controlled_smoke"]["preflight"]["allowlist_canonical_paths"]
    assert set(recorded.keys()) == {"318155", "318455"}
    for tid, canon_str in recorded.items():
        assert str(allowlist[tid]["canonical_path"]) == canon_str


# ─── validate_controlled_smoke_inputs unit tests ──────────────────────────────

def test_validate_inputs_duplicate_tile_id_rejected(tmp_path):
    """Duplicate tile IDs are rejected by explicit_tile_inputs before allowlist check."""
    allowlist, _ = _make_allowlist(tmp_path)
    canon_155 = allowlist["318155"]["canonical_path"]

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={canon_155}",
        "--tile", f"318155={canon_155}",
    ])

    assert code == 2


def test_validate_inputs_rejects_basename_only_match(tmp_path, monkeypatch):
    """A file with the right basename but under a different parent is rejected."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    # Same filename, different parent directory
    different_parent = tmp_path / "other_dir"
    different_parent.mkdir()
    canon_455_name = allowlist["318455"]["canonical_path"].name
    imposter = different_parent / canon_455_name
    imposter.write_bytes(b"synthetic_tile_318455")

    canon_155 = allowlist["318155"]["canonical_path"]

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={canon_155}",
        "--tile", f"318455={imposter}",
    ])

    assert code == 2


# ─── missing canonical source file ────────────────────────────────────────────

def test_controlled_smoke_missing_canonical_source_file_fails_preflight(
    tmp_path, monkeypatch, capsys
):
    """
    Allowlisted tile with the correct canonical path but a missing source file
    fails preflight before the PDAL/subprocess process boundary is crossed.

    Proves:
      1. return code is non-zero;
      2. captured stderr identifies the missing canonical source;
      3. subprocess.run spy call count is zero (no PDAL process launched);
      4. no processing output directory exists;
      5. no successful validator or QA manifest exists.
    """
    allowlist, _ = _make_allowlist(tmp_path)
    allowlist["318155"]["canonical_path"].unlink()
    assert not allowlist["318155"]["canonical_path"].exists()

    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    # Spy: any subprocess.run call means PDAL was invoked — must not happen.
    spy_calls: list = []

    def _spy_run(*args, **kwargs):
        spy_calls.append(args)
        raise AssertionError("subprocess.run must not be called when source file is missing")

    monkeypatch.setattr(harness.subprocess, "run", _spy_run)

    out = tmp_path / "out"
    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    captured = capsys.readouterr()

    # 1. Non-zero exit
    assert code == 2

    # 2. Stderr identifies the missing canonical source for 318155
    assert "318155" in captured.err

    # 3. Process boundary was never crossed
    assert len(spy_calls) == 0

    # 4. No processing output written
    assert not out.exists()

    # 5. No QA manifest or validator result
    assert not (out / "qa" / "miami_metric_smoke_manifest.json").exists()


# ─── exact two-tile-set enforcement ───────────────────────────────────────────

def test_controlled_smoke_omit_318155_fails(tmp_path, monkeypatch):
    """Omitting tile 318155 causes failure (two-tile set is required)."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318455={allowlist['318455']['canonical_path']}",
        # 318155 deliberately omitted
    ])

    assert code == 2


def test_controlled_smoke_omit_318455_fails(tmp_path, monkeypatch):
    """Omitting tile 318455 causes failure (two-tile set is required)."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={allowlist['318155']['canonical_path']}",
        # 318455 deliberately omitted
    ])

    assert code == 2


def test_controlled_smoke_duplicate_tile_id_fails(tmp_path, monkeypatch):
    """Providing the same tile ID twice fails before controlled smoke validation."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    canon_155 = allowlist["318155"]["canonical_path"]
    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile", f"318155={canon_155}",
        "--tile", f"318155={canon_155}",  # duplicate
    ])

    assert code == 2


def test_controlled_smoke_exactly_one_318155_and_one_318455_passes_dry_run(tmp_path, monkeypatch):
    """Exactly one 318155 and one 318455 (complete canonical set) passes dry-run preflight."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(out),
        "--tile", f"318155={allowlist['318155']['canonical_path']}",
        "--tile", f"318455={allowlist['318455']['canonical_path']}",
    ])

    assert code == 0
    m = _manifest_at(out)
    tile_ids = {item["tile_id"] for item in m["inputs"]}
    assert tile_ids == {"318155", "318455"}
    assert m["controlled_smoke"]["preflight"]["input_errors"] == []
    assert m["dry_run"] is True


# ─── P2-02: --tile-id + --discover-root symlink rejection ────────────────────

def test_controlled_smoke_discover_root_symlink_rejected(tmp_path, monkeypatch):
    """--discover-root path with a caller-introduced symlink component is rejected in controlled
    smoke mode. The pre-resolution symlink check must apply to the discovery root, not only
    to explicit --tile paths."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)

    real_dir = allowlist["318155"]["canonical_path"].parent
    sym_root = tmp_path / "sym_discover_root"
    sym_root.symlink_to(real_dir)

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        "--tile-id", "318155",
        "--tile-id", "318455",
        "--discover-root", str(sym_root),
    ])

    assert code == 2


# ─── process boundary: subprocess target pipeline validation ──────────────────

_EXPECTED_ASSIGN_VALUE = "Z = Z * 0.3048006096012192"


def _import_run_tile_miami():
    """Import run_tile_miami fresh; requires pdal to be installed (pdal_env)."""
    pytest.importorskip("pdal")
    import importlib
    miami_scripts = REPO_ROOT / "scripts" / "miami"
    if str(miami_scripts) not in sys.path:
        sys.path.insert(0, str(miami_scripts))
    for name in ("run_tile_miami", "miami_city_config"):
        sys.modules.pop(name, None)
    return importlib.import_module("run_tile_miami")


def test_harness_command_argv_targets_run_tile_miami(tmp_path, monkeypatch):
    """Per-tile commands in the harness manifest target run_tile_miami.py, not s01_extract.py.

    Verifies the process boundary: the harness must invoke the city pipeline
    (run_tile_miami.py), which now contains the Z normalization stage, not the
    Bikini s01_extract.py pipeline which has separate normalization logic.
    """
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out"

    harness.main(["--controlled-smoke", "--output-root", str(out), *_tile_flags(allowlist)])

    m = _manifest_at(out)
    tile_cmds = [c for c in m["commands"] if c["label"] == "run_tile_miami"]
    assert len(tile_cmds) == 2
    for cmd in tile_cmds:
        argv_str = " ".join(cmd["argv"])
        assert "run_tile_miami.py" in argv_str
        assert "s01_extract" not in argv_str


def test_run_tile_miami_building_steps_has_exactly_one_assign_with_correct_factor():
    """_building_steps() has exactly one filters.assign with the exact US survey foot factor.

    Fails closed if the stage is missing, duplicated, or uses the wrong conversion constant.
    """
    rtm = _import_run_tile_miami()
    steps = rtm._building_steps(Path("tile.laz"), 1.0)
    types = [s["type"] for s in steps]

    assert types.count("filters.assign") == 1, f"assign count: {types}"
    assign_idx = types.index("filters.assign")
    assert steps[assign_idx]["value"] == _EXPECTED_ASSIGN_VALUE


def test_run_tile_miami_building_steps_z_normalization_ordering():
    """filters.assign is after filters.reprojection and before filters.hag_nn and filters.range.

    Ordering is the runtime contract: horizontal reprojection does not convert Z units,
    so the explicit assign stage must intervene before any metric Z semantics.
    """
    rtm = _import_run_tile_miami()
    types = [s["type"] for s in rtm._building_steps(Path("tile.laz"), 1.0)]

    rep = types.index("filters.reprojection")
    asgn = types.index("filters.assign")
    hag = types.index("filters.hag_nn")
    rng = types.index("filters.range")

    assert rep < asgn, "Z conversion must be after XY reprojection"
    assert asgn < hag, "Z conversion must be before HAG (HAG requires metric Z)"
    assert asgn < rng, "Z conversion must be before Z range filter"


def test_run_tile_miami_ground_steps_has_assign_with_correct_factor():
    """_ground_steps() has exactly one filters.assign with the correct factor after reprojection.

    Ground Z must be metric for height estimation (h90 - ground_z); a foot-valued
    ground_z paired with a metric building Z produces wrong height deltas.
    """
    rtm = _import_run_tile_miami()
    steps = rtm._ground_steps(Path("tile.laz"), 1.0)
    types = [s["type"] for s in steps]

    assert types.count("filters.assign") == 1, f"assign count in ground steps: {types}"
    asgn = types.index("filters.assign")
    assert steps[asgn]["value"] == _EXPECTED_ASSIGN_VALUE
    assert types.index("filters.reprojection") < asgn


def test_run_tile_miami_vegetation_steps_has_assign_with_correct_factor():
    """_vegetation_steps() has exactly one filters.assign with the correct factor after reprojection.

    Vegetation Z must be metric for completeness and future range-filter correctness.
    """
    rtm = _import_run_tile_miami()
    steps = rtm._vegetation_steps(Path("tile.laz"), 1.0)
    types = [s["type"] for s in steps]

    assert types.count("filters.assign") == 1, f"assign count in vegetation steps: {types}"
    asgn = types.index("filters.assign")
    assert steps[asgn]["value"] == _EXPECTED_ASSIGN_VALUE
    assert types.index("filters.reprojection") < asgn


def test_run_tile_miami_reprojection_does_not_substitute_for_z_normalization():
    """filters.reprojection targets horizontal EPSG:32617 only; filters.assign is the
    exclusive Z normalization mechanism.

    Horizontal reprojection between EPSG:6438 and EPSG:32617 does not convert Z units.
    Both stages must co-exist: reprojection for XY, assign for Z.
    """
    rtm = _import_run_tile_miami()
    steps = rtm._building_steps(Path("tile.laz"), 1.0)

    rep_step = next(s for s in steps if s["type"] == "filters.reprojection")
    assert "32617" in rep_step.get("out_srs", ""), (
        f"reprojection must target UTM 17N (EPSG:32617), got {rep_step.get('out_srs')!r}"
    )

    types = [s["type"] for s in steps]
    assert "filters.assign" in types, (
        "filters.assign must exist as the explicit Z normalization stage; "
        "reprojection alone does not convert Z from US survey feet to metres"
    )


# ─── production harness runtime-proof gate ────────────────────────────────────
#
# These tests exercise the harness gate itself (validate_runtime_pipeline_normalization
# called from build_controlled_smoke_preflight) via monkeypatched step builders.
# No pdal import is required: the step builders return plain Python dicts.
# Each test drives harness.main() and asserts on the manifest — proving that
# authorization is blocked and the reason is recorded in preflight output.

_REPROJECTION_STEP = {"type": "filters.reprojection", "out_srs": "EPSG:32617"}
_HAG_STEP = {"type": "filters.hag_nn"}
_RANGE_STEP = {"type": "filters.range", "limits": "Classification[6:6],HeightAboveGround[2.5:300]"}
_ASSIGN_CORRECT = {"type": "filters.assign", "value": "Z = Z * 0.3048006096012192"}
_ASSIGN_WRONG_FACTOR = {"type": "filters.assign", "value": "Z = Z * 0.3048"}
_READERS_LAS = {"type": "readers.las", "filename": "dummy.laz"}


def _inject_step_builders(monkeypatch, building, ground=None, vegetation=None):
    """Monkeypatch validate_runtime_pipeline_normalization to use explicit step lists."""
    ground = ground if ground is not None else building
    vegetation = vegetation if vegetation is not None else building

    def _gate(**_):
        errors = []
        for mode, steps in [("building", building), ("ground", ground), ("vegetation", vegetation)]:
            errors.extend(harness._validate_step_builder_normalization(mode, steps))
        return errors

    monkeypatch.setattr(harness, "validate_runtime_pipeline_normalization", _gate)


def _run_dry_smoke(tmp_path, monkeypatch, allowlist=None):
    """Run controlled smoke dry-run and return (code, manifest)."""
    if allowlist is None:
        allowlist, _ = _make_allowlist(tmp_path)
        monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out"
    code = harness.main(["--controlled-smoke", "--output-root", str(out), *_tile_flags(allowlist)])
    return code, _manifest_at(out)


def test_harness_runtime_gate_refuses_absent_assign(tmp_path, monkeypatch):
    """Harness preflight records and flags absent filters.assign as a normalization error.

    When filters.assign is missing from the building pipeline, controlled smoke
    cannot be authorized because the subprocess would apply HAG/range to foot-valued Z.
    """
    bad_steps = [_READERS_LAS, _REPROJECTION_STEP, _HAG_STEP, _RANGE_STEP]
    _inject_step_builders(monkeypatch, bad_steps)

    code, m = _run_dry_smoke(tmp_path, monkeypatch)

    preflight = m["controlled_smoke"]["preflight"]
    errors = preflight["runtime_normalization_errors"]
    assert errors, "harness must record normalization errors when assign is absent"
    assert not preflight["all_clear"]
    assert any("absent" in e for e in errors), f"expected 'absent' in errors: {errors}"
    assert code == 0  # dry-run; runtime gate recorded but does not affect exit code


def test_harness_runtime_gate_refuses_duplicate_assign(tmp_path, monkeypatch):
    """Harness preflight records duplicate filters.assign as a normalization error.

    Two assign stages would double the Z conversion, producing height values ~2× too large.
    """
    dup_steps = [_READERS_LAS, _REPROJECTION_STEP, _ASSIGN_CORRECT, _ASSIGN_CORRECT, _HAG_STEP, _RANGE_STEP]
    _inject_step_builders(monkeypatch, dup_steps)

    code, m = _run_dry_smoke(tmp_path, monkeypatch)

    preflight = m["controlled_smoke"]["preflight"]
    errors = preflight["runtime_normalization_errors"]
    assert errors
    assert not preflight["all_clear"]
    assert any("2" in e or "duplicate" in e.lower() or "exactly once" in e.lower() for e in errors), \
        f"expected duplicate-assign error: {errors}"


def test_harness_runtime_gate_refuses_wrong_factor(tmp_path, monkeypatch):
    """Harness preflight records wrong Z conversion factor as a normalization error.

    0.3048 (international foot) differs from 0.3048006096012192 (US survey foot / EPSG:6360);
    the error accumulates over large coordinates.
    """
    bad_steps = [_READERS_LAS, _REPROJECTION_STEP, _ASSIGN_WRONG_FACTOR, _HAG_STEP, _RANGE_STEP]
    _inject_step_builders(monkeypatch, bad_steps)

    code, m = _run_dry_smoke(tmp_path, monkeypatch)

    preflight = m["controlled_smoke"]["preflight"]
    errors = preflight["runtime_normalization_errors"]
    assert errors
    assert not preflight["all_clear"]
    assert any("0.3048" in e for e in errors), f"expected factor mismatch error: {errors}"


def test_harness_runtime_gate_refuses_assign_after_hag(tmp_path, monkeypatch):
    """Harness preflight records assign-after-HAG as a normalization ordering error.

    HAG computation (filters.hag_nn) requires metric Z values. Normalizing after HAG
    means HAG receives foot-valued Z and produces incorrect HeightAboveGround values.
    """
    bad_steps = [_READERS_LAS, _REPROJECTION_STEP, _HAG_STEP, _ASSIGN_CORRECT, _RANGE_STEP]
    _inject_step_builders(monkeypatch, bad_steps)

    code, m = _run_dry_smoke(tmp_path, monkeypatch)

    preflight = m["controlled_smoke"]["preflight"]
    errors = preflight["runtime_normalization_errors"]
    assert errors
    assert not preflight["all_clear"]
    assert any("hag_nn" in e.lower() or "hag" in e.lower() for e in errors), \
        f"expected HAG ordering error: {errors}"


def test_harness_runtime_gate_refuses_assign_after_range(tmp_path, monkeypatch):
    """Harness preflight records assign-after-range as a normalization ordering error.

    filters.range applies metric height thresholds (e.g. 2.5–300 m). Normalizing after
    range means the filter sees foot-valued Z and discards nearly all building points.
    """
    bad_steps = [_READERS_LAS, _REPROJECTION_STEP, _RANGE_STEP, _ASSIGN_CORRECT]
    _inject_step_builders(monkeypatch, bad_steps)

    code, m = _run_dry_smoke(tmp_path, monkeypatch)

    preflight = m["controlled_smoke"]["preflight"]
    errors = preflight["runtime_normalization_errors"]
    assert errors
    assert not preflight["all_clear"]
    assert any("range" in e.lower() for e in errors), f"expected range ordering error: {errors}"


def test_harness_runtime_gate_passes_correct_pipeline(tmp_path, monkeypatch):
    """Harness preflight records no normalization errors for the correctly ordered pipeline.

    Correct order: readers.las → reprojection → assign (0.3048006096012192) → hag_nn → range.
    This is the repaired run_tile_miami.py step sequence. all_clear reflects this.
    """
    good_steps = [_READERS_LAS, _REPROJECTION_STEP, _ASSIGN_CORRECT, _HAG_STEP, _RANGE_STEP]
    _inject_step_builders(monkeypatch, good_steps)

    code, m = _run_dry_smoke(tmp_path, monkeypatch)

    preflight = m["controlled_smoke"]["preflight"]
    assert preflight["runtime_normalization_errors"] == [], \
        f"valid pipeline should produce no errors: {preflight['runtime_normalization_errors']}"
    assert preflight["all_clear"]
    assert code == 0


# ─── controlled-execution flag propagation ─────────────────────────────────────
#
# Covers the fix/miami-controlled-execution-flag-propagation repair: the
# harness's own --execute must not, by itself, cause run_tile_miami.py to
# receive real-execution flags. Flags may only be embedded in argv when every
# gate (feature gate, release status, clean provenance, controlled-smoke
# activation + exact token, clean allowlist/T7/runtime preflight, and the
# module-level REAL_DATA_EXECUTION_ENABLED lock) has independently passed.
# No test here performs real PDAL processing, touches /mnt/t7, or invokes a
# real subprocess — run_command is monkeypatched throughout.

def _authorized_command_args(allowlist, hashes, tmp_path, out):
    """Full CLI args for an otherwise-fully-authorized controlled-smoke --execute run."""
    contract = _write_contract(tmp_path / "auth_contract.json", hashes)
    validator = _write(tmp_path / "auth_validator.py", b"")
    return [
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", harness.CONTROLLED_SMOKE_AUTH_TOKEN,
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--building-characteristics-validator", str(validator),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ]


def _tile_commands(manifest: dict) -> list[dict]:
    return [c for c in manifest["commands"] if c["label"] == "run_tile_miami"]


def _fake_run_command(calls: list[str], *, tile_returncodes=None, write_tile_output=True,
                       qa_returncode=0, validator_returncode=0):
    """Synthetic run_command: records call order, never spawns a real subprocess.

    tile_returncodes: optional dict[tile_id] -> returncode override (default 0).
    write_tile_output: if True, writes the per-tile manifest file run_tile_miami.py
    only writes on real processing, simulating genuine successful output.
    """
    tile_returncodes = tile_returncodes or {}

    def fake(command: dict) -> None:
        calls.append(command["label"])
        if command["label"] == "run_tile_miami":
            out_dir = Path(command["argv"][command["argv"].index("--out") + 1])
            tile_id = out_dir.name
            rc = tile_returncodes.get(tile_id, 0)
            if rc == 0 and write_tile_output:
                manifest_dir = out_dir / "manifest"
                manifest_dir.mkdir(parents=True, exist_ok=True)
                (manifest_dir / f"{tile_id}_manifest.json").write_text("{}", encoding="utf-8")
            command["returncode"] = rc
        elif command["label"] == "miami_processed_qa_json":
            command["returncode"] = qa_returncode
        elif command["label"] == "building_characteristics_validator":
            command["returncode"] = validator_returncode

    return fake


def test_dry_run_child_commands_lack_execution_flags(tmp_path, monkeypatch):
    """Controlled-smoke dry-run (no --execute) never embeds child execution flags."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    out = tmp_path / "out"

    code = harness.main(["--controlled-smoke", "--output-root", str(out), *_tile_flags(allowlist)])

    assert code == 0
    m = _manifest_at(out)
    assert m["controlled_smoke"]["child_execution_authorized"] is False
    tile_cmds = _tile_commands(m)
    assert len(tile_cmds) == 2
    for cmd in tile_cmds:
        assert "--execute" not in cmd["argv"]
        assert "--controlled-execution-authorization" not in cmd["argv"]


def test_authorized_execution_generates_child_execution_flags(tmp_path, monkeypatch):
    """Fully authorized --execute embeds both required flags in both tile commands."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(harness, "run_command", _fake_run_command(calls))
    out = tmp_path / "out"

    code = harness.main(_authorized_command_args(allowlist, hashes, tmp_path, out))

    assert code == 0
    m = _manifest_at(out)
    assert m["controlled_smoke"]["child_execution_authorized"] is True
    tile_cmds = _tile_commands(m)
    assert len(tile_cmds) == 2
    assert {Path(c["argv"][c["argv"].index("--out") + 1]).name for c in tile_cmds} == {
        "318155", "318455",
    }
    for cmd in tile_cmds:
        assert "--execute" in cmd["argv"]
        assert "--controlled-execution-authorization" in cmd["argv"]
        auth_idx = cmd["argv"].index("--controlled-execution-authorization")
        assert cmd["argv"][auth_idx + 1] == harness.CONTROLLED_SMOKE_AUTH_TOKEN
    assert calls == [
        "run_tile_miami", "run_tile_miami", "miami_processed_qa_json",
        "building_characteristics_validator",
    ]


def test_no_third_tile_can_be_authorized(tmp_path, monkeypatch):
    """A third --tile is rejected before any manifest or command is built."""
    allowlist, _ = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    third = _write(tmp_path / "inputs" / "USGS_LPC_FL_MiamiDade_D23_LID2024_777777_0901.laz")

    code = harness.main([
        "--controlled-smoke",
        "--output-root", str(tmp_path / "out"),
        *_tile_flags(allowlist),
        "--tile", f"777777={third}",
    ])

    assert code == 2
    assert not (tmp_path / "out").exists()


def test_missing_authorization_token_prevents_child_flags(tmp_path, monkeypatch):
    """--execute without --controlled-smoke-authorization never reaches child argv."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(harness, "run_command", _fake_run_command(calls))
    contract = _write_contract(tmp_path / "c.json", hashes)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        # deliberately omit --controlled-smoke-authorization
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    assert calls == []
    m = _manifest_at(out)
    assert m["controlled_smoke"]["child_execution_authorized"] is False
    for cmd in _tile_commands(m):
        assert "--execute" not in cmd["argv"]


def test_invalid_authorization_token_prevents_child_flags(tmp_path, monkeypatch):
    """--execute with an incorrect token never reaches child argv."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(harness, "run_command", _fake_run_command(calls))
    contract = _write_contract(tmp_path / "c.json", hashes)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", "WRONG_TOKEN",
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    assert calls == []
    m = _manifest_at(out)
    assert m["controlled_smoke"]["child_execution_authorized"] is False
    for cmd in _tile_commands(m):
        assert "--execute" not in cmd["argv"]


def test_module_lock_false_prevents_child_flags(tmp_path, monkeypatch):
    """REAL_DATA_EXECUTION_ENABLED=False (the default) blocks flag propagation
    even when every other gate — token, contract, allowlist, T7 — passes."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    # REAL_DATA_EXECUTION_ENABLED intentionally left at its default False.
    assert harness.REAL_DATA_EXECUTION_ENABLED is False
    calls: list[str] = []
    monkeypatch.setattr(harness, "run_command", _fake_run_command(calls))
    out = tmp_path / "out"

    code = harness.main(_authorized_command_args(allowlist, hashes, tmp_path, out))

    assert code == 2
    assert calls == []
    m = _manifest_at(out)
    assert m["controlled_smoke"]["child_execution_authorized"] is False
    for cmd in _tile_commands(m):
        assert "--execute" not in cmd["argv"]


def test_child_nonzero_return_stops_downstream_qa(tmp_path, monkeypatch):
    """A real (non-dry-run) tile failure halts the sequence before qa_processed_outputs."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(
        harness, "run_command", _fake_run_command(calls, tile_returncodes={"318155": 1})
    )
    out = tmp_path / "out"

    code = harness.main(_authorized_command_args(allowlist, hashes, tmp_path, out))

    assert code == 1
    assert "miami_processed_qa_json" not in calls
    assert "building_characteristics_validator" not in calls
    m = _manifest_at(out)
    assert m["execution_status"] == "failed"
    assert "returncode 1" in m["execution_failure_reason"]


def test_parent_harness_receives_repaired_child_failure_and_skips_qa(tmp_path, monkeypatch):
    """The controlled-smoke parent must stop on the repaired child nonzero exit."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(
        harness,
        "run_command",
        _fake_run_command(calls, tile_returncodes={"318155": 1}, write_tile_output=False),
    )
    out = tmp_path / "out"

    code = harness.main(_authorized_command_args(allowlist, hashes, tmp_path, out))

    assert code == 1
    assert calls == ["run_tile_miami"]
    m = _manifest_at(out)
    tile_cmds = _tile_commands(m)
    assert tile_cmds[0]["returncode"] == 1
    assert tile_cmds[1]["returncode"] is None
    assert "miami_processed_qa_json" not in calls
    assert "building_characteristics_validator" not in calls


def test_exit_code_repair_keeps_both_execution_locks_false():
    """The child exit-code repair must not enable either real-data execution lock."""
    harness_source = (REPO_ROOT / "scripts" / "diagnostics" / "miami_metric_smoke_harness.py").read_text(
        encoding="utf-8"
    )
    runtime_source = (REPO_ROOT / "scripts" / "miami" / "run_tile_miami.py").read_text(
        encoding="utf-8"
    )

    assert "REAL_DATA_EXECUTION_ENABLED = False" in harness_source
    assert "REAL_DATA_EXECUTION_ENABLED = True" not in harness_source
    assert "REAL_DATA_EXECUTION_ENABLED: bool = False" in runtime_source
    assert "REAL_DATA_EXECUTION_ENABLED: bool = True" not in runtime_source


def test_exit_code_repair_keeps_miami_production_allowed_false():
    """The child exit-code repair must not alter Miami production authorization."""
    city_config = json.loads((REPO_ROOT / "configs" / "cities" / "miami.json").read_text(encoding="utf-8"))

    production_allowed_values: list[bool] = []

    def _collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "production_allowed":
                    production_allowed_values.append(item)
                _collect(item)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    _collect(city_config)
    assert production_allowed_values
    assert all(value is False for value in production_allowed_values)


def test_child_success_returncode_with_no_output_is_still_failure(tmp_path, monkeypatch):
    """A dry-run result (returncode 0, no processed output) must not be classified
    as successful real execution — the overall run must fail, not silently pass."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(
        harness, "run_command", _fake_run_command(calls, write_tile_output=False)
    )
    out = tmp_path / "out"

    code = harness.main(_authorized_command_args(allowlist, hashes, tmp_path, out))

    assert code != 0
    m = _manifest_at(out)
    assert m["execution_status"] == "failed"


def test_missing_tile_output_skips_qa_with_structured_finding(tmp_path, monkeypatch):
    """Missing processed output produces a structured skip record, never an exception,
    and qa_processed_outputs.py / the validator are never actually invoked."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(
        harness, "run_command", _fake_run_command(calls, write_tile_output=False)
    )
    out = tmp_path / "out"

    code = harness.main(_authorized_command_args(allowlist, hashes, tmp_path, out))

    assert code == 3
    assert calls == ["run_tile_miami", "run_tile_miami"]
    assert "miami_processed_qa_json" not in calls
    assert "building_characteristics_validator" not in calls
    m = _manifest_at(out)
    qa_cmd = [c for c in m["commands"] if c["label"] == "miami_processed_qa_json"][0]
    assert qa_cmd.get("skipped") is True
    assert "no real processed-tile output" in qa_cmd["skip_reason"]
    assert m["execution_status"] == "failed"
    assert "no real processed-tile output" in m["execution_failure_reason"]
    assert not (out / "tiles" / "318155" / "manifest").exists()


def test_successful_synthetic_output_permits_downstream_sequencing(tmp_path, monkeypatch):
    """Genuine synthetic tile output (manifest files present) lets qa and the
    validator run in sequence, and a fully clean run returns 0."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setattr(harness, "REAL_DATA_EXECUTION_ENABLED", True)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(harness, "run_command", _fake_run_command(calls))
    out = tmp_path / "out"

    code = harness.main(_authorized_command_args(allowlist, hashes, tmp_path, out))

    assert code == 0
    assert calls == [
        "run_tile_miami", "run_tile_miami", "miami_processed_qa_json",
        "building_characteristics_validator",
    ]
    m = _manifest_at(out)
    assert m["execution_status"] == "passed"
    assert "execution_failure_reason" not in m


def test_runnable_true_does_not_bypass_refusal_gates(tmp_path, monkeypatch):
    """command_record.runnable is reporting-only: even when every command is
    recorded runnable=True (because --execute was supplied), an unauthorized
    run (wrong token) must still result in zero commands actually executed."""
    allowlist, hashes = _make_allowlist(tmp_path)
    monkeypatch.setattr(harness, "CONTROLLED_SMOKE_ALLOWLIST", allowlist)
    monkeypatch.setattr(harness, "check_t7_read_only", _t7_ro_mock)
    monkeypatch.setenv(harness.GATE_ENV, "1")
    calls: list[str] = []
    monkeypatch.setattr(harness, "run_command", _fake_run_command(calls))
    contract = _write_contract(tmp_path / "c.json", hashes)
    out = tmp_path / "out"

    code = harness.main([
        "--controlled-smoke", "--execute",
        "--controlled-smoke-authorization", "WRONG_TOKEN",
        "--release-status", "CONDITIONAL_GO",
        "--source-contract", str(contract),
        "--output-root", str(out),
        *_tile_flags(allowlist),
    ])

    assert code == 2
    m = _manifest_at(out)
    assert all(cmd["runnable"] is True for cmd in m["commands"])
    assert all(cmd["returncode"] is None for cmd in m["commands"])
    assert calls == []


def test_module_locks_default_false_outside_authorized_window():
    """Both execution locks default to False at import time (no authorized window active)."""
    assert harness.REAL_DATA_EXECUTION_ENABLED is False
    import importlib
    miami_scripts = REPO_ROOT / "scripts" / "miami"
    if str(miami_scripts) not in sys.path:
        sys.path.insert(0, str(miami_scripts))
    for name in ("run_tile_miami", "miami_city_config"):
        sys.modules.pop(name, None)
    try:
        rtm = importlib.import_module("run_tile_miami")
    except ImportError:
        pytest.skip("pdal not installed; run_tile_miami cannot be imported in this environment")
    assert rtm.REAL_DATA_EXECUTION_ENABLED is False


def test_production_allowed_remains_false_in_miami_city_config():
    """This repair must not have touched production_allowed anywhere in the Miami config."""
    import json as _json
    config_path = REPO_ROOT / "configs" / "cities" / "miami.json"
    config = _json.loads(config_path.read_text(encoding="utf-8"))

    def _walk(node):
        if isinstance(node, dict):
            if "production_allowed" in node:
                assert node["production_allowed"] is False
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(config)
