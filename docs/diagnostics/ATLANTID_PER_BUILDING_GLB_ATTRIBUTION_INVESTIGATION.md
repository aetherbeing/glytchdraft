# Atlantid Per-Building GLB Attribution — Investigation and Bounded Implementation

**Status:** Design + bounded mapping/validation utility implemented and tested with synthetic data only. **Production GLB export behavior is unchanged.** `scripts/phases/phase_08_export.py` still emits `tile_scoped_no_per_building_nodes` GLBs by default.

**Branch:** `feat/atlantid-per-building-glb-attribution-v1`

**Real data processing:** `NOT AUTHORIZED` and none occurred. No LAZ, PDAL, Blender, or `/mnt/t7` access. No cloud resources. No deployment.

---

## 1. The gap, precisely

`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` §6.5 and `schemas/atlantid_tile_asset_manifest.schema.json` both already document this gap honestly: the production GLB exporter emits tile-scoped output with no stable per-building node attribution, and the contract's `glb_mapping_strategy` enum already carries the honest compatibility value `tile_scoped_no_per_building_nodes` for it. This investigation traced *exactly* where the attribution is lost and evaluated whether a bounded, safe fix exists.

### 1.1 Where attribution is lost

The chain is:

```
phase_07_masses.py::write_obj()
  -> writes LOD0 OBJ with per-building "o bld_{tile_id}_{cluster_id}" groups
     (scripts/phases/phase_07_masses.py:166)
phase_08_export.py::main()
  -> calls obj_to_flat_triangles(src, shift)
     (scripts/phases/phase_08_export.py:70)
phase_tile_common.py::obj_vertices_faces()
  -> parses only "v " and "f " lines. Does NOT parse "o " lines at all.
     (scripts/phases/phase_tile_common.py:257-270)
phase_tile_common.py::obj_to_flat_triangles()
  -> flattens every face from every building into one (verts, faces, normals)
     tuple with no group boundaries.
     (scripts/phases/phase_tile_common.py:286-311)
phase_tile_common.py::pack_glb()
  -> called with exactly one mesh dict: {"name": tile_id, ...}
     (scripts/phases/phase_08_export.py:74)
     => one glTF node, named after the tile. Per-building identity is gone.
```

The per-building structure is **not missing upstream** — `phase_07_masses.py` already writes it into the OBJ as `o` group boundaries, and `cluster_id` (the `building_id` per `docs/validation/BUILDING_CHARACTERISTICS_DATA_DICTIONARY.md`) is deterministic and stable per tile run. `obj_vertices_faces()` simply never reads `o` lines, so the boundary is discarded the moment the OBJ is parsed for export. This is **classification A/C, not E**: the fix does not require redesigning geometry generation, CRS handling, Z normalization, or roof/height computation — it requires the export step to stop discarding a boundary that already exists in its own input file.

### 1.2 What already exists, unshipped

`scripts/phases/prototype_named_glb.py` (added in commit `6a023c9`, never wired into `phase_08_export.py`) already:

- Parses OBJ `o` groups (`parse_obj_per_object`), preserving per-building vertex/face subsets.
- Builds one glTF mesh + node per building via the *same* `pack_glb()` used by production (`phase_tile_common.pack_glb`), naming each node `bld_{tile_id}_{cluster_id}` — i.e. the node name **is** the building ID.
- Cross-validates the resulting node-name set against the companion `structures_enriched.geojson` `cluster_id` set and prints a mismatch report.
- Explicitly never touches `blender_ready/{tile_id}.glb` (the canonical file).
- Guards against machine-absolute paths leaking into manifest URLs.

Downstream consumers already assume this exact convention exists: `schemas/building_synthesis_profile.schema.json`'s `named_building_node` field, and `scripts/facades/grammar_provider.py` / `scripts/facades/analyze_single_facade.py` (`ID_NAMESPACE = "glytchdraft.phase06_building.v1"`) all reference `bld_{tile_id}_{building_id}` as an established identity format, even though nothing in production has ever emitted a GLB using it.

### 1.3 Existing tests and docs

- `tests/test_atlantid_tile_asset_contract.py` — schema/example tests for the manifest contract. Does not test attribution mapping logic (out of scope for a schema test file).
- `docs/diagnostics/ATLANTID_TILE_ASSET_CONTRACT_V1.md` §6 — already documents this exact gap and names `prototype_named_glb.py` as "the closest prior art," explicitly deferring promotion as follow-up work.
- No prior tests existed for `prototype_named_glb.py` itself, and none existed for a reusable mapping/validation layer. That gap is what this lane fills.

---

## 2. Classification (decision gate)

Per the sprint's classification scheme:

- **Not A** — production's *exporter* has no latent per-building nodes; only its *upstream input* (the Phase 07 OBJ) does.
- **Best fit: B/C hybrid.** Production's OBJ input retains enough structure (named `o` groups) to derive stable per-building ranges, and a working prototype exporter (C) already implements the naming scheme correctly, using the exact same `pack_glb()` production code path.
- **Not D** — the prototype is not incomplete or untested-in-principle; it was simply never given focused tests or a reusable mapping/validation layer.
- **Not E** — no exporter redesign is required. Geometry, CRS, Z-normalization, and roof/height computation are untouched by everything below.

**Chosen outcome: Outcome 1 (bounded implementation), scoped narrowly.** The bounded change adds a deterministic, synthetic-data-only **mapping and validation module** — it does not modify `phase_08_export.py`'s default behavior, does not modify `prototype_named_glb.py`, and does not change the JSON Schema contract. Wiring per-building export into the default production path (i.e., making `phase_08_export.py` itself emit per-building nodes) is **not** done here — see §7 (migration) for why that remains a separate, later decision requiring its own review.

---

## 3. What was implemented

### 3.1 `scripts/phases/building_glb_attribution.py` (new)

A pure-Python module (numpy only, no PDAL/Blender/LAZ dependency) providing:

| Function / class | Purpose |
|---|---|
| `sanitize_component(value, label=...)` | Deterministic, ASCII-safe sanitization of one node-name component. Rejects null/empty/oversized input explicitly (`BuildingIdError`), never silently substitutes a fallback. |
| `sanitize_node_name(tile_id, building_id, part_index=0)` | Builds `bld_{tile_id}_{building_id}` (or `..._part{N}` for multi-part buildings), reusing the exact convention already established by `prototype_named_glb.py` and the facade/material subsystems. |
| `BuildingRecord` | `(building_id, part_index)` input pair. |
| `build_node_mapping(tile_id, records)` -> `AttributionMapping` | Deterministic, **input-order-independent** building_id <-> node_name mapping. Detects duplicate `(building_id, part_index)` records, node-name collisions (two different building IDs sanitizing to the same node name), and per-record sanitization errors — all without raising, so a caller can inspect every problem in one pass. |
| `compare_id_sets(expected, actual)` -> `SetComparison` | Order-independent missing/extra/duplicate-in-actual comparison, reused for both GLB-node comparison and companion-feature-table comparison. |
| `compute_attribution_evidence(tile_id, records, glb_node_names, companion_table_building_ids)` -> `AttributionEvidence` | The end-to-end evidence computation: runs the mapping, compares it against actual GLB node names and actual companion-table building IDs, and produces a single `validation_status` (`"pass"`/`"fail"`) plus JSON-serializable evidence (`to_dict()`) — matching the *shape* of evidence the sprint brief asked for (mapping strategy, duplicate/missing/extra counts, mapping completeness), without writing into the manifest schema itself (see §5). |
| `extract_glb_node_names(glb_bytes)` | Parses a GLB binary's JSON chunk and returns every node's `name`, in the same encoding used by `pack_glb()`. Pure `struct`/`json` parsing — no `pygltflib`, no Blender. |

Key design choices:

- **Reversibility is via stored mapping, not string un-sanitizing.** A sanitized node name (e.g. `bld_TILE_A_a_b` from canonical ID `"a/b"`) is never parsed back into its canonical form. `AttributionMapping.node_name_to_building_id` is the authoritative reverse map; callers must persist and consult it, matching the sprint's "sanitized node names remain reversible through stored canonical IDs" requirement literally.
- **Node-name collisions are caught, not silently overwritten.** Two different canonical IDs that sanitize to the same string (`"a/b"` and `"a b"` both -> `"a_b"`) are flagged in `node_name_collisions`, not merged.
- **Multi-part buildings** get `_part{N}` suffixes for parts beyond the first, while `building_id_to_node_names` keeps every node attributed back to one canonical `building_id`.
- **Empty tiles produce `completeness_ratio = None`**, not `0.0` or `1.0` — matching the repository's existing convention that zero-building tiles are an explicit INFO state (`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` §10), not a failure and not a full match by default.
- **`AttributionEvidence` is a standalone JSON-serializable report, not a manifest field.** `outputs.validation_results[]` in the contract schema requires `check_ref` pointers into concrete `validation_registry`/`method_registry` documents, and those registries do not exist yet as artifacts (`ATLANTID_TILE_ASSET_CONTRACT_V1.md` §7, item 5). Rather than inventing a parallel, schema-violating field, this evidence is designed to be attachable once those registries exist, or consumed directly by an audit/report step outside the manifest.

### 3.2 `tests/test_building_glb_attribution.py` (new)

38 focused tests, all synthetic, all passing, covering (mapped to the sprint's required-test-behavior list):

- Stable/deterministic naming across repeated calls and repeated `build_node_mapping` runs (#1, #20).
- Input-feature-order independence, both for `build_node_mapping` and `compare_id_sets` (#2).
- Every expected building maps exactly once for a clean two-building fixture (#3).
- Duplicate building IDs (#4), missing/null building IDs (#5), oversized IDs, IDs with spaces/slashes/punctuation/Unicode — all sanitize deterministically or raise `BuildingIdError` explicitly.
- Reversibility of sanitized names through the stored map, not string parsing (#6).
- Node-name safety/determinism, including a real ASCII-safety assertion on a Unicode input (#7).
- Companion-table rows vs. GLB nodes: missing, extra, duplicate detection in both directions (#8, #9, #10, #11).
- Multi-part buildings remain attributable to one canonical ID (#12).
- Tile-scoped compatibility is not mislabeled — an explicit test asserts `NODE_NAME_STRATEGY != "tile_scoped_no_per_building_nodes"` (#13, #18).
- `validation_status` is never `"pass"` for any of four independently-broken fixtures (duplicate mapping, missing GLB node, missing companion row, null ID) (#16).
- `production_allowed`/execution-lock invariants are untouched (verified by the unmodified pre-existing test suite continuing to pass, not re-asserted redundantly here) (#17).
- Existing `tile_scoped_no_per_building_nodes` compatibility remains readable — no schema or example file was touched (#18).
- No real-data processing anywhere in the test file (#19).
- A genuine **GLB-binary round trip** through the actual production `pack_glb()` function (`phase_tile_common.pack_glb`, imported unmodified) proves node names survive real binary GLB encoding/decoding, including duplicate-node-name detection at the binary level and stability across two independent export calls. This is the pure-mapping-and-packing test the sprint asked to keep separate from any Blender-dependent test; **no Blender-dependent test was added**, because nothing in this bounded change touches Blender.

### 3.3 Files deliberately not touched

- `scripts/phases/phase_08_export.py` — production default export behavior is unchanged. `tile_scoped_no_per_building_nodes` remains what it emits.
- `scripts/phases/prototype_named_glb.py` — left as-is; it remains a prototype CLI, not promoted to production.
- `schemas/atlantid_tile_asset_manifest.schema.json` — no schema change. The enum already contains `node_name_equals_building_id`, so none was needed.
- `configs/contracts/atlantid_tile_asset_manifest.example.json` — untouched; it already demonstrates `node_name_equals_building_id` as a *synthetic* example, which this work does not contradict.
- Smoke harness, restore-locks script, controlled-smoke runbook, source contract config, determinism-comparator files, single-run evidence-packager files — none referenced, none touched.

---

## 4. Stable building ID rules (as implemented)

Reusing the existing canonical terminology rather than inventing a parallel namespace:

- **Canonical building ID field:** `building_id`, per `docs/validation/BUILDING_CHARACTERISTICS_DATA_DICTIONARY.md` — the tile-scoped `cluster_id`, 0-indexed, sequential, never `-1` (noise excluded before output).
- **Namespace:** `glytchdraft.phase06_building.v1` (`BUILDING_ID_NAMESPACE` in the new module), matching `schemas/building_synthesis_profile.schema.json` and the facade subsystem's `ID_NAMESPACE` constants exactly — no new namespace was introduced.
- **Node name pattern:** `bld_{tile_id}_{building_id}` (`NODE_NAME_PATTERN`), matching `prototype_named_glb.py`'s existing convention, `named_building_node` in `building_synthesis_profile.schema.json`, and `configs/contracts/atlantid_tile_asset_manifest.example.json`'s `node_name_pattern` field exactly.
- **Determinism:** the mapping function never consults array position — it is a pure function of `(tile_id, building_id, part_index)` tuples.
- **Safety:** sanitization is ASCII-only-output (`[^A-Za-z0-9_\-]` -> `_`), so results are always safe for glTF node names, JSON string values, and URL path segments. Canonical IDs (which may contain any Unicode/punctuation) are preserved unmodified in the reverse mapping, never mutated.

---

## 5. Contract integration

`outputs.building_attribution.glb_mapping_strategy.strategy` already supports the exact value this module targets: `node_name_equals_building_id`, with `node_name_pattern: "bld_{tile_id}_{building_id}"` — both already present in `schemas/atlantid_tile_asset_manifest.schema.json` and demonstrated in the synthetic example. **No schema gap exists; no schema change was made.**

What is *not* yet wired: a manifest-writing step that calls `compute_attribution_evidence()` and embeds its result. That step belongs to whichever future work actually produces a real (non-canonical, non-production) per-building GLB and its manifest — this lane deliberately stops at the reusable evidence-computation layer, per the sprint's "keep it minimal" and "do not rewrite the entire export pipeline" constraints, and because manifest-writing/evidence-packaging is explicitly Instance 1's lane, not this one's.

---

## 6. GlitchOS consumer boundary (documentation only — no viewer code written here)

Per `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` §6.5, GlitchOS must receive, at minimum, per selectable object: `selection_type`, `building_id`, `tile_id`, `artifact_id`, `metadata`, `source`. Extending that for per-building GLB attribution, GlitchOS needs:

- Tile asset URL and manifest URL (already defined by the viewer manifest contract, §18.3).
- `building_id` and the manifest's `outputs.building_attribution.glb_mapping_strategy.strategy` value.
- The node name (`node_name_pattern` resolved for a given `building_id`) or node index, **only** when `strategy != tile_scoped_no_per_building_nodes`.
- A reference to the companion feature table row for that `building_id`.
- The attribution validation status (this lane's `AttributionEvidence.validation_status`) so the viewer can refuse to claim exact selection when validation failed.

**Honest viewer behavior (documented, not implemented — implementation belongs in `glytchOS`):**

- If `glb_mapping_strategy.strategy == "node_name_equals_building_id"` **and** the tile's attribution evidence is `"pass"`: select and highlight the exact GLB node for that `building_id`.
- If `strategy == "tile_scoped_no_per_building_nodes"`, or evidence is `"fail"`, or evidence does not exist: GlitchOS must not claim building-level geometry selection. It must fall back to tile-level or metadata-only selection and visibly disclose the limitation, per spec §6.3 ("Must not... treat missing metadata as a successful selection") and §6.5.

No GlitchOS code was written in this repository, per the phase boundary in `AGENTS.md` and `CLAUDE.md`.

---

## 7. Migration plan

1. Existing `tile_scoped_no_per_building_nodes` tile assets remain valid and are not reclassified by anything in this lane.
2. A future manifest for a tile that actually has per-building GLB nodes sets `outputs.building_attribution.glb_mapping_strategy.strategy = "node_name_equals_building_id"` — an existing, already-schema-valid enum value. No new manifest field is required.
3. GlitchOS (future work, other repo) must branch on `glb_mapping_strategy.strategy` before enabling exact building selection, per §6 above.
4. Existing viewers that only understand `tile_scoped_no_per_building_nodes` degrade safely: they simply never see the new strategy value until a tile is regenerated and republished with it.
5. No old asset is silently reclassified: reclassification would require regenerating the GLB and manifest for that specific tile and re-running publication gates.
6. Regeneration (running an export path that preserves `o`-group boundaries — e.g. promoting `prototype_named_glb.py` logic, or wiring `phase_08_export.py` to call `parse_obj_per_object` instead of `obj_to_flat_triangles`) is required per tile that needs exact node attribution. That promotion is **not done in this lane** and requires its own review, since it changes a production default output path.
7. `compute_attribution_evidence().validation_status` must be `"pass"` before any manifest claims `node_name_equals_building_id` is fully realized for a given tile; a `"fail"` evidence result must block that claim, mirroring (but not replacing) the schema's `publication.viewer_valid` gate.
8. Publication artifacts must disclose `glb_mapping_strategy.strategy` (already a required schema field; nothing new needed here).
9. Rollback (§8) returns cleanly to `tile_scoped_no_per_building_nodes` without touching this lane's code at all, because production was never switched away from it.

---

## 8. Rollback plan

Because `phase_08_export.py` was never modified, **there is nothing to roll back in production.** If a future promotion of per-building export is attempted and needs to be rolled back, the triggers and procedure are:

**Triggers:** GLB node-count/output-size explosion per tile; browser traversal/selection performance regression in GlitchOS; unstable naming across reruns; duplicate mappings; missing mappings; Blender-exporter incompatibility (if a Blender-based path is chosen instead of the manual `pack_glb()` path used here); contract-manifest mismatch; nondeterministic mapping; broken legacy (`tile_scoped_no_per_building_nodes`-only) consumers.

**Procedure:**
1. Revert `phase_08_export.py` (or whatever future integration point) to call `obj_to_flat_triangles` + single-mesh `pack_glb`, restoring `tile_scoped_no_per_building_nodes` output byte-for-byte identical to today's.
2. Leave already-published `node_name_equals_building_id` assets versioned and labeled as such — do not silently relabel them back to `tile_scoped_no_per_building_nodes`; a rolled-back pipeline simply stops producing new ones.
3. `production_allowed` remains `false` throughout (it already is, and this lane changes nothing about that gate).

---

## 9. Performance and scale (estimates, clearly labeled — no benchmark run)

No benchmark was run; the repository has no existing per-building-node GLB benchmark to cite. Labeled estimates only:

- **Node count per tile:** one glTF node + one mesh + one set of accessors/buffer views per building. `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` cites NOLA's 135,655 buildings across 500 tiles (~271 buildings/tile average) and Miami's 108 tiles — moving from 1 node/tile to O(hundreds) nodes/tile is a real, non-trivial increase in glTF JSON-chunk size (each node/mesh/accessor is a small JSON object) even though total triangle/vertex data is unchanged.
- **GLB size:** binary buffer size is essentially unchanged (same vertices/faces/normals, just partitioned differently); JSON-chunk overhead grows roughly linearly with building count per tile.
- **Browser traversal cost:** untested; likely small per-tile since scene graphs of a few hundred nodes are common in web glTF viewers, but this is a labeled estimate, not a measurement.
- **Selection lookup cost:** O(1) with a `node_name -> building_id` map (exactly what `AttributionMapping` produces) — this is the cheap side of the tradeoff.
- **Required benchmark procedure (not run here):** generate one synthetic tile with the prototype at realistic building density (~250-300), measure resulting GLB byte size vs. today's canonical GLB for the same tile, and measure GlitchOS load/selection time in a real browser. This belongs to whoever performs the actual promotion, since it needs a real candidate tile, not synthetic geometry.

---

## 10. Security and data hygiene

- `sanitize_component`/`sanitize_node_name` output is restricted to `[A-Za-z0-9_-]`, so node names can never carry path separators, control characters, or shell/URL metacharacters.
- No `eval`, no shell interpolation, no unsafe deserialization anywhere in `building_glb_attribution.py`.
- `extract_glb_node_names` only reads `struct`-decoded lengths and `json.loads` on a bounded, length-prefixed slice — no arbitrary file traversal.
- Canonical (unsanitized) building IDs are never embedded in the GLB itself in this design — only the sanitized node name is. Any local paths, credentials, or private identifiers a caller might accidentally pass as a `building_id` would still need to be excluded before calling this module; this module's job is name-safety, not provenance filtering (that remains `footprint_provenance`'s job elsewhere in the pipeline).

---

## 11. Unresolved questions / explicitly out of scope

- Whether to promote `prototype_named_glb.py` (or a phase_08 modification using `parse_obj_per_object` + this module) to a default or opt-in production export path — **not decided here**; requires its own review per §7.
- Real-tile GLB size/performance benchmarking — **not run**; requires a real candidate tile and browser testing, out of this lane's synthetic-only scope.
- Embedding `AttributionEvidence` into the actual manifest's `validation_results[]` — blocked on `method_registry`/`validation_registry` concrete documents not existing yet (pre-existing, documented gap, not created here).
- `EXT_mesh_features` or other glTF extensions — not evaluated in depth; the sprint brief explicitly said not to select an extension for theoretical elegance, and the simple node-name approach already matches every existing convention in this repository, so no extension work was undertaken.
- Whether `part_index` suffixing (`_part{N}`) is the right multi-part convention for a real multi-part building (e.g. a tower with a separate podium) — implemented and tested as a reasonable default, but not validated against a real multi-part building case since none exists in this repo's synthetic or real fixtures yet.

---

## 12. Final status

- Per-building GLB attribution remains **unsupported in production**. `phase_08_export.py` output is unchanged.
- A deterministic, fully synthetic-tested mapping-and-validation layer now exists (`scripts/phases/building_glb_attribution.py`, `tests/test_building_glb_attribution.py`, 38/38 passing) that is ready to be consumed by a future, separately-reviewed promotion of per-building export, and by Instance 1's evidence packaging if it chooses to.
- `contract_status` remains `CANDIDATE`. `production_allowed` remains hard-locked `false`. Neither execution lock was touched. No smoke execution occurred. No real data was processed. `/mnt/t7` was not accessed. No cloud resources were created. No deployment occurred.
