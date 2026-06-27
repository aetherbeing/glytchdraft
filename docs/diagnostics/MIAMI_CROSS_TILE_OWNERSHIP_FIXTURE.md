# Miami Cross-Tile Ownership Fixture

This diagnostic is isolated from the normal Miami production pipeline. It does
not regenerate Miami outputs, does not activate `MIAMI_TWO_TILE_UNIT_FIXTURE=1`,
and writes generated JSON outside the repository by default.

Runner:

```bash
python scripts/miami/run_cross_tile_ownership_fixture.py
```

Default output:

```text
/tmp/glytchdraft_miami_cross_tile_ownership_fixture/miami_cross_tile_ownership_fixture.json
```

## Scope

Primary source tiles:

- `318455`
- `318155`

Optional validation set:

- `318455`
- `318454`
- `318155`
- `318154`

Known LAZ source root:

```text
/mnt/t7/miami/data_raw/laz/
```

The fixture records source paths, SHA-256 hashes, LAS/LAZ header bounds, CRS
text when present in VLRs, inferred units, selected seam coordinates, point
contribution by tile, cluster bounds, footprint bounds and area, ownership
decision, duplicate-suppression result, deterministic rerun result, and
limitations.

## Strategy Under Test

The fixture uses source-tile context before clustering or building extraction.
For each candidate footprint, it gathers points from every source tile whose
tile bounds intersect the buffered footprint. The constructed cluster therefore
can extend beyond the eventual owner tile and is not clipped before building
construction.

Ownership is deterministic and independent of processing order:

1. Use the authoritative representative interior point when available.
2. Use the authoritative footprint centroid when the representative point is
   unavailable.
3. Use largest footprint-area intersection when no interior point is available.
4. Break equal-score ties lexicographically by tile id.
5. Use the stable source footprint id as the entity identity input.

The diagnostic records all candidate results so the selected rule is auditable
rather than casual.

## Duplicate Suppression

The stable emitted identifier is:

```text
<source-footprint-id>:<owner-tile-id>
```

Only the selected owner emits the entity. Non-owner tile attempts for the same
source footprint id are suppressed. Tests verify that reversing input tile order
does not change owners or identifiers.

## Limitations

This fixture proves deterministic ownership behavior for seam-crossing
footprints. It does not prove exact physical-building identity from a point
cluster. It must not be cited as resolving or identifying the exact 1601
Collins parcel.

The runner records real LAZ headers and hashes when source files are available,
but it does not decompress LAZ point records and does not regenerate production
Miami GLBs, JSON metadata, logs, caches, or tile outputs.
