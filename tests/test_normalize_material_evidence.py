from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "scripts" / "materials" / "material_evidence_adapters.py"
NORMALIZER_PATH = REPO_ROOT / "scripts" / "materials" / "normalize_material_evidence.py"
PROFILE_PATH = REPO_ROOT / "scripts" / "materials" / "build_material_profile.py"
SCHEMA_PATH = REPO_ROOT / "schemas" / "material_external_evidence.schema.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ADAPTERS = load_module("material_evidence_adapters", ADAPTER_PATH)
NORMALIZER = load_module("normalize_material_evidence", NORMALIZER_PATH)
PROFILE = load_module("material_profile_for_adapter_tests", PROFILE_PATH)


def record(
    evidence_id: str,
    source_type: str,
    evidence: dict,
    *,
    building_id: str = "building-1",
    namespace: str = "open-city-footprints:v1",
    confidence: float = 1.0,
    provenance_status: str | None = None,
) -> dict:
    status = provenance_status or {
        "osm_tags": "record_derived",
        "municipal_record": "record_derived",
        "historic_inventory": "record_derived",
        "licensed_imagery": "inferred",
        "generic": "record_derived",
    }.get(source_type, "record_derived")
    return {
        "schema_version": "glytchos.material_external_evidence.v1",
        "evidence_id": evidence_id,
        "building_id": building_id,
        "building_id_namespace": namespace,
        "source_artifact_reference": f"fixture://artifact/{evidence_id}",
        "source_record_id": f"source-{evidence_id}",
        "source_digest": f"sha256:{'a' * 64}",
        "source_type": source_type,
        "source_license": "synthetic-test-license",
        "observed_at": "2026-01-02T03:04:05Z",
        "provenance_status": status,
        "confidence": confidence,
        "evidence": evidence,
    }


def normalize(records: list[dict]) -> list[dict]:
    return ADAPTERS.normalize_records(
        records,
        target_building_id="building-1",
        target_building_id_namespace="open-city-footprints:v1",
    )


def top(profile: dict, surface: str) -> dict:
    return profile[surface]["ranked_candidates"][0]


def test_direct_municipal_material_record_preserves_source_and_license():
    clues = normalize([
        record("municipal-brick", "municipal_record", {
            "documented_construction_material": "brick",
        }),
    ])

    assert len(clues) == 1
    clue = clues[0]
    assert clue["value"] == "brick"
    assert clue["source_type"] == "municipal_record"
    assert clue["provenance_status"] == "record_derived"
    assert clue["confidence"] == 0.9
    assert clue["license"] == "synthetic-test-license"
    assert "source_digest=sha256:" in clue["source_reference"]
    assert any(flag.startswith("source_digest:") for flag in clue["quality_flags"])


def test_osm_material_tag_is_conservative_record_derived():
    clue = normalize([
        record("osm-brick", "osm_tags", {"tags": {"building:material": "brick"}}),
    ])[0]

    assert clue["value"] == "brick"
    assert clue["source_type"] == "building_inventory"
    assert clue["provenance_status"] == "record_derived"
    assert clue["confidence"] == 0.65


def test_historic_inventory_description_and_material_remain_record_derived():
    clues = normalize([
        record("historic", "historic_inventory", {
            "documented_facade_material": "stone",
            "architectural_description": "Two-story commercial block.",
        }),
    ])

    by_observation = {clue["observation_type"]: clue for clue in clues}
    assert by_observation["envelope_material"]["value"] == "stone"
    assert by_observation["envelope_material"]["confidence"] == 0.85
    assert by_observation["architectural_description"]["provenance_status"] == "record_derived"


def test_imagery_material_probability_remains_inferred_with_model_metadata():
    clue = normalize([
        record("imagery", "licensed_imagery", {
            "material_probabilities": [{
                "surface_type": "envelope",
                "material": "brick",
                "probability": 0.92,
            }],
            "model_metadata": {
                "model_name": "synthetic-segmenter",
                "model_version": "1.2.3",
                "human_verified": True,
            },
        }),
    ])[0]

    assert clue["value"] == "brick"
    assert clue["provenance_status"] == "inferred"
    assert clue["confidence"] == 0.75
    assert "model_version:1.2.3" in clue["quality_flags"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("building_use", "residential"), ("construction_year", 1920)],
)
def test_context_alone_produces_no_exact_material_clue(field: str, value: object):
    clues = normalize([
        record(f"context-{field}", "municipal_record", {field: value}),
    ])

    assert len(clues) == 1
    assert clues[0]["observation_type"] == field
    profile = PROFILE.build_profiles([{"building_id": "building-1"}], clues)[0]
    assert top(profile, "exterior_envelope")["material_class"] == "unknown"
    assert top(profile, "roof")["material_class"] == "unknown"


def test_conflicting_material_records_remain_auditable():
    clues = normalize([
        record("brick-record", "municipal_record", {
            "documented_construction_material": "brick",
        }),
        record("stone-record", "historic_inventory", {
            "documented_facade_material": "stone",
        }),
    ])
    profile = PROFILE.build_profiles([{"building_id": "building-1"}], clues)[0]
    candidates = profile["exterior_envelope"]["ranked_candidates"]

    assert {clue["value"] for clue in clues} == {"brick", "stone"}
    assert {"brick", "stone"}.issubset({candidate["material_class"] for candidate in candidates})
    assert {item["evidence_id"] for item in profile["evidence_provenance"]} == {
        clue["clue_id"] for clue in clues
    }


def test_unsupported_source_type_fails_validation():
    bad = record("unsupported", "municipal_record", {"building_use": "office"})
    bad["source_type"] = "private_magic"

    with pytest.raises(ValueError, match="source_type|validation"):
        normalize([bad])


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("source_artifact_reference", "source_artifact_reference"),
        ("source_record_id", "source_record_id"),
        ("source_license", "source_license"),
        ("source_digest", "source_digest"),
        ("observed_at", "observed_at"),
        ("building_id_namespace", "building_id_namespace"),
    ],
)
def test_required_provenance_and_identity_fields_fail(field: str, message: str):
    bad = record("missing", "municipal_record", {"building_use": "office"})
    del bad[field]

    with pytest.raises(ValueError, match=message):
        normalize([bad])


@pytest.mark.parametrize(
    ("building_id", "namespace"),
    [
        ("other-building", "open-city-footprints:v1"),
        ("building-1", "other-namespace:v2"),
    ],
)
def test_mismatched_building_identity_fails(building_id: str, namespace: str):
    bad = record(
        "mismatch",
        "municipal_record",
        {"building_use": "office"},
        building_id=building_id,
        namespace=namespace,
    )

    with pytest.raises(ValueError, match="identity mismatch"):
        normalize([bad])


def test_cluster_id_is_explicitly_rejected():
    bad = record("cluster", "municipal_record", {"building_use": "office"})
    bad["cluster_id"] = 17

    with pytest.raises(ValueError, match="prohibited identity field.*cluster_id"):
        normalize([bad])


@pytest.mark.parametrize(
    "namespace",
    ["cid", "17", "   ", "cluster_id", "cluster_id:v1", "CID:v1"],
)
def test_unqualified_or_prohibited_namespace_is_rejected(namespace: str):
    bad = record(
        "bad-namespace",
        "municipal_record",
        {"building_use": "office"},
        namespace=namespace,
    )

    with pytest.raises(ValueError, match="building_id_namespace|namespace"):
        normalize([bad])


@pytest.mark.parametrize("namespace", ["cid", "17", "cluster_id:v1", "CID:v1"])
def test_unqualified_or_prohibited_target_namespace_is_rejected(namespace: str):
    valid = record("valid-record", "municipal_record", {"building_use": "office"})

    with pytest.raises(ValueError, match="qualified|prohibited"):
        ADAPTERS.normalize_records(
            [valid],
            target_building_id="building-1",
            target_building_id_namespace=namespace,
        )


def test_invalid_observation_timestamp_is_rejected():
    bad = record("timestamp", "municipal_record", {"building_use": "office"})
    bad["observed_at"] = "not-a-timestamp"

    with pytest.raises(ValueError, match="observed_at"):
        normalize([bad])


@pytest.mark.parametrize(
    "field",
    ["evidence_id", "building_id", "source_artifact_reference", "source_record_id", "source_license"],
)
def test_whitespace_only_required_identity_or_provenance_string_is_rejected(field: str):
    bad = record("blank", "municipal_record", {"building_use": "office"})
    bad[field] = "   "

    with pytest.raises(ValueError, match=field):
        normalize([bad])


@pytest.mark.parametrize(
    ("source_type", "evidence", "status"),
    [
        ("osm_tags", {"tags": {"name": "unmapped"}}, "record_derived"),
        ("municipal_record", {"model_metadata": {"model_name": "x", "model_version": "1"}}, "record_derived"),
        ("historic_inventory", {"building_use": "office"}, "record_derived"),
        ("licensed_imagery", {
            "model_metadata": {"model_name": "x", "model_version": "1"},
        }, "inferred"),
    ],
)
def test_records_with_no_adapter_supported_evidence_fail(
    source_type: str, evidence: dict, status: str,
):
    bad = record("no-clues", source_type, evidence, provenance_status=status)

    with pytest.raises(ValueError, match="produced no material clues"):
        normalize([bad])


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_confidence_cannot_bypass_caps(non_finite: float):
    bad = record(
        "non-finite",
        "municipal_record",
        {"documented_construction_material": "brick"},
        confidence=non_finite,
    )

    with pytest.raises(ValueError, match="non-finite"):
        normalize([bad])


def test_reordered_input_is_byte_deterministic_and_output_order_is_stable():
    records = [
        record("roof", "municipal_record", {"documented_roof_material": "tile"}),
        record("wall", "municipal_record", {"documented_construction_material": "brick"}),
        record("use", "municipal_record", {"building_use": "commercial"}),
    ]
    first = normalize(records)
    second = normalize(list(reversed(records)))

    assert first == second
    assert json.dumps({"clues": first}, indent=2, sort_keys=True) == json.dumps(
        {"clues": second}, indent=2, sort_keys=True,
    )
    keys = [
        (clue["building_id"], clue["surface_type"], clue["observation_type"], clue["clue_id"])
        for clue in first
    ]
    assert keys == sorted(keys)


def test_unknown_and_zero_confidence_clues_cannot_influence_profile():
    records = [
        record("unknown", "generic", {
            "generic_clues": [{
                "surface_type": "envelope",
                "observation_type": "envelope_material",
                "value": "brick",
                "clue_source_type": "street_scan",
                "provenance_status": "unknown",
                "confidence": 1.0,
            }],
        }, provenance_status="unknown"),
        record("zero", "generic", {
            "generic_clues": [{
                "surface_type": "roof",
                "observation_type": "roof_material",
                "value": "tile",
                "clue_source_type": "street_scan",
                "provenance_status": "inferred",
                "confidence": 0.0,
            }],
        }, confidence=0.0, provenance_status="inferred"),
    ]
    clues = normalize(records)
    profile = PROFILE.build_profiles([{"building_id": "building-1"}], clues)[0]

    assert all(clue["provenance_status"] == "unknown" for clue in clues)
    assert all(clue["confidence"] == 0 for clue in clues)
    assert top(profile, "exterior_envelope")["material_class"] == "unknown"
    assert top(profile, "roof")["material_class"] == "unknown"


def test_cli_refuses_to_overwrite_input(tmp_path: Path):
    input_path = tmp_path / "evidence.json"
    input_path.write_text(json.dumps([
        record("input", "municipal_record", {"building_use": "office"}),
    ]), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input", str(input_path),
            "--output", str(input_path),
            "--building-id", "building-1",
            "--building-id-namespace", "open-city-footprints:v1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "overwrite the input" in result.stderr


def test_cli_refuses_hard_link_alias_of_input(tmp_path: Path):
    input_path = tmp_path / "evidence.json"
    output_path = tmp_path / "hard-link.json"
    input_path.write_text(json.dumps([
        record("hard-link", "municipal_record", {"building_use": "office"}),
    ]), encoding="utf-8")
    os.link(input_path, output_path)

    result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--building-id", "building-1",
            "--building-id-namespace", "open-city-footprints:v1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "overwrite the input" in result.stderr


def test_cli_rejects_non_finite_json_number(tmp_path: Path):
    input_path = tmp_path / "evidence.json"
    output_path = tmp_path / "clues.json"
    payload = record(
        "nan",
        "municipal_record",
        {"documented_construction_material": "brick"},
    )
    input_path.write_text(
        json.dumps(payload).replace('"confidence": 1.0', '"confidence": NaN'),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--building-id", "building-1",
            "--building-id-namespace", "open-city-footprints:v1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "non-finite" in result.stderr
    assert not output_path.exists()


def test_cli_rejects_unknown_evidence_wrapper_fields(tmp_path: Path):
    input_path = tmp_path / "evidence.json"
    output_path = tmp_path / "clues.json"
    input_path.write_text(json.dumps({
        "evidence": [record("wrapper", "municipal_record", {"building_use": "office"})],
        "ignored": True,
    }), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--building-id", "building-1",
            "--building-id-namespace", "open-city-footprints:v1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "wrapper has unknown fields" in result.stderr
    assert not output_path.exists()


@pytest.mark.parametrize(
    "relative_output",
    [
        Path("configs/cities/.material-evidence-review-test.json"),
        Path("configs/other/../cities/.material-evidence-review-test.json"),
        Path("regions/.material-evidence-review-test.json"),
    ],
)
def test_cli_blocks_canonical_output_roots_by_default(
    tmp_path: Path, relative_output: Path,
):
    input_path = tmp_path / "evidence.json"
    output_path = REPO_ROOT / relative_output
    assert not output_path.exists()
    input_path.write_text(json.dumps([
        record("protected-output", "municipal_record", {"building_use": "office"}),
    ]), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--building-id", "building-1",
            "--building-id-namespace", "open-city-footprints:v1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "canonical city directory" in result.stderr
    assert not output_path.exists()


def test_atomic_write_does_not_damage_existing_output_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "clues.json"
    output.write_text("original\n", encoding="utf-8")

    def fail_replace(self: Path, target: Path):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replace failure"):
        NORMALIZER.atomic_write_json(output, {"clues": []})

    assert output.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_adapter_has_no_network_access(monkeypatch: pytest.MonkeyPatch):
    def network_forbidden(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    clues = normalize([
        record("offline", "osm_tags", {"tags": {"building:material": "wood"}}),
    ])

    source = ADAPTER_PATH.read_text(encoding="utf-8")
    assert len(clues) == 1
    assert "requests" not in source
    assert "urlopen" not in source


def test_output_is_compatible_with_build_material_profile_cli(tmp_path: Path):
    evidence_path = tmp_path / "evidence.json"
    clues_path = tmp_path / "clues.json"
    metadata_path = tmp_path / "metadata.json"
    profiles_path = tmp_path / "profiles.json"
    evidence_path.write_text(json.dumps([
        record("compatible", "municipal_record", {
            "documented_construction_material": "brick",
        }),
    ]), encoding="utf-8")
    metadata_path.write_text(json.dumps([{"building_id": "building-1"}]), encoding="utf-8")

    normalize_result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input", str(evidence_path),
            "--output", str(clues_path),
            "--building-id", "building-1",
            "--building-id-namespace", "open-city-footprints:v1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert normalize_result.returncode == 0, normalize_result.stderr

    profile_result = subprocess.run(
        [
            sys.executable,
            str(PROFILE_PATH),
            "--building-metadata", str(metadata_path),
            "--clues", str(clues_path),
            "--output", str(profiles_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert profile_result.returncode == 0, profile_result.stderr
    profile = json.loads(profiles_path.read_text(encoding="utf-8"))["profiles"][0]
    assert top(profile, "exterior_envelope")["material_class"] == "brick"


def test_external_evidence_schema_is_valid_draft_07_and_accepts_fixture():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.Draft7Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(record("schema", "municipal_record", {"building_use": "office"}))


def test_cli_requires_explicit_output_and_identity():
    result = subprocess.run(
        [sys.executable, str(NORMALIZER_PATH), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--output" in result.stdout
    assert "--building-id-namespace" in result.stdout


def test_new_files_are_city_agnostic_and_code_has_no_prohibited_proxy_fields():
    paths = [
        ADAPTER_PATH,
        NORMALIZER_PATH,
        SCHEMA_PATH,
        REPO_ROOT / "docs" / "MATERIAL_EVIDENCE_ADAPTERS.md",
    ]
    city_or_path_tokens = (
        "miami",
        "new orleans",
        "los angeles",
        "/mnt/",
        "c:\\",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        assert not any(token in text for token in city_or_path_tokens), path

    implementation = (
        ADAPTER_PATH.read_text(encoding="utf-8")
        + SCHEMA_PATH.read_text(encoding="utf-8")
    ).lower()
    for field in ("property_value", "neighborhood_prestige", "household_income"):
        assert field not in implementation
