"""
Tests for schemas/gcp_batch_tile_task.schema.json and associated config files.

These tests run without PDAL, without /mnt/t7 access, and without any real Miami data.
They validate:
  - The schema is valid JSON and loadable
  - The example manifest validates against the schema
  - The schema correctly rejects invalid manifests
  - The schema rejects output_prefix values that lack a distinct run-id segment between
    'runs/' and 'tiles/', which would otherwise let two different runs of the same tile
    collide on the same output path
  - The example manifest and batch job template do not contain real Miami tile IDs or real execution authorization
  - The existing execution locks in run_tile_miami.py and miami_metric_smoke_harness.py remain False
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "gcp_batch_tile_task.schema.json"
EXAMPLE_MANIFEST_PATH = REPO_ROOT / "configs" / "cloud" / "gcp_batch_tile_task.example.json"
BATCH_JOB_TEMPLATE_PATH = REPO_ROOT / "configs" / "cloud" / "gcp_batch_job_template.json"
RUN_TILE_MIAMI_PATH = REPO_ROOT / "scripts" / "miami" / "run_tile_miami.py"
SMOKE_HARNESS_PATH = REPO_ROOT / "scripts" / "diagnostics" / "miami_metric_smoke_harness.py"

_REAL_TILE_IDS = ("318155", "318455")


try:
    import jsonschema
    from jsonschema import validate, ValidationError, Draft7Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


@pytest.fixture(scope="module")
def schema():
    assert SCHEMA_PATH.exists(), f"Schema file not found: {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def valid_manifest():
    """A minimal valid NO_OP manifest for schema testing."""
    return {
        "schema_version": "glytchos.gcp_batch_tile_task.v1",
        "run_id": "test-bench-0001",
        "tile_id": "SYNTHETIC_TILE_0000",
        "tile_scope": {
            "explicit_single_tile": True,
            "tile_id_confirmation": "SYNTHETIC_TILE_0000",
            "city_wide_execution": False,
        },
        "input_object_uri": "gs://test-input-bucket/synthetic/laz/SYNTHETIC_TILE_0000/aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111.laz",
        "input_sha256": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
        "source_contract_uri": "gs://test-input-bucket/contracts/miami_laz_source_contract_v1.json",
        "source_contract_digest": "sha256:bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222",
        "repository_commit_sha": "cccc3333cccc3333cccc3333cccc3333cccc3333",
        "container_image_digest": "sha256:dddd4444dddd4444dddd4444dddd4444dddd4444dddd4444dddd4444dddd4444",
        "output_prefix": "gs://test-run-bucket/synthetic/runs/test-bench-0001/tiles/SYNTHETIC_TILE_0000/",
        "execution_mode": "NO_OP",
        "real_data_execution_enabled": False,
        "attempt_number": 1,
        "max_attempts": 2,
        "expected_processed_crs": "EPSG:32617",
        "expected_processed_units": "meters",
        "created_at": "2026-01-01T00:00:00Z",
    }


# ── File integrity ─────────────────────────────────────────────────────────────

def test_schema_file_is_valid_json():
    """Schema file must load as valid JSON."""
    assert SCHEMA_PATH.exists(), f"Missing: {SCHEMA_PATH}"
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("$id") == "glytchos.gcp_batch_tile_task.v1"
    assert data.get("$schema") == "http://json-schema.org/draft-07/schema#"


def test_example_manifest_is_valid_json():
    """Example manifest must load as valid JSON."""
    assert EXAMPLE_MANIFEST_PATH.exists(), f"Missing: {EXAMPLE_MANIFEST_PATH}"
    data = json.loads(EXAMPLE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_batch_job_template_is_valid_json():
    """Batch job template must load as valid JSON."""
    assert BATCH_JOB_TEMPLATE_PATH.exists(), f"Missing: {BATCH_JOB_TEMPLATE_PATH}"
    data = json.loads(BATCH_JOB_TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ── Example manifest safety checks ────────────────────────────────────────────

def test_example_manifest_execution_mode_is_noop():
    """Example manifest must use execution_mode = NO_OP."""
    data = json.loads(EXAMPLE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("execution_mode") == "NO_OP", (
        f"Example manifest execution_mode must be 'NO_OP', got {data.get('execution_mode')!r}"
    )


def test_example_manifest_real_data_execution_disabled():
    """Example manifest must have real_data_execution_enabled = false."""
    data = json.loads(EXAMPLE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("real_data_execution_enabled") is False, (
        "Example manifest real_data_execution_enabled must be false"
    )


def test_example_manifest_no_real_miami_tile_ids():
    """Example manifest must not contain real Miami tile IDs 318155 or 318455."""
    raw = EXAMPLE_MANIFEST_PATH.read_text(encoding="utf-8")
    for tile_id in _REAL_TILE_IDS:
        assert tile_id not in raw, (
            f"Example manifest must not contain real Miami tile ID {tile_id}"
        )


def test_example_manifest_tile_scope_single():
    """Example manifest must assert explicit_single_tile=true and city_wide_execution=false."""
    data = json.loads(EXAMPLE_MANIFEST_PATH.read_text(encoding="utf-8"))
    scope = data.get("tile_scope", {})
    assert scope.get("explicit_single_tile") is True
    assert scope.get("city_wide_execution") is False


# ── Batch job template safety checks ──────────────────────────────────────────

def test_batch_job_template_execution_mode_noop():
    """Batch job template environment must have GLYTCHDRAFT_EXECUTION_MODE = NO_OP."""
    data = json.loads(BATCH_JOB_TEMPLATE_PATH.read_text(encoding="utf-8"))
    env = (
        data.get("taskGroups", [{}])[0]
        .get("taskSpec", {})
        .get("environment", {})
        .get("variables", {})
    )
    assert env.get("GLYTCHDRAFT_EXECUTION_MODE") == "NO_OP"


def test_batch_job_template_real_data_execution_disabled():
    """Batch job template must have REAL_DATA_EXECUTION_ENABLED = 'false'."""
    data = json.loads(BATCH_JOB_TEMPLATE_PATH.read_text(encoding="utf-8"))
    env = (
        data.get("taskGroups", [{}])[0]
        .get("taskSpec", {})
        .get("environment", {})
        .get("variables", {})
    )
    assert env.get("REAL_DATA_EXECUTION_ENABLED") == "false", (
        "REAL_DATA_EXECUTION_ENABLED in batch template must be the string 'false'"
    )


def test_batch_job_template_no_real_miami_tile_ids():
    """Batch job template must not contain real Miami tile IDs 318155 or 318455."""
    raw = BATCH_JOB_TEMPLATE_PATH.read_text(encoding="utf-8")
    for tile_id in _REAL_TILE_IDS:
        assert tile_id not in raw, (
            f"Batch job template must not contain real Miami tile ID {tile_id}"
        )


def test_batch_job_template_parallelism_bounded():
    """Batch job template initial parallelism must be <= 2."""
    data = json.loads(BATCH_JOB_TEMPLATE_PATH.read_text(encoding="utf-8"))
    task_group = data.get("taskGroups", [{}])[0]
    parallelism = task_group.get("parallelism", 0)
    task_count = task_group.get("taskCount", 0)
    assert parallelism <= 2, f"Initial benchmark parallelism must be <= 2, got {parallelism}"
    assert task_count <= 2, f"Initial benchmark taskCount must be <= 2, got {task_count}"


# ── Execution lock checks ──────────────────────────────────────────────────────

def test_run_tile_miami_execution_lock_remains_false():
    """REAL_DATA_EXECUTION_ENABLED must remain False in run_tile_miami.py."""
    assert RUN_TILE_MIAMI_PATH.exists(), f"Missing: {RUN_TILE_MIAMI_PATH}"
    source = RUN_TILE_MIAMI_PATH.read_text(encoding="utf-8")
    assert "REAL_DATA_EXECUTION_ENABLED: bool = False" in source, (
        "run_tile_miami.py REAL_DATA_EXECUTION_ENABLED must remain False. "
        "Do not enable without independent review."
    )
    assert "REAL_DATA_EXECUTION_ENABLED: bool = True" not in source


def test_smoke_harness_execution_lock_remains_false():
    """REAL_DATA_EXECUTION_ENABLED must remain False in miami_metric_smoke_harness.py."""
    assert SMOKE_HARNESS_PATH.exists(), f"Missing: {SMOKE_HARNESS_PATH}"
    source = SMOKE_HARNESS_PATH.read_text(encoding="utf-8")
    assert "REAL_DATA_EXECUTION_ENABLED = False" in source, (
        "miami_metric_smoke_harness.py REAL_DATA_EXECUTION_ENABLED must remain False."
    )
    assert "REAL_DATA_EXECUTION_ENABLED = True" not in source


# ── JSON Schema validation tests (require jsonschema) ─────────────────────────

pytestmark_jsonschema = pytest.mark.skipif(
    not HAS_JSONSCHEMA, reason="jsonschema not installed"
)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_valid_manifest_passes_schema(schema, valid_manifest):
    """A well-formed NO_OP manifest must validate against the schema."""
    validate(instance=valid_manifest, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_example_manifest_passes_schema(schema):
    """The example manifest must validate against the schema after replacing placeholder values with valid-format synthetics."""
    import re
    raw = EXAMPLE_MANIFEST_PATH.read_text(encoding="utf-8")
    # Replace placeholder bucket names with valid GCS bucket name syntax
    raw = re.sub(r"<PLACEHOLDER_[A-Z0-9_]+>", "placeholder-bucket", raw)
    data = json.loads(raw)
    # Remove _NOTICE and other _ keys (not in schema)
    data_clean = {k: v for k, v in data.items() if not k.startswith("_")}
    # Replace zero-only placeholder hashes with valid-format hex strings
    data_clean["input_sha256"] = "a" * 64
    data_clean["source_contract_digest"] = "sha256:" + "b" * 64
    data_clean["repository_commit_sha"] = "c" * 40
    data_clean["container_image_digest"] = "sha256:" + "d" * 64
    # Fix input_object_uri to match .laz pattern and use a valid bucket
    data_clean["input_object_uri"] = "gs://placeholder-bucket/synthetic/laz/SYNTHETIC_TILE_0000/" + "a" * 64 + ".laz"
    # Fix output_prefix to match required pattern
    data_clean["output_prefix"] = "gs://placeholder-bucket/synthetic/runs/noop-bench-2026-01-01-001/tiles/SYNTHETIC_TILE_0000/"
    data_clean["source_contract_uri"] = "gs://placeholder-bucket/contracts/miami_laz_source_contract_v1.json"
    validate(instance=data_clean, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_array_tile_id(schema, valid_manifest):
    """tile_id must be a string; an array value must be rejected."""
    bad = dict(valid_manifest)
    bad["tile_id"] = ["TILE_A", "TILE_B"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_input_sha256(schema, valid_manifest):
    """Missing input_sha256 must cause schema validation to fail."""
    bad = dict(valid_manifest)
    del bad["input_sha256"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_container_image_digest(schema, valid_manifest):
    """Missing container_image_digest must cause schema validation to fail."""
    bad = dict(valid_manifest)
    del bad["container_image_digest"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_mutable_tag_image_identity(schema, valid_manifest):
    """container_image_digest without sha256: prefix must be rejected."""
    bad = dict(valid_manifest)
    # A mutable tag alone (no digest) must be rejected
    bad["container_image_digest"] = "us-docker.pkg.dev/myproject/repo/image:latest"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_bucket_root_output_prefix(schema, valid_manifest):
    """output_prefix as a bucket root without /tiles/<tile-id>/ must be rejected."""
    bad = dict(valid_manifest)
    bad["output_prefix"] = "gs://my-run-bucket/"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_output_prefix_with_no_run_segment_before_tiles(schema, valid_manifest):
    """output_prefix with 'runs/' immediately followed by 'tiles/' (no run-id segment) must be rejected.

    Without a distinct run segment, two different runs of the same tile would
    collide on the identical output_prefix.
    """
    bad = dict(valid_manifest)
    bad["output_prefix"] = "gs://example-bucket/miami/runs/tiles/synthetic-tile/"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_output_prefix_missing_runs_segment_entirely(schema, valid_manifest):
    """output_prefix that omits the 'runs/<run-id>/' path component entirely must be rejected."""
    bad = dict(valid_manifest)
    bad["output_prefix"] = "gs://example-bucket/miami/tiles/synthetic-tile/"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_output_prefix_with_shared_unscoped_prefix(schema, valid_manifest):
    """output_prefix under a shared, non-run-scoped path must be rejected."""
    bad = dict(valid_manifest)
    bad["output_prefix"] = "gs://example-bucket/shared/tiles/synthetic-tile/"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_accepts_output_prefix_with_distinct_run_segment(schema, valid_manifest):
    """output_prefix with a distinct, non-empty run segment between 'runs/' and 'tiles/' must validate."""
    good = dict(valid_manifest)
    good["output_prefix"] = "gs://test-run-bucket/synthetic/runs/test-bench-0001/tiles/SYNTHETIC_TILE_0000/"
    validate(instance=good, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_real_data_enabled_in_noop_mode(schema, valid_manifest):
    """In NO_OP mode, real_data_execution_enabled=true must be rejected."""
    bad = dict(valid_manifest)
    bad["execution_mode"] = "NO_OP"
    bad["real_data_execution_enabled"] = True
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_real_data_enabled_in_dry_run_mode(schema, valid_manifest):
    """In DRY_RUN mode, real_data_execution_enabled=true must be rejected."""
    bad = dict(valid_manifest)
    bad["execution_mode"] = "DRY_RUN"
    bad["real_data_execution_enabled"] = True
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_run_id(schema, valid_manifest):
    """Missing run_id must cause schema validation to fail."""
    bad = dict(valid_manifest)
    del bad["run_id"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_excessive_max_attempts(schema, valid_manifest):
    """max_attempts > 3 must be rejected."""
    bad = dict(valid_manifest)
    bad["max_attempts"] = 10
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_source_contract_digest(schema, valid_manifest):
    """Missing source_contract_digest must cause schema validation to fail."""
    bad = dict(valid_manifest)
    del bad["source_contract_digest"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_missing_repository_commit_sha(schema, valid_manifest):
    """Missing repository_commit_sha must cause schema validation to fail."""
    bad = dict(valid_manifest)
    del bad["repository_commit_sha"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_invalid_execution_mode(schema, valid_manifest):
    """An unlisted execution_mode must be rejected."""
    bad = dict(valid_manifest)
    bad["execution_mode"] = "FULL_CITY"
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_rejects_city_wide_execution_in_tile_scope(schema, valid_manifest):
    """tile_scope.city_wide_execution=true must be rejected."""
    bad = dict(valid_manifest)
    bad["tile_scope"] = dict(valid_manifest["tile_scope"])
    bad["tile_scope"]["city_wide_execution"] = True
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)
