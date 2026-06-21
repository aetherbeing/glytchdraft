from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FACADE_DIR = REPO_ROOT / "scripts" / "facades"
sys.path.insert(0, str(FACADE_DIR))
facades = importlib.import_module("build_facade_recipe")
grammar = importlib.import_module("grammar_provider")


def source(status: str = "record_derived", confidence: float = 0.9) -> dict:
    return {
        "source_type": "building_inventory",
        "source_reference": "fixture://inventory",
        "license": "CC0-1.0",
        "source_timestamp": "2025-01-02T00:00:00Z",
        "attribution_requirements": "Retain source name.",
        "confidence": confidence,
        "provenance_status": status,
        "quality_flags": [],
    }


def building(building_id: str, **fields: object) -> dict:
    return {
        "building_id": building_id,
        "building_id_namespace": grammar.ID_NAMESPACE,
        "tile_id": "tile-a",
        "named_building_node": f"bld_tile-a_{building_id}",
        "source": {"footprint_id": f"fp-{building_id}", "source_footprint_id": f"source-{building_id}"},
        **fields,
    }


def metadata(*records: dict) -> dict:
    return {
        "schema_version": "glytchdraft.facade_building_input.v1",
        "building_id_namespace": grammar.ID_NAMESPACE,
        "source_pipeline_commit": "deadbeef",
        "buildings": list(records),
    }


def evidence(building_id: str, evidence_id: str, evidence_type: str, value: object, **overrides: object) -> dict:
    item = {
        "evidence_id": evidence_id,
        "building_id": building_id,
        "building_id_namespace": grammar.ID_NAMESPACE,
        "facade_edge_id": None,
        "evidence_type": evidence_type,
        "value": value,
        "unit": None,
        "source_type": "building_inventory",
        "source_reference": f"fixture://{evidence_id}",
        "license": "CC0-1.0",
        "source_timestamp": "2025-01-02T00:00:00Z",
        "attribution_requirements": "Retain fixture attribution.",
        "confidence": 0.9,
        "provenance_status": "record_derived",
        "quality_flags": [],
    }
    item.update(overrides)
    return item


def evidence_payload(*records: dict) -> dict:
    return {
        "schema_version": facades.EVIDENCE_VERSION,
        "building_id_namespace": grammar.ID_NAMESPACE,
        "evidence": list(records),
    }


def materials(*profiles: dict) -> dict:
    return {"schema_version": facades.MATERIAL_VERSION, "profiles": list(profiles)}


def run(records: list[dict], clues: list[dict], material_profiles: list[dict] | None = None) -> dict:
    return facades.build_output(
        metadata(*records),
        materials(*(material_profiles or [])),
        [],
        evidence_payload(*clues),
        "reference",
    )


def recipe(output: dict, building_id: str = "b1") -> dict:
    return next(item for item in output["recipes"] if item["building_id"] == building_id)


def test_no_evidence_produces_unknown_recipe():
    result = recipe(run([building("b1")], []))
    assert result["typology"]["candidate"] == "unknown"
    assert result["typology"]["provenance_status"] == "procedural"
    assert result["typology"]["applicability_score"] == 0
    assert "confidence" not in result["typology"]
    assert result["materials"]["status"] == "missing"
    assert result["roof"]["status"] == "missing"


@pytest.mark.parametrize(
    ("use", "expected"),
    [
        ("warehouse", "warehouse_bays"),
        ("parking structure", "parking_structure_openings"),
    ],
)
def test_explicit_use_rules(use: str, expected: str):
    result = recipe(run([building("b1")], [evidence("b1", "use", "building_use", use)]))
    assert result["typology"]["candidate"] == expected
    assert result["typology"]["provenance_status"] == "procedural"
    assert 0 < result["typology"]["applicability_score"] < 1.0


def test_explicit_hotel_with_floor_count():
    result = recipe(run(
        [building("b1", floor_count=12)],
        [evidence("b1", "hotel-use", "building_use", "hotel")],
    ))
    assert result["typology"]["candidate"] == "hotel_bay_rhythm"
    assert result["vertical_organization"]["estimated_floor_count"]["value"] == 12


def test_mixed_use_podium_tower():
    result = recipe(run(
        [building("b1", podium_levels=2, floor_count=18)],
        [evidence("b1", "mixed-use", "building_use", "mixed use")],
    ))
    assert result["typology"]["candidate"] == "mixed_use_podium_tower"
    assert "retail_podium" in result["typology"]["alternatives"]


def test_office_weak_versus_strong_glazing():
    weak = recipe(run(
        [building("b1")],
        [
            evidence("b1", "office", "building_use", "office"),
            evidence("b1", "weak-glazing", "glazing_ratio", 0.8, confidence=0.4),
        ],
    ))
    strong = recipe(run(
        [building("b1")],
        [
            evidence("b1", "office", "building_use", "office"),
            evidence("b1", "strong-glazing", "glazing_ratio", 0.8, confidence=0.9),
        ],
    ))
    assert weak["typology"]["candidate"] == "office_grid"
    assert strong["typology"]["candidate"] == "curtain_wall_candidate"


def test_conflicting_use_records_are_conservative():
    result = recipe(run(
        [building("b1")],
        [
            evidence("b1", "hotel", "building_use", "hotel"),
            evidence("b1", "warehouse", "building_use", "warehouse"),
        ],
    ))
    assert result["typology"]["candidate"] == "unknown"
    assert {"hotel_bay_rhythm", "warehouse_bays"}.issubset(result["typology"]["alternatives"])


def test_missing_material_and_roof_evidence_are_explicit():
    result = recipe(run([building("b1")], [evidence("b1", "use", "building_use", "warehouse")]))
    assert result["materials"]["source_digest"] is None
    assert result["roof"]["source_digest"] is None


def test_mismatched_building_ids_fail():
    with pytest.raises(ValueError, match="do not exist"):
        facades.build_output(
            metadata(building("b1")), materials(), [],
            evidence_payload(evidence("other", "bad", "building_use", "hotel")),
            "reference",
        )


def test_mismatched_sidecar_ids_fail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        facades,
        "material_records",
        lambda payload: [{"building_id": "other"}],
    )
    with pytest.raises(ValueError, match="do not exist"):
        facades.build_output(
            metadata(building("b1")),
            {},
            [],
            evidence_payload(),
            "reference",
        )


def test_mismatched_building_namespace_fails():
    payload = metadata(building("b1"))
    payload["building_id_namespace"] = "phase03.cluster"
    with pytest.raises(ValueError, match="namespace"):
        facades.build_output(payload, materials(), [], evidence_payload(), "reference")


def test_mismatched_evidence_namespace_fails():
    clue = evidence("b1", "bad-namespace", "building_use", "hotel")
    clue["building_id_namespace"] = "phase03.cluster"
    with pytest.raises(ValueError, match="validation|namespace"):
        facades.build_output(
            metadata(building("b1")),
            materials(),
            [],
            evidence_payload(clue),
            "reference",
        )


def test_per_building_namespace_is_required():
    record = building("b1")
    del record["building_id_namespace"]
    with pytest.raises(ValueError, match="has no building-ID namespace"):
        facades.build_output(metadata(record), materials(), [], evidence_payload(), "reference")


@pytest.mark.parametrize("building_id", ["17", "cluster_17", "phase03:17"])
def test_phase03_cluster_ids_are_rejected(building_id: str):
    with pytest.raises(ValueError, match="Phase 03 cluster ID"):
        facades.build_output(
            metadata(building(building_id)),
            materials(),
            [],
            evidence_payload(),
            "reference",
        )


@pytest.mark.parametrize(
    ("payload_name", "payload", "match"),
    [
        ("metadata", {"schema_version": "unsupported", "buildings": []}, "unsupported building metadata"),
        ("materials", {"schema_version": "unsupported", "profiles": []}, "unsupported material"),
        ("roof", [{"schema_version": "unsupported"}], "unsupported roof"),
    ],
)
def test_unsupported_schema_versions_fail(payload_name: str, payload: object, match: str):
    values = {
        "metadata": metadata(building("b1")),
        "materials": materials(),
        "roof": [],
        "facade": evidence_payload(),
    }
    values[payload_name] = payload
    with pytest.raises(ValueError, match=match):
        facades.build_output(values["metadata"], values["materials"], values["roof"], values["facade"], "reference")


def test_provenance_license_timestamp_and_attribution_are_preserved():
    clue = evidence("b1", "licensed-use", "building_use", "warehouse")
    result = recipe(run([building("b1")], [clue]))
    assert result["evidence_catalog"] == [clue]
    assert result["source_ids"] == {
        "footprint_id": "fp-b1",
        "source_footprint_id": "source-b1",
    }
    assert result["source_pipeline_commit"] == "deadbeef"
    assert len(result["source_metadata_digest"]) == 64
    assert len(result["source_facade_evidence_digest"]) == 64


def test_deterministic_repeated_and_reordered_input():
    buildings = [
        building("z"),
        building(
            "a",
            floor_count=7,
            street_facing_edges=[
                {"facade_edge_id": "west", "frontage_length_m": 12},
                {"facade_edge_id": "east", "frontage_length_m": 18},
            ],
        ),
    ]
    clues = [
        evidence("z", "z-use", "building_use", "warehouse"),
        evidence("a", "a-use", "building_use", "hotel"),
    ]
    first = run(buildings, clues)
    reordered_buildings = list(reversed(buildings))
    reordered_buildings[0] = {
        **reordered_buildings[0],
        "street_facing_edges": list(
            reversed(reordered_buildings[0]["street_facing_edges"])
        ),
    }
    second = run(reordered_buildings, list(reversed(clues)))
    assert first == second
    assert [item["building_id"] for item in first["recipes"]] == ["a", "z"]


def test_duplicate_evidence_and_edge_ids_fail_explicitly():
    duplicate_clues = [
        evidence("b1", "same", "building_use", "hotel"),
        evidence("b1", "same", "building_use", "office"),
    ]
    with pytest.raises(ValueError, match="duplicate facade evidence_id"):
        run([building("b1")], duplicate_clues)

    record = building(
        "b1",
        street_facing_edges=[
            {"facade_edge_id": "primary", "frontage_length_m": 10},
            {"facade_edge_id": "primary", "frontage_length_m": 12},
        ],
    )
    with pytest.raises(ValueError, match="duplicate facade_edge_id"):
        run([record], [])


def test_all_procedural_values_are_labeled_procedural():
    result = recipe(run([building("b1", floor_count=8)], [evidence("b1", "hotel", "building_use", "hotel")]))

    def walk(value: object):
        if isinstance(value, dict):
            if "applicability_score" in value:
                assert value["provenance_status"] == "procedural"
                assert "confidence" not in value
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)


def test_form_alone_never_proves_material():
    result = recipe(run(
        [building("b1", height_m=50, floor_count=15, frontage_length_m=30)],
        [],
    ))
    assert result["materials"]["status"] == "missing"
    assert result["typology"]["candidate"] == "unknown"


def test_city_independent_operation():
    first = run([building("b1")], [evidence("b1", "use", "building_use", "warehouse")])
    second_metadata = metadata(building("b1"))
    second_metadata["city_id"] = "arbitrary_city_label"
    second = facades.build_output(second_metadata, materials(), [], evidence_payload(
        evidence("b1", "use", "building_use", "warehouse")
    ), "reference")
    assert first == second


def test_private_provider_interface_compatibility():
    class PrivateProvider(grammar.FacadeGrammarProvider):
        provider_name = "private-test"

        def build_recipe(self, evidence, material_profile, roof_evidence):
            return grammar.ReferenceFacadeGrammarProvider().build_recipe(
                evidence, material_profile, roof_evidence
            )

    profiles, material_index, roof_index = facades.build_profiles(
        metadata(building("b1")), materials(), [], evidence_payload()
    )
    output = PrivateProvider().build_recipe(profiles[0], material_index.get("b1"), roof_index.get("b1"))
    assert output["schema_version"] == facades.RECIPE_VERSION


def test_private_provider_loading_requires_explicit_allowlist(monkeypatch: pytest.MonkeyPatch):
    class PrivateProvider(grammar.FacadeGrammarProvider):
        provider_name = "private-test"

        def build_recipe(self, evidence, material_profile, roof_evidence):
            return {}

    class Module:
        Provider = PrivateProvider

    monkeypatch.setattr(grammar.importlib, "import_module", lambda name: Module)
    with pytest.raises(ValueError, match="not allowlisted"):
        grammar.load_provider("vendor.facades:Provider")
    monkeypatch.setenv("GLYTCHOS_FACADE_PROVIDER_ALLOWLIST", "vendor.facades:Provider")
    assert isinstance(grammar.load_provider("vendor.facades:Provider"), PrivateProvider)


@pytest.mark.parametrize("specification", ["os:system.extra", "_private:Provider", "module:_provider"])
def test_unsafe_provider_specs_are_rejected(
    specification: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("GLYTCHOS_FACADE_PROVIDER_ALLOWLIST", specification)
    with pytest.raises(ValueError):
        grammar.load_provider(specification)


def test_missing_sidecar_payloads_are_nonblocking():
    output = facades.build_output(
        metadata(building("b1")),
        None,
        None,
        None,
        "reference",
    )
    result = recipe(output)
    assert result["materials"]["status"] == "missing"
    assert result["roof"]["status"] == "missing"
    assert result["materials"]["building_id_namespace"] is None


def test_roof_normalization_does_not_mutate_input(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "schema_version": facades.ROOF_VERSION,
        "building": {"building_id": "b1", "tile_id": "tile-a"},
    }
    original = json.loads(json.dumps(payload))
    monkeypatch.setattr(facades, "validate", lambda *args: None)
    assert facades.roof_records(payload) == [payload]
    assert payload == original
    assert "building_id" not in payload


def test_roof_tile_mismatch_fails_explicitly(monkeypatch: pytest.MonkeyPatch):
    roof = {
        "schema_version": facades.ROOF_VERSION,
        "building": {"building_id": "b1", "tile_id": "wrong-tile"},
    }
    monkeypatch.setattr(facades, "roof_records", lambda payload: [roof])
    original_validate = facades.validate

    def selective_validate(instance, name, label):
        if name != "roof_evidence.schema.json":
            return original_validate(instance, name, label)

    monkeypatch.setattr(facades, "validate", selective_validate)
    with pytest.raises(ValueError, match="roof evidence tile_id mismatch"):
        facades.build_output(
            metadata(building("b1")),
            materials(),
            roof,
            evidence_payload(),
            "reference",
        )


@pytest.mark.parametrize(
    ("status", "confidence"),
    [("inferred", 1.0), ("unknown", 0.5)],
)
def test_nonconservative_evidence_confidence_fails(status: str, confidence: float):
    clue = evidence(
        "b1",
        "unsafe-confidence",
        "building_use",
        "hotel",
        provenance_status=status,
        confidence=confidence,
    )
    with pytest.raises(ValueError, match="facade evidence.*validation"):
        facades.build_output(
            metadata(building("b1")),
            materials(),
            [],
            evidence_payload(clue),
            "reference",
        )


def test_schemas_and_cli(tmp_path: Path):
    output = run([building("b1")], [evidence("b1", "use", "building_use", "warehouse")])
    recipe_schema = json.loads((REPO_ROOT / "schemas" / "facade_recipe.schema.json").read_text())
    evidence_schema = json.loads((REPO_ROOT / "schemas" / "facade_evidence.schema.json").read_text())
    resolver = jsonschema.RefResolver.from_schema(
        recipe_schema,
        store={
            "facade_evidence.schema.json": evidence_schema,
            evidence_schema["$id"]: evidence_schema,
        },
    )
    jsonschema.Draft7Validator(recipe_schema, resolver=resolver).validate(output)

    paths = {
        "metadata": tmp_path / "metadata.json",
        "materials": tmp_path / "materials.json",
        "roof": tmp_path / "roof.json",
        "facade": tmp_path / "facade.json",
        "output": tmp_path / "output.json",
    }
    paths["metadata"].write_text(json.dumps(metadata(building("b1"))))
    paths["materials"].write_text(json.dumps(materials()))
    paths["roof"].write_text("[]")
    paths["facade"].write_text(json.dumps(evidence_payload()))
    command = [
        sys.executable, str(FACADE_DIR / "build_facade_recipe.py"),
        "--building-metadata", str(paths["metadata"]),
        "--material-profiles", str(paths["materials"]),
        "--roof-evidence", str(paths["roof"]),
        "--facade-evidence", str(paths["facade"]),
        "--output", str(paths["output"]),
        "--grammar-provider", "reference",
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(paths["output"].read_text())["recipes"][0]["building_id"] == "b1"

    paths["output"].unlink()
    no_sidecars = subprocess.run(
        [
            sys.executable, str(FACADE_DIR / "build_facade_recipe.py"),
            "--building-metadata", str(paths["metadata"]),
            "--output", str(paths["output"]),
            "--grammar-provider", "reference",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert no_sidecars.returncode == 0, no_sidecars.stderr
