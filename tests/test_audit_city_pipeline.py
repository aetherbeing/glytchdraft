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


def feature(props: dict | None = None) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [0, 0]},
        "properties": props or {},
    }


@pytest.fixture()
def fake_city(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "city"
    city = SimpleNamespace(
        requested_city="test_city",
        display_name="Test City",
        output_root=root,
        tiles_root=root / "tiles",
        metadata_dir=root / "metadata",
        audit_dir=root / "audit",
        tile_manifest=root / "tile_manifest.json",
        city_manifest=root / "metadata" / "city_manifest.json",
        address_points=root / "metadata" / "address_points.geojson",
        structures_enriched=root / "metadata" / "structures_enriched.geojson",
        laz_dir=tmp_path / "raw_laz",
        address_source={
            "path": str(tmp_path / "source_addresses.geojson"),
            "source_name": "Test Address Source",
            "input_crs": "EPSG:4326",
            "field_map": {"full_address": "addr"},
        },
        address_join_radius_m=100.0,
        preserve_raw_laz=True,
        out_epsg=32611,
        bbox_4326={"xmin": -1, "ymin": -1, "xmax": 1, "ymax": 1},
        raw_config=SimpleNamespace(DBSCAN_EPS=3.0, DBSCAN_MIN_SAMPLES=10),
    )

    monkeypatch.setattr(audit, "load_city", lambda city_name: city)
    monkeypatch.setattr(audit, "validate_city_config", lambda city: ([], []))
    return city


def create_clean_outputs(city, *, tile_count: int = 1) -> None:
    city.laz_dir.mkdir(parents=True, exist_ok=True)
    tiles = []
    for idx in range(tile_count):
        tile_id = f"tile_{idx}"
        laz_name = f"{tile_id}.laz"
        (city.laz_dir / laz_name).write_bytes(b"laz")
        tile_dir = city.tiles_root / tile_id
        (tile_dir / "pointcloud").mkdir(parents=True, exist_ok=True)
        (tile_dir / "pointcloud" / f"{tile_id}_ground.ply").write_text("ply", encoding="utf-8")
        write_geojson(tile_dir / "footprints" / f"{tile_id}_footprints_32611.geojson", [feature()])
        (tile_dir / "masses").mkdir(parents=True, exist_ok=True)
        (tile_dir / "masses" / f"{tile_id}.obj").write_text("o mesh\n", encoding="utf-8")
        (tile_dir / "blender_ready").mkdir(parents=True, exist_ok=True)
        (tile_dir / "blender_ready" / f"{tile_id}.glb").write_bytes(b"glb")
        write_json(tile_dir / "manifest" / f"{tile_id}_manifest.json", {"tile_id": tile_id})
        tiles.append({"tile_id": tile_id, "laz_filename": laz_name})

    write_json(city.tile_manifest, {"tiles": tiles})
    write_json(city.city_manifest, {"schema_version": "1.0", "city": city.display_name})
    write_json(city.metadata_dir / "index.json", {"ok": True})
    (city.output_root / "blender_ready").mkdir(parents=True, exist_ok=True)
    (city.output_root / "blender_ready" / "city.glb").write_bytes(b"glb")
    write_geojson(city.address_points, [feature({"source": "Test Address Source"})])
    write_geojson(
        city.structures_enriched,
        [
            feature(
                {
                    "match_status": "matched",
                    "nearest_address": "1 Test St",
                    "address_source": "Test Address Source",
                }
            ),
            feature(
                {
                    "match_status": "unmatched",
                    "nearest_address": None,
                    "address_source": None,
                }
            ),
        ],
    )


def run_assess(city_name: str = "test_city"):
    return audit.assess(argparse.Namespace(city=city_name, json=False))


def test_valid_city_manifest_is_pass(fake_city):
    create_clean_outputs(fake_city)

    _, lines, _ = run_assess()

    assert any(line == "PASS: city_manifest.json - valid JSON" for line in lines)


def test_missing_city_manifest_is_fail(fake_city):
    create_clean_outputs(fake_city)
    fake_city.city_manifest.unlink()

    code, lines, summary = run_assess()

    assert code == 2
    assert summary["status"] == "FAIL"
    assert any(line.startswith("FAIL: city_manifest.json - missing city manifest:") for line in lines)


def test_raw_laz_retention_count_is_detected(fake_city):
    create_clean_outputs(fake_city, tile_count=3)

    _, lines, summary = run_assess()

    assert summary["raw_laz_count"] == 3
    assert any("PASS: raw LAZ retained - 3 .laz file(s)" in line for line in lines)


def test_missing_raw_laz_files_reported_clearly(fake_city):
    create_clean_outputs(fake_city)
    for path in fake_city.laz_dir.glob("*.laz"):
        path.unlink()

    code, lines, _ = run_assess()

    assert code == 1
    assert any(line.startswith("WARN: raw LAZ retained - 0 .laz files") for line in lines)


def test_tile_directory_counts_are_detected(fake_city):
    create_clean_outputs(fake_city, tile_count=2)

    _, lines, summary = run_assess()

    assert summary["processed_tile_dirs"] == 2
    assert summary["tile_dirs"] == 2
    assert any("PASS: processed tile geometry - 2/2 tile dir(s)" in line for line in lines)


def test_missing_tile_mass_and_export_outputs_are_reported(fake_city):
    create_clean_outputs(fake_city)
    for path in (fake_city.tiles_root / "tile_0" / "masses").glob("*.obj"):
        path.unlink()
    for path in (fake_city.tiles_root / "tile_0" / "blender_ready").glob("*.glb"):
        path.unlink()

    _, lines, summary = run_assess()

    assert summary["missing_output_tiles"] == 1
    assert any("WARN: missing per-tile outputs - 1 tile(s); tile_0: masses_obj,blender_ue_ready_export" in line for line in lines)


def test_city_level_exports_are_detected(fake_city):
    create_clean_outputs(fake_city)

    _, lines, _ = run_assess()

    assert any("PASS: Blender/UE-ready exports - 1 city-level export file(s)" in line for line in lines)


def test_missing_address_points_is_reported(fake_city):
    create_clean_outputs(fake_city)
    fake_city.address_points.unlink()

    code, lines, _ = run_assess()

    assert code == 2
    assert any(line.startswith("FAIL: address_points.geojson -") for line in lines)


def test_structures_enriched_address_coverage_is_parsed(fake_city):
    create_clean_outputs(fake_city)

    _, lines, summary = run_assess()

    assert summary["address_coverage_pct"] == 50.0
    assert any("PASS: structure address coverage - 1/2 matched (50.0%)" in line for line in lines)


def test_missing_match_status_and_address_source_fields_warn(fake_city):
    create_clean_outputs(fake_city)
    write_geojson(
        fake_city.structures_enriched,
        [feature({"address_status": "matched", "nearest_address": "1 Test St"})],
    )

    _, lines, _ = run_assess()

    assert any(line.startswith("WARN: match_status field -") for line in lines)
    assert any(line.startswith("WARN: address provenance fields -") for line in lines)


def test_audit_output_includes_pass_warn_fail_labels(fake_city):
    create_clean_outputs(fake_city)
    fake_city.city_manifest.unlink()
    for path in fake_city.laz_dir.glob("*.laz"):
        path.unlink()

    _, lines, _ = run_assess()

    labels = {line.split(":", 1)[0] for line in lines}
    assert {"PASS", "WARN", "FAIL"} <= labels


def test_main_exit_code_clean_vs_failing_audits(fake_city, capsys):
    create_clean_outputs(fake_city)

    assert audit.main(["--city", "test_city"]) == 0
    clean_output = capsys.readouterr().out
    assert "Overall: PASS" in clean_output

    fake_city.city_manifest.unlink()

    assert audit.main(["--city", "test_city"]) == 1
    failing_output = capsys.readouterr().out
    assert "Overall: FAIL" in failing_output
