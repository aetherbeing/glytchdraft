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
