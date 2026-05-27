from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "new_orleans_build_catalog.py"
NOLA_CONFIG = REPO_ROOT / "configs" / "cities" / "new_orleans.json"


# ── import safety ─────────────────────────────────────────────────────────────

def test_no_miami_city_config_import():
    """Script must not import miami_city_config."""
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "miami_city_config", (
                    "Script imports miami_city_config"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module != "miami_city_config", (
                "Script imports from miami_city_config"
            )


# ── --help ────────────────────────────────────────────────────────────────────

def test_help_exits_cleanly():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "dry-run" in result.stdout.lower()
    assert "config" in result.stdout.lower()


# ── config loading ────────────────────────────────────────────────────────────

def test_load_config_reads_nola_json():
    from scripts.new_orleans_build_catalog import load_config
    cfg = load_config(NOLA_CONFIG)
    assert cfg["city_slug"] == "new_orleans"
    assert "laz_dir" in cfg
    assert "output_root" in cfg


def test_load_config_missing_raises(tmp_path):
    import pytest
    from scripts.new_orleans_build_catalog import load_config
    with pytest.raises(SystemExit):
        load_config(tmp_path / "nonexistent.json")


def test_load_config_temp(tmp_path):
    cfg = {
        "schema_version": "1.0",
        "city_slug": "test_city",
        "laz_dir": str(tmp_path / "laz"),
        "output_root": str(tmp_path / "out"),
        "tile_manifest": str(tmp_path / "out" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "out" / "metadata" / "city_manifest.json"),
        "output_epsg": 32615,
        "keep_raw_laz": True,
    }
    config_path = tmp_path / "test_city.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")

    from scripts.new_orleans_build_catalog import load_config
    loaded = load_config(config_path)
    assert loaded["city_slug"] == "test_city"
    assert loaded["keep_raw_laz"] is True


# ── LAZ scanning and grouping ─────────────────────────────────────────────────

def test_scan_laz_empty_dir(tmp_path):
    from scripts.new_orleans_build_catalog import scan_laz
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    assert scan_laz(laz_dir) == []


def test_scan_laz_missing_dir(tmp_path):
    from scripts.new_orleans_build_catalog import scan_laz
    assert scan_laz(tmp_path / "no_such_dir") == []


def test_scan_laz_counts(tmp_path):
    from scripts.new_orleans_build_catalog import scan_laz
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(5):
        (laz_dir / f"PROJ_A_{i:06d}.laz").write_bytes(b"x" * 1024)
    (laz_dir / "not_a_laz.txt").write_text("ignore")
    files = scan_laz(laz_dir)
    assert len(files) == 5
    assert all(f.suffix == ".laz" for f in files)


def test_extract_project_strips_tile_index():
    from scripts.new_orleans_build_catalog import _extract_project
    assert _extract_project("ARRA_LA_COASTAL_Z16_2011_000001.laz") == "ARRA_LA_COASTAL_Z16_2011"
    assert _extract_project("LA_NOLA_2022_001234.laz") == "LA_NOLA_2022"


def test_extract_project_no_index():
    from scripts.new_orleans_build_catalog import _extract_project
    assert _extract_project("SOMEFILE.laz") == "SOMEFILE"


def test_extract_project_double_extension():
    from scripts.new_orleans_build_catalog import _extract_project
    assert _extract_project("USGS_LPC_Barataria_000100.laz.laz") == "USGS_LPC_Barataria"


def test_build_catalog_grouping(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"PROJ_A_{i:06d}.laz").write_bytes(b"x" * 512)
    for i in range(2):
        (laz_dir / f"PROJ_B_{i:06d}.laz").write_bytes(b"x" * 512)

    cfg = {
        "city_slug": "test",
        "laz_dir": str(laz_dir),
        "output_root": "/tmp/out",
        "tile_manifest": "/tmp/out/tile_manifest.json",
        "city_manifest": "/tmp/out/metadata/city_manifest.json",
        "output_epsg": 32615,
        "keep_raw_laz": True,
    }
    catalog = build_catalog(cfg, laz_dir=laz_dir)
    assert catalog["laz_count"] == 5
    assert catalog["project_groups"]["PROJ_A"] == 3
    assert catalog["project_groups"]["PROJ_B"] == 2
    assert catalog["keep_raw_laz"] is True
    assert catalog["first_file"] is not None
    assert catalog["last_file"] is not None


# ── dry-run via subprocess ────────────────────────────────────────────────────

def test_dry_run_with_temp_config(tmp_path):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(4):
        (laz_dir / f"NOLA_2022_{i:06d}.laz").write_bytes(b"0" * 100)

    cfg = {
        "schema_version": "1.0",
        "city_slug": "new_orleans_test",
        "laz_dir": str(laz_dir),
        "output_root": str(tmp_path / "out"),
        "tile_manifest": str(tmp_path / "out" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "out" / "metadata" / "city_manifest.json"),
        "output_epsg": 32615,
        "keep_raw_laz": True,
    }
    config_path = tmp_path / "nola_test.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(config_path), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "dry run" in output.lower()
