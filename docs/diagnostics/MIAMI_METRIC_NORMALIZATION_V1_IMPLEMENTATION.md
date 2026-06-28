# Miami Metric Normalization V1 Implementation

## Files changed

- `scripts/miami/metric_normalization_v1.py` adds the reusable production guard, conversion step builder, source CRS/unit validation, SHA-256 provenance, and provenance envelope writer.
- `scripts/diagnostics/check_miami_vertical_units.py` keeps the standalone diagnostic interface while reusing the production guard core.
- `scripts/miami/bikini_config.py` adds the `MIAMI_METRIC_NORMALIZATION_V1` gate, source/target unit config, exact factor, expected EPSG contract, and a versioned temp output root.
- `scripts/miami/s01_extract.py` validates source CRS/units and inserts the Z conversion only when the gate is enabled.
- `scripts/miami/s05_masses.py`, `scripts/miami/s06_export.py`, and `scripts/miami/s07_metadata.py` record whether downstream Z values are normalized meters.
- `scripts/miami/run_two_tile_unit_fixture.py` now drives the corrected pass with the production gate and records source hashes/gate state.
- `tests/test_miami_metric_normalization_v1.py` adds focused normalization coverage.
- `tests/test_miami_two_tile_unit_fixture.py` now uses the production gate for the enabled-path stage-order test.

## Gate off

Default behavior is unchanged. `MIAMI_METRIC_NORMALIZATION_V1` is off unless set to `1`.

With the gate off:

```text
readers.las
filters.reprojection
filters.hag_nn
filters.range
filters.sample
```

No `filters.assign` Z conversion is inserted. Existing canonical Miami output roots are still the default for legacy Bikini runs. Newly generated gate-off metadata does not declare Z as normalized meters.

## Gate on

With `MIAMI_METRIC_NORMALIZATION_V1=1`, output defaults to:

```text
/mnt/c/Users/Glytc/miami_metric_normalization_v1/corrected
```

The temp root can be overridden with `MIAMI_METRIC_NORMALIZATION_V1_OUT_ROOT`. The controlled validation used:

```text
/tmp/miami_metric_normalization_v1_two_tile_validation
```

The enabled extraction order is:

```text
readers.las
filters.reprojection
filters.assign: Z = Z * 0.3048006096012192
filters.hag_nn
filters.range
later processing
```

`HeightAboveGround[2.5:300.0]` is interpreted as meters because Z is converted before `filters.hag_nn`.

## Unit guard

The guard fails closed when source vertical units are unknown, tile units contradict each other, metric source data is asked to run through ftUS conversion, the conversion step is requested twice from the same guard, or the EPSG:6438 + EPSG:6360 source contract is not present in PDAL CRS metadata.

The guard does not add `override_srs=EPSG:2236` and does not erase source CRS metadata.

## Downstream corrections

Corrected outputs carry explicit unit state:

- mass metadata emits `_m` fields only when the gate is enabled;
- OBJ headers record `vertical_unit`;
- export shift notes record `vertical_unit` and normalization version;
- manifests declare `viewer_hints.units: meters` only for corrected outputs;
- manifests include normalization config and source provenance links.

Minimum and fallback constants remain meter-valued on the corrected path: `DEFAULT_FALLBACK_HEIGHT = 6.0`, `RING_BUFFER_M = 5.0`, `LOD2_BUFFER_M = 8.0`.

## Provenance

Gate-on extraction writes:

```text
metadata/source_unit_profile.json
metadata/normalization_provenance.json
```

The provenance envelope records source LAZ path, source SHA-256, source horizontal CRS, source vertical CRS, source vertical unit, target unit, exact conversion factor, pipeline commit, normalization version, generated timestamp, contributing source tiles, and feature-gate state.

## Tests

Focused tests cover gate defaults, disabled stage-order regression, enabled conversion insertion, exact factor, ordering before HAG/range, fail-closed unit cases, double-conversion prevention, HAG thresholds, `_m` metadata, manifest unit declarations, water-plane metric geometry semantics, fallback constants, output isolation, provenance completeness, and gate-off regression behavior.

The adversarial review corrections are resolved:

- P2-1: water-plane coverage now builds terrain geometry and asserts the GLB Y-up water coordinate is exactly `-1.0` under the metric gate.
- P2-2: contradictory vertical units are tested through `s01_extract.main()`, which aborts before normalization-stage construction, extraction, provenance writing, or output emission.
- P2-3: profile-based Z conversion now requires explicit `normalize_z_to_meters: true`; a conversion factor alone is a no-op, and fixture tests use the full production-equivalent profile.
- P2-4: repeated production normalization-step calls are covered as pure helper invocations, each assembled building/ground pipeline contains exactly one `filters.assign`, and the stateful guard still fails closed on an actual second conversion attempt.

## Two-tile validation

Command:

```bash
PATH=/home/gytchdrafter/miniconda3/envs/pdal_env/bin:$PATH \
PROJ_DATA=/home/gytchdrafter/miniconda3/envs/pdal_env/share/proj \
PROJ_LIB=/home/gytchdrafter/miniconda3/envs/pdal_env/share/proj \
/home/gytchdrafter/miniconda3/envs/pdal_env/bin/python \
scripts/miami/run_two_tile_unit_fixture.py \
--out-root /tmp/miami_metric_normalization_v1_two_tile_validation \
--skip-old
```

Result:

- status `PASS`;
- source CRS validated as EPSG:6438 + EPSG:6360;
- source vertical units: US survey foot for both tiles;
- exactly one conversion step in enabled pipeline construction;
- HAG stored as meters, range max observed `78.98298196596392`;
- OBJ LOD0 vertical extent `50.962` m;
- GLB LOD0 vertical extent `51.96200180053711` m including water plane at Y = -1;
- corrected manifest declares meters;
- both `318455` and `318155` contributed points to the observed seam-crossing cluster.

Observed cluster ID `6` is only a validation artifact. This implementation does not claim cluster 6 is a verified individual building and does not claim 1601 Collins Avenue is repaired.

## Remaining blockers

- Real cross-tile physical-building identity remains unresolved. The deterministic ownership fixture is still isolated; production seam reconstruction is a follow-up.
- Full Miami regeneration, four-tile South Beach validation, viewer asset replacement, and readiness classification changes are not authorized here.

## Non-authorization

No full Miami regeneration was performed. No canonical viewer assets were replaced. No deployment was performed. No city readiness classifications were changed.
