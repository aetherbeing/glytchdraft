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
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "miami_city_config"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "miami_city_config"


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
    assert "include-pattern" in result.stdout.lower()
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


# ── LAZ scanning ──────────────────────────────────────────────────────────────

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


# ── _major_project grouping ───────────────────────────────────────────────────

def test_major_project_sequential_tiles():
    from scripts.new_orleans_build_catalog import _major_project
    # ARRA sequential tiles
    assert _major_project("USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001.laz") == "ARRA_LA_COASTAL_Z16_2011"
    assert _major_project("USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000197.laz") == "ARRA_LA_COASTAL_Z16_2011"


def test_major_project_coordinate_grid():
    from scripts.new_orleans_build_catalog import _major_project
    # GreaterNewOrleans west/north coordinate tile IDs
    assert _major_project("USGS_LPC_LA_2021GreaterNewOrleans_C22_w0775n3318.laz") == "LA_2021GreaterNewOrleans_C22"
    assert _major_project("USGS_LPC_LA_2021GreaterNewOrleans_C22_w0788n3316.laz") == "LA_2021GreaterNewOrleans_C22"


def test_major_project_usgs_grid_id():
    from scripts.new_orleans_build_catalog import _major_project
    # FloridaParishes USGS 100k grid IDs
    assert _major_project("USGS_LPC_LA_2021FloridaParishes_C24_16RBU0745.laz") == "LA_2021FloridaParishes_C24"
    assert _major_project("USGS_LPC_LA_2021FloridaParishes_C24_16RBU1043.laz") == "LA_2021FloridaParishes_C24"
    # Barataria grid IDs
    assert _major_project("USGS_LPC_Barataria_and_Jean_Lafitte_LiDAR_15RYP8607.laz") == "Barataria_and_Jean_Lafitte_LiDAR"
    assert _major_project("USGS_LPC_Barataria_and_Jean_Lafitte_LiDAR_16RBU8907.laz") == "Barataria_and_Jean_Lafitte_LiDAR"


def test_major_project_double_extension():
    from scripts.new_orleans_build_catalog import _major_project
    # .laz.laz download artifact
    assert _major_project("USGS_LPC_Barataria_and_Jean_Lafitte_LiDAR_000100.laz.laz") == "Barataria_and_Jean_Lafitte_LiDAR"
    assert _major_project("USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001.laz.laz") == "ARRA_LA_COASTAL_Z16_2011"


# ── build_catalog ─────────────────────────────────────────────────────────────

def _make_cfg(tmp_path: Path) -> dict:
    return {
        "city_slug": "test",
        "laz_dir": str(tmp_path / "laz"),
        "output_root": str(tmp_path / "out"),
        "tile_manifest": str(tmp_path / "out" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "out" / "metadata" / "city_manifest.json"),
        "output_epsg": 32615,
        "keep_raw_laz": True,
    }


def test_build_catalog_unfiltered(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"USGS_LPC_PROJ_A_{i:06d}.laz").write_bytes(b"x" * 512)
    for i in range(2):
        (laz_dir / f"USGS_LPC_PROJ_B_{i:06d}.laz").write_bytes(b"x" * 512)

    cfg = _make_cfg(tmp_path)
    catalog = build_catalog(cfg, laz_dir=laz_dir)

    assert catalog["laz_count_total"] == 5
    assert catalog["laz_count_selected"] == 5
    assert catalog["filter_patterns"] is None
    assert catalog["major_groups"]["PROJ_A"] == 3
    assert catalog["major_groups"]["PROJ_B"] == 2
    assert len(catalog["files"]) == 5
    assert catalog["keep_raw_laz"] is True
    assert catalog["first_file"] is not None


def test_build_catalog_filtered(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"USGS_LPC_PROJ_A_{i:06d}.laz").write_bytes(b"x" * 512)
    for i in range(2):
        (laz_dir / f"USGS_LPC_PROJ_B_{i:06d}.laz").write_bytes(b"x" * 512)

    cfg = _make_cfg(tmp_path)
    catalog = build_catalog(cfg, laz_dir=laz_dir, include_patterns=["PROJ_A"])

    assert catalog["laz_count_total"] == 5
    assert catalog["laz_count_selected"] == 3
    assert catalog["filter_patterns"] == ["PROJ_A"]
    assert catalog["selected_groups"]["PROJ_A"] == 3
    assert "PROJ_B" not in catalog["selected_groups"]
    assert len(catalog["files"]) == 3
    assert all("PROJ_A" in f for f in catalog["files"])
    assert "suggested_catalog_path" in catalog


def test_build_catalog_filter_no_match(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    (laz_dir / "USGS_LPC_PROJ_A_000001.laz").write_bytes(b"x" * 512)

    cfg = _make_cfg(tmp_path)
    catalog = build_catalog(cfg, laz_dir=laz_dir, include_patterns=["PROJ_Z"])

    assert catalog["laz_count_selected"] == 0
    assert catalog["files"] == []


def test_build_catalog_filter_case_insensitive(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(2):
        (laz_dir / f"USGS_LPC_GreaterNewOrleans_C22_w077{i}n3318.laz").write_bytes(b"x" * 512)

    cfg = _make_cfg(tmp_path)
    catalog = build_catalog(cfg, laz_dir=laz_dir, include_patterns=["greaternewOrleans"])

    assert catalog["laz_count_selected"] == 2


def test_build_catalog_multi_pattern(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(2):
        (laz_dir / f"USGS_LPC_PROJ_A_{i:06d}.laz").write_bytes(b"x" * 512)
    for i in range(2):
        (laz_dir / f"USGS_LPC_PROJ_B_{i:06d}.laz").write_bytes(b"x" * 512)
    (laz_dir / "USGS_LPC_PROJ_C_000001.laz").write_bytes(b"x" * 512)

    cfg = _make_cfg(tmp_path)
    catalog = build_catalog(cfg, laz_dir=laz_dir, include_patterns=["PROJ_A", "PROJ_B"])

    assert catalog["laz_count_selected"] == 4


# ── dry-run via subprocess ────────────────────────────────────────────────────

def _make_subprocess_cfg(tmp_path: Path, laz_dir: Path) -> Path:
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
    p = tmp_path / "nola_test.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def test_dry_run_no_output_written(tmp_path):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(4):
        (laz_dir / f"USGS_LPC_NOLA_2022_{i:06d}.laz").write_bytes(b"0" * 100)
    cfg_path = _make_subprocess_cfg(tmp_path, laz_dir)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(cfg_path), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "dry run" in (result.stdout + result.stderr).lower()
    assert not any((tmp_path / "out").rglob("*.json"))


def test_include_pattern_dry_run(tmp_path):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"USGS_LPC_GreaterNOLA_C22_w077{i}n3318.laz").write_bytes(b"0" * 100)
    for i in range(2):
        (laz_dir / f"USGS_LPC_ARRA_2011_{i:06d}.laz").write_bytes(b"0" * 100)
    cfg_path = _make_subprocess_cfg(tmp_path, laz_dir)

    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--config", str(cfg_path),
         "--include-pattern", "GreaterNOLA",
         "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "dry run" in output.lower()
    # selected count visible in report
    assert "3" in output


def test_include_pattern_writes_catalog(tmp_path):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"USGS_LPC_GreaterNOLA_C22_w077{i}n3318.laz").write_bytes(b"0" * 100)
    for i in range(2):
        (laz_dir / f"USGS_LPC_ARRA_2011_{i:06d}.laz").write_bytes(b"0" * 100)
    cfg_path = _make_subprocess_cfg(tmp_path, laz_dir)
    out_path = tmp_path / "filtered.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--config", str(cfg_path),
         "--include-pattern", "GreaterNOLA",
         "--output", str(out_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["laz_count_selected"] == 3
    assert data["laz_count_total"] == 5
    assert data["filter_patterns"] == ["GreaterNOLA"]
    assert len(data["files"]) == 3
    assert all("GreaterNOLA" in f for f in data["files"])
