#!/usr/bin/env python3
"""
Deterministic per-building GLB node attribution: ID sanitization, node-name
mapping construction, and mapping validation for the
`node_name_equals_building_id` glb_mapping_strategy defined in
schemas/atlantid_tile_asset_manifest.schema.json.

This module is the bounded, testable counterpart to
scripts/phases/prototype_named_glb.py. It does not depend on Blender, PDAL,
OBJ parsing, or any real LAZ/Miami/NOLA tile data — it operates entirely on
in-memory building ID lists and GLB node-name lists, so it can be fully
exercised with synthetic fixtures.

It does not modify scripts/phases/phase_08_export.py. The current production
tile GLB (`{tile_id}.glb`, one node named after the tile) remains
`tile_scoped_no_per_building_nodes`. Wiring a per-building export path into
Phase 08 by default is a separate promotion decision — see
docs/diagnostics/ATLANTID_PER_BUILDING_GLB_ATTRIBUTION_INVESTIGATION.md.

Node naming convention (reused, not invented here): `bld_{tile_id}_{building_id}`,
already established by scripts/phases/prototype_named_glb.py,
scripts/facades/grammar_provider.py, scripts/facades/analyze_single_facade.py,
and schemas/building_synthesis_profile.schema.json's `named_building_node`
field. `building_id` itself follows the tile-scoped cluster_id convention
documented in docs/validation/BUILDING_CHARACTERISTICS_DATA_DICTIONARY.md.
"""
from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field

BUILDING_ID_NAMESPACE = "glytchdraft.phase06_building.v1"
NODE_NAME_STRATEGY = "node_name_equals_building_id"
NODE_NAME_PATTERN = "bld_{tile_id}_{building_id}"

# glTF node names are free-form strings, but the sanitized form must be safe
# to use as a JSON value, a URL path segment (GlitchOS selection/receipt
# URLs), and a stable cross-run identifier. Anything outside this set is
# deterministically collapsed to '_' — the canonical building_id is never
# itself mutated and must be recovered from the stored mapping, not by
# unsanitizing the node name.
_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_\-]")
_MAX_BUILDING_ID_LEN = 128
_MAX_NODE_NAME_LEN = 200


class BuildingIdError(ValueError):
    """Raised when a building ID fails deterministic-attribution safety rules."""


def sanitize_component(value: str, *, label: str) -> str:
    """Deterministically sanitize one node-name component (tile_id or building_id).

    Raises BuildingIdError for null, non-string, empty, or oversized input.
    """
    if value is None:
        raise BuildingIdError(f"{label} must not be null")
    if not isinstance(value, str):
        raise BuildingIdError(f"{label} must be a string, got {type(value).__name__}")
    if value == "":
        raise BuildingIdError(f"{label} must not be empty")
    if len(value) > _MAX_BUILDING_ID_LEN:
        raise BuildingIdError(f"{label} exceeds {_MAX_BUILDING_ID_LEN} chars: {value!r}")
    return _UNSAFE_CHARS_RE.sub("_", value)


def sanitize_node_name(tile_id: str, building_id: str, *, part_index: int = 0) -> str:
    """Build the deterministic glTF node name for one building (or building part).

    part_index == 0 uses the bare `bld_{tile_id}_{building_id}` form (matching
    existing prototype/facade convention exactly). part_index > 0 appends
    `_part{N}` so a multi-part building can emit more than one node while
    every node still resolves back to the same canonical building_id via the
    returned mapping (see build_node_mapping), not via string parsing.
    """
    safe_tile = sanitize_component(tile_id, label="tile_id")
    safe_building = sanitize_component(building_id, label="building_id")
    node_name = NODE_NAME_PATTERN.format(tile_id=safe_tile, building_id=safe_building)
    if part_index:
        if part_index < 0:
            raise BuildingIdError(f"part_index must be >= 0, got {part_index}")
        node_name = f"{node_name}_part{part_index}"
    if len(node_name) > _MAX_NODE_NAME_LEN:
        raise BuildingIdError(f"generated node name exceeds {_MAX_NODE_NAME_LEN} chars: {node_name!r}")
    return node_name


@dataclass
class BuildingRecord:
    """One (building_id, part_index) pair to attribute to a GLB node."""

    building_id: str
    part_index: int = 0


@dataclass
class AttributionMapping:
    """Result of building_node_mapping: deterministic, order-independent."""

    tile_id: str
    building_id_namespace: str
    node_name_to_building_id: dict = field(default_factory=dict)
    building_id_to_node_names: dict = field(default_factory=dict)
    duplicate_records: list = field(default_factory=list)
    node_name_collisions: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.duplicate_records and not self.node_name_collisions and not self.errors


def build_node_mapping(tile_id: str, records: list[BuildingRecord]) -> AttributionMapping:
    """Build a deterministic building_id <-> node_name mapping.

    Input order never affects the resulting mapping: node_name_to_building_id
    and building_id_to_node_names are plain dicts built from the (building_id,
    part_index) identity of each record, not from list position.

    Detects (without raising):
      - duplicate_records: the exact same (building_id, part_index) pair
        appears more than once in `records` (a real duplicate, not a
        legitimate multi-part building).
      - node_name_collisions: two different (building_id, part_index) pairs
        sanitize to the same node_name (e.g. "a/b" and "a b" both -> "a_b").
      - errors: records whose building_id failed sanitize_node_name
        (null, empty, oversized, or otherwise unsafe).

    AttributionMapping.ok is False if any of the above occurred; callers must
    check .ok (or the mapping-completeness fields from
    compute_attribution_evidence) before treating the mapping as usable.
    """
    seen_pairs: dict[tuple, int] = {}
    node_to_building: dict[str, str] = {}
    building_to_nodes: dict[str, list[str]] = {}
    duplicate_records: list[dict] = []
    node_name_collisions: dict[str, list[str]] = {}
    errors: list[dict] = []

    for rec in records:
        pair = (rec.building_id, rec.part_index)
        seen_pairs[pair] = seen_pairs.get(pair, 0) + 1
        if seen_pairs[pair] > 1:
            duplicate_records.append({"building_id": rec.building_id, "part_index": rec.part_index})
            continue

        try:
            node_name = sanitize_node_name(tile_id, rec.building_id, part_index=rec.part_index)
        except BuildingIdError as exc:
            errors.append({"building_id": rec.building_id, "part_index": rec.part_index, "reason": str(exc)})
            continue

        if node_name in node_to_building and node_to_building[node_name] != rec.building_id:
            node_name_collisions.setdefault(node_name, [node_to_building[node_name]]).append(rec.building_id)
            continue

        node_to_building[node_name] = rec.building_id
        building_to_nodes.setdefault(rec.building_id, []).append(node_name)

    return AttributionMapping(
        tile_id=tile_id,
        building_id_namespace=BUILDING_ID_NAMESPACE,
        node_name_to_building_id=node_to_building,
        building_id_to_node_names=building_to_nodes,
        duplicate_records=duplicate_records,
        node_name_collisions=node_name_collisions,
        errors=errors,
    )


@dataclass
class SetComparison:
    """Deterministic comparison between an expected ID set and an actual ID set."""

    matched: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    extra: list = field(default_factory=list)
    duplicates_in_actual: list = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing and not self.extra and not self.duplicates_in_actual

    @property
    def completeness_ratio(self) -> float | None:
        total = len(self.matched) + len(self.missing)
        if total == 0:
            return None  # empty tile: completeness is not meaningful, not zero
        return len(self.matched) / total


def compare_id_sets(expected: list[str], actual: list[str]) -> SetComparison:
    """Compare an expected ID list (e.g. building IDs) against an actual ID
    list (e.g. GLB node names or companion-table IDs), detecting missing,
    extra, and duplicate-in-actual entries. Order in either list never
    affects the result.
    """
    expected_set = set(expected)
    actual_counts: dict[str, int] = {}
    for item in actual:
        actual_counts[item] = actual_counts.get(item, 0) + 1
    actual_set = set(actual_counts)

    matched = sorted(expected_set & actual_set)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    duplicates_in_actual = sorted(k for k, v in actual_counts.items() if v > 1)

    return SetComparison(matched=matched, missing=missing, extra=extra, duplicates_in_actual=duplicates_in_actual)


@dataclass
class AttributionEvidence:
    """Structured evidence for one tile's per-building GLB attribution.

    Shaped to be embeddable as a companion evidence report (JSON-serializable
    via to_dict()) alongside a manifest's outputs.building_attribution
    fields. This module does not write directly into
    schemas/atlantid_tile_asset_manifest.schema.json — the schema's
    registry_ref-based validation_results entries require concrete
    method_registry/validation_registry documents that do not exist yet
    (see docs/diagnostics/ATLANTID_TILE_ASSET_CONTRACT_V1.md §7 item 5).
    """

    tile_id: str
    building_id_namespace: str
    glb_mapping_strategy: str
    mapping_errors: int
    duplicate_building_records: int
    node_name_collisions: int
    glb_comparison: SetComparison
    companion_table_comparison: SetComparison
    validation_status: str  # "pass" | "fail"

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "building_id_namespace": self.building_id_namespace,
            "glb_mapping_strategy": self.glb_mapping_strategy,
            "mapping_errors": self.mapping_errors,
            "duplicate_building_records": self.duplicate_building_records,
            "node_name_collisions": self.node_name_collisions,
            "glb": {
                "matched_count": len(self.glb_comparison.matched),
                "missing_count": len(self.glb_comparison.missing),
                "extra_count": len(self.glb_comparison.extra),
                "duplicate_node_name_count": len(self.glb_comparison.duplicates_in_actual),
                "mapping_completeness": self.glb_comparison.completeness_ratio,
            },
            "companion_feature_table": {
                "matched_count": len(self.companion_table_comparison.matched),
                "missing_count": len(self.companion_table_comparison.missing),
                "extra_count": len(self.companion_table_comparison.extra),
                "duplicate_row_id_count": len(self.companion_table_comparison.duplicates_in_actual),
                "mapping_completeness": self.companion_table_comparison.completeness_ratio,
            },
            "validation_status": self.validation_status,
        }


def compute_attribution_evidence(
    tile_id: str,
    records: list[BuildingRecord],
    glb_node_names: list[str],
    companion_table_building_ids: list[str],
) -> AttributionEvidence:
    """Compute full deterministic attribution evidence for one tile.

    validation_status is "pass" only when:
      - the ID/node mapping itself produced no errors, duplicate records, or
        node-name collisions;
      - every expected building_id resolves to exactly one GLB node and
        vice versa (no missing, no extra, no duplicate GLB node names);
      - every expected building_id has exactly one companion-table row and
        vice versa (no missing, no extra, no duplicate row IDs).

    A "fail" validation_status must block any claim that per-building GLB
    attribution is complete for this tile (see publication.viewer_valid in
    schemas/atlantid_tile_asset_manifest.schema.json — this evidence is an
    input to that gate, not a replacement for it).
    """
    mapping = build_node_mapping(tile_id, records)
    expected_building_ids = sorted(mapping.building_id_to_node_names)
    expected_node_names = sorted(mapping.node_name_to_building_id)

    glb_comparison = compare_id_sets(expected_node_names, glb_node_names)
    companion_comparison = compare_id_sets(expected_building_ids, companion_table_building_ids)

    validation_status = (
        "pass"
        if mapping.ok and glb_comparison.complete and companion_comparison.complete
        else "fail"
    )

    return AttributionEvidence(
        tile_id=tile_id,
        building_id_namespace=BUILDING_ID_NAMESPACE,
        glb_mapping_strategy=NODE_NAME_STRATEGY,
        mapping_errors=len(mapping.errors),
        duplicate_building_records=len(mapping.duplicate_records),
        node_name_collisions=len(mapping.node_name_collisions),
        glb_comparison=glb_comparison,
        companion_table_comparison=companion_comparison,
        validation_status=validation_status,
    )


def extract_glb_node_names(glb_bytes: bytes) -> list[str]:
    """Parse a GLB binary's JSON chunk and return every node's `name` field,
    in the order nodes appear in the glTF `nodes` array.

    Duplicate names are preserved (not deduplicated) so callers such as
    compare_id_sets can detect duplicate-in-actual node names. Nodes without
    a `name` field are skipped (they cannot participate in
    node_name_equals_building_id attribution).

    Pure struct/json parsing — no Blender, no pygltflib, no PDAL.
    """
    if len(glb_bytes) < 20:
        raise ValueError("not a valid GLB: too short for header + chunk header")
    magic, version, _length = struct.unpack_from("<III", glb_bytes, 0)
    if magic != 0x46546C67:
        raise ValueError("not a valid GLB: bad magic")
    json_len, chunk_type = struct.unpack_from("<II", glb_bytes, 12)
    if chunk_type != 0x4E4F534A:
        raise ValueError("not a valid GLB: first chunk is not JSON")
    gltf = json.loads(glb_bytes[20 : 20 + json_len])
    return [node["name"] for node in gltf.get("nodes", []) if "name" in node]
