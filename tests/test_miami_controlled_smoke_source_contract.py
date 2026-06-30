"""
tests/test_miami_controlled_smoke_source_contract.py

Focused tests for configs/smoke/miami_controlled_two_tile_source_contract.json.

Proves that the repository-controlled source-contract artifact:
  - parses as valid JSON
  - contains all validator-required keys with concrete values
  - contains no null, blank, unknown, TBD, TODO, or placeholder text
  - exactly matches the authoritative CRS, units, and Z-factor values
  - contains exactly the two canonical tile hashes and no others
  - is accepted by harness.provenance_findings() with zero blockers
  - alone cannot authorize execution (both execution locks remain False)

No real LAZ data is read. No PDAL pipeline is invoked.
No writes occur to /mnt/t7.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "smoke" / "miami_controlled_two_tile_source_contract.json"
DIAG_DIR = REPO_ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAG_DIR))

import miami_metric_smoke_harness as harness  # noqa: E402

# Canonical values from the controlled-preflight evidence
_TILE_318155_SHA = "0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095"
_TILE_318455_SHA = "dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816"
_EXPECTED_TILE_IDS = frozenset({"318155", "318455"})
_EXPECTED_Z_FACTOR = 0.3048006096012192

# Exact forbidden keyword strings (case-sensitive)
_PLACEHOLDER_KEYWORDS = ("TODO", "TBD", "unknown", "unconfirmed", "placeholder")

# Angle-bracket placeholder pattern: <word> or <multi-word> but NOT -> (CRS arrow notation)
_ANGLE_BRACKET_PLACEHOLDER_RE = re.compile(r"<[^>]+>")


# ─── fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


# ─── parse and structure ──────────────────────────────────────────────────────

def test_contract_file_exists():
    assert CONTRACT_PATH.exists(), f"contract file not found: {CONTRACT_PATH}"


def test_contract_parses_as_json_object(contract):
    assert isinstance(contract, dict), "contract must be a JSON object"


def test_all_required_provenance_keys_present(contract):
    for key in harness.REQUIRED_PROVENANCE_KEYS:
        assert key in contract, f"required key missing: {key!r}"


def test_no_required_value_is_none(contract):
    for key in harness.REQUIRED_PROVENANCE_KEYS:
        assert contract[key] is not None, f"required key {key!r} is null"


def test_no_required_value_is_blank(contract):
    for key in harness.REQUIRED_PROVENANCE_KEYS:
        val = contract[key]
        if isinstance(val, str):
            assert val.strip() != "", f"required key {key!r} is blank"


def test_no_required_value_is_placeholder_keyword(contract):
    for key in harness.REQUIRED_PROVENANCE_KEYS:
        val = contract[key]
        if not isinstance(val, str):
            continue
        for bad in _PLACEHOLDER_KEYWORDS:
            assert bad not in val, (
                f"required key {key!r} contains placeholder keyword {bad!r}: {val!r}"
            )


def test_no_required_value_contains_angle_bracket_placeholder(contract):
    """Detect <word> style placeholders; excludes -> CRS arrow notation."""
    for key in harness.REQUIRED_PROVENANCE_KEYS:
        val = contract[key]
        if not isinstance(val, str):
            continue
        matches = _ANGLE_BRACKET_PLACEHOLDER_RE.findall(val)
        assert not matches, (
            f"required key {key!r} contains angle-bracket placeholder(s) {matches}: {val!r}"
        )


# ─── CRS and unit exact values ────────────────────────────────────────────────

def test_source_horizontal_crs(contract):
    assert contract["source_horizontal_crs"] == "EPSG:6438"


def test_source_vertical_crs(contract):
    assert contract["source_vertical_crs"] == "EPSG:6360"


def test_source_horizontal_unit(contract):
    assert contract["source_horizontal_unit"] == "US survey foot"


def test_source_vertical_unit(contract):
    assert contract["source_vertical_unit"] == "US survey foot"


def test_processed_horizontal_crs(contract):
    assert contract["processed_horizontal_crs"] == "EPSG:32617"


# ─── processed Z unit accepted by harness ────────────────────────────────────

def test_processed_z_unit_is_nonempty_string(contract):
    val = contract["processed_z_unit"]
    assert isinstance(val, str) and val.strip(), (
        "processed_z_unit must be a non-empty string"
    )


def test_processed_z_unit_not_in_harness_absent_sentinel(contract):
    _absent = (None, "", "unknown", "unconfirmed")
    assert contract["processed_z_unit"] not in _absent, (
        "processed_z_unit is in the harness absent sentinel — harness would flag missing_provenance"
    )


# ─── Z conversion factor ──────────────────────────────────────────────────────

def test_z_conversion_factor_exact(contract):
    assert contract["z_conversion_factor"] == _EXPECTED_Z_FACTOR, (
        f"expected {_EXPECTED_Z_FACTOR!r}, got {contract['z_conversion_factor']!r}"
    )


# ─── boolean guards ───────────────────────────────────────────────────────────

def test_xy_reprojection_converts_z_is_false(contract):
    assert contract["xy_reprojection_converts_z"] is False, (
        "xy_reprojection_converts_z must be JSON false (Python False)"
    )


def test_possible_double_conversion_is_false(contract):
    assert contract["possible_double_conversion"] is False, (
        "possible_double_conversion must be JSON false (Python False)"
    )


# ─── canonical input hashes ───────────────────────────────────────────────────

def test_canonical_input_hashes_is_dict(contract):
    hashes = contract["canonical_input_hashes"]
    assert isinstance(hashes, dict), (
        "canonical_input_hashes must be a JSON object (dict)"
    )


def test_exactly_two_tile_hashes(contract):
    hashes = contract["canonical_input_hashes"]
    assert set(hashes.keys()) == _EXPECTED_TILE_IDS, (
        f"expected exactly tiles {_EXPECTED_TILE_IDS}, got {set(hashes.keys())}"
    )


def test_no_additional_tile_hash(contract):
    hashes = contract["canonical_input_hashes"]
    extra = set(hashes.keys()) - _EXPECTED_TILE_IDS
    assert not extra, f"unexpected tile IDs in canonical_input_hashes: {extra}"


def test_tile_318155_hash_exact(contract):
    assert contract["canonical_input_hashes"]["318155"] == _TILE_318155_SHA


def test_tile_318455_hash_exact(contract):
    assert contract["canonical_input_hashes"]["318455"] == _TILE_318455_SHA


def test_tile_hashes_are_64_hex_chars(contract):
    for tile_id, sha in contract["canonical_input_hashes"].items():
        assert len(sha) == 64, f"hash for {tile_id} is not 64 chars: {sha!r}"
        assert all(c in "0123456789abcdef" for c in sha), (
            f"hash for {tile_id} contains non-hex characters: {sha!r}"
        )


# ─── source contract status ───────────────────────────────────────────────────

def test_source_contract_status_is_conditional_go(contract):
    assert contract["source_contract_status"] == "CONDITIONAL_GO"


# ─── harness provenance acceptance ────────────────────────────────────────────

def test_harness_load_source_contract_succeeds():
    loaded = harness.load_source_contract(CONTRACT_PATH)
    assert isinstance(loaded, dict)
    assert len(loaded) > 0


def test_harness_provenance_findings_zero_blockers_without_inputs(contract):
    """provenance_findings() with no input_records returns [] for this contract."""
    findings = harness.provenance_findings(contract, input_records=None)
    assert findings == [], (
        f"harness reported blocker findings against the contract: {findings}"
    )


def test_harness_provenance_findings_accepts_matching_input_records(contract):
    """provenance_findings() accepts input_records whose hashes match the contract."""
    input_records = [
        {"tile_id": "318155", "sha256": _TILE_318155_SHA},
        {"tile_id": "318455", "sha256": _TILE_318455_SHA},
    ]
    findings = harness.provenance_findings(contract, input_records=input_records)
    assert findings == [], (
        f"harness reported blockers against matching input records: {findings}"
    )


def test_harness_contract_hashes_returns_both_tiles(contract):
    hashes = harness._contract_hashes(contract)
    assert set(hashes.keys()) == _EXPECTED_TILE_IDS
    assert hashes["318155"] == _TILE_318155_SHA
    assert hashes["318455"] == _TILE_318455_SHA


# ─── artifact cannot authorize execution alone ────────────────────────────────

def test_contract_does_not_contain_execution_authorization(contract):
    """The contract artifact must not embed an execution authorization token."""
    contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert harness.CONTROLLED_SMOKE_AUTH_TOKEN not in contract_text, (
        "contract must not embed the controlled smoke authorization token"
    )


def test_harness_execution_lock_remains_false():
    """REAL_DATA_EXECUTION_ENABLED must remain False in miami_metric_smoke_harness."""
    assert harness.REAL_DATA_EXECUTION_ENABLED is False


def test_runtime_execution_lock_remains_false():
    """REAL_DATA_EXECUTION_ENABLED must remain False in run_tile_miami."""
    import importlib
    import types

    miami_dir = str(REPO_ROOT / "scripts" / "miami")
    if miami_dir not in sys.path:
        sys.path.insert(0, miami_dir)

    # Stub heavy optional deps so the module can be imported without pdal/sklearn/shapely
    for mod_name, mod in [
        ("pdal", types.ModuleType("pdal")),
        ("shapely", types.ModuleType("shapely")),
        ("shapely.geometry", types.ModuleType("shapely.geometry")),
        ("shapely.prepared", types.ModuleType("shapely.prepared")),
        ("shapely.ops", types.ModuleType("shapely.ops")),
        ("sklearn", types.ModuleType("sklearn")),
        ("sklearn.cluster", types.ModuleType("sklearn.cluster")),
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = mod

    # Provide minimum attributes needed at import time
    pdal_mod = sys.modules["pdal"]
    if not hasattr(pdal_mod, "Pipeline"):
        class _MockPipeline:
            def __init__(self, s):
                self.arrays: list = []
            def execute(self) -> int:
                return 0
        pdal_mod.Pipeline = _MockPipeline  # type: ignore[attr-defined]

    geom = sys.modules["shapely.geometry"]
    for attr in ("Polygon", "MultiPolygon", "MultiPoint", "Point", "mapping", "shape"):
        if not hasattr(geom, attr):
            setattr(geom, attr, None)
    prep = sys.modules["shapely.prepared"]
    if not hasattr(prep, "prep"):
        prep.prep = lambda g: g  # type: ignore[attr-defined]
    ops = sys.modules["shapely.ops"]
    if not hasattr(ops, "unary_union"):
        ops.unary_union = lambda gs: None  # type: ignore[attr-defined]
    cluster = sys.modules["sklearn.cluster"]
    if not hasattr(cluster, "DBSCAN"):
        cluster.DBSCAN = None  # type: ignore[attr-defined]

    sys.modules.pop("run_tile_miami", None)
    sys.modules.pop("miami_city_config", None)
    rtm = importlib.import_module("run_tile_miami")
    assert rtm.REAL_DATA_EXECUTION_ENABLED is False


def test_production_allowed_remains_false():
    """Miami production_allowed must remain false in configs/cities/miami.json."""
    miami_cfg = REPO_ROOT / "configs" / "cities" / "miami.json"
    data = json.loads(miami_cfg.read_text(encoding="utf-8"))
    footprint = data["pipeline_tunables"]["footprint_source_detail"]
    assert footprint["production_allowed"] is False


# ─── no real data / no T7 writes ─────────────────────────────────────────────

def test_contract_source_paths_not_accessed(contract):
    """The contract file does not contain filesystem paths to actual LAZ files."""
    contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "/mnt/t7" not in contract_text, (
        "contract must not reference /mnt/t7 paths — it is a provenance record, not an execution plan"
    )
