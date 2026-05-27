from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
sys.path.insert(0, str(PHASES_DIR))

import audit_city_pipeline as audit  # noqa: E402


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_geojson(path: Path, features: list[dict]) -> Path:
    return write_json(path, {"type": "FeatureCollection", "features": features})


def feature(tile_id: str | None = None) -> dict:
    props = {"tile_id": tile_id} if tile_id else {}
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [0, 0]},
        "properties": props,
    }


def write_mass_csv(path: Path, rows: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["tile_id,cluster_id,estimated_height\n"]
    lines.extend(f"{path.parent.parent.name},{idx},10\n" for idx in range(rows))
    path.write_text("".join(lines), encoding="utf-8")
    return path


@pytest.fixture()
def fake_city(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "city"
    city = SimpleNamespace(
        requested_city="miami",
        display_name="Miami Test",
        output_root=root,
        tiles_root=root / "tiles",
        metadata_dir=root / "metadata",
        audit_dir=root / "audit",
        tile_manifest=root / "tile_manifest.json",
        city_manifest=root / "metadata" / "miami_city_manifest.json",
        address_points=root / "metadata" / "address_points.geojson",
        structures_enriched=root / "metadata" / "structures_enriched.geojson",
        laz_dir=tmp_path / "raw_laz",
        address_source={"path": str(tmp_path / "addresses.geojson"), "field_map": {"full_address": "addr"}, "input_crs": "EPSG:4326"},
        address_join_radius_m=100.0,
        preserve_raw_laz=True,
        out_epsg=32617,
        bbox_4326={"xmin": -80.3, "ymin": 25.7, "xmax": -80.1, "ymax": 25.9},
        raw_config=SimpleNamespace(DBSCAN_EPS=3.0, DBSCAN_MIN_SAMPLES=10),
    )
    monkeypatch.setattr(audit, "load_city", lambda city_name: city)
    monkeypatch.setattr(audit, "validate_city_config", lambda city: ([], []))
    return city


def create_base_city(city, manifest_tiles: dict) -> None:
    city.laz_dir.mkdir(parents=True, exist_ok=True)
    (city.laz_dir / "tile_a.laz").write_bytes(b"laz")
    write_json(city.tile_manifest, {"tiles": [{"tile_id": "tile_a", "laz_filename": "tile_a.laz"}]})
    write_json(
        city.city_manifest,
        {
            "schema_version": "1.0",
            "city_id": "miami_city",
            "tiles": manifest_tiles,
        },
    )
    write_json(city.metadata_dir / "index.json", {"ok": True})
    write_geojson(city.address_points, [feature()])
    (city.output_root / "blender_ready").mkdir(parents=True, exist_ok=True)
    (city.output_root / "blender_ready" / "city.glb").write_bytes(b"glb")


def create_tile_outputs(city, tile_id: str, *, mass_rows: int = 0, footprint_count: int = 0, structures: int = 0, glb: bool = False) -> None:
    tile_dir = city.tiles_root / tile_id
    (tile_dir / "pointcloud").mkdir(parents=True, exist_ok=True)
    write_json(tile_dir / "manifest" / f"{tile_id}_manifest.json", {"tile_id": tile_id})
    if mass_rows:
        write_mass_csv(tile_dir / "masses" / f"{tile_id}_masses_metadata.csv", mass_rows)
        (tile_dir / "masses" / f"{tile_id}_LOD0_convexhull.obj").write_text("o mesh\n", encoding="utf-8")
    if footprint_count:
        write_geojson(tile_dir / "footprints" / f"{tile_id}_footprints_convex_32617.geojson", [feature() for _ in range(footprint_count)])
    if glb:
        (tile_dir / "blender_ready").mkdir(parents=True, exist_ok=True)
        (tile_dir / "blender_ready" / f"{tile_id}.glb").write_bytes(b"glb")
    if structures:
        write_geojson(city.structures_enriched, [feature(tile_id) for _ in range(structures)])


def zero_manifest() -> dict:
    return {"n_clusters": 0, "n_footprints": 0, "lod0_count": 0, "lod1_count": 0, "errors": {}}


def test_tile_with_outputs_is_not_treated_as_true_zero_when_manifest_is_stale(fake_city):
    create_base_city(fake_city, {"tile_a": zero_manifest()})
    create_tile_outputs(fake_city, "tile_a", mass_rows=2, footprint_count=2, structures=2, glb=True)

    result = audit.classify_zero_building_tile(
        "tile_a",
        fake_city.tiles_root / "tile_a",
        zero_manifest(),
        {"tile_a": 2},
        fake_city.out_epsg,
    )

    assert result["classification"] == "suspicious_manifest_false_positive"
    assert result["expected_zero"] is False
    assert result["mass_metadata_rows"] == 2
    assert result["footprint_features"] == 2
    assert result["structure_records"] == 2


def test_stale_zero_manifest_with_non_empty_supporting_outputs_is_flagged(fake_city):
    create_base_city(fake_city, {"tile_a": zero_manifest()})
    create_tile_outputs(fake_city, "tile_a", mass_rows=1, footprint_count=0, structures=0, glb=False)

    consistency = audit.zero_building_consistency(json.loads(fake_city.city_manifest.read_text()), fake_city)

    assert len(consistency["suspicious"]) == 1
    assert consistency["suspicious"][0]["classification"] == "suspicious_manifest_false_positive"


def test_manifest_zero_with_empty_supporting_outputs_is_expected_zero(fake_city):
    create_base_city(fake_city, {"tile_a": zero_manifest()})
    create_tile_outputs(fake_city, "tile_a", mass_rows=0, footprint_count=0, structures=0, glb=False)
    write_geojson(fake_city.structures_enriched, [])

    consistency = audit.zero_building_consistency(json.loads(fake_city.city_manifest.read_text()), fake_city)

    assert consistency["suspicious"] == []
    assert len(consistency["expected_zero"]) == 1
    assert consistency["expected_zero"][0]["classification"] == "expected_zero"


def test_city_qa_aggregation_counts_suspicious_and_true_empty_separately(fake_city):
    create_base_city(fake_city, {"tile_a": zero_manifest(), "tile_b": zero_manifest()})
    create_tile_outputs(fake_city, "tile_a", mass_rows=3, footprint_count=1, structures=0, glb=True)
    create_tile_outputs(fake_city, "tile_b", mass_rows=0, footprint_count=0, structures=0, glb=False)
    write_geojson(fake_city.structures_enriched, [])

    code, lines, summary = audit.assess(argparse.Namespace(city="miami", json=False))

    assert code == 1
    assert summary["suspicious_zero_building_tiles"] == 1
    assert summary["expected_zero_building_tiles"] == 1
    assert any("WARN: zero-building manifest consistency - 1 suspicious false positive(s); 1 expected zero tile(s)" in line for line in lines)


def test_per_tile_glb_presence_is_reported(fake_city):
    create_base_city(fake_city, {"tile_a": zero_manifest()})
    create_tile_outputs(fake_city, "tile_a", mass_rows=0, footprint_count=0, structures=0, glb=True)
    write_geojson(fake_city.structures_enriched, [])

    result = audit.classify_zero_building_tile(
        "tile_a",
        fake_city.tiles_root / "tile_a",
        zero_manifest(),
        {},
        fake_city.out_epsg,
    )

    assert result["has_glb"] is True
    assert result["glb_paths"] == [str(fake_city.tiles_root / "tile_a" / "blender_ready" / "tile_a.glb")]
