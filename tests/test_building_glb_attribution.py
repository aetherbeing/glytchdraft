"""
Focused, non-processing tests for scripts/phases/building_glb_attribution.py.

These tests run without PDAL, without Blender, without /mnt/t7 access, and
without any real LAZ, GLB, or Miami/NOLA tile data. All geometry and IDs are
synthetic, clearly labeled fixtures. They validate:

  - Stable, deterministic node-name attribution across repeated runs
  - Input-order independence
  - Duplicate/missing/null/malformed/oversized/unicode/punctuation building IDs
  - Sanitized node names remain reversible through the stored mapping (not
    through unsanitizing the string)
  - Companion-table <-> GLB-node mapping validation (missing/extra/duplicate)
  - Multi-part buildings remain attributable
  - Empty tile handling
  - A real GLB round-trip through the production pack_glb() packer
    (scripts/phases/phase_tile_common.py) proving node names survive binary
    GLB encoding, with no Blender dependency
  - A failed mapping produces validation_status == "fail", never "pass"
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
sys.path.insert(0, str(PHASES_DIR))

attribution = importlib.import_module("building_glb_attribution")
tile_common = importlib.import_module("phase_tile_common")

BuildingRecord = attribution.BuildingRecord
BuildingIdError = attribution.BuildingIdError


# ── sanitize_node_name ──────────────────────────────────────────────────────

def test_sanitize_node_name_stable_for_simple_id():
    assert attribution.sanitize_node_name("TILE_A", "42") == "bld_TILE_A_42"


def test_sanitize_node_name_deterministic_across_repeated_calls():
    names = {attribution.sanitize_node_name("TILE_A", "42") for _ in range(5)}
    assert names == {"bld_TILE_A_42"}


def test_sanitize_node_name_handles_spaces():
    assert attribution.sanitize_node_name("TILE A", "building 1") == "bld_TILE_A_building_1"


def test_sanitize_node_name_handles_slashes():
    assert attribution.sanitize_node_name("TILE/A", "42/b") == "bld_TILE_A_42_b"


def test_sanitize_node_name_handles_punctuation():
    assert attribution.sanitize_node_name("TILE-A", "b#42!") == "bld_TILE-A_b_42_"


def test_sanitize_node_name_handles_unicode():
    name = attribution.sanitize_node_name("TILE_A", "büilding中")
    assert name.startswith("bld_TILE_A_")
    assert name.encode("ascii")  # must be ASCII-safe for glTF/JSON/URL use


def test_sanitize_node_name_rejects_null_building_id():
    with pytest.raises(BuildingIdError):
        attribution.sanitize_node_name("TILE_A", None)


def test_sanitize_node_name_rejects_empty_building_id():
    with pytest.raises(BuildingIdError):
        attribution.sanitize_node_name("TILE_A", "")


def test_sanitize_node_name_rejects_oversized_building_id():
    with pytest.raises(BuildingIdError):
        attribution.sanitize_node_name("TILE_A", "x" * 500)


def test_sanitize_node_name_multi_part_suffix():
    base = attribution.sanitize_node_name("TILE_A", "42", part_index=0)
    part1 = attribution.sanitize_node_name("TILE_A", "42", part_index=1)
    assert base == "bld_TILE_A_42"
    assert part1 == "bld_TILE_A_42_part1"
    assert base != part1


# ── build_node_mapping ───────────────────────────────────────────────────────

def test_mapping_two_valid_buildings():
    mapping = attribution.build_node_mapping("TILE_A", [BuildingRecord("1"), BuildingRecord("2")])
    assert mapping.ok
    assert mapping.node_name_to_building_id == {"bld_TILE_A_1": "1", "bld_TILE_A_2": "2"}


def test_mapping_stable_across_repeated_runs():
    records = [BuildingRecord("1"), BuildingRecord("2"), BuildingRecord("3")]
    first = attribution.build_node_mapping("TILE_A", records)
    second = attribution.build_node_mapping("TILE_A", list(records))
    assert first.node_name_to_building_id == second.node_name_to_building_id
    assert first.building_id_to_node_names == second.building_id_to_node_names


def test_mapping_input_order_does_not_change_result():
    forward = attribution.build_node_mapping("TILE_A", [BuildingRecord("1"), BuildingRecord("2"), BuildingRecord("3")])
    reversed_ = attribution.build_node_mapping("TILE_A", [BuildingRecord("3"), BuildingRecord("2"), BuildingRecord("1")])
    assert forward.node_name_to_building_id == reversed_.node_name_to_building_id
    assert forward.building_id_to_node_names == reversed_.building_id_to_node_names


def test_mapping_detects_duplicate_building_id():
    mapping = attribution.build_node_mapping("TILE_A", [BuildingRecord("1"), BuildingRecord("1")])
    assert not mapping.ok
    assert mapping.duplicate_records == [{"building_id": "1", "part_index": 0}]


def test_mapping_detects_missing_building_id_as_error():
    mapping = attribution.build_node_mapping("TILE_A", [BuildingRecord(None)])
    assert not mapping.ok
    assert mapping.errors[0]["reason"]


def test_mapping_detects_node_name_collision():
    # "a/b" and "a b" both sanitize to "a_b" — different canonical IDs colliding
    # on the same node name must be caught, not silently overwritten.
    mapping = attribution.build_node_mapping("TILE_A", [BuildingRecord("a/b"), BuildingRecord("a b")])
    assert not mapping.ok
    assert "bld_TILE_A_a_b" in mapping.node_name_collisions


def test_mapping_multi_part_building_remains_attributable():
    mapping = attribution.build_node_mapping(
        "TILE_A", [BuildingRecord("1", part_index=0), BuildingRecord("1", part_index=1)]
    )
    assert mapping.ok
    assert set(mapping.building_id_to_node_names["1"]) == {"bld_TILE_A_1", "bld_TILE_A_1_part1"}
    assert mapping.node_name_to_building_id["bld_TILE_A_1"] == "1"
    assert mapping.node_name_to_building_id["bld_TILE_A_1_part1"] == "1"


def test_mapping_empty_tile_produces_empty_ok_mapping():
    mapping = attribution.build_node_mapping("TILE_EMPTY", [])
    assert mapping.ok
    assert mapping.node_name_to_building_id == {}


def test_mapping_reversible_through_stored_map_not_string_parsing():
    # The canonical ID must be recoverable from the stored reverse map even
    # when the node name itself cannot be un-sanitized character-for-character.
    mapping = attribution.build_node_mapping("TILE_A", [BuildingRecord("weird id/with slash")])
    assert mapping.ok
    (node_name,) = mapping.node_name_to_building_id.keys()
    assert mapping.node_name_to_building_id[node_name] == "weird id/with slash"


# ── compare_id_sets ──────────────────────────────────────────────────────────

def test_compare_id_sets_exact_match():
    cmp = attribution.compare_id_sets(["a", "b"], ["a", "b"])
    assert cmp.complete
    assert cmp.matched == ["a", "b"]
    assert cmp.completeness_ratio == 1.0


def test_compare_id_sets_order_independent():
    cmp_a = attribution.compare_id_sets(["a", "b", "c"], ["c", "a", "b"])
    cmp_b = attribution.compare_id_sets(["c", "b", "a"], ["a", "b", "c"])
    assert cmp_a.matched == cmp_b.matched == ["a", "b", "c"]


def test_compare_id_sets_detects_missing():
    cmp = attribution.compare_id_sets(["a", "b"], ["a"])
    assert not cmp.complete
    assert cmp.missing == ["b"]


def test_compare_id_sets_detects_extra():
    cmp = attribution.compare_id_sets(["a"], ["a", "b"])
    assert not cmp.complete
    assert cmp.extra == ["b"]


def test_compare_id_sets_detects_duplicate_in_actual():
    cmp = attribution.compare_id_sets(["a"], ["a", "a"])
    assert not cmp.complete
    assert cmp.duplicates_in_actual == ["a"]


def test_compare_id_sets_empty_expected_completeness_is_none():
    cmp = attribution.compare_id_sets([], [])
    assert cmp.complete
    assert cmp.completeness_ratio is None


# ── compute_attribution_evidence ────────────────────────────────────────────

def test_evidence_passes_for_clean_tile():
    records = [BuildingRecord("1"), BuildingRecord("2")]
    ev = attribution.compute_attribution_evidence(
        "TILE_A", records,
        glb_node_names=["bld_TILE_A_1", "bld_TILE_A_2"],
        companion_table_building_ids=["1", "2"],
    )
    assert ev.validation_status == "pass"
    d = ev.to_dict()
    assert d["glb"]["mapping_completeness"] == 1.0
    assert d["companion_feature_table"]["mapping_completeness"] == 1.0
    assert d["glb_mapping_strategy"] == "node_name_equals_building_id"
    assert d["building_id_namespace"] == "glytchdraft.phase06_building.v1"


def test_evidence_fails_when_glb_missing_a_node():
    records = [BuildingRecord("1"), BuildingRecord("2")]
    ev = attribution.compute_attribution_evidence(
        "TILE_A", records,
        glb_node_names=["bld_TILE_A_1"],  # building 2's node never written
        companion_table_building_ids=["1", "2"],
    )
    assert ev.validation_status == "fail"
    assert ev.glb_comparison.missing == ["bld_TILE_A_2"]


def test_evidence_fails_when_glb_has_extra_node():
    records = [BuildingRecord("1")]
    ev = attribution.compute_attribution_evidence(
        "TILE_A", records,
        glb_node_names=["bld_TILE_A_1", "bld_TILE_A_stray"],
        companion_table_building_ids=["1"],
    )
    assert ev.validation_status == "fail"
    assert ev.glb_comparison.extra == ["bld_TILE_A_stray"]


def test_evidence_fails_when_glb_has_duplicate_node_name():
    records = [BuildingRecord("1")]
    ev = attribution.compute_attribution_evidence(
        "TILE_A", records,
        glb_node_names=["bld_TILE_A_1", "bld_TILE_A_1"],
        companion_table_building_ids=["1"],
    )
    assert ev.validation_status == "fail"
    assert ev.glb_comparison.duplicates_in_actual == ["bld_TILE_A_1"]


def test_evidence_fails_when_companion_table_row_missing():
    records = [BuildingRecord("1"), BuildingRecord("2")]
    ev = attribution.compute_attribution_evidence(
        "TILE_A", records,
        glb_node_names=["bld_TILE_A_1", "bld_TILE_A_2"],
        companion_table_building_ids=["1"],  # malformed/incomplete companion table
    )
    assert ev.validation_status == "fail"
    assert ev.companion_table_comparison.missing == ["2"]


def test_evidence_fails_when_mapping_itself_has_duplicates():
    records = [BuildingRecord("1"), BuildingRecord("1")]
    ev = attribution.compute_attribution_evidence(
        "TILE_A", records,
        glb_node_names=["bld_TILE_A_1"],
        companion_table_building_ids=["1"],
    )
    assert ev.validation_status == "fail"
    assert ev.duplicate_building_records == 1


def test_evidence_never_reports_pass_for_a_failed_mapping():
    """A failed mapping must never be representable as validation_status=pass
    (this is the evidence input a manifest's publication.viewer_valid gate
    must not treat as satisfied when it fails)."""
    for records, glb_names, table_ids in [
        ([BuildingRecord("1"), BuildingRecord("1")], ["bld_TILE_A_1"], ["1"]),
        ([BuildingRecord("1")], [], ["1"]),
        ([BuildingRecord("1")], ["bld_TILE_A_1"], []),
        ([BuildingRecord(None)], [], []),
    ]:
        ev = attribution.compute_attribution_evidence("TILE_A", records, glb_names, table_ids)
        assert ev.validation_status == "fail"


def test_evidence_empty_tile_is_not_mislabeled_as_failed_or_per_building_complete():
    """An empty tile (zero buildings) is a legitimate INFO case, not a failure,
    per docs: 'zero-building tiles missing per-tile GLBs are INFO'. Its
    mapping_completeness must be None (not measured), not silently 1.0 or 0.0."""
    ev = attribution.compute_attribution_evidence("TILE_EMPTY", [], glb_node_names=[], companion_table_building_ids=[])
    assert ev.validation_status == "pass"
    d = ev.to_dict()
    assert d["glb"]["mapping_completeness"] is None
    assert d["companion_feature_table"]["mapping_completeness"] is None


# ── extract_glb_node_names + real pack_glb() round trip ────────────────────

def _synthetic_triangle_mesh(name: str) -> dict:
    """A minimal one-triangle mesh dict, shaped exactly as pack_glb() expects."""
    return {
        "name": name,
        "vertices": np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32),
        "faces": np.array([[0, 1, 2]], dtype=np.uint32),
        "normals": np.array([[0, 0, 1], [0, 0, 1], [0, 0, 1]], dtype=np.float32),
    }


def test_glb_round_trip_preserves_node_names_via_production_pack_glb():
    """Uses the real production GLB packer (phase_tile_common.pack_glb, also
    used unmodified by phase_08_export.py and prototype_named_glb.py) to
    prove that stable node names survive actual binary GLB encoding —
    no geometry algorithm is touched, only node naming."""
    mapping = attribution.build_node_mapping("TILE_A", [BuildingRecord("1"), BuildingRecord("2")])
    node_names = sorted(mapping.node_name_to_building_id)
    meshes = [_synthetic_triangle_mesh(name) for name in node_names]

    glb_bytes = tile_common.pack_glb(meshes)
    extracted = attribution.extract_glb_node_names(glb_bytes)

    assert sorted(extracted) == node_names


def test_glb_round_trip_detects_duplicate_node_name_in_actual_glb():
    meshes = [_synthetic_triangle_mesh("bld_TILE_A_1"), _synthetic_triangle_mesh("bld_TILE_A_1")]
    glb_bytes = tile_common.pack_glb(meshes)
    extracted = attribution.extract_glb_node_names(glb_bytes)

    cmp = attribution.compare_id_sets(["bld_TILE_A_1"], extracted)
    assert cmp.duplicates_in_actual == ["bld_TILE_A_1"]


def test_glb_round_trip_stable_across_repeated_export():
    mapping = attribution.build_node_mapping("TILE_A", [BuildingRecord("1"), BuildingRecord("2"), BuildingRecord("3")])
    node_names = sorted(mapping.node_name_to_building_id)
    meshes = [_synthetic_triangle_mesh(name) for name in node_names]

    first = attribution.extract_glb_node_names(tile_common.pack_glb(meshes))
    second = attribution.extract_glb_node_names(tile_common.pack_glb(meshes))
    assert sorted(first) == sorted(second) == node_names


def test_extract_glb_node_names_rejects_non_glb_bytes():
    with pytest.raises(ValueError):
        attribution.extract_glb_node_names(b"not a glb")


# ── tile-scoped compatibility not mislabeled ────────────────────────────────

def test_tile_scoped_strategy_constant_matches_schema_enum_value():
    """outputs.building_attribution.glb_mapping_strategy.strategy in the
    contract schema includes 'tile_scoped_no_per_building_nodes' as the
    honest label for today's production GLB (one node named after the tile).
    This module's NODE_NAME_STRATEGY must never be silently substituted for
    that value — callers choose the strategy string based on what the actual
    GLB contains, not on which module happens to be imported."""
    assert attribution.NODE_NAME_STRATEGY == "node_name_equals_building_id"
    assert attribution.NODE_NAME_STRATEGY != "tile_scoped_no_per_building_nodes"
