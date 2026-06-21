from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import struct
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts/roofs/run_roof_real_data_smoke.py"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/roofs/real_tile_fixture.json"
SPEC = importlib.util.spec_from_file_location("run_roof_real_data_smoke", MODULE_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
FOOTPRINT_NAMESPACE = "miami-dade-building-footprints:UNIQUEID"


def minimal_glb(node_names: list[str]) -> bytes:
    payload = json.dumps(
        {"asset": {"version": "2.0"}, "nodes": [{"name": name} for name in node_names]},
        separators=(",", ":"),
    ).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    return (
        b"glTF"
        + struct.pack("<II", 2, 20 + len(payload))
        + struct.pack("<II", len(payload), 0x4E4F534A)
        + payload
    )


def materialize_tile(tmp_path: Path) -> tuple[Path, dict]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    tile = tmp_path / "source" / fixture["tile_id"]
    for directory in ("clusters", "footprints", "masses", "blender_ready"):
        (tile / directory).mkdir(parents=True, exist_ok=True)

    all_points = []
    all_labels = []
    features = []
    rows = []
    for building in fixture["buildings"]:
        cluster_id = building["cluster_id"]
        ring = building["footprint"]
        min_x = min(point[0] for point in ring)
        max_x = max(point[0] for point in ring)
        min_y = min(point[1] for point in ring)
        max_y = max(point[1] for point in ring)
        x = np.arange(min_x + 0.175, max_x, 0.35)
        y = np.arange(min_y + 0.175, max_y, 0.35)
        xx, yy = np.meshgrid(x, y)
        if building["roof"]["kind"] == "gable":
            zz = (
                building["roof"]["ridge_z"]
                - building["roof"]["slope"] * np.abs(xx)
            )
        else:
            zz = np.full_like(xx, building["roof"]["height"])
        points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
        all_points.append(points)
        all_labels.append(np.full(len(points), cluster_id, dtype=np.int32))
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "cluster_id": cluster_id,
                    "unique_id": building["unique_id"],
                    "footprint_provenance": "open_city_footprint",
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
        rows.append(
            {
                "tile_id": fixture["tile_id"],
                "cluster_id": cluster_id,
                "centroid_x": (min_x + max_x) / 2,
                "centroid_y": (min_y + max_y) / 2,
                "footprint_area_m2": (max_x - min_x) * (max_y - min_y),
                "ground_z": building["ground_z"],
                "height_p90": float(np.percentile(points[:, 2], 90)),
                "estimated_height": float(
                    np.percentile(points[:, 2], 90) - building["ground_z"]
                ),
                "source_quality": "good",
                "point_count_inside": len(points),
            }
        )

    points = np.vstack(all_points)
    labels = np.concatenate(all_labels)
    np.savez_compressed(
        tile / "clusters/building_clusters.npz",
        X=points[:, 0],
        Y=points[:, 1],
        Z=points[:, 2],
        cluster_id=labels,
    )
    (tile / "footprints" / f"{fixture['tile_id']}_footprints_convex_32617.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    with (tile / "masses" / f"{fixture['tile_id']}_masses_metadata.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (tile / "blender_ready" / f"{fixture['tile_id']}_glb_offset.json").write_text(
        json.dumps(fixture["offset"]), encoding="utf-8"
    )
    (tile / "blender_ready" / f"{fixture['tile_id']}.glb").write_bytes(
        minimal_glb(
            [
                smoke.cluster_qualified_id(fixture["tile_id"], building["cluster_id"])
                for building in fixture["buildings"]
            ]
        )
    )
    return tile, fixture


def run(tile: Path, output: Path) -> dict:
    return smoke.execute(
        tile_dir=tile,
        output_dir=output,
        crs="EPSG:32617",
        requested_building_id=None,
        footprint_id_namespace=FOOTPRINT_NAMESPACE,
        max_candidates=25,
        emit_svg=True,
        emit_obj=True,
    )


def test_fixture_selects_first_supported_real_contract_building(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    output = tmp_path / "diagnostic"
    payload = run(tile, output)

    expected_id = "MDC_FIXTURE_3"
    assert payload["manifest"]["identity"] == {
        "building_id": expected_id,
        "building_id_namespace": FOOTPRINT_NAMESPACE,
        "identity_source": "footprint_unique_id",
        "source_cluster_id": 3,
        "glb_node": f"bld_{fixture['tile_id']}_3",
        "canonical_identity_claimed": False,
    }
    assert payload["result"]["eligibility"]["eligible"] is True
    assert payload["result"]["flags"]["diagnostic_only"] is True
    assert payload["result"]["flags"]["canonical"] is False
    assert payload["manifest"]["coordinate_reference"]["crs"] == "EPSG:32617"
    assert (
        payload["manifest"]["coordinate_reference"][
            "glb_offset_recorded_not_applied"
        ]
        == {"crs": fixture["crs"], **fixture["offset"]}
    )
    roles = {source["role"] for source in payload["manifest"]["sources"]}
    assert roles == {"clusters", "footprints", "masses", "offset", "glb"}
    assert all(len(source["sha256"]) == 64 for source in payload["manifest"]["sources"])
    assert list(output.glob("*.svg"))
    assert list(output.glob("*.obj"))
    assert not list(output.rglob("*.glb"))


def test_result_is_schema_valid_and_byte_identical_on_repeat(tmp_path: Path):
    import jsonschema

    tile, fixture = materialize_tile(tmp_path)
    output = tmp_path / "repeatable"
    run(tile, output)
    result_path = output / "MDC_FIXTURE_3_roof_diagnostic.json"
    first = result_path.read_bytes()
    manifest_first = (output / "roof_real_data_smoke_manifest.json").read_bytes()
    shutil.rmtree(output)
    run(tile, output)
    second = result_path.read_bytes()
    manifest_second = (output / "roof_real_data_smoke_manifest.json").read_bytes()

    assert first == second
    assert manifest_first == manifest_second
    schema = json.loads(
        (REPO_ROOT / "schemas/roof_diagnostic_geometry.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft7Validator(schema).validate(json.loads(first))


def test_explicit_building_can_return_structured_rejection(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    building_id = "MDC_FIXTURE_8"
    payload = smoke.execute(
        tile_dir=tile,
        output_dir=tmp_path / "flat_rejection",
        crs="EPSG:32617",
        requested_building_id=building_id,
        footprint_id_namespace=FOOTPRINT_NAMESPACE,
        max_candidates=1,
        emit_svg=True,
        emit_obj=True,
    )

    assert payload["result"]["geometry"] is None
    assert payload["result"]["eligibility"]["eligible"] is False
    assert payload["manifest"]["result"]["rejection_reasons"]
    assert not list((tmp_path / "flat_rejection").glob("*.svg"))
    assert not list((tmp_path / "flat_rejection").glob("*.obj"))


def test_deterministic_candidate_order_and_qualified_ids(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    paths = smoke.discover(tile, fixture["crs"])
    candidates = smoke.candidates(
        tile.name,
        paths["footprints"],
        paths["masses"],
        paths["clusters"],
        FOOTPRINT_NAMESPACE,
        paths["glb"],
    )

    assert [candidate["cluster_id"] for candidate in candidates] == [3, 8]
    assert [candidate["building_id"] for candidate in candidates] == [
        "MDC_FIXTURE_3",
        "MDC_FIXTURE_8",
    ]
    assert all(not candidate["building_id"].isdigit() for candidate in candidates)


def test_missing_inputs_and_source_output_alias_fail(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    (tile / "masses" / f"{fixture['tile_id']}_masses_metadata.csv").unlink()
    with pytest.raises(smoke.SmokeInputError, match="missing required"):
        smoke.discover(tile, fixture["crs"])

    tile, _ = materialize_tile(tmp_path / "second")
    with pytest.raises(smoke.SmokeInputError, match="canonical city root"):
        smoke.execute(
            tile_dir=tile,
            output_dir=tile / "diagnostic",
            crs="EPSG:32617",
            requested_building_id=None,
            footprint_id_namespace=FOOTPRINT_NAMESPACE,
            max_candidates=25,
            emit_svg=False,
            emit_obj=False,
        )


def test_nonempty_output_and_candidate_limit_fail(tmp_path: Path):
    tile, _ = materialize_tile(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "preserve.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(smoke.SmokeInputError, match="nonempty"):
        run(tile, output)
    assert (output / "preserve.txt").read_text(encoding="utf-8") == "preserve"
    with pytest.raises(smoke.SmokeInputError, match="between 1 and 25"):
        smoke.execute(
            tile_dir=tile,
            output_dir=tmp_path / "too_many",
            crs="EPSG:32617",
            requested_building_id=None,
            footprint_id_namespace=FOOTPRINT_NAMESPACE,
            max_candidates=26,
            emit_svg=False,
            emit_obj=False,
        )


def test_cli_missing_mount_fails_without_outputs(tmp_path: Path):
    output = tmp_path / "not_created"
    code = smoke.main(
        [
            "--tile-dir", "/mnt/e/definitely-not-mounted/tile",
            "--output-dir", str(output),
            "--crs", "EPSG:32617",
        ]
    )

    assert code == 2
    assert not output.exists()


def test_stable_footprint_id_requires_explicit_namespace(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    paths = smoke.discover(tile, fixture["crs"])

    with pytest.raises(smoke.SmokeInputError, match="footprint-id-namespace"):
        smoke.candidates(
            tile.name,
            paths["footprints"],
            paths["masses"],
            paths["clusters"],
            None,
            paths["glb"],
        )


def test_cluster_identity_is_only_a_declared_fallback(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    footprint_path = (
        tile
        / "footprints"
        / f"{fixture['tile_id']}_footprints_convex_32617.geojson"
    )
    payload = json.loads(footprint_path.read_text(encoding="utf-8"))
    for feature in payload["features"]:
        feature["properties"].pop("unique_id")
    footprint_path.write_text(json.dumps(payload), encoding="utf-8")
    paths = smoke.discover(tile, fixture["crs"])
    found = smoke.candidates(
        tile.name,
        paths["footprints"],
        paths["masses"],
        paths["clusters"],
        None,
        paths["glb"],
    )

    assert found[0]["building_id"] == f"bld_{tile.name}_3"
    assert found[0]["building_id_namespace"] == smoke.CLUSTER_IDENTITY_NAMESPACE
    assert found[0]["identity_source"] == "tile_cluster_fallback"


def test_duplicate_and_missing_joins_fail_explicitly(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    masses = tile / "masses" / f"{fixture['tile_id']}_masses_metadata.csv"
    lines = masses.read_text(encoding="utf-8").splitlines()
    masses.write_text("\n".join(lines + [lines[1]]) + "\n", encoding="utf-8")
    paths = smoke.discover(tile, fixture["crs"])
    with pytest.raises(smoke.SmokeInputError, match="duplicate masses"):
        smoke.candidates(
            tile.name,
            paths["footprints"],
            paths["masses"],
            paths["clusters"],
            FOOTPRINT_NAMESPACE,
            paths["glb"],
        )

    tile, fixture = materialize_tile(tmp_path / "missing")
    footprint_path = (
        tile
        / "footprints"
        / f"{fixture['tile_id']}_footprints_convex_32617.geojson"
    )
    payload = json.loads(footprint_path.read_text(encoding="utf-8"))
    payload["features"][0]["properties"]["cluster_id"] = 999
    footprint_path.write_text(json.dumps(payload), encoding="utf-8")
    paths = smoke.discover(tile, fixture["crs"])
    with pytest.raises(smoke.SmokeInputError, match="missing masses"):
        smoke.candidates(
            tile.name,
            paths["footprints"],
            paths["masses"],
            paths["clusters"],
            FOOTPRINT_NAMESPACE,
            paths["glb"],
        )


def test_crs_offset_and_glb_identity_are_validated(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    with pytest.raises(smoke.SmokeInputError, match="projected-meter"):
        smoke.discover(tile, "EPSG:4326")
    with pytest.raises(smoke.SmokeInputError, match="EPSG"):
        smoke.discover(tile, "32617")

    offset = tile / "blender_ready" / f"{fixture['tile_id']}_glb_offset.json"
    offset.write_text(
        json.dumps({"crs": "EPSG:32616", **fixture["offset"]}),
        encoding="utf-8",
    )
    paths = smoke.discover(tile, fixture["crs"])
    with pytest.raises(smoke.SmokeInputError, match="does not match"):
        smoke._offset_record(paths["offset"], fixture["crs"])

    offset.write_text(json.dumps(fixture["offset"]), encoding="utf-8")
    glb = tile / "blender_ready" / f"{fixture['tile_id']}.glb"
    glb.write_bytes(minimal_glb(["wrong_node"]))
    paths = smoke.discover(tile, fixture["crs"])
    with pytest.raises(smoke.SmokeInputError, match="GLB node missing"):
        smoke.candidates(
            tile.name,
            paths["footprints"],
            paths["masses"],
            paths["clusters"],
            FOOTPRINT_NAMESPACE,
            paths["glb"],
        )


def test_npz_validation_rejects_empty_and_nonfinite_points(tmp_path: Path):
    tile, fixture = materialize_tile(tmp_path)
    clusters = tile / "clusters/building_clusters.npz"
    np.savez_compressed(
        clusters,
        X=np.array([], dtype=float),
        Y=np.array([], dtype=float),
        Z=np.array([], dtype=float),
        cluster_id=np.array([], dtype=int),
    )
    with pytest.raises(smoke.SmokeInputError, match="no points"):
        smoke._cluster_counts(clusters)

    np.savez_compressed(
        clusters,
        X=np.array([np.nan]),
        Y=np.array([0.0]),
        Z=np.array([1.0]),
        cluster_id=np.array([3]),
    )
    with pytest.raises(smoke.SmokeInputError, match="nonfinite"):
        smoke._cluster_counts(clusters)


def test_existing_empty_directory_city_root_and_symlink_escape_fail(tmp_path: Path):
    tile, _ = materialize_tile(tmp_path / "fixture")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(smoke.SmokeInputError, match="existing output"):
        run(tile, empty)

    city_root = tmp_path / "city"
    real_tile = city_root / "tiles" / tile.name
    real_tile.parent.mkdir(parents=True)
    shutil.copytree(tile, real_tile)
    with pytest.raises(smoke.SmokeInputError, match="canonical city root"):
        run(real_tile, city_root / "diagnostic")

    link = tmp_path / "source_link"
    link.symlink_to(real_tile, target_is_directory=True)
    with pytest.raises(smoke.SmokeInputError, match="canonical city root"):
        run(real_tile, link / "diagnostic")


def test_all_emitted_files_are_host_path_independent(tmp_path: Path):
    first_tile, _ = materialize_tile(tmp_path / "host_a")
    second_tile = tmp_path / "host_b" / "source" / first_tile.name
    second_tile.parent.mkdir(parents=True)
    shutil.copytree(first_tile, second_tile)
    first_output = tmp_path / "out_a"
    second_output = tmp_path / "out_b"

    run(first_tile, first_output)
    run(second_tile, second_output)
    first_files = {
        path.relative_to(first_output): path.read_bytes()
        for path in first_output.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second_output): path.read_bytes()
        for path in second_output.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_cli_writes_structured_rejection_for_invalid_polygon_and_crs(
    tmp_path: Path,
):
    tile, fixture = materialize_tile(tmp_path)
    footprint_path = (
        tile
        / "footprints"
        / f"{fixture['tile_id']}_footprints_convex_32617.geojson"
    )
    payload = json.loads(footprint_path.read_text(encoding="utf-8"))
    payload["features"][0]["geometry"]["coordinates"] = [
        [[0, 0], [5, 5], [0, 5], [5, 0], [0, 0]]
    ]
    footprint_path.write_text(json.dumps(payload), encoding="utf-8")
    invalid_output = tmp_path / "invalid_polygon"
    code = smoke.main(
        [
            "--tile-dir", str(tile),
            "--output-dir", str(invalid_output),
            "--crs", fixture["crs"],
            "--footprint-id-namespace", FOOTPRINT_NAMESPACE,
            "--building-id", "MDC_FIXTURE_3",
        ]
    )
    rejection = json.loads(
        (invalid_output / "roof_real_data_smoke_rejection.json").read_text(
            encoding="utf-8"
        )
    )
    assert code == 2
    assert rejection["status"] == "rejected"
    assert rejection["geometry"] is None
    assert rejection["rejection_reasons"]

    tile, fixture = materialize_tile(tmp_path / "crs")
    crs_output = tmp_path / "invalid_crs"
    code = smoke.main(
        [
            "--tile-dir", str(tile),
            "--output-dir", str(crs_output),
            "--crs", "EPSG:4326",
            "--footprint-id-namespace", FOOTPRINT_NAMESPACE,
        ]
    )
    rejection = json.loads(
        (crs_output / "roof_real_data_smoke_rejection.json").read_text(
            encoding="utf-8"
        )
    )
    assert code == 2
    assert rejection["status"] == "rejected"
    assert "projected-meter" in rejection["rejection_reasons"][0]
