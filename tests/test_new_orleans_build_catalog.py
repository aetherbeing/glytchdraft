from __future__ import annotations

import ast
import json
import struct
import subprocess
import sys
from pathlib import Path

import importlib.util

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "new_orleans_build_catalog.py"
NOLA_CONFIG = REPO_ROOT / "configs" / "cities" / "new_orleans.json"

_HAS_PYPROJ = importlib.util.find_spec("pyproj") is not None
needs_pyproj = pytest.mark.skipif(not _HAS_PYPROJ, reason="pyproj not installed")


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_cfg(tmp_path: Path, laz_dir: Path | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "city_slug": "test",
        "laz_dir": str(laz_dir or tmp_path / "laz"),
        "output_root": str(tmp_path / "out"),
        "tile_manifest": str(tmp_path / "out" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "out" / "metadata" / "city_manifest.json"),
        "output_epsg": 32615,
        "keep_raw_laz": True,
        "bbox_4326": {"xmin": -90.14, "ymin": 29.86, "xmax": -89.63, "ymax": 30.20},
    }


def _write_cfg(tmp_path: Path, laz_dir: Path | None = None) -> Path:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(_make_cfg(tmp_path, laz_dir)), encoding="utf-8")
    return p


def _make_las_bytes(
    xmin: float, ymin: float, xmax: float, ymax: float,
    z0: float = 0.0, z1: float = 100.0,
) -> bytes:
    """Minimal valid LAS 1.2 header bytes (227 bytes) with the given bbox."""
    buf = bytearray(227)
    buf[0:4] = b"LASF"
    buf[24], buf[25] = 1, 2          # version 1.2
    struct.pack_into("<H", buf, 94, 227)   # header size
    # bbox at offset 179: max_x, min_x, max_y, min_y, max_z, min_z
    struct.pack_into("<dddddd", buf, 179, xmax, xmin, ymax, ymin, z1, z0)
    return bytes(buf)


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
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    out = result.stdout.lower()
    assert "dry-run" in out
    assert "include-pattern" in out
    assert "spatial-filter" in out


# ── config loading ────────────────────────────────────────────────────────────

def test_load_config_reads_nola_json():
    from scripts.new_orleans_build_catalog import load_config
    cfg = load_config(NOLA_CONFIG)
    assert cfg["city_slug"] == "new_orleans"
    assert "laz_dir" in cfg and "output_root" in cfg


def test_load_config_missing_raises(tmp_path):
    from scripts.new_orleans_build_catalog import load_config
    with pytest.raises(SystemExit):
        load_config(tmp_path / "nonexistent.json")


def test_load_config_temp(tmp_path):
    from scripts.new_orleans_build_catalog import load_config
    loaded = load_config(_write_cfg(tmp_path))
    assert loaded["city_slug"] == "test"
    assert loaded["keep_raw_laz"] is True


# ── scan ──────────────────────────────────────────────────────────────────────

def test_scan_laz_empty_dir(tmp_path):
    from scripts.new_orleans_build_catalog import scan_laz
    d = tmp_path / "laz"; d.mkdir()
    assert scan_laz(d) == []


def test_scan_laz_missing_dir(tmp_path):
    from scripts.new_orleans_build_catalog import scan_laz
    assert scan_laz(tmp_path / "no_such_dir") == []


def test_scan_laz_counts(tmp_path):
    from scripts.new_orleans_build_catalog import scan_laz
    d = tmp_path / "laz"; d.mkdir()
    for i in range(5):
        (d / f"PROJ_{i:06d}.laz").write_bytes(b"x" * 32)
    (d / "ignore.txt").write_text("x")
    assert len(scan_laz(d)) == 5


# ── _major_project ────────────────────────────────────────────────────────────

def test_major_project_sequential():
    from scripts.new_orleans_build_catalog import _major_project
    assert _major_project("USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001.laz") == "ARRA_LA_COASTAL_Z16_2011"


def test_major_project_wn_grid():
    from scripts.new_orleans_build_catalog import _major_project
    assert _major_project("USGS_LPC_LA_2021GreaterNewOrleans_C22_w0775n3318.laz") == "LA_2021GreaterNewOrleans_C22"


def test_major_project_usgs_grid_id():
    from scripts.new_orleans_build_catalog import _major_project
    assert _major_project("USGS_LPC_LA_2021FloridaParishes_C24_16RBU0745.laz") == "LA_2021FloridaParishes_C24"
    assert _major_project("USGS_LPC_Barataria_and_Jean_Lafitte_LiDAR_15RYP8607.laz") == "Barataria_and_Jean_Lafitte_LiDAR"


def test_major_project_double_extension():
    from scripts.new_orleans_build_catalog import _major_project
    assert _major_project("USGS_LPC_Barataria_and_Jean_Lafitte_LiDAR_000100.laz.laz") == "Barataria_and_Jean_Lafitte_LiDAR"


# ── decode_wn_tile (fast path) ────────────────────────────────────────────────

def test_decode_wn_tile_returns_none_without_pattern():
    from scripts.new_orleans_build_catalog import decode_wn_tile
    assert decode_wn_tile("USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001.laz") is None


@needs_pyproj
def test_decode_wn_tile_returns_wgs84_bbox():
    from scripts.new_orleans_build_catalog import decode_wn_tile
    # Known tile: UTM 15N w775000..776000, n3318000..3319000
    result = decode_wn_tile("USGS_LPC_LA_2021GreaterNewOrleans_C22_w0775n3318.laz")
    assert result is not None
    xmin, ymin, xmax, ymax = result
    # NOLA area: lon ~ -90.1 to -90.0, lat ~ 29.9 to 30.0
    assert -90.5 < xmin < -89.0
    assert  29.0 < ymin <  30.5
    assert xmin < xmax
    assert ymin < ymax
    assert (xmax - xmin) < 0.02   # ~1 km tile in degrees


@needs_pyproj
def test_decode_wn_tile_different_tiles_have_different_bounds():
    from scripts.new_orleans_build_catalog import decode_wn_tile
    a = decode_wn_tile("USGS_LPC_LA_2021GreaterNewOrleans_C22_w0775n3318.laz")
    b = decode_wn_tile("USGS_LPC_LA_2021GreaterNewOrleans_C22_w0788n3316.laz")
    assert a is not None and b is not None
    assert a[0] != b[0]   # different longitudes


# ── read_header_raw ───────────────────────────────────────────────────────────

def test_read_header_raw_valid(tmp_path):
    from scripts.new_orleans_build_catalog import read_header_raw
    f = tmp_path / "tile.laz"
    f.write_bytes(_make_las_bytes(100.0, 200.0, 101.0, 201.0))
    result = read_header_raw(f)
    assert result is not None
    xmin, ymin, xmax, ymax = result
    assert abs(xmin - 100.0) < 1e-9
    assert abs(ymin - 200.0) < 1e-9
    assert abs(xmax - 101.0) < 1e-9
    assert abs(ymax - 201.0) < 1e-9


def test_read_header_raw_bad_magic(tmp_path):
    from scripts.new_orleans_build_catalog import read_header_raw
    f = tmp_path / "bad.laz"
    f.write_bytes(b"NLAS" + bytes(223))
    assert read_header_raw(f) is None


def test_read_header_raw_too_short(tmp_path):
    from scripts.new_orleans_build_catalog import read_header_raw
    f = tmp_path / "short.laz"
    f.write_bytes(b"LASF" + bytes(10))
    assert read_header_raw(f) is None


# ── bbox_intersects ───────────────────────────────────────────────────────────

def test_bbox_intersects_overlap():
    from scripts.new_orleans_build_catalog import bbox_intersects
    city = {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0}
    assert bbox_intersects((-89.5, 29.5, -89.2, 29.8), city)


def test_bbox_intersects_no_overlap_east():
    from scripts.new_orleans_build_catalog import bbox_intersects
    city = {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0}
    assert not bbox_intersects((-88.9, 29.5, -88.5, 29.8), city)


def test_bbox_intersects_partial_overlap():
    from scripts.new_orleans_build_catalog import bbox_intersects
    city = {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0}
    # tile straddles left edge of city bbox
    assert bbox_intersects((-90.5, 29.5, -89.8, 29.8), city)


def test_bbox_intersects_touching_edge():
    from scripts.new_orleans_build_catalog import bbox_intersects
    city = {"xmin": -90.0, "ymin": 29.0, "xmax": -89.0, "ymax": 30.0}
    assert bbox_intersects((-91.0, 29.0, -90.0, 30.0), city)  # touches left edge


# ── apply_spatial_filter ──────────────────────────────────────────────────────

@needs_pyproj
def test_apply_spatial_filter_wn_tiles(tmp_path):
    """Fast path: w/n coordinate tiles decoded from filename."""
    from scripts.new_orleans_build_catalog import apply_spatial_filter
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()

    # Known NOLA tiles (inside bbox) and one far outside
    inside_names = [
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0780n3318.laz",   # inside
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3320.laz",   # inside
    ]
    outside_names = [
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0600n3200.laz",   # far south-west
    ]
    files = []
    for name in inside_names + outside_names:
        p = laz_dir / name
        p.write_bytes(b"x" * 32)
        files.append(p)

    nola_bbox = {"xmin": -90.14, "ymin": 29.86, "xmax": -89.63, "ymax": 30.20}
    hit, miss, unknown = apply_spatial_filter(files, nola_bbox)

    assert len(unknown) == 0
    assert len(hit) == 2
    assert len(miss) == 1
    assert all("w0600" not in f.name for f in hit)


def test_apply_spatial_filter_header_read(tmp_path):
    """Slow path: sequential-named tiles use binary header reads."""
    from scripts.new_orleans_build_catalog import apply_spatial_filter
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()

    # Geographic coordinates (already WGS84 in header) to avoid needing CRS
    inside_file = laz_dir / "USGS_LPC_PROJ_000001.laz"
    outside_file = laz_dir / "USGS_LPC_PROJ_000002.laz"
    # Inside NOLA bbox
    inside_file.write_bytes(_make_las_bytes(-89.9, 30.0, -89.8, 30.1))
    # Far outside
    outside_file.write_bytes(_make_las_bytes(-85.0, 25.0, -84.0, 26.0))

    nola_bbox = {"xmin": -90.14, "ymin": 29.86, "xmax": -89.63, "ymax": 30.20}
    hit, miss, unknown = apply_spatial_filter([inside_file, outside_file], nola_bbox)

    assert len(unknown) == 0
    assert len(hit) == 1
    assert len(miss) == 1
    assert "000001" in hit[0].name


def test_apply_spatial_filter_bad_header_goes_to_unknown(tmp_path):
    from scripts.new_orleans_build_catalog import apply_spatial_filter
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    bad = laz_dir / "USGS_LPC_PROJ_000001.laz"
    bad.write_bytes(b"NOTLASF" + bytes(250))
    nola_bbox = {"xmin": -90.14, "ymin": 29.86, "xmax": -89.63, "ymax": 30.20}
    hit, miss, unknown = apply_spatial_filter([bad], nola_bbox)
    assert len(unknown) == 1
    assert len(hit) == 0


# ── build_catalog with spatial filter ─────────────────────────────────────────

def test_build_catalog_unfiltered(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"USGS_LPC_PROJ_A_{i:06d}.laz").write_bytes(b"x" * 512)
    for i in range(2):
        (laz_dir / f"USGS_LPC_PROJ_B_{i:06d}.laz").write_bytes(b"x" * 512)
    cfg = _make_cfg(tmp_path, laz_dir)
    c = build_catalog(cfg, laz_dir=laz_dir)
    assert c["laz_count_total"] == 5
    assert c["laz_count_selected"] == 5
    assert c["filter_patterns"] is None
    assert c["spatial_filter_applied"] is False
    assert len(c["files"]) == 5


def test_build_catalog_project_filter(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"USGS_LPC_PROJ_A_{i:06d}.laz").write_bytes(b"x" * 512)
    for i in range(2):
        (laz_dir / f"USGS_LPC_PROJ_B_{i:06d}.laz").write_bytes(b"x" * 512)
    cfg = _make_cfg(tmp_path, laz_dir)
    c = build_catalog(cfg, laz_dir=laz_dir, include_patterns=["PROJ_A"])
    assert c["laz_count_selected"] == 3
    assert len(c["files"]) == 3


@needs_pyproj
def test_build_catalog_spatial_filter_wn(tmp_path):
    """Spatial filter with w/n-encoded tiles exercises fast path end-to-end."""
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    # Inside NOLA bbox (UTM 15N tiles)
    for name in [
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0780n3318.laz",
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3320.laz",
    ]:
        (laz_dir / name).write_bytes(b"x" * 512)
    # Outside
    (laz_dir / "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0600n3200.laz").write_bytes(b"x" * 512)

    cfg = _make_cfg(tmp_path, laz_dir)
    cfg["bbox_4326"] = {"xmin": -90.14, "ymin": 29.86, "xmax": -89.63, "ymax": 30.20}
    c = build_catalog(cfg, laz_dir=laz_dir,
                      include_patterns=["GreaterNewOrleans"],
                      spatial_filter=True)

    assert c["spatial_filter_applied"] is True
    assert c["laz_count_selected"] == 3      # project filter
    assert c["laz_count_bbox"] == 2          # bbox filter
    assert c["laz_count_bbox_excluded"] == 1
    assert c["laz_count_bbox_unknown"] == 0
    assert len(c["files"]) == 2
    assert all("w0600" not in f for f in c["files"])


def test_build_catalog_spatial_filter_no_bbox_in_config(tmp_path):
    from scripts.new_orleans_build_catalog import build_catalog
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    (laz_dir / "USGS_LPC_PROJ_000001.laz").write_bytes(b"x" * 32)
    cfg = _make_cfg(tmp_path, laz_dir)
    del cfg["bbox_4326"]
    with pytest.raises(SystemExit):
        build_catalog(cfg, laz_dir=laz_dir, spatial_filter=True)


# ── subprocess / CLI ──────────────────────────────────────────────────────────

def _make_subprocess_cfg(tmp_path: Path, laz_dir: Path) -> Path:
    cfg = {
        "schema_version": "1.0",
        "city_slug": "test_nola",
        "laz_dir": str(laz_dir),
        "output_root": str(tmp_path / "out"),
        "tile_manifest": str(tmp_path / "out" / "tile_manifest.json"),
        "city_manifest": str(tmp_path / "out" / "metadata" / "city_manifest.json"),
        "output_epsg": 32615,
        "keep_raw_laz": True,
        "bbox_4326": {"xmin": -90.14, "ymin": 29.86, "xmax": -89.63, "ymax": 30.20},
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def test_dry_run_no_output_written(tmp_path):
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    for i in range(3):
        (laz_dir / f"USGS_LPC_NOLA_2022_{i:06d}.laz").write_bytes(b"0" * 64)
    cfg_path = _make_subprocess_cfg(tmp_path, laz_dir)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(cfg_path), "--dry-run"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "dry run" in (r.stdout + r.stderr).lower()
    assert not list((tmp_path / "out").rglob("*.json")) if (tmp_path / "out").exists() else True


@needs_pyproj
def test_spatial_filter_dry_run_subprocess(tmp_path):
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    # 2 tiles inside, 1 outside (w/n fast path)
    for name in [
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0780n3318.laz",
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3320.laz",
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0600n3200.laz",
    ]:
        (laz_dir / name).write_bytes(b"x" * 64)
    cfg_path = _make_subprocess_cfg(tmp_path, laz_dir)
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--config", str(cfg_path),
         "--include-pattern", "GreaterNewOrleans",
         "--spatial-filter", "--dry-run"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0
    out = r.stdout + r.stderr
    assert "dry run" in out.lower()
    assert "2" in out    # 2 bbox-hit tiles visible in report


@needs_pyproj
def test_spatial_filter_writes_catalog(tmp_path):
    laz_dir = tmp_path / "laz"; laz_dir.mkdir()
    for name in [
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0780n3318.laz",
        "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0600n3200.laz",  # outside
    ]:
        (laz_dir / name).write_bytes(b"x" * 64)
    cfg_path = _make_subprocess_cfg(tmp_path, laz_dir)
    out_path = tmp_path / "catalog.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--config", str(cfg_path),
         "--include-pattern", "GreaterNewOrleans",
         "--spatial-filter",
         "--output", str(out_path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["spatial_filter_applied"] is True
    assert data["laz_count_bbox"] == 1
    assert data["laz_count_bbox_excluded"] == 1
    assert len(data["files"]) == 1
    assert "w0780" in data["files"][0]
