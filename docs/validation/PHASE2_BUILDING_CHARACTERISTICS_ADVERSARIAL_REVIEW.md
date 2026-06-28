# Phase 2 Building Characteristics Adversarial Review

**Decision:** NO-GO

## Scope

- Repository: `aetherbeing/glytchdraft`
- Baseline: `64faee98fe5957a82ea823d9e24b67cd815369b9`
- Canonical branch: `origin/master`
- Review branch: `audit/phase2-building-characteristics-review`
- Review date: 2026-06-28

## Reviewed Branches

| Lane | Branch | Expected SHA | Verified SHA | Baseline ancestor |
|---|---|---:|---:|---|
| Validator | `origin/test/building-characteristics-validation` | `a60d1d2641eaa1cebfa7a617a12dac243599e125` | `a60d1d2641eaa1cebfa7a617a12dac243599e125` | yes |
| Truth audit | `origin/audit/building-characteristics-matrix` | `6be1983e67328a83454aece6c7238ff63e5ab2cb` | `6be1983e67328a83454aece6c7238ff63e5ab2cb` | yes |
| QA reporting | `origin/feat/building-characteristics-qa-reporting` | `6aeadf1581793e4ef35c2da4fd45a00622fb2571` | `6aeadf1581793e4ef35c2da4fd45a00622fb2571` | yes |

`origin/master` verified at `64faee98fe5957a82ea823d9e24b67cd815369b9`.

## Branch Delta Summary

Validator lane changed only:

- `docs/validation/BUILDING_CHARACTERISTICS_VALIDATOR.md`
- `scripts/validation/__init__.py`
- `scripts/validation/building_characteristics.py`
- `tests/validation/__init__.py`
- `tests/validation/test_building_characteristics.py`

Truth-audit lane changed only:

- `docs/validation/BUILDING_CHARACTERISTICS_DATA_DICTIONARY.md`
- `docs/validation/BUILDING_CHARACTERISTICS_TECHNICAL_DEBT.md`
- `docs/validation/BUILDING_CHARACTERISTICS_VALIDATION_MATRIX.md`

QA-reporting lane changed only:

- `docs/validation/BUILDING_CHARACTERISTICS_QA_REPORTING.md`
- `scripts/validation/building_characteristics_qa.py`
- `scripts/validation/render_building_characteristics_dashboard.py`
- `tests/validation/test_building_characteristics_dashboard.py`
- `tests/validation/test_building_characteristics_qa.py`
- `tests/validation/test_building_characteristics_qa_cli.py`

No production assets, viewer code, deployment configuration, city readiness classifications, or generated city outputs changed in any reviewed branch.

## Integration

Disposable local integration branch: `tmp/phase2-building-characteristics-integration-review`

Merge order:

1. `origin/audit/building-characteristics-matrix`
2. `origin/test/building-characteristics-validation`
3. `origin/feat/building-characteristics-qa-reporting`

Integration HEAD: `0463dbf86805682d29f240e2c929491f13c56325`

Merge conflicts: none.

The temporary integration branch was not pushed.

## Test Results

From the disposable integration worktree:

- `pytest -q tests/validation/`: 131 passed, 0 failed, 0 skipped, 0 deselected; one pytest cache warning caused by read-only worktree cache metadata.
- Existing regressions: `pytest -q tests/test_miami_metric_normalization_v1.py tests/test_check_miami_vertical_units.py tests/test_miami_manifest_consistency.py tests/test_city_config_schema_validation.py tests/test_generate_viewer_manifest.py`: 63 passed, 0 failed, 0 skipped, 0 deselected; one pytest cache warning caused by read-only worktree cache metadata.
- `python -m py_compile scripts/validation/*.py`: initial run failed because the sandbox could not create `scripts/validation/__pycache__`; rerun with `PYTHONPYCACHEPREFIX=/tmp/glytchdraft_phase2_pycache` passed.
- Wildcard imports from all three validation modules passed.
- `git diff --check origin/master...HEAD`: passed with no output.
- `git status --short --untracked-files=all`: clean.

## Synthetic End-to-End Result

A representative clean synthetic path was run through validator findings, strict JSON serialization, QA ingestion, and report generation in `/tmp`.

Result:

- Loaded records: 2
- Loaded findings: 23
- Rule codes preserved: `AREA-001`, `CONF-005`, `CONF-006`, `GEOM-002`, `GEOM-003`, `GEOM-015`, `HEIGHT-003`, `HEIGHT-005`, `HEIGHT-006`, `HEIGHT-007`, `LIDAR-003`, `PROV-003`, `PROV-005`, `PROV-006`, `PROV-007`, `UNIT-003`, `UNIT-006`, `UNIT-007`, `VOLUME-001`
- Severity aggregation preserved: 17 `ERROR`, 3 `WARNING`, 3 `INFO`
- JSON, Markdown, HTML, and CSV outputs were generated.
- HTML escaped the injected building ID `bad<script>alert(1)</script>`.
- Markdown included the missing-findings caveat.

A non-finite synthetic path failed strict JSON serialization. That is recorded as finding P1-01.

## Contract Alignment Summary

Finding schema alignment is mostly present at field-name level. The validator emits the requested keys: `code`, `characteristic`, `severity`, `message`, `observed_value`, `expected_constraint`, `building_id`, `source_tile`, `source_file`, `confidence`, and `remediation_hint`. The QA reporter tolerates unknown finding fields and aggregates supplied findings by severity, rule, characteristic, tile, source file, pipeline version, confidence, and building ID.

The blocking alignment failures are elsewhere:

- QA relationship diagnostics default to generic field names (`height`, `ground_elevation`, `footprint_area`, `point_count_filtered`) while the Atlas pipeline and validator use `estimated_height`, `ground_z`, `footprint_area_m2`, and `point_count_inside`.
- Validator finding serialization is not strict-JSON safe for `NaN` and infinity observed values even though non-finite handling is a named review target.
- Validator Miami CRS normalization is hardcoded to `EPSG:6438` even though the repo currently contains a documented Miami source CRS contradiction against `configs/cities/miami.json` (`EPSG:3857`).
- The data dictionary claims full coverage but materially underdocuments the 75-characteristic matrix.

## Security And Immutability Review

The validator copies input records shallowly and does not intentionally mutate caller dictionaries. The QA report builder copies records before analysis. HTML rendering escapes table/card text and escapes `</` inside the embedded JSON script payload. No external CDN or network requirement was found.

A blocking destructive behavior exists in the QA CLI output handling: if `--output-dir` is the input file's parent directory, `write_report_outputs()` deletes every file in that directory, including the source file and unrelated sibling files, before replacing report outputs. This was reproduced in `/tmp` with both the input JSON and a sentinel file deleted while the command returned success.

## Documentation Accuracy Review

The validation matrix contains 75 characteristic rows, and its summary counts total 75 for status and confidence. The technical-debt register contains 20 entries. The data dictionary contains only 39 explicit characteristic sections despite stating that it documents every persisted building characteristic. It uses narrative cross-references for multiple groups rather than complete dictionary entries. That is not sufficient for a contract document that governs validator and QA coverage.

The matrix and debt register correctly surface the Miami CRS contradiction (`configs/cities/miami.json` says `EPSG:3857`; `metric_normalization_v1.py` says `EPSG:6438`). The validator then encodes one side of that contradiction as a universal rule for normalized outputs, which is premature and can false-fail corrected outputs if the actual LAZ metadata validates the config side instead.

## Findings

### P0-01 - QA CLI can delete source and unrelated files

- Severity: P0
- Affected branch: `feat/building-characteristics-qa-reporting`
- File/function: `scripts/validation/building_characteristics_qa.py`, `main()` and `write_report_outputs()`
- Evidence: `main()` only rejects `source_path == output_dir` or `source_path in output_dir.parents`; it allows `--output-dir` equal to the parent of an input file. `write_report_outputs()` then iterates `output_dir.iterdir()` and unlinks every file before moving new outputs. Reproduction in `/tmp`: command returned 0, `input_exists_after False`, `sentinel_exists_after False`.
- Consequence: Running the QA reporter with a plausible output directory can delete canonical input records and unrelated files. This violates source immutability and output-directory isolation.
- Required correction: Reject output directories that are the input file's parent or otherwise contain the source file; never clear arbitrary pre-existing files. Replace only known report filenames, and preserve all unrelated files.
- Blocks merge: yes.

### P1-01 - Validator findings are not strict-JSON safe for NaN/infinity

- Severity: P1
- Affected branch: `test/building-characteristics-validation`
- File/function: `scripts/validation/building_characteristics.py`, `Finding.to_dict()`
- Evidence: `to_dict()` calls `json.dumps(d["observed_value"])` without `allow_nan=False`, so `inf` and `nan` are considered serializable and remain as non-standard JSON floats. Synthetic validation of records with `footprint_area_m2=inf` and `estimated_height=nan` produced findings whose strict `json.dumps(..., allow_nan=False)` failed with `ValueError: Out of range float values are not JSON compliant`.
- Consequence: The validator detects non-finite values but can emit findings that cannot be serialized into standards-compliant JSON or consumed by the QA reporter's own `allow_nan=False` report contract.
- Required correction: Normalize all finding payload values recursively before returning dictionaries: convert `NaN`, positive infinity, and negative infinity to stable strings or structured sentinel objects.
- Blocks merge: yes.

### P1-02 - QA diagnostics do not use the actual Atlas pipeline field contract

- Severity: P1
- Affected branch: `feat/building-characteristics-qa-reporting`
- File/function: `scripts/validation/building_characteristics_qa.py`, `QAConfig` and `relationship_diagnostics()`
- Evidence: Default expected/numeric fields use `height`, `ground_elevation`, `roof_elevation`, `footprint_area`, `perimeter`, `roof_area`, `volume`, and `point_count_filtered`. Current producing code emits `estimated_height`, `ground_z`, `height_p90`, `footprint_area_m2`, `point_count_inside`, and related `_m2`/`_m3` names. Relationship checks for roof-ground-height, zero/negative footprint area, density, and filtered-vs-raw point count are therefore skipped for native Phase 1 records unless a custom config remaps the names.
- Consequence: QA reports can look healthy while missing the core building-height, area, density, and mixed-unit signals that Phase 2 is supposed to expose. Historical Miami mixed-unit records could be summarized without the intended relationship diagnostics.
- Required correction: Make the default QA contract match the actual Atlas fields and aliases. At minimum support `estimated_height`, `ground_z`, `roof_z`, `footprint_area_m2`, `perimeter_m`, `roof_area_m2`, `volume_m3`, and `point_count_inside` in completeness, numeric distributions, and relationship diagnostics.
- Blocks merge: yes.

### P1-03 - Data dictionary is incomplete as a governing contract

- Severity: P1
- Affected branch: `audit/building-characteristics-matrix`
- File/function: `docs/validation/BUILDING_CHARACTERISTICS_DATA_DICTIONARY.md`
- Evidence: The dictionary says it documents every persisted building characteristic, but it contains 39 explicit characteristic sections while the matrix contains 75 rows. Whole groups are summarized by prose cross-reference, including AI enrichment and facade evidence, rather than full dictionary entries. The validator and QA reporter are expected to align to this contract.
- Consequence: Implementers cannot reliably derive field names, units, nullability, provenance, and measured/derived/estimated/fallback semantics for all audited characteristics from the dictionary.
- Required correction: Either document all 75 audited characteristics with full dictionary entries or narrow the document's stated scope and explicitly map which matrix rows are intentionally deferred to schemas only.
- Blocks merge: yes.

### P1-04 - Validator hardcodes one side of the unresolved Miami source CRS contradiction

- Severity: P1
- Affected branch: `test/building-characteristics-validation`
- File/function: `scripts/validation/building_characteristics.py`, `_check_crs_and_units()` / `UNIT-005`
- Evidence: The repo currently declares Miami `source_crs` as `EPSG:3857` in `configs/cities/miami.json`, while `scripts/miami/metric_normalization_v1.py` declares `EXPECTED_SOURCE_HORIZONTAL_CRS = "EPSG:6438"`. The audit docs correctly label this as unresolved. The validator nevertheless requires every normalization-enabled record to reference `EPSG:6438`, and the rule is not gated to Miami city records.
- Consequence: The validator can false-fail valid records if LAZ metadata confirms the config side, and it applies a Miami-specific CRS assertion to any record with a normalization feature gate.
- Required correction: Make the rule city-contract driven. Do not hardcode `EPSG:6438` as a universal validation truth until the Miami CRS investigation is resolved against actual LAZ metadata.
- Blocks merge: yes.

### P2-01 - QA provenance diagnostic treats source hash as equivalent to footprint provenance

- Severity: P2
- Affected branch: `feat/building-characteristics-qa-reporting`
- File/function: `scripts/validation/building_characteristics_qa.py`, `PROVENANCE_KEYS` and `relationship_diagnostics()`
- Evidence: `PROVENANCE_KEYS` includes `source_hash` and `source_sha256`; `REL-PROVENANCE-MISSING` fires only when none of those fields are present. A record with a source hash but no `footprint_provenance` avoids the missing-provenance diagnostic.
- Consequence: QA provenance coverage can be overstated. Source immutability evidence is not a substitute for footprint derivation provenance.
- Required correction: Split source hash coverage from footprint provenance coverage and report both independently.
- Blocks merge: no, after P0/P1 fixes.

### P2-02 - QA duplicate source-tile diagnostic flags normal repeated tile membership

- Severity: P2
- Affected branch: `feat/building-characteristics-qa-reporting`
- File/function: `scripts/validation/building_characteristics_qa.py`, `relationship_diagnostics()`
- Evidence: After per-record checks, the reporter counts top-level `source_tile` values across all records and emits `REL-DUPLICATE-SOURCE-TILE` whenever more than one building references the same tile. Multiple buildings per tile are normal.
- Consequence: QA reports can contain misleading duplicate-tile signals that look like contract issues but are expected pipeline behavior.
- Required correction: Remove this dataset-level duplicate source-tile diagnostic or redefine it to inspect duplicate entries inside a single building's source tile list.
- Blocks merge: no.

## Deferred Characteristics

The following remain intentionally deferred or not production-ready based on the truth-audit docs and current code:

- Cross-tile ownership and deduplication.
- Facade evidence and building synthesis profiles at city scale.
- Roof evidence production integration and roof aspect convention.
- AI enrichment joining back into `structures_enriched.geojson`.
- Miami regeneration/certification pending vertical-unit and CRS provenance resolution.
- Persistent global building ID across tiles.

## Recommended Merge Order

No implementation branch should merge in its current state.

After corrections, merge order should be:

1. Truth-audit lane, after the data dictionary is made complete or explicitly scoped.
2. Validator lane, after serialization and city-contract CRS fixes align with the corrected truth audit.
3. QA-reporting lane, after output isolation and pipeline field-name alignment are fixed.

## Required Correction Assignments

- QA-reporting lane: fix P0-01, P1-02, P2-01, and P2-02.
- Validator lane: fix P1-01 and P1-04.
- Truth-audit lane: fix P1-03 and confirm the Miami CRS claim remains framed as unresolved unless actual LAZ metadata has been checked.
- Integration owner: rerun the same disposable integration merge and full test/end-to-end sequence after all corrections land.

## Final Decision

NO-GO.

Decision basis: unresolved P0 and P1 findings exist. Per the requested decision rules, any unresolved P0 or P1 requires `NO-GO`.
