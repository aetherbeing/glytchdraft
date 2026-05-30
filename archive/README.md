# archive/

Quarantined code that predates the Phase 1 agnostic pipeline.

Do not import from or revive anything here without a deliberate decision
to port it to `scripts/phases/` or `scripts/common/`.

## Contents

### `glytchos_legacy/`

The original Atlas-era pipeline module (`glytchos/`). Written before the
phase-based pipeline existed. References `atlas_output/` as its export
root and uses region configs (`glytchos/regions/`) that are superseded
by `configs/cities/`.

Not used by any current phase script. Kept for reference only.
