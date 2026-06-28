"""
Regression suite for scripts/validation/building_characteristics.py

All tests use synthetic fixtures only — no external files or mounted drives required.
The suite must pass even when the T7 drive is absent.

Test index (matches Step 6 of the mission specification)
---------------------------------------------------------
 1  Fully valid building record produces no findings
 2  Missing building ID
 3  Duplicate building IDs
 4  Missing source footprint ID
 5  Missing source tiles
 6  Duplicate source tiles
 7  Invalid SHA-256
 8  Invalid timestamp
 9  Missing CRS
10  Contradictory CRS or units
11  Mixed feet/meters
12  _m field without metric provenance
13  NaN in geometry coordinate
14  Infinity in geometry coordinate
15  Negative area
16  Zero area
17  Negative perimeter
18  Empty geometry (< 3 vertices)
19  Invalid geometry (degenerate — all points collinear / zero area)
20  Inverted bounding box
21  Bounding box not containing geometry
22  Centroid outside footprint
23  Invalid orientation
24  Inconsistent height percentiles
25  Roof below ground
26  Negative volume
27  Volume inconsistency
28  Suspicious roof area
29  Negative point count
30  Filtered point count above raw count
31  Density mismatch
32  Invalid LiDAR return counts
33  Missing quality flags (source_quality absent → CONF-001)
34  Invalid confidence (outside 0–1 range)
35  Fallback use  (source_quality=fallback → HEIGHT-007 info)
36  Approximate / unnormalised _m field
37  Missing provenance
38  Cross-tile source tracking
39  Corrected Miami metric record (no findings expected)
40  Historical mixed-unit record downgraded (UNIT-007)
41  Deterministic finding ordering
42  Rule-code uniqueness
43  Validator never mutates the supplied record
44  Validator produces machine-readable (serialisable) results
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

from building_characteristics import (  # noqa: E402
    Finding,
    Severity,
    ValidationConfig,
    RULE_REGISTRY,
    validate_building,
    validate_dataset,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# A fully-valid building record.  All optional extras included so the suite
# can modify individual fields without adding boilerplate.
_VALID_RECORD: dict = {
    # Identity
    "cluster_id": 42,
    # Provenance
    "footprint_source_id": "fp-001",
    "source_tiles": ["318455_0901"],
    "pipeline_version": "1.0",
    "normalization_version": "miami_metric_normalization_v1",
    "source_sha256": "a" * 64,
    "generated_at": "2024-06-15T10:00:00Z",
    "footprint_provenance": "open_county_footprint",
    # CRS / units
    "horizontal_crs": "EPSG:32617",
    "vertical_crs": "EPSG:5703",
    "horizontal_unit": "meters",
    "vertical_unit": "metre",
    "z_values_metric": True,
    "coordinate_system": {
        "processed_crs": "EPSG:32617",
        "xy_unit": "meters",
        "z_unit": "metre",
        "z_values_metric": True,
    },
    "metric_normalization_version": "miami_metric_normalization_v1",
    # Geometry (simple 4-vertex square: 10 m × 10 m = 100 m²)
    "footprint_coords": [
        [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]
    ],
    "footprint_area_m2": 100.0,
    "perimeter_m": 40.0,
    "centroid_x": 5.0,
    "centroid_y": 5.0,
    "bbox_xmin": 0.0,
    "bbox_ymin": 0.0,
    "bbox_xmax": 10.0,
    "bbox_ymax": 10.0,
    "orientation": 0.0,
    # Height
    "ground_z": 2.0,
    "height_p90": 12.0,
    "height_p95": 13.0,
    "height_max": 14.0,
    "estimated_height": 10.0,
    "source_quality": "good",
    # LiDAR
    "point_count_cluster": 500,
    "point_count_inside": 200,
    # Confidence
    "confidence": 0.9,
}


def _mutate(key: str, value) -> dict:
    """Return a copy of _VALID_RECORD with one field changed."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec[key] = value
    return rec


def _remove(key: str) -> dict:
    """Return a copy of _VALID_RECORD with one field removed."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec.pop(key, None)
    return rec


def _codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings]


def _has_code(findings: list[Finding], code: str) -> bool:
    return code in _codes(findings)


# ---------------------------------------------------------------------------
# Test 1: Fully valid record → no findings
# ---------------------------------------------------------------------------

def test_01_valid_record_no_findings():
    findings = validate_building(_VALID_RECORD)
    assert findings == [], f"Expected no findings, got: {findings}"


# ---------------------------------------------------------------------------
# Test 2: Missing building ID → ID-001
# ---------------------------------------------------------------------------

def test_02_missing_building_id():
    rec = copy.deepcopy(_VALID_RECORD)
    rec.pop("cluster_id", None)
    rec.pop("building_id", None)
    findings = validate_building(rec)
    assert _has_code(findings, "ID-001"), f"Expected ID-001, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 3: Duplicate building IDs in dataset → PROV-010
# ---------------------------------------------------------------------------

def test_03_duplicate_building_ids():
    r1 = copy.deepcopy(_VALID_RECORD)
    r2 = copy.deepcopy(_VALID_RECORD)
    # Both have cluster_id=42
    findings = validate_dataset([r1, r2])
    assert _has_code(findings, "PROV-010"), f"Expected PROV-010, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 4: Missing source footprint ID → PROV-001
# ---------------------------------------------------------------------------

def test_04_missing_footprint_id():
    rec = _remove("footprint_source_id")
    rec.pop("footprint_provenance", None)
    rec.pop("footprint_id", None)
    rec.pop("footprint_method", None)
    rec.pop("geopin", None)
    rec.pop("objectid", None)
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-001"), f"Expected PROV-001, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 5: Missing source tiles → PROV-002
# ---------------------------------------------------------------------------

def test_05_missing_source_tiles():
    rec = _remove("source_tiles")
    rec.pop("contributing_source_tiles", None)
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-002"), f"Expected PROV-002, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 6: Duplicate source tiles → PROV-003
# ---------------------------------------------------------------------------

def test_06_duplicate_source_tiles():
    rec = _mutate("source_tiles", ["tile_A", "tile_A", "tile_B"])
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-003"), f"Expected PROV-003, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 7: Invalid SHA-256 → PROV-006
# ---------------------------------------------------------------------------

def test_07_invalid_sha256_too_short():
    rec = _mutate("source_sha256", "abc123")
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-006"), f"Expected PROV-006, got: {_codes(findings)}"


def test_07b_invalid_sha256_uppercase():
    rec = _mutate("source_sha256", "A" * 64)
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-006"), "Upper-case SHA-256 should fail PROV-006"


def test_07c_valid_sha256_passes():
    findings = validate_building(_VALID_RECORD)
    assert not _has_code(findings, "PROV-006"), "Valid SHA-256 should not trigger PROV-006"


# ---------------------------------------------------------------------------
# Test 8: Invalid timestamp → PROV-007
# ---------------------------------------------------------------------------

def test_08_invalid_timestamp():
    rec = _mutate("generated_at", "not-a-date")
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-007"), f"Expected PROV-007, got: {_codes(findings)}"


def test_08b_valid_timestamp_passes():
    findings = validate_building(_VALID_RECORD)
    assert not _has_code(findings, "PROV-007"), "Valid timestamp should not trigger PROV-007"


# ---------------------------------------------------------------------------
# Test 9: Missing CRS → CRS-001
# ---------------------------------------------------------------------------

def test_09_missing_crs():
    rec = copy.deepcopy(_VALID_RECORD)
    for k in ("horizontal_crs", "vertical_crs", "source_horizontal_crs",
               "source_vertical_crs", "processed_crs"):
        rec.pop(k, None)
    rec["coordinate_system"] = {}  # empty dict — no processed_crs
    findings = validate_building(rec)
    assert _has_code(findings, "CRS-001"), f"Expected CRS-001, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 10: Contradictory CRS/units → UNIT-003
# ---------------------------------------------------------------------------

def test_10_contradictory_units_ftus_but_metric_flag():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["vertical_unit"] = "US survey foot"
    rec["z_values_metric"] = True
    findings = validate_building(rec)
    assert _has_code(findings, "UNIT-003"), f"Expected UNIT-003, got: {_codes(findings)}"


def test_10b_contradictory_units_metric_but_no_metric_flag():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["vertical_unit"] = "metre"
    rec["z_values_metric"] = False
    rec["metric_normalization_version"] = None  # remove provenance
    findings = validate_building(rec)
    assert _has_code(findings, "UNIT-003"), f"Expected UNIT-003, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 11: Mixed feet/meters → UNIT-006
# ---------------------------------------------------------------------------

def test_11_mixed_feet_meters():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["horizontal_unit"] = "meters"
    rec["vertical_unit"] = "US survey foot"
    findings = validate_building(rec)
    assert _has_code(findings, "UNIT-006"), f"Expected UNIT-006, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 12: _m field without metric provenance → UNIT-004
# ---------------------------------------------------------------------------

def test_12_m_field_without_metric_provenance():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["estimated_height_m"] = 10.0
    rec.pop("metric_normalization_version", None)
    rec.pop("normalization_version", None)
    rec["z_values_metric"] = None  # no metric declaration
    rec["coordinate_system"] = {}
    findings = validate_building(rec)
    assert _has_code(findings, "UNIT-004"), f"Expected UNIT-004, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 13: NaN in geometry → GEOM-013
# ---------------------------------------------------------------------------

def test_13_nan_in_geometry():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_coords"] = [[0.0, 0.0], [float("nan"), 0.0], [10.0, 10.0], [0.0, 10.0]]
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-013"), f"Expected GEOM-013, got: {_codes(findings)}"


def test_13b_nan_in_area_field():
    rec = _mutate("footprint_area_m2", float("nan"))
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-013"), f"Expected GEOM-013, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 14: Infinity in geometry → GEOM-014
# ---------------------------------------------------------------------------

def test_14_inf_in_geometry():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_coords"] = [[0.0, 0.0], [float("inf"), 0.0], [10.0, 10.0], [0.0, 10.0]]
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-014"), f"Expected GEOM-014, got: {_codes(findings)}"


def test_14b_inf_in_area_field():
    rec = _mutate("footprint_area_m2", float("inf"))
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-014"), f"Expected GEOM-014, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 15: Negative area → GEOM-003
# ---------------------------------------------------------------------------

def test_15_negative_area():
    rec = _mutate("footprint_area_m2", -50.0)
    rec["footprint_coords"] = None  # disable coords-based check, use numeric
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-003"), f"Expected GEOM-003, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 16: Zero area → AREA-001
# ---------------------------------------------------------------------------

def test_16_zero_area():
    rec = _mutate("footprint_area_m2", 0.0)
    rec["footprint_coords"] = None
    findings = validate_building(rec)
    # Zero area should trigger GEOM-003 (not positive) and AREA-001 (exactly zero)
    assert _has_code(findings, "AREA-001") or _has_code(findings, "GEOM-003"), (
        f"Expected AREA-001 or GEOM-003 for zero area, got: {_codes(findings)}"
    )


# ---------------------------------------------------------------------------
# Test 17: Negative perimeter → GEOM-004
# ---------------------------------------------------------------------------

def test_17_negative_perimeter():
    rec = _mutate("perimeter_m", -10.0)
    rec["footprint_coords"] = None
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-004"), f"Expected GEOM-004, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 18: Empty geometry (< 3 vertices) → GEOM-002
# ---------------------------------------------------------------------------

def test_18_empty_geometry_too_few_vertices():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_coords"] = [[0.0, 0.0], [10.0, 0.0]]  # only 2 points
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-002"), f"Expected GEOM-002, got: {_codes(findings)}"


def test_18b_empty_list():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_coords"] = []
    findings = validate_building(rec)
    # Empty list is not >=3 vertices; GEOM-002 should fire
    assert _has_code(findings, "GEOM-002"), f"Expected GEOM-002 for empty coords, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 19: Degenerate / zero-area geometry → GEOM-003 from coords
# ---------------------------------------------------------------------------

def test_19_degenerate_collinear_geometry():
    rec = copy.deepcopy(_VALID_RECORD)
    rec.pop("footprint_area_m2", None)
    # Collinear points — zero shoelace area
    rec["footprint_coords"] = [[0.0, 0.0], [5.0, 0.0], [10.0, 0.0], [15.0, 0.0]]
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-003"), f"Expected GEOM-003 for degenerate geometry, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 20: Inverted bounding box → GEOM-008
# ---------------------------------------------------------------------------

def test_20_inverted_bbox_x():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["bbox_xmin"] = 20.0
    rec["bbox_xmax"] = 5.0  # inverted
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-008"), f"Expected GEOM-008, got: {_codes(findings)}"


def test_20b_inverted_bbox_y():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["bbox_ymin"] = 20.0
    rec["bbox_ymax"] = 5.0
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-008"), f"Expected GEOM-008, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 21: Bounding box not containing geometry → GEOM-009
# ---------------------------------------------------------------------------

def test_21_bbox_not_containing_geometry():
    rec = copy.deepcopy(_VALID_RECORD)
    # Ring goes to x=10, but bbox only covers x=0..8
    rec["bbox_xmin"] = 0.0
    rec["bbox_ymin"] = 0.0
    rec["bbox_xmax"] = 8.0   # too small
    rec["bbox_ymax"] = 10.0
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-009"), f"Expected GEOM-009, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 22: Centroid outside footprint → GEOM-006
# ---------------------------------------------------------------------------

def test_22_centroid_outside_footprint():
    # Use a large tolerance breach: centroid 100m outside a 10m square
    rec = copy.deepcopy(_VALID_RECORD)
    rec["centroid_x"] = 999.0   # wildly outside
    rec["centroid_y"] = 999.0
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-006"), f"Expected GEOM-006, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 23: Invalid orientation → GEOM-011
# ---------------------------------------------------------------------------

def test_23_orientation_out_of_range():
    rec = _mutate("orientation", 270.0)  # outside [-180, 180]
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-011"), f"Expected GEOM-011, got: {_codes(findings)}"


def test_23b_orientation_nan():
    rec = _mutate("orientation", float("nan"))
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-010"), f"Expected GEOM-010 for NaN orientation, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 24: Inconsistent height percentiles → HEIGHT-003
# ---------------------------------------------------------------------------

def test_24_height_p95_less_than_p90():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["height_p90"] = 15.0
    rec["height_p95"] = 12.0  # p95 < p90 — impossible
    findings = validate_building(rec)
    assert _has_code(findings, "HEIGHT-003"), f"Expected HEIGHT-003, got: {_codes(findings)}"


def test_24b_height_max_less_than_p95():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["height_p95"] = 15.0
    rec["height_max"] = 13.0  # max < p95 — impossible
    findings = validate_building(rec)
    assert _has_code(findings, "HEIGHT-003"), f"Expected HEIGHT-003, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 25: Roof below ground → HEIGHT-005
# ---------------------------------------------------------------------------

def test_25_roof_below_ground():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["ground_z"] = 20.0
    rec["height_p90"] = 10.0  # 10 < 20 — below ground
    rec["estimated_height"] = 10.0
    findings = validate_building(rec)
    assert _has_code(findings, "HEIGHT-005"), f"Expected HEIGHT-005, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 26: Negative volume → VOLUME-001
# ---------------------------------------------------------------------------

def test_26_negative_volume():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["volume_m3"] = -500.0
    findings = validate_building(rec)
    assert _has_code(findings, "VOLUME-001"), f"Expected VOLUME-001, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 27: Volume inconsistency → VOLUME-002
# ---------------------------------------------------------------------------

def test_27_volume_too_large():
    rec = copy.deepcopy(_VALID_RECORD)
    # area=100, height=10 → expected ≈ 1000; supply 5000 → 400% off
    rec["volume_m3"] = 5000.0
    findings = validate_building(rec)
    assert _has_code(findings, "VOLUME-002"), f"Expected VOLUME-002, got: {_codes(findings)}"


def test_27b_volume_too_small():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["volume_m3"] = 10.0   # expected ~1000; 10 is only 1%
    findings = validate_building(rec)
    assert _has_code(findings, "VOLUME-002"), f"Expected VOLUME-002, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 28: Suspicious roof area → AREA-003
# ---------------------------------------------------------------------------

def test_28_suspicious_roof_area():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_area_m2"] = 100.0
    rec["roof_area_m2"] = 500.0  # 5× footprint — exceeds default warn ratio of 2
    findings = validate_building(rec)
    assert _has_code(findings, "AREA-003"), f"Expected AREA-003, got: {_codes(findings)}"


def test_28b_reasonable_roof_area_no_warning():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_area_m2"] = 100.0
    rec["roof_area_m2"] = 120.0  # 1.2× — fine
    findings = validate_building(rec)
    assert not _has_code(findings, "AREA-003"), "Reasonable roof area should not trigger AREA-003"


# ---------------------------------------------------------------------------
# Test 29: Negative point count → LIDAR-001
# ---------------------------------------------------------------------------

def test_29_negative_point_count():
    rec = _mutate("point_count_cluster", -1)
    findings = validate_building(rec)
    assert _has_code(findings, "LIDAR-001"), f"Expected LIDAR-001, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 30: Filtered count above raw count → LIDAR-003
# ---------------------------------------------------------------------------

def test_30_filtered_exceeds_raw():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["point_count_cluster"] = 100
    rec["point_count_inside"] = 200  # filtered > raw
    findings = validate_building(rec)
    assert _has_code(findings, "LIDAR-003"), f"Expected LIDAR-003, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 31: Density mismatch → LIDAR-005
# ---------------------------------------------------------------------------

def test_31_density_mismatch():
    rec = copy.deepcopy(_VALID_RECORD)
    # point_count_inside=200, footprint_area_m2=100 → expected density=2.0
    rec["point_count_inside"] = 200
    rec["footprint_area_m2"] = 100.0
    rec["point_density"] = 50.0  # wildly wrong
    findings = validate_building(rec)
    assert _has_code(findings, "LIDAR-005"), f"Expected LIDAR-005, got: {_codes(findings)}"


def test_31b_correct_density_no_warning():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["point_count_inside"] = 200
    rec["footprint_area_m2"] = 100.0
    rec["point_density"] = 2.0  # exact
    findings = validate_building(rec)
    assert not _has_code(findings, "LIDAR-005"), "Correct density should not trigger LIDAR-005"


# ---------------------------------------------------------------------------
# Test 32: Invalid LiDAR return counts → LIDAR-006
# ---------------------------------------------------------------------------

def test_32_return_counts_exceed_total():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["return_count_total"] = 100
    rec["returns_single"] = 80
    rec["returns_multiple"] = 50  # 80+50=130 > 100
    findings = validate_building(rec)
    assert _has_code(findings, "LIDAR-006"), f"Expected LIDAR-006, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 33: Missing quality flags → CONF-001
# ---------------------------------------------------------------------------

def test_33_missing_source_quality():
    rec = _remove("source_quality")
    findings = validate_building(rec)
    assert _has_code(findings, "CONF-001"), f"Expected CONF-001, got: {_codes(findings)}"


def test_33b_missing_estimated_height():
    rec = _remove("estimated_height")
    findings = validate_building(rec)
    assert _has_code(findings, "CONF-001"), f"Expected CONF-001, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 34: Invalid confidence (outside 0–1) → CONF-002
# ---------------------------------------------------------------------------

def test_34_confidence_too_high():
    rec = _mutate("confidence", 1.5)
    findings = validate_building(rec)
    assert _has_code(findings, "CONF-002"), f"Expected CONF-002, got: {_codes(findings)}"


def test_34b_confidence_negative():
    rec = _mutate("confidence", -0.1)
    findings = validate_building(rec)
    assert _has_code(findings, "CONF-002"), f"Expected CONF-002, got: {_codes(findings)}"


def test_34c_confidence_nan():
    rec = _mutate("confidence", float("nan"))
    findings = validate_building(rec)
    assert _has_code(findings, "CONF-002"), f"Expected CONF-002 for NaN confidence, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 35: Fallback use → HEIGHT-007 (INFO)
# ---------------------------------------------------------------------------

def test_35_fallback_source_quality():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_quality"] = "fallback"
    rec["estimated_height"] = 6.0   # typical default fallback height
    rec["height_p90"] = None
    rec["height_p95"] = None
    rec["height_max"] = None
    findings = validate_building(rec)
    assert _has_code(findings, "HEIGHT-007"), f"Expected HEIGHT-007 for fallback quality, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 36: _m field without normalization version → UNIT-007
# ---------------------------------------------------------------------------

def test_36_m_fields_no_normalization_version():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["estimated_height_m"] = 10.0
    rec["height_p90_m"] = 12.0
    rec.pop("metric_normalization_version", None)
    rec.pop("normalization_version", None)
    # z_values_metric=True but no normalization_version → UNIT-007
    rec["z_values_metric"] = True
    findings = validate_building(rec)
    assert _has_code(findings, "UNIT-007"), f"Expected UNIT-007, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 37: Missing provenance → PROV-001
# ---------------------------------------------------------------------------

def test_37_missing_all_provenance():
    rec = copy.deepcopy(_VALID_RECORD)
    for k in ("footprint_source_id", "footprint_provenance", "footprint_method",
               "geopin", "objectid", "footprint_id"):
        rec.pop(k, None)
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-001"), f"Expected PROV-001, got: {_codes(findings)}"


# ---------------------------------------------------------------------------
# Test 38: Cross-tile source tracking → GEOM-015 / CONF-006
# ---------------------------------------------------------------------------

def test_38_cross_tile_no_risk_flag():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_tiles"] = ["tile_A", "tile_B", "tile_C"]  # 3 tiles
    rec.pop("cross_tile_risk", None)
    findings = validate_building(rec)
    codes = _codes(findings)
    assert "GEOM-015" in codes or "CONF-006" in codes, (
        f"Expected GEOM-015 or CONF-006 for multi-tile building, got: {codes}"
    )


def test_38b_cross_tile_with_risk_flag_no_finding():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_tiles"] = ["tile_A", "tile_B"]
    rec["cross_tile_risk"] = True
    findings = validate_building(rec)
    assert not _has_code(findings, "GEOM-015"), "Flagged cross-tile risk should not trigger GEOM-015"
    assert not _has_code(findings, "CONF-006"), "Flagged cross-tile risk should not trigger CONF-006"


# ---------------------------------------------------------------------------
# Test 39: Corrected Miami metric record → no normalization-related findings
# ---------------------------------------------------------------------------

def test_39_corrected_miami_metric_record():
    """A properly-formed Miami metric record should pass all unit/CRS checks."""
    rec = {
        "cluster_id": 1001,
        "footprint_source_id": "miami-fp-001",
        "source_tiles": ["318455_0901"],
        "pipeline_version": "1.0",
        "generated_at": "2024-06-15T12:00:00Z",
        "source_sha256": "b" * 64,
        "footprint_provenance": "open_county_footprint",
        # Miami source CRS contract
        "source_horizontal_crs": "EPSG:6438",
        "source_vertical_crs": "EPSG:6360",
        "horizontal_crs": "EPSG:32617",
        "vertical_crs": "EPSG:5703",
        "horizontal_unit": "meters",
        "vertical_unit": "metre",
        "z_values_metric": True,
        "metric_normalization_version": "miami_metric_normalization_v1",
        "normalization_version": "miami_metric_normalization_v1",
        "feature_gate_enabled": True,
        "conversion_factor": 0.3048006096012192,
        "metric_normalization": {
            "enabled": True,
            "source_horizontal_crs": "EPSG:6438",
            "source_vertical_crs": "EPSG:6360",
            "conversion_factor": 0.3048006096012192,
        },
        "coordinate_system": {
            "processed_crs": "EPSG:32617",
            "xy_unit": "meters",
            "z_unit": "metre",
            "z_values_metric": True,
        },
        "footprint_area_m2": 250.0,
        "footprint_coords": [[0.0, 0.0], [25.0, 0.0], [25.0, 10.0], [0.0, 10.0]],
        "centroid_x": 12.5,
        "centroid_y": 5.0,
        "bbox_xmin": 0.0, "bbox_ymin": 0.0, "bbox_xmax": 25.0, "bbox_ymax": 10.0,
        "ground_z": 3.0,
        "height_p90": 33.0,
        "height_p95": 34.0,
        "height_max": 36.0,
        "estimated_height": 30.0,
        "estimated_height_m": 30.0,
        "height_p90_m": 33.0,
        "source_quality": "good",
        "point_count_cluster": 400,
        "point_count_inside": 150,
        "confidence": 0.9,
    }
    findings = validate_building(rec)
    unit_crs_codes = [f.code for f in findings if f.code.startswith(("UNIT-", "CRS-", "PROV-008"))]
    assert unit_crs_codes == [], (
        f"Corrected Miami metric record should have no unit/CRS/provenance-008 findings, "
        f"got: {unit_crs_codes}"
    )


# ---------------------------------------------------------------------------
# Test 40: Historical mixed-unit record → UNIT-007
# ---------------------------------------------------------------------------

def test_40_historical_mixed_unit_record():
    """_m fields present + z_values_metric=True but no normalization_version → UNIT-007."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["estimated_height_m"] = 10.0
    rec["ground_z_m"] = 2.0
    rec.pop("metric_normalization_version", None)
    rec.pop("normalization_version", None)
    # Still claims metric
    rec["z_values_metric"] = True
    findings = validate_building(rec)
    assert _has_code(findings, "UNIT-007"), (
        f"Historical mixed-unit record should trigger UNIT-007, got: {_codes(findings)}"
    )


# ---------------------------------------------------------------------------
# Test 41: Deterministic finding ordering
# ---------------------------------------------------------------------------

def test_41_deterministic_ordering():
    """validate_building must return the same findings in the same order each time."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_tiles"] = ["tile_A", "tile_A"]      # PROV-003
    rec.pop("footprint_source_id", None)             # PROV-001
    rec.pop("footprint_provenance", None)

    r1 = validate_building(rec)
    r2 = validate_building(rec)
    assert r1 == r2, "validate_building output is not deterministic"

    # Also check ordering invariant: sorted by (code, building_id, source_file, message)
    codes_seen = [f.code for f in r1]
    assert codes_seen == sorted(codes_seen) or len(set(codes_seen)) != len(codes_seen), (
        "Findings should be sorted by code (ties resolved by later fields)"
    )


# ---------------------------------------------------------------------------
# Test 42: Rule-code uniqueness
# ---------------------------------------------------------------------------

def test_42_rule_code_uniqueness():
    """RULE_REGISTRY must contain no duplicate codes."""
    codes = list(RULE_REGISTRY.keys())
    assert len(codes) == len(set(codes)), f"Duplicate rule codes: {codes}"


def test_42b_rule_registry_not_empty():
    assert len(RULE_REGISTRY) >= 50, f"Expected >= 50 rules, got {len(RULE_REGISTRY)}"


# ---------------------------------------------------------------------------
# Test 43: Validator never mutates the supplied record
# ---------------------------------------------------------------------------

def test_43_no_mutation_of_record():
    original = copy.deepcopy(_VALID_RECORD)
    snapshot = copy.deepcopy(_VALID_RECORD)
    _ = validate_building(original)
    assert original == snapshot, "validate_building mutated the supplied record"


def test_43b_no_mutation_via_dataset():
    records = [copy.deepcopy(_VALID_RECORD), copy.deepcopy(_VALID_RECORD)]
    records[1]["cluster_id"] = 99
    snapshots = [copy.deepcopy(r) for r in records]
    _ = validate_dataset(records)
    for i, (rec, snap) in enumerate(zip(records, snapshots)):
        assert rec == snap, f"validate_dataset mutated record at index {i}"


# ---------------------------------------------------------------------------
# Test 44: Validator produces machine-readable (JSON-serialisable) results
# ---------------------------------------------------------------------------

def test_44_machine_readable_findings():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_tiles"] = ["tile_A", "tile_A"]
    findings = validate_building(rec)
    for finding in findings:
        d = finding.to_dict()
        try:
            json.dumps(d)
        except (TypeError, ValueError) as exc:
            pytest.fail(f"Finding {finding.code} is not JSON-serialisable: {exc}\n{d}")


def test_44b_finding_to_dict_has_all_fields():
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_tiles"] = ["tile_A", "tile_A"]
    findings = validate_building(rec)
    required_keys = {
        "code", "characteristic", "severity", "message",
        "observed_value", "expected_constraint", "building_id",
        "source_tile", "source_file", "confidence", "remediation_hint",
    }
    for finding in findings:
        d = finding.to_dict()
        missing = required_keys - d.keys()
        assert not missing, f"Finding {finding.code} dict is missing keys: {missing}"


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_missing_building_id_value_none():
    """building_id key present but value is None → ID-001."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["cluster_id"] = None
    rec["building_id"] = None
    findings = validate_building(rec)
    assert _has_code(findings, "ID-001"), f"Expected ID-001 for None building_id, got: {_codes(findings)}"


def test_blank_building_id():
    """Blank string building_id → ID-002."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["cluster_id"] = "  "
    findings = validate_building(rec)
    assert _has_code(findings, "ID-002"), f"Expected ID-002 for blank building_id, got: {_codes(findings)}"


def test_normalization_version_required_when_z_metric_true():
    """z_values_metric=True with no normalization_version → PROV-005."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["z_values_metric"] = True
    rec.pop("metric_normalization_version", None)
    rec.pop("normalization_version", None)
    # Also clear coordinate_system to avoid it being used as fallback
    rec["coordinate_system"] = {"z_values_metric": True}
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-005"), (
        f"Expected PROV-005 when z_values_metric=True but no normalization_version, "
        f"got: {_codes(findings)}"
    )


def test_lidar_low_support_percentile_flag():
    """height_p90 set but only 2 points → LIDAR-008."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["point_count_inside"] = 2
    rec["height_p90"] = 10.0
    findings = validate_building(rec)
    assert _has_code(findings, "LIDAR-008"), f"Expected LIDAR-008, got: {_codes(findings)}"


def test_unit_005_miami_missing_source_crs():
    """metric_normalization.enabled=True but wrong source CRS → UNIT-005."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["metric_normalization"] = {
        "enabled": True,
        "source_horizontal_crs": "EPSG:4326",   # wrong
        "source_vertical_crs": "EPSG:6360",
        "conversion_factor": 0.3048006096012192,
    }
    findings = validate_building(rec)
    assert _has_code(findings, "UNIT-005"), f"Expected UNIT-005 for wrong source CRS, got: {_codes(findings)}"


def test_validate_dataset_single_valid_record():
    """Dataset of one valid record should return no ERROR findings."""
    findings = validate_dataset([_VALID_RECORD])
    errors = [f for f in findings if f.severity == Severity.ERROR]
    assert errors == [], f"Unexpected errors in valid dataset: {errors}"


def test_validate_building_source_file_label():
    """source_file label is propagated into findings."""
    rec = _remove("source_tiles")
    rec.pop("contributing_source_tiles", None)
    findings = validate_building(rec, source_file="test_data/buildings.json")
    assert all(f.source_file == "test_data/buildings.json" for f in findings), (
        "source_file label not propagated into all findings"
    )


def test_finding_immutability():
    """Finding objects are frozen (immutable)."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec.pop("source_tiles", None)
    rec.pop("contributing_source_tiles", None)
    findings = validate_building(rec)
    assert findings, "Need at least one finding to test immutability"
    with pytest.raises((AttributeError, TypeError)):
        findings[0].code = "HACKED"


def test_config_custom_thresholds():
    """Custom config thresholds are respected."""
    cfg = ValidationConfig(roof_area_ratio_warn=10.0)
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_area_m2"] = 100.0
    rec["roof_area_m2"] = 500.0  # 5× — normally AREA-003 but not with threshold=10
    findings = validate_building(rec, config=cfg)
    assert not _has_code(findings, "AREA-003"), (
        "Custom roof_area_ratio_warn=10.0 should suppress AREA-003 for 5× ratio"
    )


def test_negative_area_no_coords():
    """Negative footprint_area_m2 with no footprint_coords → GEOM-003 from numeric check."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["footprint_area_m2"] = -1.0
    rec.pop("footprint_coords", None)
    rec.pop("footprint_geojson", None)
    rec.pop("geometry", None)
    findings = validate_building(rec)
    assert _has_code(findings, "GEOM-003"), f"Expected GEOM-003, got: {_codes(findings)}"


def test_geojson_polygon_coords_accepted():
    """footprint_geojson key with GeoJSON Polygon geometry is parsed correctly."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec.pop("footprint_coords", None)
    rec["footprint_geojson"] = {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]]
    }
    findings = validate_building(rec)
    geom_errors = [f for f in findings if f.code.startswith("GEOM-") and f.severity == Severity.ERROR]
    assert geom_errors == [], f"Valid GeoJSON should not trigger geometry errors: {geom_errors}"


def test_prov006_sha256_in_source_laz_list():
    """SHA-256 validation fires for invalid hashes inside source_laz list."""
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_laz"] = [{"sha256": "short_invalid_hash", "path": "/data/tile.laz"}]
    findings = validate_building(rec)
    assert _has_code(findings, "PROV-006"), f"Expected PROV-006 for invalid source_laz sha256, got: {_codes(findings)}"


def test_severity_vocabulary():
    """All Finding severity values are from the documented vocabulary."""
    valid_severities = {Severity.ERROR, Severity.WARNING, Severity.INFO}
    rec = copy.deepcopy(_VALID_RECORD)
    rec["source_tiles"] = ["tile_A", "tile_A"]
    rec["source_sha256"] = "bad"
    rec["generated_at"] = "not-a-date"
    findings = validate_building(rec)
    for finding in findings:
        assert finding.severity in valid_severities, (
            f"Finding {finding.code} has unknown severity: {finding.severity!r}"
        )
