from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIAMI_DIR = REPO_ROOT / "scripts" / "miami"
sys.path.insert(0, str(MIAMI_DIR))

import run_cross_tile_ownership_fixture as fixture  # noqa: E402


def _run(reverse: bool = False) -> dict:
    return fixture.run_fixture(
        source_root=Path("/tmp/glytchdraft_missing_fixture_sources"),
        hash_sources=False,
        reverse_input_order=reverse,
    )


def _building(result: dict, footprint_id: str) -> dict:
    return next(item for item in result["emitted_buildings"] if item["footprint_id"] == footprint_id)


def test_context_from_both_sides_of_seam_is_available_before_clustering():
    result = _run()
    crossing = _building(result, "fixture_seam_crossing_not_1601_collins")

    assert crossing["context_tiles_before_clustering"] == ["318155", "318455"]
    assert crossing["point_contribution_by_tile"]["318155"] > 0
    assert crossing["point_contribution_by_tile"]["318455"] > 0


def test_exactly_one_owner_is_selected():
    result = _run()
    crossing = _building(result, "fixture_seam_crossing_not_1601_collins")

    assert crossing["ownership_decision"]["owner_tile"] == "318155"
    assert crossing["ownership_decision"]["rule"] == "representative_interior_point"


def test_reversing_input_tile_order_produces_same_owner_and_identifier():
    normal = _run()
    reversed_order = _run(reverse=True)

    normal_pairs = [
        (item["stable_entity_identifier"], item["ownership_decision"]["owner_tile"])
        for item in normal["emitted_buildings"]
    ]
    reversed_pairs = [
        (item["stable_entity_identifier"], item["ownership_decision"]["owner_tile"])
        for item in reversed_order["emitted_buildings"]
    ]

    assert normal_pairs == reversed_pairs


def test_seam_crossing_entity_is_not_emitted_twice():
    result = _run()
    footprint_ids = [item["footprint_id"] for item in result["emitted_buildings"]]

    assert footprint_ids.count("fixture_seam_crossing_not_1601_collins") == 1
    assert result["duplicate_suppression_result"]["no_duplicate_footprint_ids"] is True


def test_seam_crossing_entity_is_not_clipped_to_owner_tile_before_construction():
    result = _run()
    crossing = _building(result, "fixture_seam_crossing_not_1601_collins")
    cluster_min_y = crossing["cluster_bounds"][1]
    cluster_max_y = crossing["cluster_bounds"][4]
    owner_tile = crossing["ownership_decision"]["owner_tile"]
    owner_bounds = result["tile_bounds"][owner_tile]

    assert cluster_max_y > owner_bounds[3]
    assert cluster_min_y < owner_bounds[3]


def test_non_crossing_buildings_remain_owned_by_their_natural_tile():
    result = _run()
    natural = _building(result, "fixture_natural_318455")

    assert natural["ownership_decision"]["owner_tile"] == "318455"
    assert natural["candidate_results"]["representative_interior_point"] == "318455"


def test_tie_behavior_is_deterministic():
    result = _run()
    tied = _building(result, "fixture_exact_area_tie")

    assert tied["candidate_results"]["largest_intersection_tie_candidates"] == ["318155", "318455"]
    assert tied["ownership_decision"]["owner_tile"] == "318155"
    assert tied["ownership_decision"]["tie_break"] == "lexicographic_tile_id_when_candidate_scores_match"


def test_generated_metadata_records_all_contributing_source_tiles():
    result = _run()
    crossing = _building(result, "fixture_seam_crossing_not_1601_collins")

    assert crossing["contributing_source_tiles"] == ["318155", "318455"]
    assert set(crossing["point_contribution_by_tile"]) == {"318155", "318455"}


def test_no_claim_is_made_that_cluster_identity_proves_exact_1601_collins_parcel():
    result = _run()
    payload = str(result).lower()

    assert "1601 collins" in payload
    assert "exact 1601 collins parcel" in payload
    assert "repaired" not in payload
    assert "repair" not in payload
