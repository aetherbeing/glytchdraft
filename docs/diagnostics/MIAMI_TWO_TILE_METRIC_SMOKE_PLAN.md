# Miami Two-Tile Metric Normalization Smoke Plan

Status: preparation only. Real-data execution is blocked.

## Blocker

Do not run this harness against real Miami tiles until Instance 1 and Instance 2 resolve the authoritative source contract and return at least `CONDITIONAL_GO`.

This harness revision records command plans and validates evidence, but `--execute` still refuses before launching the real-data commands. A later reviewed change must deliberately enable real-data execution.

Instance 1 reported commit `11ceaa0f204882be380200775962ea1c1f5daa07` and found that the accessible 2024 D23 LAZ declares horizontal CRS `EPSG:6438`, vertical CRS `EPSG:6360`, and US survey feet for both horizontal and vertical units. That finding conflicts with `configs/cities/miami.json` `source_crs: EPSG:3857` and agrees with `metric_normalization_v1.py`.

Contract-reconciliation candidate `b5ab5a081f490656b4e08fbee8d6899ee96efe6b` proposes:

- source horizontal CRS: `EPSG:6438`
- source vertical CRS: `EPSG:6360`
- source XY/Z units: US survey feet
- processed horizontal CRS: `EPSG:32617`
- processed XY units: metres
- processed numeric Z units after V1: metres
- explicit Z factor: `0.3048006096012192`

This remains a candidate contract pending independent review. This plan does not encode `EPSG:6438` or `EPSG:6360` as global assumptions. The smoke harness requires an explicit authoritative contract file or verified profile for the run being tested. Canonical T7 tiles `318455` and `318155` remain unavailable because `/mnt/t7` and `/mnt/e` returned `No such device`; therefore no real-data execution is authorized from the current evidence. Downloads files must not be used as substitutes for canonical T7 inputs.

## Scope

The harness prepares a controlled two-tile smoke for `MIAMI_METRIC_NORMALIZATION_V1=1`.

It is designed to:

- discover inputs from explicit tile IDs under an explicit discovery root, or accept explicit `tile_id=/path/to/file.laz` mappings
- default outputs to a fresh `/tmp/glytchdraft_miami_metric_smoke_*` diagnostic directory
- refuse canonical Miami production outputs, viewer paths, existing output directories, and resolved source/output overlap
- preserve source files and record SHA-256 hashes for every explicit input
- record git SHA, branch, dirty state, environment variables, command records, timestamps, and output hashes
- serialize strict JSON with `allow_nan=False`
- generate QA JSON, Markdown, HTML, and CSV artifacts
- record source horizontal CRS, source vertical CRS, source horizontal unit, source vertical unit, processed horizontal CRS, processed vertical datum if known, processed Z unit, XY reprojection stage, Z conversion stage, Z conversion factor, and normalization provenance as separate fields
- refuse execution without evidence that XY reprojection has not already converted Z before the explicit Z factor is applied
- detect missing provenance, missing canonical input hashes, hash mismatches, and possible double conversion
- build command records for the Miami per-tile runner, processed-output QA, and building-characteristics validator
- keep the feature gate off by default
- keep real-data command execution disabled in this revision

It must not:

- overwrite canonical Miami assets
- change city readiness
- trigger full-city regeneration
- modify the viewer
- silently infer CRS or units
- claim success without authoritative source contract evidence

## Harness

Script:

```bash
python scripts/diagnostics/miami_metric_smoke_harness.py
```

Dry-run with synthetic or staged files:

```bash
python scripts/diagnostics/miami_metric_smoke_harness.py \
  --tile 318455=/tmp/miami-smoke-inputs/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz \
  --tile 318155=/tmp/miami-smoke-inputs/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz
```

Proposed real-data command after evidence review:

```bash
MIAMI_METRIC_NORMALIZATION_V1=1 \
python scripts/diagnostics/miami_metric_smoke_harness.py \
  --execute \
  --release-status CONDITIONAL_GO \
  --source-contract /tmp/miami_authoritative_contract.json \
  --building-characteristics-validator /path/to/building_characteristics_validator.py \
  --tile 318455=/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz \
  --tile 318155=/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz
```

The contract file must include:

```json
{
  "source_contract_status": "CONDITIONAL_GO",
  "source_horizontal_crs": "EPSG:<authoritative-horizontal-crs>",
  "source_vertical_crs": "EPSG:<authoritative-vertical-crs>",
  "source_horizontal_unit": "<authoritative-horizontal-unit>",
  "source_vertical_unit": "<authoritative-vertical-unit>",
  "processed_horizontal_crs": "EPSG:<processed-horizontal-crs>",
  "processed_vertical_datum": null,
  "processed_z_unit": "<processed-z-unit-after-v1>",
  "xy_reprojection_stage": "<stage-name-or-command-that-reprojects-XY>",
  "z_conversion_stage": "<stage-name-or-command-that-converts-Z>",
  "z_conversion_factor": 0.3048006096012192,
  "normalization_provenance": "<evidence reference>",
  "z_not_already_converted_evidence": "<evidence that XY reprojection preserved source Z units before explicit Z factor>",
  "xy_reprojection_converts_z": false,
  "canonical_input_hashes": {
    "318455": "<sha256>",
    "318155": "<sha256>"
  },
  "possible_double_conversion": false
}
```

The values above are placeholders except where supplied by the evidence file. `EPSG:32617` is a processed horizontal CRS only; the harness does not describe it as a vertical CRS. The harness refuses execution if the contract is absent, unreleased, missing canonical input hashes, mismatched against the actual input files, flagged for possible double conversion, or lacking evidence that Z was not already converted during XY reprojection.

## Initial Tests

Only synthetic/unit tests are authorized before release:

```bash
python -m pytest tests/test_miami_metric_smoke_harness.py
```

These tests cover:

- real execution refusal without a verified contract
- dry-run without mounted T7 data
- explicit input-file requirement
- canonical-looking tile IDs not bypassing file/hash verification
- source/output overlap rejection after symlink resolution
- manifest separation of source/processed horizontal and vertical contract fields, reprojection/conversion stages, and explicit Z factor
