from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FACADE_DIR = REPO_ROOT / "scripts" / "facades"
sys.path.insert(0, str(FACADE_DIR))
recipe_builder = importlib.import_module("build_facade_recipe")
analyzer = importlib.import_module("analyze_single_facade")
grammar = importlib.import_module("grammar_provider")


def evidence(building_id: str, use: str = "hotel") -> dict:
    return {
        "schema_version": recipe_builder.EVIDENCE_VERSION,
        "building_id_namespace": grammar.ID_NAMESPACE,
        "evidence": [{
            "evidence_id": "use-record",
            "building_id": building_id,
            "building_id_namespace": grammar.ID_NAMESPACE,
            "facade_edge_id": None,
            "evidence_type": "building_use",
            "value": use,
            "unit": None,
            "source_type": "building_inventory",
            "source_reference": "fixture://inventory",
            "license": "CC0-1.0",
            "source_timestamp": "2025-01-02T00:00:00Z",
            "attribution_requirements": "Retain fixture attribution.",
            "confidence": 0.9,
            "provenance_status": "record_derived",
            "quality_flags": [],
        }],
    }


def metadata(
    building_id: str = "building-a",
    namespace: str = grammar.ID_NAMESPACE,
    edge_id: str = "south-edge",
    start: list[float] | None = None,
    end: list[float] | None = None,
    height: float = 12.0,
) -> dict:
    return {
        "schema_version": "glytchdraft.facade_building_input.v1",
        "building_id_namespace": namespace,
        "source_pipeline_commit": "48150bf",
        "buildings": [{
            "building_id": building_id,
            "building_id_namespace": namespace,
            "tile_id": "tile-a",
            "named_building_node": f"bld_tile-a_{building_id}",
            "height_m": height,
            "ground_z": 2.0,
            "building_top_z": 2.0 + height,
            "floor_count": 4,
            "source": {
                "footprint_id": "fp-a",
                "source_footprint_id": "source-a"
            },
            "street_facing_edges": [{
                "facade_edge_id": edge_id,
                "frontage_length_m": 20.0,
                "orientation_degrees": 90.0
            }],
            "facade_edges": [{
                "facade_edge_id": edge_id,
                "start": start if start is not None else [100.0, 200.0],
                "end": end if end is not None else [120.0, 200.0],
                "outward_normal": [0.0, -1.0],
                "ground_z": 2.0,
                "building_top_z": 2.0 + height
            }]
        }],
    }


def contracts(meta: dict | None = None, use: str = "hotel") -> tuple[dict, dict, dict]:
    meta = meta or metadata()
    clues = evidence(meta["buildings"][0]["building_id"], use)
    profiles, _, _ = recipe_builder.build_profiles(meta, None, None, clues)
    profile_payload = {
        "schema_version": recipe_builder.PROFILE_VERSION,
        "building_id_namespace": grammar.ID_NAMESPACE,
        "profiles": profiles,
    }
    recipes = recipe_builder.build_output(meta, None, None, clues, "reference")
    return meta, profile_payload, recipes


def analyze(meta: dict | None = None, use: str = "hotel") -> dict:
    meta, profiles, recipes = contracts(meta, use)
    return analyzer.analyze_facade(
        meta, profiles, recipes, meta["buildings"][0]["building_id"], "south-edge"
    )


def test_phase0_analysis_reports_identity_frame_support_and_provenance():
    meta, profiles, recipes = contracts()
    result = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    assert result["status"] == "eligible"
    assert result["building_id_namespace"] == grammar.ID_NAMESPACE
    assert result["facade_edge_id"] == "south-edge"
    assert result["edge"]["length_m"] == 20.0
    assert result["edge"]["direction"] == [1.0, 0.0, 0.0]
    assert result["edge"]["outward_normal"] == [0.0, -1.0, 0.0]
    assert result["local_frame"]["u_axis"] == [1.0, 0.0, 0.0]
    assert result["local_frame"]["z_axis"] == [0.0, 0.0, 1.0]
    assert result["local_frame"]["n_axis"] == [0.0, -1.0, 0.0]
    assert result["vertical_support"]["ground_z"] == 2.0
    assert result["vertical_support"]["building_top_z"] == 14.0
    assert result["vertical_support"]["floor_count"] == 4
    assert result["grammar"]["candidate"] == "hotel_bay_rhythm"
    assert result["pipeline_commit"] == "48150bf"
    assert len(result["source_digests"]["recipe_digest"]) == 64
    assert (
        result["source_digests"]["metadata_digest"]
        == recipes["recipes"][0]["source_metadata_digest"]
    )
    assert result["diagnostic_only"] is True
    assert result["production_allowed"] is False


@pytest.mark.parametrize(
    "building_id",
    [
        "17",
        "cluster_17",
        "phase03:17",
        "cid",
        "row_4",
        "index:2",
        "array[2]",
        "filename_17",
        "tile.geojson:17",
    ],
)
def test_unstable_building_id_is_structurally_rejected(building_id: str):
    meta = metadata(building_id=building_id)
    result = analyzer.analyze_facade(meta, {}, {}, building_id, "south-edge")
    assert result["status"] == "rejected"
    assert "stable Phase 06" in result["rejection_reasons"][0]


def test_namespace_mismatch_is_rejected():
    meta = metadata(namespace="phase03.cluster")
    result = analyzer.analyze_facade(meta, {}, {}, "building-a", "south-edge")
    assert result["status"] == "rejected"
    assert "namespace" in result["rejection_reasons"][0]


def test_building_id_mismatch_is_rejected():
    meta, profiles, recipes = contracts()
    result = analyzer.analyze_facade(
        meta,
        profiles,
        recipes,
        "building-other",
        "south-edge",
        {"building_metadata": "metadata.json"},
    )
    assert result["status"] == "rejected"
    assert "building-ID mismatch" in result["rejection_reasons"][0]
    assert result["source_artifacts"] == {"building_metadata": "metadata.json"}
    assert result["grammar_provider"] == "reference.v1"
    assert result["grammar_provider_version"] == "reference.v1"


def test_facade_edge_mismatch_is_rejected():
    meta, profiles, recipes = contracts()
    result = analyzer.analyze_facade(meta, profiles, recipes, "building-a", "north-edge")
    assert result["status"] == "rejected"
    assert "facade-edge mismatch" in result["rejection_reasons"][0]


def test_profile_facade_length_mismatch_is_rejected():
    meta, profiles, recipes = contracts()
    profiles["profiles"][0]["building_facts"]["street_facing_edges"][0][
        "frontage_length_m"
    ] = 19.0
    result = analyzer.analyze_facade(
        meta, profiles, recipes, "building-a", "south-edge"
    )
    assert result["status"] == "rejected"
    assert "metadata and profile" in result["rejection_reasons"][0]


def test_duplicate_facade_edge_ids_are_rejected():
    meta = metadata()
    meta["buildings"][0]["facade_edges"].append(
        dict(meta["buildings"][0]["facade_edges"][0])
    )
    _, profiles, recipes = contracts(metadata())
    result = analyzer.analyze_facade(meta, profiles, recipes, "building-a", "south-edge")
    assert result["status"] == "rejected"
    assert "duplicate facade_edge_id" in result["rejection_reasons"][0]


def test_zero_length_edge_is_rejected():
    meta = metadata(end=[100.0, 200.0])
    meta["buildings"][0]["street_facing_edges"][0]["frontage_length_m"] = 0.001
    meta, profiles, recipes = contracts(meta)
    result = analyzer.analyze_facade(meta, profiles, recipes, "building-a", "south-edge")
    assert result["status"] == "rejected"
    assert "zero-length" in result["rejection_reasons"][0]


def test_invalid_height_is_rejected():
    meta = metadata(height=0.0)
    meta, profiles, recipes = contracts(meta)
    result = analyzer.analyze_facade(meta, profiles, recipes, "building-a", "south-edge")
    assert result["status"] == "rejected"
    assert "nonpositive" in result["rejection_reasons"][0]


def test_pipeline_commit_and_source_digest_mismatches_are_rejected():
    meta, profiles, recipes = contracts()
    bad_commit = json.loads(json.dumps(meta))
    bad_commit["source_pipeline_commit"] = "different"
    result = analyzer.analyze_facade(
        bad_commit, profiles, recipes, "building-a", "south-edge"
    )
    assert result["status"] == "rejected"
    assert "pipeline commit mismatch" in result["rejection_reasons"][0]

    bad_profile = json.loads(json.dumps(profiles))
    bad_profile["profiles"][0]["source_metadata_digest"] = "0" * 64
    result = analyzer.analyze_facade(
        meta, bad_profile, recipes, "building-a", "south-edge"
    )
    assert result["status"] == "rejected"
    assert "source metadata digest mismatch" in result["rejection_reasons"][0]

    bad_evidence_digest = json.loads(json.dumps(profiles))
    bad_evidence_digest["profiles"][0]["source_facade_evidence_digest"] = "0" * 64
    result = analyzer.analyze_facade(
        meta, bad_evidence_digest, recipes, "building-a", "south-edge"
    )
    assert result["status"] == "rejected"
    assert "facade evidence digest mismatch" in result["rejection_reasons"][0]


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "MultiPolygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[], []]},
    ],
)
def test_unsupported_multipart_and_holes_are_rejected(geometry: dict):
    meta = metadata()
    meta["buildings"][0]["geometry"] = geometry
    meta, profiles, recipes = contracts(meta)
    result = analyzer.analyze_facade(meta, profiles, recipes, "building-a", "south-edge")
    assert result["status"] == "rejected"
    assert "unsupported" in result["rejection_reasons"][0]


def test_reordered_equivalent_input_is_byte_identical():
    meta, profiles, recipes = contracts()
    first = analyzer.analyze_facade(meta, profiles, recipes, "building-a", "south-edge")
    reordered_meta = {
        key: meta[key] for key in reversed(list(meta))
    }
    reordered_profiles = {
        **profiles,
        "profiles": list(reversed(profiles["profiles"])),
    }
    reordered_recipes = {
        **recipes,
        "recipes": list(reversed(recipes["recipes"])),
    }
    second = analyzer.analyze_facade(
        reordered_meta, reordered_profiles, reordered_recipes, "building-a", "south-edge"
    )
    assert analyzer.canonical_json(first) == analyzer.canonical_json(second)


def test_cli_help_and_atomic_overwrite_protection(tmp_path: Path):
    meta, profiles, recipes = contracts()
    inputs = {
        "metadata": tmp_path / "metadata.json",
        "profiles": tmp_path / "profiles.json",
        "recipes": tmp_path / "recipes.json",
    }
    for name, payload in (
        ("metadata", meta), ("profiles", profiles), ("recipes", recipes)
    ):
        inputs[name].write_text(json.dumps(payload), encoding="utf-8")
    command = [
        sys.executable,
        str(FACADE_DIR / "analyze_single_facade.py"),
        "--building-metadata", str(inputs["metadata"]),
        "--synthesis-profile", str(inputs["profiles"]),
        "--facade-recipe", str(inputs["recipes"]),
        "--building-id", "building-a",
        "--facade-edge-id", "south-edge",
        "--output-dir", str(tmp_path / "diagnostic"),
    ]
    first = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    assert first.returncode == 0, first.stderr
    output = tmp_path / "diagnostic" / "facade_analysis.json"
    assert json.loads(output.read_text())["status"] == "eligible"
    before = output.read_bytes()
    second = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    assert second.returncode != 0
    assert output.read_bytes() == before
    help_result = subprocess.run(
        [sys.executable, str(FACADE_DIR / "analyze_single_facade.py"), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert help_result.returncode == 0


def test_analyzer_refuses_canonical_city_output():
    assert analyzer.forbidden_output(REPO_ROOT / "configs" / "cities" / "diagnostic")
    assert analyzer.forbidden_output(
        Path("/mnt/e/new_orleans/data_processed/new_orleans/diagnostic")
    )
