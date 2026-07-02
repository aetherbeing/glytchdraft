"""
Tests for schemas/atlantid_tile_asset_manifest.schema.json and its synthetic example.

These tests run without PDAL, without /mnt/t7 access, and without any real LAZ,
GLB, or Miami/NOLA tile data. They validate:
  - The schema is valid JSON and loadable as a draft-07 schema
  - The synthetic example manifest validates against the schema
  - The schema rejects manifests missing required identity/hash/CRS/mapping fields
  - The schema rejects mutable ('latest'/'current'/'final-final') asset names
  - The schema rejects wildcard tile scope and city-wide scope in a single-tile manifest
  - The schema rejects production_allowed=true while the contract is a CANDIDATE, and
    while license_status is unresolved
  - The schema enforces the structured knowledge/confidence evidence model
  - The example contains no real Miami tile IDs and no /mnt/t7 paths
  - Both REAL_DATA_EXECUTION_ENABLED locks remain False (unrelated files untouched)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "atlantid_tile_asset_manifest.schema.json"
EXAMPLE_PATH = REPO_ROOT / "configs" / "contracts" / "atlantid_tile_asset_manifest.example.json"
RUN_TILE_MIAMI_PATH = REPO_ROOT / "scripts" / "miami" / "run_tile_miami.py"
SMOKE_HARNESS_PATH = REPO_ROOT / "scripts" / "diagnostics" / "miami_metric_smoke_harness.py"

_REAL_TILE_IDS = ("318155", "318455")

try:
    from jsonschema import Draft7Validator, ValidationError, validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False

pytestmark_jsonschema = pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")


@pytest.fixture(scope="module")
def schema():
    assert SCHEMA_PATH.exists(), f"Schema file not found: {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def example_raw():
    assert EXAMPLE_PATH.exists(), f"Example manifest not found: {EXAMPLE_PATH}"
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def valid_manifest(example_raw):
    """The synthetic example with the _NOTICE annotation key stripped."""
    return {k: v for k, v in copy.deepcopy(example_raw).items() if not k.startswith("_")}


# ── File integrity ─────────────────────────────────────────────────────────────

def test_schema_file_is_valid_json():
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("$id") == "glytchos.atlantid_tile_asset_manifest.v1"
    assert data.get("$schema") == "http://json-schema.org/draft-07/schema#"


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_is_valid_draft7(schema):
    Draft7Validator.check_schema(schema)


def test_example_manifest_is_valid_json():
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ── Example manifest safety checks ────────────────────────────────────────────

def test_example_manifest_no_real_miami_tile_ids():
    raw = EXAMPLE_PATH.read_text(encoding="utf-8")
    for tile_id in _REAL_TILE_IDS:
        assert tile_id not in raw, f"Example manifest must not contain real Miami tile ID {tile_id}"


def test_example_manifest_no_t7_paths():
    raw = EXAMPLE_PATH.read_text(encoding="utf-8").lower()
    assert "/mnt/t7" not in raw


def test_example_manifest_is_candidate_not_frozen(valid_manifest):
    assert valid_manifest["contract_status"] == "CANDIDATE"


def test_example_manifest_production_allowed_is_false(valid_manifest):
    assert valid_manifest["publication"]["production_allowed"] is False


def test_example_manifest_auto_publish_disabled(valid_manifest):
    assert valid_manifest["publication"]["auto_publish_enabled"] is False


def test_example_manifest_tile_scope_single(valid_manifest):
    scope = valid_manifest["tile_scope"]
    assert scope["explicit_single_tile"] is True
    assert scope["city_wide_scope"] is False
    assert scope["tile_id_confirmation"] == valid_manifest["tile_id"]


# ── Execution lock checks (unrelated files must remain untouched) ─────────────

def test_run_tile_miami_execution_lock_remains_false():
    assert RUN_TILE_MIAMI_PATH.exists(), f"Missing: {RUN_TILE_MIAMI_PATH}"
    source = RUN_TILE_MIAMI_PATH.read_text(encoding="utf-8")
    assert "REAL_DATA_EXECUTION_ENABLED: bool = False" in source
    assert "REAL_DATA_EXECUTION_ENABLED: bool = True" not in source


def test_smoke_harness_execution_lock_remains_false():
    assert SMOKE_HARNESS_PATH.exists(), f"Missing: {SMOKE_HARNESS_PATH}"
    source = SMOKE_HARNESS_PATH.read_text(encoding="utf-8")
    assert "REAL_DATA_EXECUTION_ENABLED = False" in source
    assert "REAL_DATA_EXECUTION_ENABLED = True" not in source


# ── JSON Schema validation: baseline ───────────────────────────────────────────

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_example_manifest_passes_schema(schema, valid_manifest):
    validate(instance=valid_manifest, schema=schema)


# ── Required-field rejection tests ─────────────────────────────────────────────

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_city_id(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["city_id"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_tile_id(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["tile_id"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_source_hash(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["source"]["laz"]["sha256"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_repository_commit(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["repository_commit_sha"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_glb_checksum(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["outputs"]["glb"]["sha256"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_processed_crs(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["source"]["crs_contract"]["processed_horizontal_crs"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_processed_units(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["source"]["crs_contract"]["processed_xy_units"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_building_id_namespace(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["outputs"]["building_attribution"]["building_id_namespace"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_glb_mapping_strategy(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["outputs"]["building_attribution"]["glb_mapping_strategy"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_companion_feature_table_checksum(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["outputs"]["companion_feature_table"]["sha256"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_companion_feature_table_reference(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["outputs"]["companion_feature_table"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


# ── Mutable naming / wildcard / scope rejection tests ──────────────────────────

@pytest.mark.parametrize(
    "mutable_uri",
    [
        "synthetic/runs/demo/tiles/TILE/latest.glb",
        "synthetic/runs/demo/tiles/TILE/current.glb",
        "synthetic/runs/demo/tiles/TILE/final-final.glb",
        "synthetic/runs/demo/tiles/TILE/LATEST.glb",
    ],
)
@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_mutable_glb_asset_names(schema, valid_manifest, mutable_uri):
    bad = copy.deepcopy(valid_manifest)
    bad["outputs"]["glb"]["uri"] = mutable_uri
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_mutable_companion_feature_table_name(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["outputs"]["companion_feature_table"]["uri"] = "synthetic/runs/demo/tiles/TILE/current.geojson"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_wildcard_tile_id(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["tile_id"] = "*"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_array_tile_id(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["tile_id"] = ["TILE_A", "TILE_B"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_city_wide_scope(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["tile_scope"] = dict(valid_manifest["tile_scope"])
    bad["tile_scope"]["city_wide_scope"] = True
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_accepts_exact_single_tile_scope(schema, valid_manifest):
    """A well-formed single-tile scope (the golden path) must validate cleanly."""
    validate(instance=valid_manifest, schema=schema)
    scope = valid_manifest["tile_scope"]
    assert scope["explicit_single_tile"] is True
    assert scope["city_wide_scope"] is False


# ── Publication gate rejection tests ───────────────────────────────────────────

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_production_allowed_with_unresolved_license(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["publication"]["license_status"] = "needs_review"
    bad["publication"]["production_allowed"] = True
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_production_allowed_while_candidate_even_with_confirmed_license(schema, valid_manifest):
    """production_allowed must stay false while contract_status is CANDIDATE, even if license is confirmed."""
    bad = copy.deepcopy(valid_manifest)
    bad["publication"]["license_status"] = "confirmed"
    bad["publication"]["license_evidence_refs"] = [{"registry": "license_registry", "ref_id": "demo_license_v1"}]
    bad["publication"]["production_allowed"] = True
    bad["publication"]["engineering_valid"] = True
    bad["publication"]["viewer_valid"] = True
    assert bad["contract_status"] == "CANDIDATE"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_auto_publish_enabled(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["publication"]["auto_publish_enabled"] = True
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_confirmed_license_without_evidence(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["publication"]["license_status"] = "confirmed"
    bad["publication"]["license_evidence_refs"] = []
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_manual_approval_without_approver(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["publication"]["manual_publication_approved"] = True
    # manual_publication_approved_by/at remain null
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_commercial_use_without_publication_allowed(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["publication"]["commercial_use_allowed"] = True
    bad["publication"]["publication_allowed"] = False
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


# ── Structured knowledge / confidence evidence model tests ────────────────────

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_measured_status_without_evidence(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["source"]["laz"]["knowledge"]["evidence_refs"] = []
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_measured_status_with_null_method_ref(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["source"]["laz"]["knowledge"]["method_ref"] = None
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_accepts_unknown_status_without_evidence(schema, valid_manifest):
    """knowledge_status='unknown' may legitimately omit method_ref/evidence_refs."""
    good = copy.deepcopy(valid_manifest)
    good["source"]["laz"]["knowledge"] = {
        "knowledge_status": "unknown",
        "method_ref": None,
        "evidence_refs": [],
        "confidence": {
            "scoring_model_ref": None,
            "score": None,
            "evidence_inputs": [],
            "calibration_status": "not_applicable",
            "limitations": ["Provenance not yet established for this synthetic case."],
        },
    }
    validate(instance=good, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_invalid_knowledge_status_value(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["source"]["laz"]["knowledge"]["knowledge_status"] = "verified_by_vibes"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_bare_confidence_score_without_model(schema, valid_manifest):
    """A numeric confidence score must never appear without a named scoring model (no arbitrary percentages)."""
    bad = copy.deepcopy(valid_manifest)
    bad["source"]["laz"]["knowledge"]["confidence"]["scoring_model_ref"] = None
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_bare_confidence_score_without_evidence_inputs(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["source"]["laz"]["knowledge"]["confidence"]["evidence_inputs"] = []
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_lidar_only_with_footprint_contribution(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["source"]["data_sources"]["lidar_only"] = True
    # footprints_contributed/footprint_source_ref left as the example's non-null contribution
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_footprint_contribution_without_source_ref(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    bad["source"]["data_sources"]["footprint_source_ref"] = None
    # footprints_contributed remains True from the example
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_registries(schema, valid_manifest):
    bad = copy.deepcopy(valid_manifest)
    del bad["registries"]["license_registry"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)
