# Atlantid Determinism Comparison Procedure

**Status:** tooling only, awaiting two completed authorized Miami controlled-smoke runs.

**Real data processing:** `NOT PERFORMED BY THIS TOOL`

**Scope:** `scripts/diagnostics/atlantid_determinism_comparator.py`,
`schemas/atlantid_determinism_report.schema.json`, this document, and
`tests/test_atlantid_determinism_comparator.py`. This lane does not execute the
Miami smoke, does not process LAZ data, does not access `/mnt/t7`, does not
modify either `REAL_DATA_EXECUTION_ENABLED` execution lock, does not modify
`production_allowed`, and does not modify
`scripts/diagnostics/miami_metric_smoke_harness.py`,
`docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md`, or the missing
`scripts/diagnostics/building_characteristics_validator.py` (owned by a
separate repair lane).

---

## 1. Purpose

Once two authorized, completed Miami controlled-smoke runs exist (each
produced by `scripts/diagnostics/miami_metric_smoke_harness.py
--controlled-smoke --execute`, per
`docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md`), this tool
compares the two output roots and answers, honestly and without silently
hiding any difference:

1. Did both runs process the same exact authorized inputs?
2. Did both runs produce the same expected file inventory?
3. Are corresponding files byte-identical?
4. Where byte identity is not expected, are outputs semantically equivalent
   after documented normalization?
5. Do CRS, units, bounds, Z-related values, point counts, class counts,
   geometry counts, and metadata counts agree (where evidence exists)?
6. Are any differences expected and explained?
7. Did either run contain a third tile?
8. Did either run write output outside its authorized root?
9. Does either run contain missing, unexpected, or unverifiable evidence?
10. Can the result be classified honestly as `PASS`, `PASS WITH NON-BLOCKING
    FINDINGS`, or `FAIL`?

**No successful real Miami smoke run exists yet.** The first authorized smoke
attempt (`/tmp/glytchdraft-miami-controlled-smoke-20260702T030834Z`) failed
safely before any tile processing because
`scripts/diagnostics/building_characteristics_validator.py` was missing. That
root has no `tiles/` directory and no processing outputs. This tool has not
read or modified it, and its own completeness check
(`validate_run_completeness`) is designed so that a root shaped like it is
refused outright, never silently treated as a successful Run A or Run B — see
§6.

---

## 2. Required inputs

```bash
python scripts/diagnostics/atlantid_determinism_comparator.py \
  --run-a /tmp/<completed-run-a-root> \
  --run-b /tmp/<completed-run-b-root> \
  --report-json /tmp/<somewhere>/determinism_report.json \
  --report-md   /tmp/<somewhere>/determinism_report.md
```

- `--run-a` / `--run-b` — two explicit, existing, completed output roots.
  Never inferred, never "latest". They must be different paths.
- `--report-json` / `--report-md` — explicit output paths. Both are refused
  if they already exist unless `--overwrite` is passed.
- `--count-tolerance INT` (default `0`) — exact by default. See §7.
- `--z-tolerance-m FLOAT` (default `0.0`) — exact by default. See §7.
- `--allow-different-commits` — must be passed explicitly to accept a
  `git.head` mismatch as an explicitly supported non-equivalent-runtime
  comparison; without it, a commit mismatch is a `FAIL`.
- `--allow-file-pattern GLOB` (repeatable) — explicitly approve a
  relative-path glob as a legitimate only-in-one-run exclusion. Empty by
  default: with no exclusions configured, any file present in only one run is
  an unexplained, blocking difference.

The comparator writes nothing to either run root. It only reads them.

---

## 3. Refusal conditions (no report is written)

The comparator exits non-zero and writes **no report at all** when:

- `--run-a` and `--run-b` resolve to the same path;
- either path does not exist or is not a directory;
- either report output path already exists and `--overwrite` was not passed;
- either run root fails `validate_run_completeness` (§6) — i.e. it is
  missing or has an unparsable `qa/miami_metric_smoke_manifest.json`, has an
  unsupported `schema_version`, has `dry_run != false`, was not an authorized
  `--controlled-smoke` execution, has unresolved `provenance_findings`, has
  any non-zero-returncode command, or has no non-empty `tiles/<tile_id>/`
  output.

These are structural refusals: the comparator judges it cannot even attempt a
meaningful comparison, not that the comparison failed. This is the mechanism
that keeps the failed pre-execution smoke root from ever being mistaken for a
completed run (§6, §9 scenario 19).

---

## 4. Comparison inputs and evidence sources

Evidence is read only from files already on disk under each run root, as
produced by `miami_metric_smoke_harness.py`:

```
$OUTPUT_ROOT/
  qa/
    miami_metric_smoke_manifest.json   <- authoritative run/tile/source/command identity
    miami_metric_smoke_report.md
    miami_metric_smoke_report.html
    miami_metric_smoke_inputs.csv
  tiles/
    <tile_id>/
      manifest/<tile_id>_manifest.json <- per-tile stage results and counts
      pointcloud/ clusters/ footprints/ masses/   <- per-tile output files
```

The full file inventory (relative path, logical role, media type, byte size,
SHA-256) is computed independently by walking the filesystem — it is not
merely copied from `miami_metric_smoke_manifest.json`'s own `output_hashes`
field, so the comparator does not simply trust the harness's self-report.

Two authorized-tile constants are embedded directly in the comparator,
sourced from the already-public
`docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md` (Step 4), rather
than imported from the harness at runtime (this lane is not permitted to
create a dependency on, or modify, that file):

| Tile | Canonical SHA-256 |
|---|---|
| `318155` | `0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095` |
| `318455` | `dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816` |

If a run's recorded source hash doesn't match these, that is reported as a
`source_hash_not_canonical` blocker — independent of whether Run A and Run B
agree with each other, so two runs cannot both be silently wrong about the
same input and still pass.

---

## 5. Normalization policy

Every normalization is a named, justified, uniformly-applied mechanism —
never a per-field ad hoc exclusion invented to force a pass. Four mechanisms,
all recorded in every report's `normalization_policy` section:

1. **`run_root_path_prefix`** — the absolute output-root path is a fresh
   UTC-stamped `/tmp` directory per run by design
   (`default_output_root()` in the harness). Its literal string value is
   substituted with `<RUN_ROOT>` before comparing JSON string values and text
   file contents. Only the literal prefix is substituted; everything else in
   the string, and all relative structure and file contents beneath the
   root, are still compared exactly.
2. **`normalized_key_name`** — JSON object keys named `created_at`,
   `generated_at`, `timestamp`, `started_at`, `ended_at`, `elapsed_s`,
   `elapsed_seconds`, `run_id` are recorded from both runs (their values are
   preserved and shown in the diff record) but excluded from the equality
   check, because they are wall-clock timestamps, elapsed durations, or
   per-run identifiers that are expected to differ between two independent
   runs of the same tiles. This mechanism applies uniformly to every JSON
   file compared, not to one file in particular.
3. **`created_timestamp_line`** — the rendered `- Created: \`<timestamp>\``
   line in the `.md`/`.html` smoke report is normalized for the same reason
   as the `created_at` field it is derived from.
4. **`unordered_array_key`** — the JSON arrays `output_hashes` and
   `provenance_findings` are sorted before equality diffing, because their
   element order reflects filesystem-walk order, not semantic content.
   Ordering of every other array (e.g. `commands`, `inputs`, `metrics`) is
   compared as-is, because their order is meaningful (declared, deterministic
   pipeline sequence).

Nothing else is normalized. Tile IDs, source hashes, output hashes, CRS,
units, bounds, Z-related values, point counts, class counts, validation
status, warnings, publication gates, contract version, pipeline commit
(`git.head`), and runtime versions are always compared as meaningful content
— never silently excluded.

---

## 6. Run completeness vs. classification-level findings

Two different mechanisms exist, deliberately:

- **Structural completeness** (`validate_run_completeness`, §3) — hard
  refusal, no report written. This catches a run that never really executed:
  no manifest, a dry run, an unauthorized/ad hoc invocation, unresolved
  provenance findings, a failed command, or no tile output at all (the shape
  of the known failed pre-execution smoke root).
- **Evidence-level findings within a structurally complete run** — a report
  *is* produced and classified `FAIL` when, for example, the tile set
  includes an unauthorized third tile, a required tile is missing, or a
  source hash doesn't match. This gives an auditable, explained result
  instead of a bare refusal, and is what the synthetic scenarios in §9
  (items 5–6) exercise.

---

## 7. Tolerance policy

No tolerance exists in the repository today for this comparison (the smoke
harness and per-tile manifests carry no documented numerical tolerance for
counts, CRS, units, or Z-related values). The comparator therefore defaults
to **exact** comparison:

- `--count-tolerance` defaults to `0` — any difference in `n_clusters`,
  `n_footprints`, `n_vegetation_pts`, `building_mass_lod0/1`, or a metrics
  `point_counts.normalized` value is a `FAIL` unless a tolerance is
  explicitly supplied.
- `--z-tolerance-m` defaults to `0.0` — any difference in a Z-related metric
  value (`height`, `ground_z`, `absolute_roof_elevation`,
  `building_relative_height`, each read from `.normalized`) is a `FAIL`
  unless a tolerance is explicitly supplied.
- CRS and unit string fields, `z_conversion_factor`, and
  `all_stages_passed`/`errors` are always exact — no tolerance concept
  applies to them.

**Tolerance is path-specific, never type-wide.** A numeric leaf is only
eligible for tolerance when its exact JSON path — with array indices stripped,
since tile ordering is not what's being tolerated — exactly equals one of the
approved patterns embedded in the comparator's
`APPROVED_COUNT_TOLERANCE_PATH_SUFFIXES` and
`APPROVED_Z_TOLERANCE_PATH_SUFFIXES` constants. Every other numeric leaf at
every other path — tile IDs, source/output byte sizes, source/output hashes,
command return codes, CRS/EPSG identifiers, version numbers, validation
thresholds, and all unlisted numeric metadata — is always compared exactly,
regardless of the configured tolerance. This prevents a non-zero count
tolerance from accidentally tolerating a tile-ID change, a byte-size change,
a return-code change, or any other field that happens to be numeric.

Both tolerances are recorded verbatim in every report's `tolerances` object.
A difference that falls within a configured, non-zero tolerance is reported
as a `warning`-severity finding (visible, non-blocking), never silently
dropped.

Every actually-applied tolerance is also recorded in the report's
`tolerance_applications` array — one record per tolerated field difference,
produced solely by the semantic comparison layer (`compare_counts_and_geospatial`).
Each record names: the relative evidence file path, the exact semantic JSON
path, the Run A value, the Run B value, the tolerance category (`count` or
`z_m`), the configured tolerance, the observed absolute difference, and the
justification. This ledger is deduplicated: even though the file-level
comparison (`compare_file_pair`) independently applies the same path-gated
tolerance to decide whether a file's content is `normalized_equal` or
`different`, it does **not** contribute to the `tolerance_applications` ledger
— so the same tolerated difference is never recorded twice.

---

## 8. Classification rules

Exactly one of three classifications, computed from finding severities:

- **`FAIL`** — at least one `blocker`-severity finding exists. Blockers
  include: unauthorized/third tile, missing required tile, tile-set mismatch
  between runs, source hash/size mismatch, non-canonical source hash,
  unexplained file present in only one run, unexplained content difference
  after normalization, symlink escape, `git.head` mismatch (unless
  `--allow-different-commits`), Python version mismatch, count mismatch
  beyond tolerance, CRS/unit mismatch, Z-value mismatch beyond tolerance,
  `z_conversion_factor` mismatch, tile-stage failure or non-empty `errors`,
  and `production_allowed=true` or `auto_publish_enabled=true` anywhere in
  either run's evidence.
- **`PASS WITH NON-BLOCKING FINDINGS`** — no blockers, but at least one
  `warning`-severity finding exists (a documented normalization actually
  fired, a within-tolerance numeric difference, a `git.dirty` or platform
  string difference, an accepted cross-commit comparison, or an external
  path reference noted for visibility).
- **`PASS`** — no blockers and no warnings. Because `--run-a` and `--run-b`
  are, by construction, two different `/tmp` paths, achieving a bare `PASS`
  in practice usually still requires the `run_root_path_prefix` mechanism to
  have fired — which is itself recorded as a warning. A true zero-warning
  `PASS` means the compared evidence contained no run-root-embedded absolute
  paths and no normalized-key differences at all.

A `FAIL` is never downgraded to a warning to force a pass, and a material
discrepancy is never hidden behind a normalization it doesn't actually match.

---

## 9. Synthetic fixtures and tested scenarios

`tests/test_atlantid_determinism_comparator.py` builds small synthetic run
roots in `tmp_path` — never real LAZ/GLB data, never a copy of the real
failed smoke root — and exercises:

1. Identical runs → `PASS`.
2. Timestamp/run-id-only differences → `PASS WITH NON-BLOCKING FINDINGS`.
3. Differing absolute output-root paths alone → not a material failure.
4. Source-hash mismatch → `FAIL`.
5. A third tile → `FAIL`.
6. A missing required tile → `FAIL`.
7. A CRS mismatch → `FAIL`.
8. A unit mismatch → `FAIL`.
9. A Z-value mismatch outside tolerance → `FAIL`; within an explicitly
   configured tolerance → not blocking (boundary tested).
10. A point-count mismatch → `FAIL`.
11. A missing required file → `FAIL` (unexplained-file-only-in-one-run).
12. An unexpected file → reported; classified per the explicit
    `--allow-file-pattern` rule.
13. `production_allowed` unexpectedly `true` → `FAIL`.
14. A tile-stage validation failure (`all_stages_passed=false` /
    non-empty `errors`) → `FAIL`.
15. A pipeline-commit (`git.head`) mismatch → visible and classified
    correctly (`FAIL` by default, `PASS WITH NON-BLOCKING FINDINGS`-eligible
    warning only with `--allow-different-commits`).
16. An unsupported manifest `schema_version` → refused (no report), not
    silently compared.
17. JSON array reordering of an explicitly unordered key does not cause a
    false failure.
18. A meaningful JSON content difference is never normalized away.
19. The failed pre-execution smoke shape (no `tiles/` directory) is refused
    outright and cannot be classified as a successful Run A or Run B.

**PR #37 bounded correctness pass** added 22 focused regression tests proving
each path-specific tolerance and deduplication invariant independently:

20. Count tolerance applies only to the approved count paths (`n_clusters`,
    `n_footprints`, `n_vegetation_pts`, `building_mass_lod0/1`,
    `metrics.point_counts.normalized`). No other numeric field is eligible.
21. Z tolerance applies only to the approved Z paths
    (`metrics.height/ground_z/absolute_roof_elevation/building_relative_height.normalized`).
22. A tile-ID field difference is a `FAIL` even with a wide count tolerance.
23. A source-file byte-size difference is a `FAIL` even with wide tolerances.
24. A command return-code difference is a `FAIL` — never tolerated.
25. A CRS/EPSG numeric-code difference is a `FAIL` — never tolerated.
26. A unit-string difference is a `FAIL`.
27. An unrelated float difference is a `FAIL` even with a wide Z tolerance.
28. The exact JSON path `git.head` is normalized only when
    `--allow-different-commits` is passed.
29. A dict key named `head` at any other path (e.g., `other.head`) is **not**
    normalized by `--allow-different-commits`; it remains exact.
30. A cross-commit comparison with `--allow-different-commits` classifies no
    better than `PASS WITH NON-BLOCKING FINDINGS` — never a clean `PASS`.
31. A commit mismatch without `--allow-different-commits` is a `FAIL`.
32. Each normalized field emits exactly one normalization event (no double-
    recording from per-side normalization).
33. Each tolerated field emits exactly one `tolerance_applications` record
    (no duplication between the file-level and semantic comparison layers).
34. A difference visible to both the file-level and the semantic comparison
    layer appears exactly once in the final report.
35. A pre-execution-refusal run shape cannot pass, even after the path-specific
    tolerance correction.
36. A processing-failure run shape cannot pass.
37. An incomplete-evidence run shape cannot pass.
38. A third tile remains a `FAIL` even with wide tolerances.
39. `production_allowed=true` remains a `FAIL` even with wide tolerances.
40. Generated reports validate against
    `schemas/atlantid_determinism_report.schema.json`.
41. A zero count or Z tolerance preserves exact comparison behavior even for
    fields whose paths are on the approved tolerance list.

Focused test commands (no PDAL, no `/mnt/t7`, no real LAZ/GLB, no network):

```bash
python -m pytest tests/test_atlantid_determinism_comparator.py -v
python -m pytest tests/test_atlantid_tile_asset_contract.py -v
python -m pytest tests/test_public_tile_staging.py -v
```

---

## 10. Relationship to the contract, publication gates, and public-tile staging

- This tool does not change `schemas/atlantid_tile_asset_manifest.schema.json`
  `contract_status`, which remains `CANDIDATE` regardless of any report this
  tool produces. Advancing it to `FROZEN` is a separate, independently
  reviewed decision (see `docs/diagnostics/ATLANTID_TILE_ASSET_CONTRACT_V1.md`
  §5).
- This tool does not compute or set `production_allowed`. It only flags an
  unexpected `production_allowed=true` or `auto_publish_enabled=true`
  anywhere in evidence as an unconditional `FAIL`.
- A future `PASS` or `PASS WITH NON-BLOCKING FINDINGS` determinism report is
  intended to become part of the audit evidence referenced by
  `docs/diagnostics/ATLANTID_BEACHHEAD_PUBLIC_TILE_STAGING.md`'s
  `audit/publication_gate.json` (whose required fields list
  "deterministic output comparison or a documented reason it is not
  deterministic"). This tool does not itself write into a public-tile
  package, deploy anything, or authorize publication.

---

## 11. Limitations

- The comparator only understands the specific evidence shape produced by
  `miami_metric_smoke_harness.py` today. Bounds and Z-range (min/max) are not
  currently captured by that harness's schema at all; this is represented
  explicitly as `"bounds": "unavailable (not captured by
  miami_metric_smoke_harness.py schema)"` in every report rather than
  invented.
- PDAL version is not captured by the harness's `selected_environment()`
  and is represented as explicitly unavailable, not invented.
- The harness's own `metrics[]` array is a placeholder (`null` values) unless
  and until real execution populates it; where it remains null, this
  comparator reports the corresponding evidence as unavailable rather than
  fabricating a value.
- The comparator's built-in canonical-source-hash cross-check is only as
  good as the two hashes on file in this document; if the canonical Miami
  source files are ever legitimately re-issued, this document and the
  comparator's `KNOWN_CANONICAL_SOURCE_SHA256` constant both need a
  coordinated update — a discrepancy here does not, by itself, mean either
  run is wrong, only that this cross-check needs to be re-verified.
- This tool does not authorize execution, does not prove licensing, does not
  make `production_allowed` true, and does not convert unknown evidence into
  confirmed evidence.

---

## Final status

**ATLANTID DETERMINISM COMPARATOR: TOOLING ONLY, AWAITING TWO COMPLETED
AUTHORIZED SMOKE RUNS**

**REAL DATA PROCESSING BY THIS TOOL: NONE**
