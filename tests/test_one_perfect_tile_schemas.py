"""
Tests for the six frozen One-Perfect-Tile JSON Schemas under schemas/one_perfect_tile/.

W1 scope: schema implementation only. These tests validate that the six accepted
frozen schemas (atlantid_tile_package_manifest, atlantid_feature_metadata,
atlantid_provenance_receipt, atlantid_design_export_manifest,
atlantid_layer_license_matrix, atlantid_join_contract) are present at their exact
canonical filenames, parse as JSON, validate as draft-07 metaschema, carry unique
$id values, are bound by a six-entry registry with correct hashes, resolve all
$ref pointers locally with no network dependency, accept their synthetic valid
fixtures, and reject every synthetic invalid/mutation fixture for the intended
reason. They also check the cross-schema invariants required by the frozen
contract: generic-join source-independence, C12 accuracy honesty, and Condition
10 remaining one dual-track export packet.

These tests run without PDAL, without /mnt/t7 access, and without any real LAZ,
GLB, or Miami/NOLA tile data. No fixture contains a real address or real tile
hash; laz_sha256/source hashes are synthetic all-same-digit placeholders.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schemas" / "one_perfect_tile"
REGISTRY_PATH = SCHEMA_DIR / "schema_registry.json"
VALID_FIXTURES_DIR = SCHEMA_DIR / "fixtures" / "valid"
INVALID_FIXTURES_DIR = SCHEMA_DIR / "fixtures" / "invalid"
VALIDATOR_SCRIPT = REPO_ROOT / "scripts" / "validate_one_perfect_tile_schemas.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import validate_one_perfect_tile_schemas as v  # noqa: E402

try:
    from jsonschema import Draft7Validator

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False

pytestmark_jsonschema = pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")

CANONICAL_FILENAMES = [
    "atlantid_tile_package_manifest.schema.json",
    "atlantid_feature_metadata.schema.json",
    "atlantid_provenance_receipt.schema.json",
    "atlantid_design_export_manifest.schema.json",
    "atlantid_layer_license_matrix.schema.json",
    "atlantid_join_contract.schema.json",
]

EXPECTED_IDS = {
    "atlantid_tile_package_manifest.schema.json": "atlantid.one_perfect_tile.tile_package_manifest.v1",
    "atlantid_feature_metadata.schema.json": "atlantid.one_perfect_tile.feature_metadata.v1",
    "atlantid_provenance_receipt.schema.json": "atlantid.one_perfect_tile.provenance_receipt.v1",
    "atlantid_design_export_manifest.schema.json": "atlantid.one_perfect_tile.design_export_manifest.v1",
    "atlantid_layer_license_matrix.schema.json": "atlantid.one_perfect_tile.layer_license_matrix.v1",
    "atlantid_join_contract.schema.json": "atlantid.one_perfect_tile.join_contract.v1",
}

_REAL_MIAMI_TILE_IDS = ("318155",)  # 318455 is the declared product tile identity, not a leak


# ── File presence / parse ──────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_canonical_schema_file_exists(filename):
    assert (SCHEMA_DIR / filename).exists(), f"Missing canonical schema: {filename}"


@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_canonical_schema_is_valid_json(filename):
    data = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    assert isinstance(data, dict)


@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_canonical_schema_has_expected_id(filename):
    data = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    assert data.get("$id") == EXPECTED_IDS[filename]


@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_canonical_schema_final_newline_and_utf8(filename):
    raw_bytes = (SCHEMA_DIR / filename).read_bytes()
    assert raw_bytes.endswith(b"\n")
    raw_bytes.decode("utf-8")  # raises if not valid UTF-8


@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_canonical_schema_is_valid_draft7(filename):
    data = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    assert data.get("$schema") == "http://json-schema.org/draft-07/schema#"
    Draft7Validator.check_schema(data)


def test_all_ids_unique():
    ids = [EXPECTED_IDS[f] for f in CANONICAL_FILENAMES]
    assert len(ids) == len(set(ids)) == 6


# ── No network dependency ──────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_no_external_url_reference(filename):
    text = (SCHEMA_DIR / filename).read_text(encoding="utf-8")
    urls = re.findall(r'https?://[^\s"]+', text)
    # The only permitted network-shaped string is the fixed draft-07 metaschema URI.
    unexpected = [u for u in urls if u != "http://json-schema.org/draft-07/schema#"]
    assert unexpected == [], f"{filename} contains unexpected network reference(s): {unexpected}"


# ── Local $ref resolution ──────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_all_refs_are_local_and_resolve(filename):
    schema = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    refs = v.find_all_ref_targets(schema)
    for ref in refs:
        assert ref.startswith("#/"), f"{filename} has non-local $ref: {ref}"
        assert v.resolve_local_pointer(schema, ref), f"{filename} $ref does not resolve: {ref}"


# ── Registry ────────────────────────────────────────────────────────────────────

def test_registry_file_exists():
    assert REGISTRY_PATH.exists()


def test_registry_has_exactly_six_entries():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert len(registry["schemas"]) == 6


def test_registry_does_not_claim_product_acceptance():
    """The registry's own structured fields must not assert an achieved product/
    acceptance state; prose disclaiming PRODUCT_COMPLETE in the disposition note
    is expected and is not itself a claim of completion."""
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert "product_state" not in registry
    assert "condition_acceptance" not in registry
    assert "gate_b_review_outcome" not in registry
    for entry in registry["schemas"]:
        assert entry["implementation_status"] != "PRODUCT_COMPLETE"


@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_registry_hash_matches_file_on_disk(filename):
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = next(e for e in registry["schemas"] if e["canonical_filename"] == filename)
    actual = v.sha256_of(SCHEMA_DIR / filename)
    assert entry["sha256"] == actual


def test_registry_hash_matches_frozen_source_manifest():
    """The registry's per-schema sha256 must equal the frozen contract manifest's
    sha256 for the same file, proving the repository copy is byte-identical to the
    accepted/frozen payload."""
    frozen_manifest = (
        Path("/home/gytchdrafter/ATLANTID_SPRINT_20260704/designs")
        / "one_perfect_tile_asset_viewer_contract_v3_ACCEPTED_FROZEN_20260715T023757Z"
        / "manifest.sha256"
    )
    if not frozen_manifest.exists():
        pytest.skip("frozen contract manifest not present in this environment")
    frozen_hashes = {}
    for line in frozen_manifest.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        frozen_hashes[parts[-1]] = parts[0]

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for entry in registry["schemas"]:
        filename = entry["canonical_filename"]
        assert frozen_hashes[filename] == entry["sha256"], f"{filename} registry hash diverges from frozen manifest"


# ── Validator CLI exit codes ────────────────────────────────────────────────────

def test_validator_script_compiles():
    import py_compile

    py_compile.compile(str(VALIDATOR_SCRIPT), doraise=True)


def test_validator_full_check_exits_zero():
    assert v.run_full_check(verbose=False) == 0


# ── Fixture loading helpers ─────────────────────────────────────────────────────

def _schema_for(path: Path) -> dict:
    for filename in CANONICAL_FILENAMES:
        prefix = filename[: -len(".schema.json")]
        if path.name.startswith(prefix + "."):
            return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    raise AssertionError(f"no schema mapping for fixture {path.name}")


VALID_FIXTURE_PATHS = sorted(VALID_FIXTURES_DIR.glob("*.json")) if VALID_FIXTURES_DIR.exists() else []
INVALID_FIXTURE_PATHS = sorted(INVALID_FIXTURES_DIR.glob("*.json")) if INVALID_FIXTURES_DIR.exists() else []


def test_expected_valid_fixture_count():
    assert len(VALID_FIXTURE_PATHS) == 6


def test_expected_invalid_fixture_count_at_least_one_per_schema():
    prefixes = {p.name.split(".")[0] + "_" + p.name.split(".")[1] for p in INVALID_FIXTURE_PATHS}
    for filename in CANONICAL_FILENAMES:
        prefix = filename[: -len(".schema.json")]
        assert any(p.name.startswith(prefix + ".") for p in INVALID_FIXTURE_PATHS), f"no invalid fixture for {filename}"


@pytest.mark.parametrize("path", VALID_FIXTURE_PATHS, ids=lambda p: p.name)
@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_valid_fixture_passes(path):
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors == [], f"{path.name} unexpectedly failed: {errors}"


@pytest.mark.parametrize("path", INVALID_FIXTURE_PATHS, ids=lambda p: p.name)
@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_invalid_fixture_is_rejected(path):
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != [], f"{path.name} was unexpectedly ACCEPTED"


# ── No real addresses / no real Miami-Dade tile leakage in fixtures ────────────

@pytest.mark.parametrize("path", VALID_FIXTURE_PATHS + INVALID_FIXTURE_PATHS, ids=lambda p: p.name)
def test_fixture_contains_no_real_expansion_tile_id(path):
    raw = path.read_text(encoding="utf-8")
    for tile_id in _REAL_MIAMI_TILE_IDS:
        assert tile_id not in raw, f"{path.name} must not reference expansion tile {tile_id}"


@pytest.mark.parametrize("path", VALID_FIXTURE_PATHS, ids=lambda p: p.name)
def test_valid_fixture_no_mnt_t7_path(path):
    raw = path.read_text(encoding="utf-8").lower()
    assert "/mnt/t7" not in raw
    assert "/mnt/e/" not in raw


# ── P3-F finding-specific Gate-B compliance tests (named per the frozen contract) ─

def test_p3f001_footprint_provenance_rejects_unknown_unsafe_source():
    path = INVALID_FIXTURES_DIR / "atlantid_feature_metadata.INVALID_unknown_unsafe_source.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert any("footprint_provenance" in e or "unknown_unsafe_source" in e for e in errors)


def test_p3f002_claim_tiers_requires_full_mandatory_set():
    path = INVALID_FIXTURES_DIR / "atlantid_feature_metadata.INVALID_missing_required_negative_tier.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


def test_p3f003_generic_exclusion_set_rejected_when_incomplete():
    path = INVALID_FIXTURES_DIR / "atlantid_tile_package_manifest.INVALID_generic_exclusion.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


def test_p3f004_null_measurement_requires_reason():
    path = INVALID_FIXTURES_DIR / "atlantid_feature_metadata.INVALID_null_measurement_no_reason.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert any("measurement_null_meaning" in e for e in errors)


def test_p3f005_cf05_gate_rejects_node_name_mismatch_via_semantic_validator():
    """Pure draft-07 cannot express node_name == feature_id (cross-field equality);
    plain jsonschema validation of this fixture passes, and only the mandatory
    CF-05 semantic gate (v.cf05_node_name_matches_feature_id) catches it."""
    path = INVALID_FIXTURES_DIR / "atlantid_feature_metadata.INVALID_node_name_mismatch.json"
    schema = json.loads((SCHEMA_DIR / "atlantid_feature_metadata.schema.json").read_text())
    instance = json.loads(path.read_text(encoding="utf-8"))

    if HAS_JSONSCHEMA:
        plain_errors = list(Draft7Validator(schema).iter_errors(instance))
        assert plain_errors == [], "fixture should be schema-valid; only CF-05 semantic gate catches the mismatch"

    gate_violations = v.cf05_node_name_matches_feature_id(instance)
    assert gate_violations != [], "CF-05 semantic gate must reject node_name != feature_id"

    full_errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert full_errors != []


def test_p3f006_contradictory_product_complete_state_rejected():
    path = INVALID_FIXTURES_DIR / "atlantid_tile_package_manifest.INVALID_contradictory_state.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


# ── Cross-schema invariants ─────────────────────────────────────────────────────

def test_stable_id_pattern_consistent_across_schemas():
    feature_metadata = json.loads((SCHEMA_DIR / "atlantid_feature_metadata.schema.json").read_text())
    join_contract = json.loads((SCHEMA_DIR / "atlantid_join_contract.schema.json").read_text())

    feature_id_pattern = feature_metadata["properties"]["features"]["items"]["properties"]["feature_id"]["pattern"]
    join_pattern_const = join_contract["properties"]["stable_identifiers"]["properties"]["feature_id_pattern"]["const"]
    assert feature_id_pattern == join_pattern_const == r"^sb_318455_[0-9]+$"

    feature_namespace_const = feature_metadata["properties"]["feature_namespace"]["const"]
    join_namespace_const = join_contract["properties"]["stable_identifiers"]["properties"]["feature_namespace"]["const"]
    assert feature_namespace_const == join_namespace_const == "atlantid.lidar_segment.shapeA.v1"


def _collect_property_keys(node) -> set[str]:
    """Recursively collect JSON Schema object *property key names* (not string
    values/consts/enum members) so 'ownership' as a permitted enum literal inside
    prohibited_identity_implications isn't confused with 'ownership' as an actual
    Shape-B-style field key."""
    keys: set[str] = set()
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            keys.update(props.keys())
            for value in props.values():
                keys.update(_collect_property_keys(value))
        for key, value in node.items():
            if key != "properties":
                keys.update(_collect_property_keys(value))
    elif isinstance(node, list):
        for item in node:
            keys.update(_collect_property_keys(item))
    return keys


def test_generic_join_contract_has_no_source_specific_fields():
    join_contract = json.loads((SCHEMA_DIR / "atlantid_join_contract.schema.json").read_text())
    property_keys = _collect_property_keys(join_contract)
    # Shape-B/source-specific field keys must never appear as actual property keys
    # in the generic Core join contract. "parcel_identity"/"ownership" etc. are
    # legitimately present as *prohibited-implication enum values*, which is a
    # different thing from being schema property keys here.
    forbidden_keys = {"address", "parcel_id", "county_building_id", "ownership", "legal_structure_identity", "county_enrichment"}
    assert not (property_keys & forbidden_keys), f"generic join contract has source-specific property keys: {property_keys & forbidden_keys}"
    assert join_contract["properties"]["core_boundary"]["properties"]["contains_source_specific_join_recipe"] == {"const": False}
    assert join_contract["properties"]["core_boundary"]["properties"]["contains_externally_derived_join_table"] == {"const": False}


def test_source_specific_join_injection_rejected():
    path = INVALID_FIXTURES_DIR / "atlantid_join_contract.INVALID_source_specific_recipe_injected.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []

    path_extra = INVALID_FIXTURES_DIR / "atlantid_join_contract.INVALID_unknown_additional_property.json"
    instance_extra = json.loads(path_extra.read_text(encoding="utf-8"))
    errors_extra = v.validate_instance(schema, schema.get("$id"), instance_extra)
    assert errors_extra != []


def test_duplicate_feature_ids_detected_as_semantic_invariant():
    path = INVALID_FIXTURES_DIR / "atlantid_feature_metadata.INVALID_duplicate_feature_id.json"
    instance = json.loads(path.read_text(encoding="utf-8"))
    violations = v.unique_feature_ids(instance)
    assert violations != []


def test_c12_status_required_nonblank_and_pending_is_not_measured():
    receipt = json.loads((SCHEMA_DIR / "atlantid_provenance_receipt.schema.json").read_text())
    accuracy = receipt["properties"]["accuracy_status"]
    assert "status" in accuracy["required"]
    assert "statement" in accuracy["required"]
    assert set(accuracy["properties"]["status"]["enum"]) == {"PENDING", "MEASURED", "NOT_BOUND"}

    valid_path = VALID_FIXTURES_DIR / "atlantid_provenance_receipt.valid.json"
    valid_instance = json.loads(valid_path.read_text(encoding="utf-8"))
    assert valid_instance["accuracy_status"]["status"] == "PENDING"
    assert valid_instance["accuracy_status"]["rmse_horizontal_m"] is None
    assert valid_instance["accuracy_status"]["evidence_ref"] is None


def test_c12_measured_without_evidence_rejected():
    path = INVALID_FIXTURES_DIR / "atlantid_provenance_receipt.INVALID_measured_accuracy_without_evidence.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


def test_c12_blank_statement_rejected():
    path = INVALID_FIXTURES_DIR / "atlantid_provenance_receipt.INVALID_blank_c12_statement.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


def test_condition_10_is_one_dual_track_schema_not_split():
    design_export = json.loads((SCHEMA_DIR / "atlantid_design_export_manifest.schema.json").read_text())
    required = set(design_export["required"])
    assert {"mesh_track", "vector_track", "terrain", "rights_and_provenance_refs", "viewer_access", "core_glb_ref", "linking_key"} <= required
    assert design_export["x-atlantid-completion-condition"] == "Condition 10 (rescoped): dual-track export set."

    manifest = json.loads((SCHEMA_DIR / "atlantid_tile_package_manifest.schema.json").read_text())
    completion_conditions_props = manifest["properties"]["completion_conditions"]["properties"]
    assert set(completion_conditions_props.keys()) == {f"c{i}" for i in range(1, 12)}, "exactly eleven conditions, no twelfth"


def test_condition10_export_component_omitted_is_rejected():
    path = INVALID_FIXTURES_DIR / "atlantid_design_export_manifest.INVALID_condition10_component_omitted.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


def test_real_address_in_shape_a_exclusion_is_rejected():
    path = INVALID_FIXTURES_DIR / "atlantid_feature_metadata.INVALID_real_address_in_shape_b_exclusions.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


def test_layer_license_matrix_records_counsel_question_9_without_resolving_it():
    valid_path = VALID_FIXTURES_DIR / "atlantid_layer_license_matrix.valid.json"
    instance = json.loads(valid_path.read_text(encoding="utf-8"))
    assert instance["draws_legal_conclusion"] is False
    outside_core = [layer for layer in instance["layers"] if layer["relationship_to_core"] != "IS_CORE"]
    assert outside_core, "fixture must exercise at least one OUTSIDE_CORE layer"
    joined_questions = " ".join(q for layer in outside_core for q in layer["unresolved_legal_questions"])
    assert "counsel question 9" in joined_questions.lower()


def test_layer_license_matrix_draws_legal_conclusion_true_is_rejected():
    path = INVALID_FIXTURES_DIR / "atlantid_layer_license_matrix.INVALID_draws_legal_conclusion_true.json"
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []


# ── additionalProperties: false is present at the root of every schema ─────────

@pytest.mark.parametrize("filename", CANONICAL_FILENAMES)
def test_schema_root_forbids_unknown_properties(filename):
    schema = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize(
    "invalid_name",
    [
        "atlantid_feature_metadata.INVALID_unknown_additional_property.json",
        "atlantid_join_contract.INVALID_unknown_additional_property.json",
    ],
)
def test_unknown_additional_property_rejected(invalid_name):
    path = INVALID_FIXTURES_DIR / invalid_name
    schema = _schema_for(path)
    instance = json.loads(path.read_text(encoding="utf-8"))
    errors = v.validate_instance(schema, schema.get("$id"), instance)
    assert errors != []
