from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
COMMON_DIR = REPO_ROOT / "scripts" / "common"
sys.path.insert(0, str(PHASES_DIR))
sys.path.insert(0, str(COMMON_DIR))

import phase_00_validate_config as phase00
from ingest_addresses import run_for_city


def write_config(tmp_path: Path, **overrides) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    output_root = tmp_path / "processed" / "detroit"
    cfg = {
        "city_slug": "detroit_test",
        "display_name": "Detroit Test",
        "laz_dir": str(laz_dir),
        "tiles_root": str(output_root / "tiles"),
        "output_root": str(output_root),
        "tile_manifest": str(output_root / "tile_manifest.json"),
        "city_manifest": str(output_root / "metadata" / "detroit_manifest.json"),
        "output_epsg": 32617,
        "bbox_4326": {"xmin": -83.35, "ymin": 42.25, "xmax": -82.90, "ymax": 42.45},
        "address_source": {
            "path": str(tmp_path / "missing_addresses.geojson"),
            "source_name": "City of Detroit Address Points",
            "input_crs": "EPSG:4326",
            "field_map": {"street": "StreetName"},
        },
        "keep_raw_laz": True,
    }
    cfg.update(overrides)
    path = tmp_path / "detroit.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def test_detroit_missing_address_source_passes_phase00_with_warning(tmp_path):
    config = write_config(tmp_path)

    rc = phase00.main(["--city", str(config), "--execute"])

    assert rc == 0
    status_path = tmp_path / "processed" / "detroit" / "status" / "phase_00.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "complete"
    assert status["details"]["address_source_missing"] is True
    assert status["details"]["address_source_path"] == str(tmp_path / "missing_addresses.geojson")
    assert status["details"]["warning"] == "Address source missing; address enrichment will be skipped."
    assert any("address source file does not exist" in warning for warning in status["warnings"])


def test_missing_laz_dir_still_fails(tmp_path):
    config = write_config(tmp_path, laz_dir=str(tmp_path / "does_not_exist"))

    rc = phase00.main(["--city", str(config), "--dry-run"])

    assert rc == 1


def test_missing_bbox_or_output_epsg_still_fails(tmp_path):
    missing_epsg = write_config(tmp_path / "epsg", output_epsg=None)
    missing_bbox = write_config(tmp_path / "bbox", bbox_4326={})

    assert phase00.main(["--city", str(missing_epsg), "--dry-run"]) == 1
    assert phase00.main(["--city", str(missing_bbox), "--dry-run"]) == 1


def test_strict_address_mode_fails_when_address_source_missing(tmp_path):
    config = write_config(tmp_path)

    rc = phase00.main(["--city", str(config), "--dry-run", "--require-addresses"])

    assert rc == 1


def test_config_strict_address_mode_fails_when_address_source_missing(tmp_path):
    config = write_config(tmp_path, require_addresses=True)

    rc = phase00.main(["--city", str(config), "--dry-run"])

    assert rc == 1


def test_address_enrichment_skips_missing_source_without_fake_output(tmp_path, capsys):
    output_root = tmp_path / "processed"
    cfg = SimpleNamespace(
        city_id="detroit_test",
        output_root=output_root,
        address_points=output_root / "metadata" / "address_points.geojson",
        address_source={"path": str(tmp_path / "missing_addresses.geojson")},
    )

    ok, count = run_for_city(cfg, 32617)

    captured = capsys.readouterr()
    assert ok is True
    assert count == 0
    assert "Address source missing; skipping address enrichment." in captured.out
    assert not cfg.address_points.exists()
