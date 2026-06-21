from __future__ import annotations

import copy
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
recipe_builder = importlib.import_module("build_facade_recipe")
analyzer = importlib.import_module("analyze_single_facade")
diagnostic = importlib.import_module("build_facade_diagnostic_prototype")
grammar = importlib.import_module("grammar_provider")
analysis_tests = importlib.import_module("test_analyze_single_facade")


def artifact(use: str, **building_fields: object) -> tuple[dict, dict]:
    meta = analysis_tests.metadata()
    meta["buildings"][0].update(building_fields)
    meta, profiles, recipes = analysis_tests.contracts(meta, use)
    analysis = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    assert analysis["eligible"], analysis
    return diagnostic.build_geometry(analysis, recipes), recipes


@pytest.mark.parametrize(
    ("use", "expected"),
    [
        ("residential", "repetitive_residential_bays"),
        ("hotel", "hotel_bay_rhythm"),
        ("office", "office_grid"),
        ("warehouse", "warehouse_bays"),
        ("parking structure", "parking_structure_openings"),
        ("civic", "civic_monumental"),
        ("industrial", "industrial_panelized"),
    ],
)
def test_required_direct_archetypes_generate_bounded_guides(use: str, expected: str):
    payload, _ = artifact(use)
    assert payload["artifact_status"] == "generated"
    assert expected in {
        element["source_rule"].split(":")[0]
        for element in payload["elements"]
        if element["element_type"] == "opening"
    }


def test_curtain_wall_candidate():
    meta = analysis_tests.metadata()
    clues = analysis_tests.evidence("building-a", "office")
    clues["evidence"].append({
        **clues["evidence"][0],
        "evidence_id": "glazing",
        "evidence_type": "glazing_ratio",
        "value": 0.82,
    })
    profiles, _, _ = recipe_builder.build_profiles(meta, None, None, clues)
    profile_payload = {
        "schema_version": recipe_builder.PROFILE_VERSION,
        "building_id_namespace": grammar.ID_NAMESPACE,
        "profiles": profiles,
    }
    recipes = recipe_builder.build_output(meta, None, None, clues, "reference")
    analysis = analyzer.analyze_facade(
        meta, profile_payload, recipes, "building-a", "south-edge"
    )
    payload = diagnostic.build_geometry(analysis, recipes)
    assert analysis["grammar"]["candidate"] == "curtain_wall_candidate"
    assert payload["artifact_status"] == "generated"


@pytest.mark.parametrize(
    ("candidate", "podium_levels"),
    [
        ("retail_podium", 1),
        ("mixed_use_podium_tower", 2),
    ],
)
def test_required_podium_archetypes(candidate: str, podium_levels: int):
    use = "mixed use"
    meta = analysis_tests.metadata()
    meta["buildings"][0]["podium_levels"] = podium_levels
    meta, profiles, recipes = analysis_tests.contracts(meta, use)
    if candidate == "retail_podium":
        recipes["recipes"][0]["typology"]["candidate"] = candidate
    analysis = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    payload = diagnostic.build_geometry(analysis, recipes)
    assert payload["artifact_status"] == "generated"
    assert any(item["element_type"] == "podium_division" for item in payload["elements"])


def test_unknown_recipe_rejection_and_low_applicability_fallback():
    meta, profiles, recipes = analysis_tests.contracts(analysis_tests.metadata(), "unknown-use")
    analysis = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    rejected = diagnostic.build_geometry(analysis, recipes)
    assert rejected["artifact_status"] == "rejected"
    assert "unknown" in rejected["rejection_reasons"][0]
    fallback = diagnostic.build_geometry(analysis, recipes, True)
    assert fallback["artifact_status"] == "generated"
    assert max(item["applicability_score"] for item in fallback["elements"]) <= 0.15


def test_geometry_is_bounded_corner_contained_and_procedural():
    payload, _ = artifact("hotel")
    bounds = payload["bounds"]
    for element in payload["elements"]:
        assert element["status"] == "procedural"
        assert "confidence" not in element
        assert element["uncertainty_note"]
        for point in element["coordinates"]["points"]:
            assert 0 <= point["u"] <= bounds["edge_length_m"]
            assert bounds["ground_z"] <= point["z"] <= bounds["building_top_z"]
            assert -payload["recess_depth_m"] <= point["n"] <= 0


def test_openings_do_not_overlap_and_have_stable_order():
    payload, _ = artifact("office")
    ids = [item["element_id"] for item in payload["elements"]]
    expected = sorted(
        payload["elements"],
        key=lambda item: (
            diagnostic.TYPE_ORDER[item["element_type"]], item["element_id"]
        ),
    )
    assert ids == [item["element_id"] for item in expected]
    diagnostic._validate_geometry(payload)


def test_all_polygons_and_element_ids_are_validated():
    payload, _ = artifact("office")
    invalid_polygon = copy.deepcopy(payload)
    boundary = next(
        item
        for item in invalid_polygon["elements"]
        if item["element_type"] == "facade_boundary"
    )
    boundary["coordinates"]["points"] = boundary["coordinates"]["points"][:2]
    with pytest.raises(ValueError, match="schema validation|polygon geometry"):
        diagnostic._validate_geometry(invalid_polygon)

    duplicate = copy.deepcopy(payload)
    duplicate["elements"][1]["element_id"] = duplicate["elements"][0]["element_id"]
    with pytest.raises(ValueError, match="duplicate element_id"):
        diagnostic._validate_geometry(duplicate)


def test_no_factual_material_or_color_claims_and_no_glb_output(tmp_path: Path):
    payload, recipes = artifact("warehouse")
    recipe_path = tmp_path / "recipes.json"
    analysis_path = tmp_path / "analysis.json"
    recipe_path.write_text(json.dumps(recipes), encoding="utf-8")
    analysis = analysis_tests.analyze(use="warehouse")
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    written = diagnostic.write_outputs(
        tmp_path / "guide", payload, [analysis_path, recipe_path], emit_obj=True
    )
    assert {path.suffix for path in written} == {".json", ".svg", ".obj"}
    assert not list((tmp_path / "guide").glob("*.glb"))
    text = "\n".join(path.read_text() for path in written)
    assert '"material"' not in text
    assert '"color"' not in text
    assert '"observed"' not in text
    assert '"record_derived"' not in text


def test_byte_identical_json_for_reordered_equivalent_recipe():
    meta, profiles, recipes = analysis_tests.contracts()
    analysis = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    first = diagnostic.build_geometry(analysis, recipes)
    reordered = copy.deepcopy(recipes)
    reordered["recipes"][0]["evidence_catalog"].reverse()
    reordered["recipes"][0]["horizontal_organization"].reverse()
    second_analysis = analyzer.analyze_facade(
        meta, profiles, reordered, "building-a", "south-edge"
    )
    second = diagnostic.build_geometry(second_analysis, reordered)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_recipe_and_edge_identity_mismatches_reject():
    payload, recipes = artifact("hotel")
    assert payload["artifact_status"] == "generated"
    analysis = analysis_tests.analyze()
    bad_building = copy.deepcopy(recipes)
    bad_building["recipes"][0]["building_id"] = "building-other"
    result = diagnostic.build_geometry(analysis, bad_building)
    assert result["artifact_status"] == "rejected"
    bad_edge = copy.deepcopy(recipes)
    bad_edge["recipes"][0]["horizontal_organization"][0]["facade_edge_id"] = "other-edge"
    result = diagnostic.build_geometry(analysis, bad_edge)
    assert result["artifact_status"] == "rejected"

    bad_namespace = copy.deepcopy(analysis)
    bad_namespace["building_id_namespace"] = "phase03.cluster"
    result = diagnostic.build_geometry(bad_namespace, recipes)
    assert result["artifact_status"] == "rejected"
    assert "namespace mismatch" in result["rejection_reasons"][0]


def test_analysis_is_cryptographically_bound_to_recipe_and_provider():
    analysis = analysis_tests.analyze()
    _, recipes = artifact("hotel")
    changed_recipe = copy.deepcopy(recipes)
    changed_recipe["recipes"][0]["openings"]["window_to_wall_ratio"]["value"] = 0.2
    result = diagnostic.build_geometry(analysis, changed_recipe)
    assert result["artifact_status"] == "rejected"
    assert "recipe digest mismatch" in result["rejection_reasons"][0]

    provider_mismatch = copy.deepcopy(analysis)
    provider_mismatch["grammar"]["provider"] = "other.v1"
    provider_mismatch["grammar"]["version"] = "other.v1"
    result = diagnostic.build_geometry(provider_mismatch, recipes)
    assert result["artifact_status"] == "rejected"
    assert "grammar provider mismatch" in result["rejection_reasons"][0]


def test_schema_draft7_validation():
    payload, _ = artifact("parking structure")
    schema = json.loads(
        (REPO_ROOT / "schemas" / "facade_diagnostic_geometry.schema.json").read_text()
    )
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.Draft7Validator(schema).validate(payload)


def test_atomic_overwrite_and_input_protection(tmp_path: Path):
    payload, recipes = artifact("hotel")
    recipe_path = tmp_path / "recipe.json"
    analysis_path = tmp_path / "analysis.json"
    recipe_path.write_text(json.dumps(recipes), encoding="utf-8")
    analysis_path.write_text(json.dumps(analysis_tests.analyze()), encoding="utf-8")
    output_dir = tmp_path / "output"
    diagnostic.write_outputs(output_dir, payload, [analysis_path, recipe_path])
    before = (output_dir / "facade_diagnostic_geometry.json").read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        diagnostic.write_outputs(output_dir, payload, [analysis_path, recipe_path])
    assert (output_dir / "facade_diagnostic_geometry.json").read_bytes() == before
    with pytest.raises(ValueError, match="overwrite an input"):
        diagnostic.write_outputs(
            tmp_path,
            payload,
            [tmp_path / "facade_diagnostic_geometry.json"],
        )


def test_reordered_inputs_write_byte_identical_json_svg_and_obj(tmp_path: Path):
    meta, profiles, recipes = analysis_tests.contracts()
    first_analysis = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    reordered_recipes = copy.deepcopy(recipes)
    reordered_recipes["recipes"][0]["evidence_catalog"].reverse()
    reordered_recipes["recipes"][0]["horizontal_organization"].reverse()
    second_analysis = analyzer.analyze_facade(
        meta, profiles, reordered_recipes, "building-a", "south-edge"
    )
    first = diagnostic.build_geometry(first_analysis, recipes)
    second = diagnostic.build_geometry(second_analysis, reordered_recipes)
    first_paths = diagnostic.write_outputs(
        tmp_path / "first", first, [], emit_obj=True
    )
    second_paths = diagnostic.write_outputs(
        tmp_path / "second", second, [], emit_obj=True
    )
    assert [path.name for path in first_paths] == [path.name for path in second_paths]
    for first_path, second_path in zip(first_paths, second_paths):
        assert first_path.read_bytes() == second_path.read_bytes()


def test_canonical_path_write_is_refused():
    payload, _ = artifact("hotel")
    with pytest.raises(ValueError, match="canonical city path"):
        diagnostic.write_outputs(
            REPO_ROOT / "configs" / "cities" / "diagnostic",
            payload,
            [],
        )
    with pytest.raises(ValueError, match="canonical city path"):
        diagnostic.write_outputs(
            Path("/mnt/e/new_orleans/data_processed/new_orleans/diagnostic"),
            payload,
            [],
        )


def test_cli_help_and_compatibility_with_recipe_builder_output(tmp_path: Path):
    meta, profiles, recipes = analysis_tests.contracts()
    analysis = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    analysis_path = tmp_path / "analysis.json"
    recipe_path = tmp_path / "recipe.json"
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    recipe_path.write_text(json.dumps(recipes), encoding="utf-8")
    command = [
        sys.executable,
        str(FACADE_DIR / "build_facade_diagnostic_prototype.py"),
        "--analysis", str(analysis_path),
        "--facade-recipe", str(recipe_path),
        "--output-dir", str(tmp_path / "guide"),
        "--emit-obj",
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "guide" / "facade_elevation.svg").exists()
    assert (tmp_path / "guide" / "facade_guide.obj").exists()
    help_result = subprocess.run(
        [
            sys.executable,
            str(FACADE_DIR / "build_facade_diagnostic_prototype.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert help_result.returncode == 0


def test_cli_writes_structured_unknown_recipe_rejection(tmp_path: Path):
    meta, profiles, recipes = analysis_tests.contracts(
        analysis_tests.metadata(), "unknown-use"
    )
    analysis = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    analysis_path = tmp_path / "analysis.json"
    recipe_path = tmp_path / "recipe.json"
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    recipe_path.write_text(json.dumps(recipes), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(FACADE_DIR / "build_facade_diagnostic_prototype.py"),
            "--analysis", str(analysis_path),
            "--facade-recipe", str(recipe_path),
            "--output-dir", str(tmp_path / "rejected"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    output = json.loads(
        (tmp_path / "rejected" / "facade_diagnostic_geometry.json").read_text()
    )
    assert output["artifact_status"] == "rejected"
    assert output["elements"] == []
    assert not (tmp_path / "rejected" / "facade_elevation.svg").exists()
