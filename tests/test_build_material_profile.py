from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "materials" / "build_material_profile.py"
SCHEMAS = REPO_ROOT / "schemas"

SPEC = importlib.util.spec_from_file_location("build_material_profile", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def clue(
    clue_id: str,
    building_id: str,
    surface_type: str,
    observation_type: str,
    value: object,
    *,
    source_type: str = "municipal_record",
    confidence: float = 0.9,
    provenance_status: str = "record_derived",
    unit: str | None = None,
) -> dict[str, object]:
    return {
        "clue_id": clue_id,
        "building_id": building_id,
        "surface_type": surface_type,
        "observation_type": observation_type,
        "value": value,
        "unit": unit,
        "source_type": source_type,
        "source_reference": f"fixture://{clue_id}",
        "observed_at": None,
        "license": "synthetic-test-data",
        "confidence": confidence,
        "spatial_resolution": None,
        "quality_flags": [],
        "provenance_status": provenance_status,
    }


def top(profile: dict, surface: str) -> dict:
    return profile[surface]["ranked_candidates"][0]


def building_evidence(building_id: str, **fields: object) -> dict[str, object]:
    record: dict[str, object] = {"building_id": building_id, **fields}
    if fields:
        record["metadata_provenance"] = {
            "source_type": "building_inventory",
            "source_reference": f"fixture://metadata/{building_id}",
            "license": "synthetic-test-data",
            "confidence": 0.8,
            "provenance_status": "record_derived",
        }
    return record


def test_strong_municipal_record_identifies_brick():
    profile = MODULE.build_profiles(
        [{"building_id": "b1"}],
        [clue("brick-record", "b1", "envelope", "envelope_material", "brick")],
    )[0]

    candidate = top(profile, "exterior_envelope")
    assert candidate["material_class"] == "brick"
    assert candidate["provenance_status"] == "record_derived"
    assert candidate["confidence"] >= 0.8
    assert candidate["evidence_references"] == ["brick-record"]
    assert "generic_masonry" in candidate["alternatives"]
    assert profile["evidence_provenance"] == [{
        "evidence_id": "brick-record",
        "source_type": "municipal_record",
        "source_reference": "fixture://brick-record",
        "license": "synthetic-test-data",
        "confidence": 0.9,
        "provenance_status": "record_derived",
        "quality_flags": [],
    }]


def test_multiple_weak_clues_suggest_stucco_without_claiming_truth():
    clues = [
        clue(
            "finish", "b2", "envelope", "surface_finish", "smooth finish",
            source_type="street_scan", confidence=0.65, provenance_status="inferred",
        ),
        clue(
            "color", "b2", "envelope", "aerial_color_character", "light neutral",
            source_type="aerial_imagery", confidence=0.6, provenance_status="inferred",
        ),
    ]
    profile = MODULE.build_profiles(
        [building_evidence("b2", building_use="residential", floors_est=3)],
        clues,
    )[0]

    candidate = top(profile, "exterior_envelope")
    assert candidate["material_class"] == "stucco"
    assert candidate["provenance_status"] == "inferred"
    assert 0 < candidate["confidence"] < 0.9
    assert {"finish", "color"}.issubset(candidate["evidence_references"])
    assert "painted_concrete" in candidate["alternatives"]


def test_conflicting_evidence_preserves_ranked_alternatives():
    clues = [
        clue("brick-a", "b3", "envelope", "material", "brick", confidence=0.85),
        clue(
            "stucco-b", "b3", "envelope", "material", "stucco",
            source_type="street_scan", confidence=0.8, provenance_status="observed",
        ),
    ]
    profile = MODULE.build_profiles([{"building_id": "b3"}], clues)[0]
    candidates = profile["exterior_envelope"]["ranked_candidates"]
    classes = [candidate["material_class"] for candidate in candidates]

    assert "brick" in classes
    assert "stucco" in classes
    brick = next(candidate for candidate in candidates if candidate["material_class"] == "brick")
    stucco = next(candidate for candidate in candidates if candidate["material_class"] == "stucco")
    assert "stucco" in brick["alternatives"]
    assert "brick" in stucco["alternatives"]
    assert brick["evidence_references"] == ["brick-a"]
    assert stucco["evidence_references"] == ["stucco-b"]


def test_missing_evidence_produces_unknown_for_every_surface():
    unusable_clues = [
        clue(
            "unknown-finish", "empty", "envelope", "surface_finish", "smooth",
            source_type="street_scan", confidence=1.0, provenance_status="unknown",
        ),
        clue(
            "unknown-ratio", "empty", "glazing", "glazing_ratio", 0.9,
            source_type="aerial_imagery", confidence=1.0, provenance_status="unknown",
        ),
    ]
    profile = MODULE.build_profiles([{"building_id": "empty"}], unusable_clues)[0]

    assert top(profile, "exterior_envelope")["material_class"] == "unknown"
    assert top(profile, "roof")["material_class"] == "unknown"
    assert top(profile, "glazing_character")["material_class"] == "unknown"
    assert top(profile, "roof")["provenance_status"] == "unknown"
    assert profile["safeguards"] == {
        "visual_interpretation_only": True,
        "surveyed_truth": False,
    }
    assert {item["evidence_id"] for item in profile["evidence_provenance"]} == {
        "unknown-finish", "unknown-ratio",
    }


def test_flat_high_rise_with_supporting_clue_infers_membrane():
    building_metadata = [building_evidence("tower", height_m=48, floors_est=14)]
    clues = [
        clue(
            "flat-shape", "tower", "roof", "roof_geometry_class", "flat",
            source_type="derived_geometry", confidence=0.9, provenance_status="inferred",
        ),
        clue(
            "roof-appearance", "tower", "roof", "roof_surface_character",
            "uniform low texture", source_type="aerial_imagery",
            confidence=0.7, provenance_status="inferred",
        ),
    ]
    profile = MODULE.build_profiles(building_metadata, clues)[0]
    candidate = top(profile, "roof")

    assert candidate["material_class"] == "membrane"
    assert candidate["provenance_status"] == "inferred"
    assert 0 < candidate["confidence"] <= 0.3
    assert {"flat-shape", "roof-appearance"}.issubset(candidate["evidence_references"])
    assert {"gravel", "concrete"}.issubset(candidate["alternatives"])


def test_pitched_geometry_without_material_evidence_remains_unknown():
    profile = MODULE.build_profiles(
        [building_evidence("pitched", roof_geometry_class="pitched", floors_est=2)],
        [],
    )[0]

    assert top(profile, "roof")["material_class"] == "unknown"
    assert top(profile, "roof")["evidence_references"] == []
    flat_profile = MODULE.build_profiles(
        [building_evidence("flat-form-only", roof_geometry_class="flat", height_m=60, floors_est=18)],
        [],
    )[0]
    assert top(flat_profile, "roof")["material_class"] == "unknown"


def test_provenance_preserved_for_observed_clue():
    profile = MODULE.build_profiles(
        [{"building_id": "observed"}],
        [
            clue(
                "scan-1", "observed", "envelope", "material", "stone",
                source_type="street_scan", confidence=1.0, provenance_status="observed",
            )
        ],
    )[0]
    candidate = top(profile, "exterior_envelope")

    assert candidate["provenance_status"] == "observed"
    assert candidate["evidence_references"] == ["scan-1"]
    assert candidate["confidence"] <= 0.98

    inferred_record = MODULE.build_profiles(
        [{"building_id": "record-inference"}],
        [
            clue(
                "record-guess", "record-inference", "envelope", "material", "brick",
                source_type="municipal_record", confidence=1.0, provenance_status="inferred",
            )
        ],
    )[0]
    assert top(inferred_record, "exterior_envelope")["provenance_status"] == "inferred"
    assert top(inferred_record, "exterior_envelope")["confidence"] <= 0.65

    mixed = MODULE.build_profiles(
        [{"building_id": "mixed-status"}],
        [
            clue(
                "observed-weak", "mixed-status", "envelope", "material", "stone",
                source_type="street_scan", confidence=0.2, provenance_status="observed",
            ),
            clue(
                "inferred-strong", "mixed-status", "envelope", "material", "stone",
                source_type="aerial_imagery", confidence=1.0, provenance_status="inferred",
            ),
        ],
    )[0]
    assert top(mixed, "exterior_envelope")["provenance_status"] == "inferred"


def test_all_inferred_candidates_have_confidence_below_one():
    profile = MODULE.build_profiles(
        [building_evidence("limits", height_m=100, floors_est=30)],
        [
            clue(
                "flat-1", "limits", "roof", "roof_geometry", "flat",
                source_type="derived_geometry", confidence=1.0, provenance_status="inferred",
            ),
            clue(
                "flat-2", "limits", "roof", "roof_geometry", "flat",
                source_type="lidar", confidence=1.0, provenance_status="inferred",
            ),
            clue(
                "surface-1", "limits", "roof", "roof_surface_character", "continuous",
                source_type="aerial_imagery", confidence=1.0, provenance_status="inferred",
            ),
        ],
    )[0]

    for surface in ("exterior_envelope", "roof", "glazing_character"):
        for candidate in profile[surface]["ranked_candidates"]:
            if candidate["provenance_status"] == "inferred":
                assert candidate["confidence"] < 1.0
            catalog_ids = {item["evidence_id"] for item in profile["evidence_provenance"]}
            assert set(candidate["evidence_references"]).issubset(catalog_ids)


def test_deterministic_output_independent_of_input_order():
    metadata = [
        building_evidence("z", height_m=45, roof_geometry_class="flat"),
        {"building_id": "a"},
    ]
    clues = [
        clue("z-roof", "z", "roof", "roof_geometry", "flat", source_type="derived_geometry",
             provenance_status="inferred"),
        clue("a-wall", "a", "envelope", "material", "wood"),
    ]

    first = MODULE.build_profiles(metadata, clues)
    second = MODULE.build_profiles(list(reversed(metadata)), list(reversed(clues)))

    assert first == second
    assert [profile["building_id"] for profile in first] == ["a", "z"]


def test_schemas_validate_fixtures_and_generated_profile():
    material_clue_schema = json.loads((SCHEMAS / "material_clue.schema.json").read_text())
    metadata_schema = json.loads((SCHEMAS / "material_building_evidence.schema.json").read_text())
    profile_schema = json.loads((SCHEMAS / "procedural_material_profile.schema.json").read_text())
    fixture = clue("valid", "schema", "glazing", "glazing_ratio", 0.7)
    jsonschema.Draft7Validator(material_clue_schema).validate(fixture)
    missing_provenance_errors = list(
        jsonschema.Draft7Validator(metadata_schema).iter_errors(
            {"building_id": "unsafe", "height_m": 20},
        )
    )
    assert missing_provenance_errors

    profile = MODULE.build_profiles([{"building_id": "schema"}], [fixture])[0]
    output = {
        "schema_version": "glytchos.procedural_material_profile.v1",
        "profiles": [profile],
    }
    jsonschema.Draft7Validator(profile_schema).validate(output)


def test_cli_validates_inputs_and_writes_schema_valid_output(tmp_path: Path):
    metadata_path = tmp_path / "metadata.json"
    clues_path = tmp_path / "clues.json"
    output_path = tmp_path / "profiles.json"
    metadata_path.write_text(json.dumps({"buildings": [{"building_id": "cli"}]}))
    clues_path.write_text(json.dumps({"clues": [clue("cli-brick", "cli", "envelope", "material", "brick")]}))

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--building-metadata", str(metadata_path),
            "--clues", str(clues_path),
            "--output", str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(output_path.read_text())
    assert output["profiles"][0]["building_id"] == "cli"
    assert top(output["profiles"][0], "exterior_envelope")["material_class"] == "brick"
    profile_schema = json.loads((SCHEMAS / "procedural_material_profile.schema.json").read_text())
    jsonschema.Draft7Validator(profile_schema).validate(output)


def test_cli_rejects_invalid_clue(tmp_path: Path):
    metadata_path = tmp_path / "metadata.json"
    clues_path = tmp_path / "clues.json"
    output_path = tmp_path / "profiles.json"
    metadata_path.write_text(json.dumps([{"building_id": "bad"}]))
    bad_clue = clue("bad-confidence", "bad", "envelope", "material", "brick")
    bad_clue["confidence"] = 2.0
    clues_path.write_text(json.dumps([bad_clue]))

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--building-metadata", str(metadata_path),
            "--clues", str(clues_path),
            "--output", str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "validation" in result.stderr
    assert not output_path.exists()


def test_new_system_files_contain_no_city_specific_names_or_paths():
    paths = [
        SCHEMAS / "material_clue.schema.json",
        SCHEMAS / "material_building_evidence.schema.json",
        SCHEMAS / "procedural_material_profile.schema.json",
        SCRIPT,
        REPO_ROOT / "docs" / "MATERIAL_CLUE_SYSTEM.md",
    ]
    forbidden = ("miami", "los angeles", "new york", "/mnt/", "c:\\")
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        assert not any(token in text for token in forbidden), path
