from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "roofs" / "build_roof_diagnostic_prototype.py"
SPEC = importlib.util.spec_from_file_location("build_roof_diagnostic_prototype", MODULE_PATH)
assert SPEC and SPEC.loader
roof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(roof)

BUILDING_ID = "open-city-building-42"
NAMESPACE = "open_city_footprint:data.example.gov"


def plane(plane_id: int, a: float, d: float, *, points: int = 160) -> dict:
    return {
        "plane_id": plane_id,
        "coefficients": {"a": a, "b": 0.0, "c": 1.0, "d": d},
        "slope_degrees": 26.565,
        "aspect_degrees": 90.0 if a < 0 else 270.0,
        "point_count": points,
        "explained_fraction": 0.48,
        "residual_error_m": {
            "median_absolute": 0.02,
            "rmse": 0.03,
            "p90_absolute": 0.05,
        },
        "spatial_coherence": {
            "largest_connected_fraction": 0.96,
            "xy_extent_m": [5.0, 10.0],
        },
    }


def evidence(
    *,
    planes: list[dict] | None = None,
    contaminated: bool = False,
    outcome: str = "reconstruction_supported",
    roof_class: str = "coherent_two_plane_ridge_candidate",
) -> dict:
    models = planes or [plane(0, -0.5, -12.0), plane(1, 0.5, -12.0)]
    return {
        "schema_version": "glytchdraft.roof_evidence.v1",
        "provenance": {
            "thresholds": {
                "minimum_plane_points": 20,
                "minimum_plane_fraction": 0.12,
                "minimum_spatial_coherence": 0.55,
                "ridge_min_confidence": 0.55,
                "ridge_min_side_purity": 0.8,
                "ridge_min_adjacent_cells": 2,
                "contamination_unexplained_fraction": 0.4,
            }
        },
        "building": {"building_id": BUILDING_ID, "tile_id": "source-tile"},
        "geometry_evidence": {
            "dominant_plane_count": len(models),
            "planes": models,
            "percent_points_explained": 96.0,
            "ridge_line_evidence": {
                "candidate_found": True,
                "confidence": 0.91,
                "intersection_crosses_footprint": True,
                "side_purity": {"plane_0": 0.98, "plane_1": 0.97},
                "adjacent_cell_count": 8,
            },
            "eave_height_evidence": {
                "status": "candidate",
                "boundary_point_count": 64,
                "candidate_height_m": 9.5,
                "height_spread_m": 1.2,
                "coherence": 0.72,
            },
        },
        "contamination": {
            "possible": contaminated,
            "unexplained_point_fraction": 0.08 if not contaminated else 0.55,
        },
        "classification": {
            "roof_class": roof_class,
            "confidence": 0.87,
            "uncertainty_notes": ["Synthetic plane intersection is inferred."],
        },
        "decision": {"outcome": outcome, "reason": "synthetic"},
    }


def footprint(
    *,
    building_id: str = BUILDING_ID,
    namespace: str | None = NAMESPACE,
    coordinates: list | None = None,
) -> dict:
    properties = {
        "building_id": building_id,
        "footprint_provenance": "open_city_footprint",
    }
    if namespace is not None:
        properties["building_id_namespace"] = namespace
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": coordinates
                    or [[[-5, -4], [5, -4], [5, 4], [-5, 4], [-5, -4]]],
                },
            }
        ],
    }


def write_inputs(
    tmp_path: Path,
    *,
    evidence_payload: dict | None = None,
    footprint_payload: dict | None = None,
) -> tuple[Path, Path]:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence_payload or evidence()), encoding="utf-8"
    )
    footprint_path = tmp_path / "footprint.geojson"
    footprint_path.write_text(
        json.dumps(footprint_payload or footprint()), encoding="utf-8"
    )
    return evidence_path, footprint_path


def build_case(
    tmp_path: Path,
    *,
    evidence_payload: dict | None = None,
    footprint_payload: dict | None = None,
) -> dict:
    evidence_path, footprint_path = write_inputs(
        tmp_path,
        evidence_payload=evidence_payload,
        footprint_payload=footprint_payload,
    )
    return roof.build(
        evidence_path=evidence_path,
        footprint_path=footprint_path,
        building_id=BUILDING_ID,
        building_id_namespace=NAMESPACE,
        source_artifact="synthetic://tile/source-tile",
        source_digest="sha256:0123456789abcdef",
        pipeline_commit="1b94b956b93aa0529b37c2c26ff9ab3b00169c9c",
    )


def test_clean_symmetric_gable_roof(tmp_path: Path):
    report = build_case(tmp_path)

    assert report["eligibility"]["eligible"] is True
    assert len(report["geometry"]["roof_plane_polygons"]) == 2
    assert report["geometry"]["ridge_segment"][0][:2] == [0.0, -4.0]
    assert report["geometry"]["ridge_segment"][1][:2] == [0.0, 4.0]
    assert all(
        -5 <= vertex[0] <= 5 and -4 <= vertex[1] <= 4
        for polygon in report["geometry"]["roof_plane_polygons"]
        for vertex in polygon["vertices"]
    )


def test_unequal_two_plane_roof(tmp_path: Path):
    models = [plane(9, -0.25, -12.25), plane(4, 0.5, -11.5)]
    report = build_case(tmp_path, evidence_payload=evidence(planes=models))

    assert report["eligibility"]["eligible"] is True
    ridge = report["geometry"]["ridge_segment"]
    assert ridge[0][0] == pytest.approx(-1.0)
    assert ridge[1][0] == pytest.approx(-1.0)
    assert ridge[0][2] == pytest.approx(12.0)


def test_reordered_input_is_deterministic(tmp_path: Path):
    models = [plane(9, -0.25, -12.25), plane(4, 0.5, -11.5)]
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = build_case(first_dir, evidence_payload=evidence(planes=models))
    second = build_case(second_dir, evidence_payload=evidence(planes=list(reversed(models))))

    for report in (first, second):
        report["provenance"]["evidence_path"] = "normalized"
        report["provenance"]["footprint_path"] = "normalized"
    assert first == second


def test_parallel_planes_have_no_stable_ridge(tmp_path: Path):
    models = [plane(0, -0.5, -12), plane(1, -0.5, -10)]
    report = build_case(tmp_path, evidence_payload=evidence(planes=models))

    assert report["eligibility"]["eligible"] is False
    assert report["geometry"] is None
    assert any("stable horizontal ridge" in reason for reason in report["eligibility"]["rejection_reasons"])


def test_ridge_outside_footprint_is_rejected(tmp_path: Path):
    models = [plane(0, -0.5, -2), plane(1, 0.5, -22)]
    report = build_case(tmp_path, evidence_payload=evidence(planes=models))

    assert report["eligibility"]["eligible"] is False
    assert any("does not span" in reason for reason in report["eligibility"]["rejection_reasons"])


def test_insufficient_inlier_support_is_rejected(tmp_path: Path):
    models = [plane(0, -0.5, -12, points=10), plane(1, 0.5, -12)]
    report = build_case(tmp_path, evidence_payload=evidence(planes=models))

    assert report["geometry"] is None
    assert report["eligibility"]["gates"]["plane_inlier_support"] is False


def test_contaminated_evidence_is_rejected(tmp_path: Path):
    report = build_case(tmp_path, evidence_payload=evidence(contaminated=True))

    assert report["geometry"] is None
    assert report["eligibility"]["gates"]["contamination_gate"] is False


def test_three_plane_roof_is_rejected(tmp_path: Path):
    models = [
        plane(0, -0.5, -12),
        plane(1, 0.5, -12),
        plane(2, 0.1, -10),
    ]
    report = build_case(
        tmp_path,
        evidence_payload=evidence(
            planes=models, roof_class="multi_plane_candidate", outcome="classification_only"
        ),
    )

    assert report["geometry"] is None
    assert report["eligibility"]["gates"]["exactly_two_dominant_planes"] is False


def test_missing_building_id_namespace_fails(tmp_path: Path):
    evidence_path, footprint_path = write_inputs(
        tmp_path, footprint_payload=footprint(namespace=None)
    )
    with pytest.raises(roof.InputError, match="namespace is missing"):
        roof.build(
            evidence_path=evidence_path,
            footprint_path=footprint_path,
            building_id=BUILDING_ID,
            building_id_namespace=NAMESPACE,
            source_artifact="synthetic://tile",
            source_digest="sha256:abcd",
            pipeline_commit=None,
        )


def test_mismatched_evidence_and_footprint_ids_fail(tmp_path: Path):
    payload = evidence()
    payload["building"]["building_id"] = "different-building"
    evidence_path, footprint_path = write_inputs(tmp_path, evidence_payload=payload)
    with pytest.raises(roof.InputError, match="does not match"):
        roof.build(
            evidence_path=evidence_path,
            footprint_path=footprint_path,
            building_id=BUILDING_ID,
            building_id_namespace=NAMESPACE,
            source_artifact="synthetic://tile",
            source_digest="sha256:abcd",
            pipeline_commit=None,
        )


def test_invalid_footprint_is_structured_rejection(tmp_path: Path):
    bowtie = [[[0, 0], [5, 5], [0, 5], [5, 0], [0, 0]]]
    report = build_case(
        tmp_path, footprint_payload=footprint(coordinates=bowtie)
    )

    assert report["geometry"] is None
    assert report["eligibility"]["gates"]["valid_supported_footprint"] is False
    assert any("self-intersecting" in reason for reason in report["eligibility"]["rejection_reasons"])


def cli_args(evidence_path: Path, footprint_path: Path, output_path: Path) -> list[str]:
    return [
        "--evidence", str(evidence_path),
        "--footprint", str(footprint_path),
        "--building-id", BUILDING_ID,
        "--building-id-namespace", NAMESPACE,
        "--source-artifact", "synthetic://tile",
        "--source-digest", "sha256:abcd",
        "--output-json", str(output_path),
        "--coordinate-units", "meters",
    ]


def test_output_overwrite_protection(tmp_path: Path):
    evidence_path, footprint_path = write_inputs(tmp_path)
    output = tmp_path / "result.json"
    output.write_text("preserve", encoding="utf-8")

    assert roof.main(cli_args(evidence_path, footprint_path, output)) == 2
    assert output.read_text(encoding="utf-8") == "preserve"
    assert roof.main(cli_args(evidence_path, footprint_path, evidence_path)) == 2


def test_atomic_output_cleanup_on_replace_failure(tmp_path: Path):
    output = tmp_path / "atomic.json"

    def fail_replace(source: str, destination: str) -> None:
        raise OSError("simulated replace failure")

    with pytest.raises(OSError, match="simulated"):
        roof._atomic_write(output, "payload", replace=fail_replace)
    assert not output.exists()
    assert list(tmp_path.glob(".atomic.json.*.tmp")) == []


def test_explicit_noncanonical_flags_and_draft7_schema(tmp_path: Path):
    import jsonschema

    report = build_case(tmp_path)
    assert report["flags"] == {
        "diagnostic_only": True,
        "canonical": False,
        "viewer_ready": False,
        "production_allowed": False,
    }
    schema = json.loads(
        (REPO_ROOT / "schemas" / "roof_diagnostic_geometry.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft7Validator(schema).validate(report)


def test_cli_writes_only_requested_noncanonical_artifacts(tmp_path: Path):
    evidence_path, footprint_path = write_inputs(tmp_path)
    output = tmp_path / "result.json"
    inspection = tmp_path / "inspection"
    args = cli_args(evidence_path, footprint_path, output) + [
        "--inspection-dir", str(inspection),
        "--emit-svg",
        "--emit-obj",
    ]

    assert roof.main(args) == 0
    assert output.exists()
    assert len(list(inspection.glob("*.svg"))) == 1
    assert len(list(inspection.glob("*.obj"))) == 1
    assert list(tmp_path.rglob("*.glb")) == []
    assert not (tmp_path / "manifests").exists()
    assert not (tmp_path / "audit").exists()
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "miami" not in source
    assert "/mnt/e" not in source
