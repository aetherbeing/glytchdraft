from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
sys.path.insert(0, str(PHASES_DIR))

from phase_common import CATALOG_ENV_VAR, _laz_files_from_catalog, laz_files, load_city


def _write_catalog(path: Path, files: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1.0", "files": files, "count": len(files)}), encoding="utf-8")
    return path


def _fake_city(laz_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(laz_dir=laz_dir, catalog_path=None)


# ── CATALOG_ENV_VAR constant ──────────────────────────────────────────────────

def test_catalog_env_var_name():
    assert CATALOG_ENV_VAR == "GLITCHOS_LAZ_CATALOG"


# ── _laz_files_from_catalog ───────────────────────────────────────────────────

def test_laz_files_from_catalog_returns_existing(tmp_path):
    laz1 = tmp_path / "a.laz"
    laz2 = tmp_path / "b.laz"
    laz1.write_bytes(b"laz")
    laz2.write_bytes(b"laz")
    catalog = _write_catalog(tmp_path / "cat.json", [str(laz1), str(laz2)])

    result = _laz_files_from_catalog(catalog)

    assert result is not None
    assert set(result) == {laz1, laz2}


def test_laz_files_from_catalog_filters_missing_files(tmp_path):
    present = tmp_path / "present.laz"
    present.write_bytes(b"laz")
    catalog = _write_catalog(tmp_path / "cat.json", [str(present), str(tmp_path / "ghost.laz")])

    result = _laz_files_from_catalog(catalog)

    assert result == [present]


def test_laz_files_from_catalog_returns_none_for_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")

    assert _laz_files_from_catalog(bad) is None


def test_laz_files_from_catalog_returns_none_when_no_files_key(tmp_path):
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps({"tiles": []}), encoding="utf-8")

    assert _laz_files_from_catalog(cat) is None


def test_laz_files_from_catalog_returns_none_for_missing_catalog(tmp_path):
    assert _laz_files_from_catalog(tmp_path / "nonexistent.json") is None


# ── laz_files() with env var ──────────────────────────────────────────────────

def test_laz_files_uses_catalog_when_env_set(tmp_path, monkeypatch):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    selected = laz_dir / "catalog_tile.laz"
    excluded = laz_dir / "extra_tile.laz"
    selected.write_bytes(b"laz")
    excluded.write_bytes(b"laz")
    catalog = _write_catalog(tmp_path / "cat.json", [str(selected)])

    monkeypatch.setenv(CATALOG_ENV_VAR, str(catalog))
    result = laz_files(_fake_city(laz_dir))

    assert result == [selected]
    assert excluded not in result


def test_laz_files_falls_back_to_glob_without_env(tmp_path, monkeypatch):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    laz1 = laz_dir / "a.laz"
    laz2 = laz_dir / "b.laz"
    laz1.write_bytes(b"laz")
    laz2.write_bytes(b"laz")

    monkeypatch.delenv(CATALOG_ENV_VAR, raising=False)
    result = laz_files(_fake_city(laz_dir))

    assert sorted(result) == [laz1, laz2]


def test_laz_files_falls_back_to_glob_when_catalog_env_is_bad(tmp_path, monkeypatch):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    laz1 = laz_dir / "a.laz"
    laz1.write_bytes(b"laz")

    monkeypatch.setenv(CATALOG_ENV_VAR, str(tmp_path / "nonexistent.json"))
    result = laz_files(_fake_city(laz_dir))

    assert result == [laz1]


# ── load_city() with full JSON path ──────────────────────────────────────────

def test_load_city_accepts_absolute_json_path(tmp_path):
    config = {
        "city_slug": "test_city",
        "display_name": "Test City",
        "output_root": str(tmp_path / "output"),
        "tiles_root": str(tmp_path / "output" / "tiles"),
        "laz_dir": str(tmp_path / "laz"),
        "tile_manifest": str(tmp_path / "output" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "output" / "city_manifest.json"),
        "output_epsg": 32615,
        "bbox_4326": {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0},
    }
    cfg_path = tmp_path / "test_city.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    city = load_city(str(cfg_path))

    assert city.city_key == "test_city"
    assert city.display_name == "Test City"


def test_load_city_display_name_falls_back_to_slug(tmp_path):
    config = {
        "city_slug": "no_display_city",
        "output_root": str(tmp_path / "output"),
        "tiles_root": str(tmp_path / "output" / "tiles"),
        "laz_dir": str(tmp_path / "laz"),
        "tile_manifest": str(tmp_path / "output" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "output" / "city_manifest.json"),
        "output_epsg": 32615,
        "bbox_4326": {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0},
    }
    cfg_path = tmp_path / "no_display_city.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    city = load_city(str(cfg_path))

    assert city.display_name == "no_display_city"
    assert city.display_name != str(cfg_path)


# ── CLI smoke tests ───────────────────────────────────────────────────────────

def _run_pipeline(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_city_pipeline.py"), *args],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def test_run_pipeline_help_shows_catalog():
    result = _run_pipeline("--help")

    assert result.returncode == 0
    assert "--catalog" in result.stdout
    assert "--config" in result.stdout


def test_run_pipeline_dry_run_catalog_reports_count(tmp_path):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    for i in range(5):
        (laz_dir / f"tile_{i:03d}.laz").write_bytes(b"laz")
    (laz_dir / "excluded.laz").write_bytes(b"laz")  # not in catalog

    catalog_files = [str(laz_dir / f"tile_{i:03d}.laz") for i in range(5)]
    catalog = _write_catalog(tmp_path / "catalog.json", catalog_files)

    config = {
        "city_slug": "test_dry",
        "display_name": "Test Dry City",
        "output_root": str(tmp_path / "output"),
        "tiles_root": str(tmp_path / "output" / "tiles"),
        "laz_dir": str(laz_dir),
        "tile_manifest": str(tmp_path / "output" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "output" / "city_manifest.json"),
        "output_epsg": 32615,
        "bbox_4326": {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0},
    }
    cfg_path = tmp_path / "test_dry.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    result = _run_pipeline("--config", str(cfg_path), "--catalog", str(catalog), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "catalog file count: 5" in result.stdout
    assert "catalog" in result.stdout.lower()


def test_run_pipeline_missing_catalog_exits_nonzero(tmp_path):
    config = {
        "city_slug": "test_fail",
        "output_root": str(tmp_path / "output"),
        "tiles_root": str(tmp_path / "output" / "tiles"),
        "laz_dir": str(tmp_path / "laz"),
        "tile_manifest": str(tmp_path / "output" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "output" / "city_manifest.json"),
        "output_epsg": 32615,
        "bbox_4326": {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0},
    }
    cfg_path = tmp_path / "test_fail.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    result = _run_pipeline(
        "--config", str(cfg_path),
        "--catalog", str(tmp_path / "nonexistent.json"),
        "--dry-run",
    )

    assert result.returncode != 0
    assert "not found" in result.stderr
