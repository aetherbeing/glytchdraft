from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "roofs" / "analyze_roof_evidence.py"
SPEC = importlib.util.spec_from_file_location("analyze_roof_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
roof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(roof)

BUILDING_ID = "building_example_7"


def rectangular_footprint(width: float, depth: float) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "building_id": BUILDING_ID,
                    "footprint_provenance": "open_city_footprint",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-width / 2, -depth / 2],
                            [width / 2, -depth / 2],
                            [width / 2, depth / 2],
                            [-width / 2, depth / 2],
                            [-width / 2, -depth / 2],
                        ]
                    ],
                },
            }
        ],
    }


def write_case(
    tmp_path: Path,
    points: np.ndarray,
    *,
    width: float = 10,
    depth: float = 10,
    ground_z: float = 0,
    p90: float | None = None,
) -> tuple[Path, Path, Path]:
    point_path = tmp_path / "points.npz"
    np.savez_compressed(point_path, X=points[:, 0], Y=points[:, 1], Z=points[:, 2])
    footprint_path = tmp_path / "footprint.geojson"
    footprint_path.write_text(
        json.dumps(rectangular_footprint(width, depth)), encoding="utf-8"
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            [
                {
                    "building_id": BUILDING_ID,
                    "tile_id": "tile_example",
                    "ground_z": ground_z,
                    "height_p90": float(np.percentile(points[:, 2], 90))
                    if p90 is None
                    else p90,
                    "estimated_height": float(np.percentile(points[:, 2], 90) - ground_z),
                    "source_quality": "synthetic",
                }
            ]
        ),
        encoding="utf-8",
    )
    return point_path, footprint_path, metadata_path


def run_case(
    tmp_path: Path,
    points: np.ndarray,
    *,
    width: float = 10,
    depth: float = 10,
    thresholds: dict | None = None,
) -> dict:
    point_path, footprint_path, metadata_path = write_case(
        tmp_path, points, width=width, depth=depth
    )
    configured = dict(roof.DEFAULT_THRESHOLDS)
    if thresholds:
        configured.update(thresholds)
    return roof.analyze(
        building_id=BUILDING_ID,
        building_points_path=point_path,
        footprint_path=footprint_path,
        metadata_path=metadata_path,
        diagnostic_dir=tmp_path / "diagnostics",
        thresholds=configured,
    )


def grid(width: float, depth: float, spacing: float = 0.35) -> tuple[np.ndarray, np.ndarray]:
    x = np.arange(-width / 2 + spacing / 2, width / 2, spacing)
    y = np.arange(-depth / 2 + spacing / 2, depth / 2, spacing)
    return np.meshgrid(x, y)


def test_clean_flat_roof(tmp_path: Path):
    x, y = grid(10, 10)
    points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 12.0)))
    report = run_case(tmp_path, points)

    assert report["classification"]["roof_class"] == "flat_roof"
    assert report["decision"]["outcome"] == "flat_fallback_recommended"
    assert report["classification"]["confidence"] <= 0.90
    assert report["geometry_evidence"]["planes"][0]["residual_error_m"]["rmse"] < 1e-6


def test_noisy_flat_roof(tmp_path: Path):
    rng = np.random.default_rng(1)
    x, y = grid(10, 10)
    z = 12 + rng.normal(0, 0.07, x.size)
    report = run_case(tmp_path, np.column_stack((x.ravel(), y.ravel(), z)))

    assert report["classification"]["roof_class"] == "flat_roof"
    assert report["points"]["noise_estimate_robust_sigma_m"] > 0


def test_single_plane_shed(tmp_path: Path):
    x, y = grid(10, 10)
    z = 12 + 0.30 * x.ravel()
    report = run_case(tmp_path, np.column_stack((x.ravel(), y.ravel(), z)))

    assert report["classification"]["roof_class"] == "single_sloped_plane"
    assert report["decision"]["outcome"] == "reconstruction_supported"
    assert 15 < report["geometry_evidence"]["planes"][0]["slope_degrees"] < 18


def test_two_plane_ridge(tmp_path: Path):
    x, y = grid(12, 10)
    z = 14 - 0.35 * np.abs(x.ravel())
    report = run_case(tmp_path, np.column_stack((x.ravel(), y.ravel(), z)), width=12)

    assert report["classification"]["roof_class"] == "coherent_two_plane_ridge_candidate"
    assert report["geometry_evidence"]["ridge_line_evidence"]["candidate_found"] is True
    assert report["classification"]["confidence"] <= 0.88

    planes = report["geometry_evidence"]["planes"][:2]
    ring = np.array([[-6, -5], [6, -5], [6, 5], [-6, 5]], dtype=float)
    disconnected = np.array(
        [
            [-4, -4, 12], [-3, -4, 12], [-4, -3, 12], [-3, -3, 12],
            [3, 3, 12], [4, 3, 12], [3, 4, 12], [4, 4, 12],
        ],
        dtype=float,
    )
    labels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    rejected = roof._ridge_evidence(
        planes, disconnected, labels, ring, dict(roof.DEFAULT_THRESHOLDS)
    )
    assert rejected["candidate_found"] is False
    assert "plane regions are spatially disconnected" in rejected["notes"]

    parallel = json.loads(json.dumps(planes))
    parallel[1]["coefficients"] = dict(parallel[0]["coefficients"])
    assert roof._ridge_evidence(
        parallel, disconnected, labels, ring, dict(roof.DEFAULT_THRESHOLDS)
    )["candidate_found"] is False

    overlapping = np.array(
        [
            [-3, 0, 12], [-2, 0, 12], [-1, 0, 12], [1, 0, 12], [2, 0, 12],
            [-2, 0.2, 12], [-1, 0.2, 12], [1, 0.2, 12], [2, 0.2, 12], [3, 0.2, 12],
        ],
        dtype=float,
    )
    overlapping_labels = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    overlap_result = roof._ridge_evidence(
        planes,
        overlapping,
        overlapping_labels,
        ring,
        dict(roof.DEFAULT_THRESHOLDS),
    )
    assert overlap_result["candidate_found"] is False
    assert "plane memberships overlap across the proposed ridge" in overlap_result["notes"]


def test_sparse_data(tmp_path: Path):
    points = np.array(
        [[-1, -1, 8], [1, -1, 8], [1, 1, 8], [-1, 1, 8], [0, 0, 8]],
        dtype=float,
    )
    report = run_case(tmp_path, points)

    assert report["classification"]["roof_class"] == "insufficient_evidence"
    assert report["decision"]["outcome"] == "insufficient_data"


def test_uneven_density_reports_reduced_coverage(tmp_path: Path):
    rng = np.random.default_rng(2)
    dense = np.column_stack(
        (
            rng.uniform(-5, 0, 600),
            rng.uniform(-5, 5, 600),
            rng.normal(10, 0.03, 600),
        )
    )
    sparse = np.column_stack(
        (
            rng.uniform(0, 5, 30),
            rng.uniform(-5, 5, 30),
            rng.normal(10, 0.03, 30),
        )
    )
    report = run_case(
        tmp_path,
        np.vstack((dense, sparse)),
        thresholds={"minimum_footprint_coverage": 0.9},
    )

    assert report["footprint"]["coverage"]["covered_fraction"] < 0.9
    assert "footprint coverage is below the configured threshold" in report["classification"]["contradictory_evidence"]


def test_contaminated_points(tmp_path: Path):
    rng = np.random.default_rng(3)
    x, y = grid(10, 10)
    roof_points = np.column_stack((x.ravel(), y.ravel(), 10 + rng.normal(0, 0.05, x.size)))
    contamination = np.column_stack(
        (
            rng.uniform(-4, 4, 800),
            rng.uniform(-4, 4, 800),
            rng.uniform(11, 18, 800),
        )
    )
    report = run_case(tmp_path, np.vstack((roof_points, contamination)))

    assert report["contamination"]["possible"] is True
    assert report["classification"]["roof_class"] in {
        "contaminated_data",
        "complex_roof",
    }


def test_conflicting_plane_fits_require_review(tmp_path: Path):
    rng = np.random.default_rng(4)
    regions = []
    for x0, x1, slope, intercept in (
        (-5, -1, 0.2, 10),
        (-1, 2, -0.45, 12),
        (2, 5, 0.6, 9),
    ):
        x = rng.uniform(x0, x1, 350)
        y = rng.uniform(-5, 5, 350)
        z = intercept + slope * x + rng.normal(0, 0.04, 350)
        regions.append(np.column_stack((x, y, z)))
    report = run_case(tmp_path, np.vstack(regions))

    assert report["classification"]["roof_class"] in {
        "multi_plane_candidate",
        "complex_roof",
        "indeterminate",
    }
    assert report["decision"]["outcome"] != "reconstruction_supported"


def test_small_low_rise_building(tmp_path: Path):
    x, y = grid(3, 3, 0.2)
    points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 2.4)))
    report = run_case(tmp_path, points, width=3, depth=3)

    assert report["classification"]["roof_class"] == "flat_roof"
    assert report["points"]["point_density_per_m2"] > 10


def test_tall_flat_high_rise(tmp_path: Path):
    rng = np.random.default_rng(5)
    x, y = grid(20, 20, 0.5)
    points = np.column_stack((x.ravel(), y.ravel(), 95 + rng.normal(0, 0.08, x.size)))
    report = run_case(tmp_path, points, width=20, depth=20)

    assert report["classification"]["roof_class"] == "flat_roof"
    assert report["points"]["elevation"]["median_m"] > 90


def test_complex_multi_plane_roof(tmp_path: Path):
    rng = np.random.default_rng(6)
    points = []
    for x0, x1, ax, ay, intercept in (
        (-6, -2, 0.25, 0.0, 12),
        (-2, 1, -0.35, 0.1, 13),
        (1, 4, 0.1, -0.3, 12),
        (4, 6, -0.2, 0.25, 14),
    ):
        x = rng.uniform(x0, x1, 450)
        y = rng.uniform(-5, 5, 450)
        z = intercept + ax * x + ay * y + rng.normal(0, 0.03, 450)
        points.append(np.column_stack((x, y, z)))
    report = run_case(tmp_path, np.vstack(points), width=12)

    assert report["geometry_evidence"]["dominant_plane_count"] >= 3
    assert report["classification"]["roof_class"] in {
        "multi_plane_candidate",
        "complex_roof",
    }


def test_repeated_results_are_deterministic(tmp_path: Path):
    rng = np.random.default_rng(7)
    x, y = grid(12, 10)
    points = np.column_stack(
        (
            x.ravel(),
            y.ravel(),
            15 - 0.3 * np.abs(x.ravel()) + rng.normal(0, 0.02, x.size),
        )
    )
    inputs = write_case(tmp_path, points, width=12)
    kwargs = {
        "building_id": BUILDING_ID,
        "building_points_path": inputs[0],
        "footprint_path": inputs[1],
        "metadata_path": inputs[2],
        "diagnostic_dir": None,
        "thresholds": dict(roof.DEFAULT_THRESHOLDS),
    }
    first = roof.analyze(**kwargs)
    second = roof.analyze(**kwargs)
    shuffled_path = tmp_path / "shuffled.npz"
    order = np.random.default_rng(99).permutation(len(points))
    np.savez_compressed(
        shuffled_path,
        X=points[order, 0],
        Y=points[order, 1],
        Z=points[order, 2],
    )
    shuffled = roof.analyze(**{**kwargs, "building_points_path": shuffled_path})

    assert first["classification"] == second["classification"]
    assert first["geometry_evidence"] == second["geometry_evidence"]
    assert first["classification"] == shuffled["classification"]
    assert first["geometry_evidence"] == shuffled["geometry_evidence"]


def test_portable_cli_and_schema(tmp_path: Path):
    import jsonschema

    x, y = grid(8, 8)
    points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 9.0)))
    point_path, footprint_path, metadata_path = write_case(
        tmp_path, points, width=8, depth=8
    )
    output_json = tmp_path / "report.json"
    output_markdown = tmp_path / "report.md"
    diagnostics = tmp_path / "diagnostics"
    code = roof.main(
        [
            "--building-id", BUILDING_ID,
            "--building-points", str(point_path),
            "--footprint", str(footprint_path),
            "--metadata", str(metadata_path),
            "--output-json", str(output_json),
            "--output-markdown", str(output_markdown),
            "--diagnostic-dir", str(diagnostics),
            "--coordinate-units", "meters",
        ]
    )

    assert code == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == roof.SCHEMA_VERSION
    schema = json.loads(
        (REPO_ROOT / "schemas" / "roof_evidence.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft7Validator(schema).validate(payload)
    invalid_payload = dict(payload)
    invalid_payload["unexpected"] = True
    assert list(jsonschema.Draft7Validator(schema).iter_errors(invalid_payload))
    assert output_markdown.exists()
    assert len(list(diagnostics.glob("*.svg"))) == 2
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "miami" not in source
    assert "/mnt/e/" not in source

    original_metadata = metadata_path.read_bytes()
    collision_code = roof.main(
        [
            "--building-id", BUILDING_ID,
            "--building-points", str(point_path),
            "--footprint", str(footprint_path),
            "--metadata", str(metadata_path),
            "--output-json", str(metadata_path),
            "--output-markdown", str(tmp_path / "collision.md"),
            "--coordinate-units", "meters",
        ]
    )
    assert collision_code == 2
    assert metadata_path.read_bytes() == original_metadata

    malformed_footprint = tmp_path / "malformed.geojson"
    malformed_footprint.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    assert roof.main(
        [
            "--building-id", BUILDING_ID,
            "--building-points", str(point_path),
            "--footprint", str(malformed_footprint),
            "--metadata", str(metadata_path),
            "--output-json", str(tmp_path / "bad.json"),
            "--output-markdown", str(tmp_path / "bad.md"),
            "--coordinate-units", "meters",
        ]
    ) == 2

    assert roof.main(
        [
            "--building-id", BUILDING_ID,
            "--building-points", str(point_path),
            "--footprint", str(footprint_path),
            "--metadata", str(metadata_path),
            "--output-json", str(tmp_path / "threshold.json"),
            "--output-markdown", str(tmp_path / "threshold.md"),
            "--coordinate-units", "meters",
            "--minimum-footprint-coverage", "1.5",
        ]
    ) == 2

    mismatched_npz = tmp_path / "clustered.npz"
    np.savez_compressed(
        mismatched_npz,
        X=np.array([0.0]),
        Y=np.array([0.0]),
        Z=np.array([9.0]),
        cluster_id=np.array([99]),
    )
    with pytest.raises(roof.InputError, match="no cluster_id matching"):
        roof._read_points(
            mismatched_npz,
            np.array([[-4, -4], [4, -4], [4, 4], [-4, 4]], dtype=float),
            BUILDING_ID,
        )

    malformed_csv = tmp_path / "malformed.csv"
    malformed_csv.write_text("longitude,latitude,height\n0,0,9\n", encoding="utf-8")
    with pytest.raises(roof.InputError, match="x, y, and z"):
        roof._read_points(
            malformed_csv,
            np.array([[-4, -4], [4, -4], [4, 4], [-4, 4]], dtype=float),
            BUILDING_ID,
        )
