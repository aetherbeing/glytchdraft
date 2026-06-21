"""
Focused tests for Phase 07 rooftop-candidate detection and metadata traceability.

Covers:
  1. Confirmed small elevated rooftop structure → rooftop_candidate=True
  2. Near-threshold case (~9.1 m gap, cid-823-equivalent) → flagged
  3. Legitimate narrow tower (~7.7 m gap, large area) → not flagged (gap below threshold)
  4. Large elevated building (gap > 20 m but area > 400 m²) → not flagged (area above limit)
  5. Footprint with no interior points → not flagged, traceability fields are None
  6. Configuration overrides for each of the three thresholds
  7. Existing CSV column order preserved; new fields appended at end

The tests exercise estimate() in isolation using synthetic point clouds and
Shapely polygons — no disk I/O, no canonical tile artifacts.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

numpy = pytest.importorskip("numpy")
shapely = pytest.importorskip("shapely")
scipy = pytest.importorskip("scipy")

import numpy as np
from shapely.geometry import Polygon

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "phases"))

from phase_07_masses import estimate


# ── helpers ───────────────────────────────────────────────────────────────────

def _city(**tunables):
    """Return a minimal mock CityRuntime whose raw_config carries tunables."""
    raw = SimpleNamespace(**tunables)
    city = MagicMock()
    city.raw_config = raw
    return city


def _rect_poly(cx, cy, half_w, half_h):
    """Axis-aligned rectangle centred at (cx, cy)."""
    return Polygon([
        (cx - half_w, cy - half_h),
        (cx + half_w, cy - half_h),
        (cx + half_w, cy + half_h),
        (cx - half_w, cy + half_h),
    ])


def _ground(cx, cy, z=5.0, n=50, spread=20.0):
    """Flat synthetic ground scan near (cx, cy)."""
    rng = np.random.default_rng(0)
    xs = cx + rng.uniform(-spread, spread, n)
    ys = cy + rng.uniform(-spread, spread, n)
    zs = np.full(n, z)
    return np.column_stack([xs, ys, zs])


def _points_inside(cx, cy, z_min, z_max, n=100):
    """Building points uniformly distributed inside a small rectangle at elevation."""
    rng = np.random.default_rng(1)
    xs = cx + rng.uniform(-1.5, 1.5, n)
    ys = cy + rng.uniform(-1.5, 1.5, n)
    zs = rng.uniform(z_min, z_max, n)
    return np.column_stack([xs, ys, zs])


EXISTING_CSV_FIELDS = [
    "ground_z", "height_p90", "estimated_height", "source_quality",
    "point_count_inside",
]
NEW_FIELDS = ["footprint_area_m2", "min_z_inside", "rooftop_gap_m", "rooftop_candidate"]


# ── test 1: confirmed small rooftop structure → flagged ───────────────────────

def test_small_elevated_structure_is_flagged():
    """
    15 m² footprint, all building points at 55–70 m, ground at 5 m.
    Gap ≈ 50 m >> 8 m default. Area 15 m² << 400 m².
    Expected: rooftop_candidate=True.
    """
    cx, cy = 0.0, 0.0
    poly = _rect_poly(cx, cy, half_w=1.93, half_h=1.94)  # ≈ 15 m²
    b_xyz = _points_inside(cx, cy, z_min=55.0, z_max=70.0, n=120)
    g_xyz = _ground(cx, cy, z=5.0)

    results = estimate([poly], b_xyz, g_xyz, _city())

    assert len(results) == 1
    r = results[0]
    assert r["rooftop_candidate"] is True
    assert r["min_z_inside"] is not None
    assert r["rooftop_gap_m"] is not None
    assert r["rooftop_gap_m"] > 8.0
    assert r["footprint_area_m2"] < 400.0
    # geometry must be unaltered
    assert r["ground_z"] == pytest.approx(5.0, abs=0.5)
    assert r["estimated_height"] > 10.0


# ── test 2: cid-823-equivalent (~9.1 m gap) → flagged ────────────────────────

def test_near_threshold_gap_is_flagged():
    """
    Equivalent to cid 823: 10 m² footprint, lowest point 9.1 m above ground.
    Under the old 20 m threshold this was missed; with 8 m it must be caught.
    """
    cx, cy = 100.0, 100.0
    poly = _rect_poly(cx, cy, half_w=1.79, half_h=1.78)  # ≈ 10 m²
    ground_z = 5.48
    min_z = 14.58  # gap = 14.58 - 5.48 = 9.10 m
    b_xyz = _points_inside(cx, cy, z_min=min_z, z_max=55.0, n=114)
    g_xyz = _ground(cx, cy, z=ground_z)

    results = estimate([poly], b_xyz, g_xyz, _city())

    r = results[0]
    assert r["rooftop_candidate"] is True, (
        f"cid-823-equivalent with gap≈9.1m must be flagged; got gap={r['rooftop_gap_m']}"
    )
    assert r["rooftop_gap_m"] > 8.0
    assert r["footprint_area_m2"] < 400.0


# ── test 3: legitimate narrow tower (~7.7 m gap, large area) → not flagged ───

def test_narrow_tower_not_flagged():
    """
    Equivalent to cid 739: 765 m² footprint, min_z ≈ 16 m, ground ≈ 8.4 m → gap 7.7 m.
    Gap is below the 8.0 m default threshold.
    Expected: rooftop_candidate=False.
    """
    cx, cy = 200.0, 200.0
    poly = _rect_poly(cx, cy, half_w=19.5, half_h=19.6)  # ≈ 765 m²
    ground_z = 8.36
    b_xyz = _points_inside(cx, cy, z_min=16.03, z_max=190.0, n=8715)
    g_xyz = _ground(cx, cy, z=ground_z)

    results = estimate([poly], b_xyz, g_xyz, _city())

    r = results[0]
    assert r["rooftop_candidate"] is False, (
        f"narrow tower with gap≈7.7m must not be flagged; got gap={r['rooftop_gap_m']}"
    )
    assert r["rooftop_gap_m"] < 8.0


# ── test 4: large elevated building (gap > 20 m, area > 400 m²) → not flagged

def test_large_elevated_building_not_flagged():
    """
    Equivalent to cid 600: 464 m² footprint, gap ≈ 21.3 m — legitimate raised structure,
    not a rooftop attachment.  Area exceeds the 400 m² guard.
    Expected: rooftop_candidate=False.
    """
    cx, cy = 300.0, 300.0
    poly = _rect_poly(cx, cy, half_w=10.75, half_h=10.75)  # ≈ 462 m²
    ground_z = 2.56
    b_xyz = _points_inside(cx, cy, z_min=23.87, z_max=37.0, n=2984)
    g_xyz = _ground(cx, cy, z=ground_z)

    results = estimate([poly], b_xyz, g_xyz, _city())

    r = results[0]
    assert r["rooftop_candidate"] is False, (
        f"large elevated building (area={r['footprint_area_m2']:.0f} m²) must not be flagged"
    )
    assert r["footprint_area_m2"] > 400.0


# ── test 5: no interior points → not flagged, traceability fields are None ───

def test_no_interior_points_not_flagged():
    """
    Footprint has no building points inside it (fallback quality).
    min_z_inside and rooftop_gap_m must be None; rooftop_candidate must be False.
    """
    cx, cy = 400.0, 400.0
    poly = _rect_poly(cx, cy, half_w=2.0, half_h=2.0)
    # All building points far outside the footprint
    b_xyz = np.column_stack([
        np.full(50, cx + 500.0),
        np.full(50, cy + 500.0),
        np.full(50, 10.0),
    ])
    g_xyz = _ground(cx, cy, z=5.0)

    results = estimate([poly], b_xyz, g_xyz, _city())

    r = results[0]
    assert r["min_z_inside"] is None
    assert r["rooftop_gap_m"] is None
    assert r["rooftop_candidate"] is False
    assert r["source_quality"] == "fallback"


# ── test 6a: ROOFTOP_GAP_MIN_M override raises the bar ───────────────────────

def test_config_override_gap_threshold():
    """
    With ROOFTOP_GAP_MIN_M=25.0, a building with gap=9.1 m must not be flagged.
    """
    cx, cy = 500.0, 500.0
    poly = _rect_poly(cx, cy, half_w=1.79, half_h=1.78)
    b_xyz = _points_inside(cx, cy, z_min=14.58, z_max=55.0, n=114)
    g_xyz = _ground(cx, cy, z=5.48)

    results = estimate([poly], b_xyz, g_xyz, _city(ROOFTOP_GAP_MIN_M=25.0))

    assert results[0]["rooftop_candidate"] is False


# ── test 6b: ROOFTOP_AREA_MAX_M2 override raises the ceiling ─────────────────

def test_config_override_area_threshold():
    """
    With ROOFTOP_AREA_MAX_M2=600.0, cid-600-equivalent (464 m², gap=21.3 m) is flagged.
    """
    cx, cy = 600.0, 600.0
    poly = _rect_poly(cx, cy, half_w=10.75, half_h=10.75)
    b_xyz = _points_inside(cx, cy, z_min=23.87, z_max=37.0, n=2984)
    g_xyz = _ground(cx, cy, z=2.56)

    results = estimate([poly], b_xyz, g_xyz, _city(ROOFTOP_AREA_MAX_M2=600.0))

    assert results[0]["rooftop_candidate"] is True


# ── test 6c: ROOFTOP_EST_H_MIN_M override filters short pads ─────────────────

def test_config_override_height_threshold():
    """
    A low flat pad: ground at 5 m, points tightly at 13.3–14.5 m.
    gap ≈ 8.3 m (> default 8 m), est_h = h90 - ground ≈ 9.5 m (< default 10 m limit).
    Default threshold (10 m): est_h just below limit → not flagged.
    Override (5 m):  est_h well above limit → flagged.
    """
    cx, cy = 700.0, 700.0
    poly = _rect_poly(cx, cy, half_w=2.0, half_h=2.0)  # 16 m²
    # Points at 13.3–14.5 m: min_z=13.3 → gap≈8.3 m, h90≈14.45 → est_h≈9.45 m
    b_xyz = _points_inside(cx, cy, z_min=13.3, z_max=14.5, n=30)
    g_xyz = _ground(cx, cy, z=5.0)

    # Default: est_h ≈ 9.45 m < 10 m → not flagged
    r_default = estimate([poly], b_xyz, g_xyz, _city())[0]
    assert r_default["rooftop_candidate"] is False, (
        f"est_h={r_default['estimated_height']:.2f} should be below 10 m default; "
        f"gap={r_default['rooftop_gap_m']}"
    )

    # Override: est_h ≈ 9.45 m > 5 m → flagged
    r_override = estimate([poly], b_xyz, g_xyz, _city(ROOFTOP_EST_H_MIN_M=5.0))[0]
    assert r_override["rooftop_candidate"] is True


# ── test 7: CSV backward-compatibility — existing fields in order, new appended

def test_output_field_order_backward_compatible():
    """
    estimate() output dict must contain all pre-existing fields before the new ones.
    The five original fields must appear in their original order.
    New fields (footprint_area_m2, min_z_inside, rooftop_gap_m, rooftop_candidate)
    must be present.
    """
    cx, cy = 800.0, 800.0
    poly = _rect_poly(cx, cy, half_w=5.0, half_h=5.0)
    b_xyz = _points_inside(cx, cy, z_min=10.0, z_max=30.0, n=50)
    g_xyz = _ground(cx, cy, z=5.0)

    results = estimate([poly], b_xyz, g_xyz, _city())
    keys = list(results[0].keys())

    # All original fields present
    for field in EXISTING_CSV_FIELDS:
        assert field in keys, f"pre-existing field '{field}' missing from estimate() output"

    # New traceability fields present
    for field in NEW_FIELDS:
        assert field in keys, f"new traceability field '{field}' missing from estimate() output"

    # Original fields appear before any new field
    last_original = max(keys.index(f) for f in EXISTING_CSV_FIELDS)
    first_new = min(keys.index(f) for f in NEW_FIELDS)
    assert last_original < first_new, (
        f"existing fields must precede new fields in output dict; "
        f"last_original={last_original} first_new={first_new} keys={keys}"
    )

    # Verify types
    r = results[0]
    assert isinstance(r["footprint_area_m2"], float)
    assert isinstance(r["rooftop_candidate"], bool)
    assert r["min_z_inside"] is None or isinstance(r["min_z_inside"], float)
    assert r["rooftop_gap_m"] is None or isinstance(r["rooftop_gap_m"], float)
