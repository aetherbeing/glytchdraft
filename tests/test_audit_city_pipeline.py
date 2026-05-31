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
                    "tile_id": f"tile_{idx}",
                    "match_status": "matched",
                    "nearest_address": "1 Test St",
                    "address_source": "Test Address Source",
                    "footprint_provenance": "open_city_footprint",
                }
            )
            for idx in range(tile_count)
        ]
        + [
            feature(
                {
                    "tile_id": "tile_0",
                    "match_status": "unmatched",
                    "nearest_address": None,
                    "address_source": None,
                    "footprint_provenance": "open_city_footprint",
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
    assert any("WARN: missing per-tile outputs - 1 building tile(s); tile_0: masses_obj,blender_ue_ready_export" in line for line in lines)


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


def test_zero_building_tile_missing_glb_does_not_block_certification(fake_city):
    """A zero-building tile without a GLB must not cause blocked_missing_outputs."""
    create_clean_outputs(fake_city)
    # Add a second tile that is explicitly zero-building (glb_exists: false in city manifest).
    zero_tile_id = "tile_zero"
    (fake_city.tiles_root / zero_tile_id / "pointcloud").mkdir(parents=True, exist_ok=True)
    (fake_city.tiles_root / zero_tile_id / "pointcloud" / f"{zero_tile_id}_ground.ply").write_text("ply")
    # City manifest declares this tile as glb_exists=false (zero buildings).
    write_json(
        fake_city.city_manifest,
        {
            "schema_version": "1.0",
            "city": fake_city.display_name,
            "city_glb_status": "skipped_oversize",
            "viewer_load_strategy": "tile_glbs",
            "tiles": {
                "tile_0": {"glb_exists": True},
                zero_tile_id: {"glb_exists": False},
            },
        },
    )

    _, lines, summary = run_assess()

    assert summary["certification_status"] != "blocked_missing_outputs", (
        f"zero-building tile should not block cert; got {summary['certification_status']!r}"
    )
    assert summary["zero_building_tiles"] >= 1
    assert summary["missing_output_building_tiles"] == 0


def test_non_empty_tile_missing_glb_still_warns(fake_city):
    """A building tile missing its GLB must appear in WARN and count as a missing output."""
    create_clean_outputs(fake_city)
    for path in (fake_city.tiles_root / "tile_0" / "blender_ready").glob("*.glb"):
        path.unlink()
    # No zero-building declaration in city manifest — tile_0 is a building tile.

    _, lines, summary = run_assess()

    assert summary["missing_output_building_tiles"] >= 1
    assert any("WARN: missing per-tile outputs" in line for line in lines)


def test_skipped_oversize_city_glb_does_not_block_when_tile_glbs_present(fake_city):
    """city_glb_status=skipped_oversize + viewer_load_strategy=tile_glbs → PASS, not WARN."""
    create_clean_outputs(fake_city)
    # Remove the city-level GLB so only per-tile GLBs exist.
    for path in (fake_city.output_root / "blender_ready").glob("*.glb"):
        path.unlink()
    write_json(
        fake_city.city_manifest,
        {
            "schema_version": "1.0",
            "city": fake_city.display_name,
            "city_glb_status": "skipped_oversize",
            "viewer_load_strategy": "tile_glbs",
        },
    )

    _, lines, summary = run_assess()

    # The export check must be PASS, not WARN or FAIL.
    assert any(
        "PASS: Blender/UE-ready exports" in line and "tile_glbs" in line
        for line in lines
    ), f"Expected PASS for skipped_oversize/tile_glbs, got: {[l for l in lines if 'export' in l.lower()]}"
    assert summary["blender_ready"] is True
    assert summary["viewer_ready"] is True


def test_certification_production_ready_when_all_building_tiles_have_outputs(fake_city):
    """All building tiles complete + valid footprint source → production_ready."""
    create_clean_outputs(fake_city)
    fake_city.raw_config = type(fake_city.raw_config)(
        DBSCAN_EPS=3.0,
        DBSCAN_MIN_SAMPLES=10,
        FOOTPRINT_SOURCE={"type": "open_city", "license": "public_domain", "production_allowed": True},
    )
    # City manifest with no zero-building tiles declared.
    write_json(fake_city.city_manifest, {"schema_version": "1.0", "city": fake_city.display_name})

    import audit_city_pipeline as audit_mod
    import phase_common as pc

    def fake_validate_production(city):
        return [], []

    original = audit_mod.__dict__.get("validate_footprint_production")
    audit_mod.validate_footprint_production = fake_validate_production
    try:
        _, _, summary = run_assess()
    finally:
        if original is not None:
            audit_mod.validate_footprint_production = original

    assert summary["missing_output_building_tiles"] == 0
    assert summary["certification_status"] in ("production_ready", "viewer_ready", "processed_complete"), (
        f"Expected a non-blocked status, got {summary['certification_status']!r}"
    )


def test_main_exit_code_clean_vs_failing_audits(fake_city, capsys):
    create_clean_outputs(fake_city)

    assert audit.main(["--city", "test_city"]) == 0
    clean_output = capsys.readouterr().out
    assert "Overall: PASS" in clean_output

    fake_city.city_manifest.unlink()

    assert audit.main(["--city", "test_city"]) == 1
    failing_output = capsys.readouterr().out
    assert "Overall: FAIL" in failing_output


# ── Provenance completeness tests ─────────────────────────────────────────────

def test_missing_provenance_in_structures_enriched_emits_fail(fake_city):
    """Structures without footprint_provenance must emit FAIL and block certification."""
    create_clean_outputs(fake_city)
    # Overwrite structures_enriched with one building that has no provenance field.
    write_geojson(
        fake_city.structures_enriched,
        [
            feature({
                "tile_id": "tile_0",
                "match_status": "matched",
                "full_address": "1 Test St",
                "address_source": "test",
                # footprint_provenance intentionally absent
            }),
        ],
    )

    code, lines, summary = run_assess()

    assert code == 2, "missing provenance must set overall status to FAIL"
    assert any("FAIL: structure footprint provenance" in line for line in lines), lines
    assert summary["missing_provenance_structure_count"] == 1
    assert summary["certification_status"] in (
        "blocked_missing_provenance", "blocked_stale_glb", "blocked_missing_outputs"
    )


def test_known_provenance_label_does_not_trigger_fail(fake_city):
    """Structures with a canonical footprint_provenance must not trigger the FAIL check."""
    create_clean_outputs(fake_city)
    write_geojson(
        fake_city.structures_enriched,
        [
            feature({
                "tile_id": "tile_0",
                "match_status": "matched",
                "full_address": "1 Test St",
                "address_source": "test",
                "footprint_provenance": "open_city_footprint",
            }),
        ],
    )

    _, lines, summary = run_assess()

    assert not any("FAIL: structure footprint provenance" in line for line in lines), lines
    assert summary["missing_provenance_structure_count"] == 0


# ── GLB freshness tests ───────────────────────────────────────────────────────

def test_orphaned_glb_emits_fail(fake_city):
    """A GLB that exists when masses manifest says lod0=0 must emit FAIL."""
    create_clean_outputs(fake_city)
    tile_dir = fake_city.tiles_root / "tile_0"
    # Overwrite the masses manifest to declare lod0=0 (OBJ is an empty stub).
    write_json(
        tile_dir / "manifest" / "tile_0_masses.json",
        {"tile_id": "tile_0", "lod0": 0, "lod1": 0},
    )
    # GLB still exists on disk (stale from a prior pipeline run).
    assert (tile_dir / "blender_ready" / "tile_0.glb").exists()

    code, lines, summary = run_assess()

    assert code == 2, "orphaned GLB must set overall status to FAIL"
    assert any("FAIL: orphaned GLBs" in line for line in lines), lines
    assert summary["orphaned_glb_count"] == 1
    assert "tile_0" in summary.get("orphaned_glb_tiles", [])


def test_stale_export_manifest_path_emits_fail(fake_city):
    """An export manifest whose GLB path does not exist on disk must emit FAIL."""
    create_clean_outputs(fake_city)
    tile_dir = fake_city.tiles_root / "tile_0"
    # Write an export manifest that points to a non-existent path.
    write_json(
        tile_dir / "manifest" / "tile_0_export.json",
        {
            "tile_id": "tile_0",
            "glb": "/mnt/old_drive/tile_0/blender_ready/tile_0.glb",
            "geometry_mode": "flat_quad_source_faces",
            "triangles": 1234,
            "vertices": 3702,
        },
    )
    # The actual GLB exists at the canonical location; the manifest path is stale.
    assert (tile_dir / "blender_ready" / "tile_0.glb").exists()
    # No masses manifest → orphaned check is skipped; only stale manifest fires.

    code, lines, summary = run_assess()

    assert code == 2, "stale export manifest must set overall status to FAIL"
    assert any("FAIL: stale export manifest paths" in line for line in lines), lines
    assert summary["stale_export_manifest_count"] == 1
    assert "tile_0" in summary.get("stale_export_manifest_tiles", [])


def test_zero_building_tile_no_glb_no_structures_is_ok(fake_city):
    """
    A tile declared as zero-building in the city manifest, with no GLB and no
    structures in structures_enriched, must not trigger any provenance or GLB FAIL.
    """
    create_clean_outputs(fake_city)
    # Add a second tile with no GLB, no masses, declared zero-building in manifest.
    zero_tile_id = "tile_zero_prov"
    (fake_city.tiles_root / zero_tile_id / "pointcloud").mkdir(parents=True, exist_ok=True)
    (fake_city.tiles_root / zero_tile_id / "pointcloud" / f"{zero_tile_id}_ground.ply").write_text("ply")
    write_json(
        fake_city.city_manifest,
        {
            "schema_version": "1.0",
            "city": fake_city.display_name,
            "city_glb_status": "skipped_oversize",
            "viewer_load_strategy": "tile_glbs",
            "tiles": {
                "tile_0": {"glb_exists": True},
                zero_tile_id: {"glb_exists": False},
            },
        },
    )
    # structures_enriched only has the building from tile_0 (with provenance).
    write_geojson(
        fake_city.structures_enriched,
        [feature({
            "tile_id": "tile_0",
            "match_status": "matched",
            "full_address": "1 Test St",
            "address_source": "test",
            "footprint_provenance": "open_city_footprint",
        })],
    )

    _, lines, summary = run_assess()

    assert not any("FAIL: structure footprint provenance" in line for line in lines), lines
    assert not any("FAIL: orphaned GLBs" in line for line in lines), lines
    assert summary["missing_provenance_structure_count"] == 0
    assert summary["orphaned_glb_count"] == 0
