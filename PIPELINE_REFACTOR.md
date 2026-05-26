# GlitchOS Pipeline Refactor — City-Agnostic Architecture

**Document purpose:** Handoff to an executing AI agent.  
**Status:** Miami pipeline is live and complete. LA and NYC pipelines exist but lack address enrichment, audit, and a unified config contract. This document specifies a 4-phase refactor to make all three cities share a common contract — and to make adding future cities (Houston, Chicago, etc.) a matter of config, not code.

**Hard constraint: do not break existing pipelines.**  
Every phase must leave LA and NYC `--dry-run` and `--execute` working identically to how they work before the phase starts. Miami's pipeline is production-live; it must not be touched until Phase 4, and even then only in ways that pass the Phase 4 smoke tests.

---

## Current State

### LA (`scripts/la/`)

| Item | Detail |
|---|---|
| Config | `CityConfig` frozen dataclass in `city_config.py`; imports `tile_config.py` for storage roots |
| Tile runner | `run_tile.py` → `run_tile(tile: TileConfig, stages)` → dispatches to `stages/s0N_*.py` |
| City runner | `run_city.py` → `execute(city_id, stages)` → `subprocess.run()` per tile (blocking, no live stdout) |
| Progress UI | Rich `Progress` bars (not `Live`) |
| Stages | `s00_extent`, `s01_footprints`, `s02_pointcloud`, `s03_validate`, `s04_masses`, `s05_manifest` |
| LAZ source | `/mnt/e/la/data_raw/laz/` (EPSG:2229 source, reprojected to EPSG:32611) |
| Output root | `/mnt/e/la/data_processed/cities/los_angeles/` |
| `address_source` | Declared on `CityConfig` (`dict | None = None`) but **never called** — no ingest, no enrichment |
| Structures | None — no `structures_enriched.geojson` |
| Audit | None |
| City manifest | Written by `_write_city_manifest()` — tiles, totals, footprint counts; **no address block, no package_status** |
| Preflight gate | None |

**Key files:**
```
scripts/la/city_config.py          CityConfig dataclass + CITIES registry
scripts/la/tile_config.py          TileConfig dataclass + storage roots + tile registry
scripts/la/run_city.py             City orchestrator (dry_run / execute)
scripts/la/run_tile.py             Tile-level runner (called as subprocess)
scripts/la/stages/s00_extent.py
scripts/la/stages/s01_footprints.py
scripts/la/stages/s02_pointcloud.py
scripts/la/stages/s03_validate.py
scripts/la/stages/s04_masses.py
scripts/la/stages/s05_manifest.py
scripts/la/tile_discovery.py       Discovers tiles from TNM API + manifest cache
```

---

### NYC (`scripts/nyc/`)

Nearly identical to LA in structure. Key differences:

| Item | Detail |
|---|---|
| Config | Same `CityConfig` shape as LA; imports from `tile_config.py` |
| LAZ source | `/mnt/t7/nyc/data_raw/laz/` (EPSG:32618, already metric) |
| Tile discovery | Disk-authoritative (scans LAZ_DIR every run); `--reprocess-failed` flag |
| Borough metadata | `boroughs` tuple added to `TileInfo` |
| s03 gate | Does NOT block s04 on failure (LA does) |
| `address_source` | Declared, **never called** — same gap as LA |
| Audit | None |
| City manifest | Same gaps as LA |

**Key files:**
```
scripts/nyc/city_config.py
scripts/nyc/tile_config.py
scripts/nyc/run_city.py
scripts/nyc/run_tile.py
scripts/nyc/stages/s00_extent.py
scripts/nyc/stages/s01_footprints.py
scripts/nyc/stages/s02_pointcloud.py
scripts/nyc/stages/s03_validate.py
scripts/nyc/stages/s04_masses.py
scripts/nyc/stages/s05_manifest.py
scripts/nyc/tile_discovery.py
```

---

### Miami (`scripts/miami/`)

Production-live. Architecturally separate from LA/NYC — no `CityConfig` dataclass, no `TileConfig`, different stage names, different orchestration model.

| Item | Detail |
|---|---|
| Config | Flat module `miami_city_config.py` — module-level constants, no dataclass |
| Tile runner | `run_tile_miami.py` — self-contained subprocess, takes `--laz` + `--out` CLI args |
| Stages | `extract`, `clean`, `cluster`, `footprints`, `masses`, `vegetation` (no `s0N` numbering) |
| City runner | `run_miami_city.py` — Rich `Live` dashboard; Popen + reader thread for real-time stdout |
| LAZ source | `/mnt/e/miami/data_raw/laz/` (EPSG:32617, already metric) |
| Output root | `/mnt/t7/miami/data_processed/miami_city/` |
| Address ingest | **Implemented and working** — `_run_address_ingest()` → `ingest_addresses()` from `scripts/common/` |
| Structures | **Implemented** — `structures_enriched.geojson` with per-structure `address_status` |
| Audit | **Implemented** — `audit_miami_city.py` writes `city_audit.json` + `city_audit.md` |
| City manifest | **Full contract** — includes `address_enrichment` block, `package_status`, `assets`, `city_assets` |
| Preflight gate | **Implemented** — `preflight_miami.py` must pass before any processing |
| PRESERVE_RAW_LAZ | `True` (enforced at module load) |
| **Terrain merge** | **Implemented** — all `ground_1m.ply` tiles merged → `blender_ready/miami_terrain_1m.ply` |
| **Vegetation** | **Implemented** — LiDAR classes 3/4/5 extracted per tile → `vegetation_1m.ply`; city-wide merge 5 m grid-subsampled |
| **City GLB** | **Implemented** — unified GLB (buildings LOD0 + terrain mesh + green veg pts) via `merge_city_assets.py` |

**Key files:**
```
scripts/miami/miami_city_config.py          Flat module config (constants)
scripts/miami/run_miami_city.py             City orchestrator (Live dashboard)
scripts/miami/run_tile_miami.py             Per-tile subprocess runner
scripts/miami/merge_city_assets.py          City-wide terrain/veg merge + GLB export (NEW)
scripts/miami/preflight_miami.py           Preflight gate
scripts/miami/audit_miami_city.py          Audit writer
scripts/miami/build_miami_catalog.py       LAZ catalog builder
scripts/common/ingest_addresses.py         Shared address ingest (used by Miami)
```

---

## Miami City-Wide Assets (Terrain, Vegetation, GLB)

These features run automatically after all 108 tiles complete. They are
implemented in `merge_city_assets.py` and called from `run_miami_city.py`'s
`_run_city_merge()` helper during the "merge" phase (between tile processing
and the audit phase).

### Terrain merge

**Per tile (stage: `extract`):** `ground_1m.ply` — ground-class (LiDAR class 2)
points at 1 m Poisson-disk sampling, written to `<tile>/pointcloud/`.

**City-wide merge:** `merge_terrain_ply()` concatenates all 108 ground PLYs
into `blender_ready/miami_terrain_1m.ply` (full 1 m resolution, ~20–30 M points).
This PLY is kept at full resolution for Blender import and GIS analysis.

**GLB terrain mesh:** `build_terrain_mesh()` reads the merged ground points and
builds a regular-grid mesh at 15 m spacing using numpy vectorized ops:
1. Assign each ground point to a grid cell, compute mean Z per cell.
2. Fill empty cells by nearest-neighbor propagation (`scipy.ndimage.distance_transform_edt`).
3. Emit two triangles per quad cell.

At 15 m spacing the Miami city area produces ~622 K vertices and ~1.2 M triangles,
yielding ~22 MB in the GLB. Grid spacing is tunable (`--terrain-grid-m N`).

### Vegetation extraction

**Config:**
```python
VEGETATION_ENABLED: bool          = True     # set False to skip entirely
VEGETATION_CLASSES: tuple[int, ...] = (3, 4, 5)  # low/medium/high vegetation
```

**Per tile (stage: `vegetation`):** PDAL reads LiDAR classes 3–5, reprojects to
UTM 17N, applies Poisson-disk sampling at 1 m, writes
`<tile>/pointcloud/<tile>_vegetation_1m.ply`. If a tile has no vegetation returns
the stage succeeds with `n_pts: 0`. The tile manifest records `n_vegetation_pts`
and `vegetation_enabled`.

**City-wide merge:** `merge_vegetation_ply()` concatenates all per-tile vegetation
PLYs, then grid-subsamples to 5 m spacing using `_subsample_grid()` (highest-Z
point per cell — canopy top selection). Full-resolution PLY:
`blender_ready/miami_vegetation_1m.ply`. The subsampled version goes into the GLB.

### City GLB export

`export_city_glb()` writes `blender_ready/miami_city.glb` — a minimal but valid
GLB 2.0 file containing three named GLTF nodes:

| Node | Type | Source | Color |
|---|---|---|---|
| `buildings` | TRIANGLES | All per-tile `LOD0_convexhull.obj` merged | (material default) |
| `terrain` | TRIANGLES | Grid mesh from merged `ground_1m.ply` | (material default) |
| `vegetation` | POINTS | 5 m grid-subsampled vegetation cloud | RGBA (0, 180, 0, 255) — green |

**Coordinate system:** All coordinates are in EPSG:32617 (UTM 17N, Z-up, meters).
The GLB subtracts the scene bounding-box minimum from all vertex positions to
maintain float32 precision (~0.06 m accuracy at Miami's ~580 000 m easting).
The offset is recorded in `miami_city_glb_offset.json`:
```json
{
  "crs": "EPSG:32617",
  "origin_utmX": 578000.0,
  "origin_utmY": 2745000.0,
  "origin_utmZ": -2.5,
  "note": "Add these values to the model matrix translation to reposition in world space."
}
```

**Three.js/R3F usage:**
```js
// Load GLB then reposition
const { scene } = useGLTF('/miami_city.glb')
const offset = await fetch('/miami_city_glb_offset.json').then(r => r.json())
scene.position.set(offset.origin_utmX, offset.origin_utmY, offset.origin_utmZ)
scene.up.set(0, 0, 1)   // Z-up
```

**Standalone CLI:**
```bash
# Merge all assets + export GLB (run after --execute completes)
conda run -n pdal_env python scripts/miami/merge_city_assets.py --all

# Tune terrain mesh resolution
conda run -n pdal_env python scripts/miami/merge_city_assets.py --export-glb --terrain-grid-m 25

# Just re-merge terrain PLY
conda run -n pdal_env python scripts/miami/merge_city_assets.py --merge-terrain
```

**Extending to LA/NYC:** LA and NYC pipelines do not yet produce `ground_1m.ply`
or vegetation PLYs (their extract stages differ). When Phase 2 wires address
enrichment into LA/NYC, terrain+vegetation extraction should also be added as
optional flags on their tile runners — the `merge_city_assets.py` script is
city-agnostic once given the correct `tiles_root` and output paths.

---

## The Three Gaps

### Gap 1 — Miami Island

Miami does not share any code with LA/NYC. There is no shared base class, no common orchestrator, no shared stage logic. Adding a fourth city (Houston) would require forking one of two incompatible architectures. The refactor must bridge this: either Miami adopts the `CityConfig`/stages pattern (Phase 4), or a thin adapter makes Miami-style configs work in a shared runner.

**Root cause:** Miami was built from scratch for a different data source (no external footprints — it clusters from 3DEP points directly). The LA/NYC pipeline requires pre-downloaded building footprints (`s01_footprints`). Miami derives footprints from the point cloud itself. This architectural difference must be preserved — but the orchestration layer (config contract, address ingest, audit) can and should be shared.

### Gap 2 — Address Enrichment Not Wired in LA/NYC

Both `CityConfig` dataclasses declare `address_source: dict | None = None` but neither `run_city.py` calls `ingest_addresses()` or produces `structures_enriched.geojson`. The mission-critical address contract (every structure gets an `address_status`, package is only `complete` when address enrichment succeeds) exists only in Miami's pipeline.

LA and NYC city manifests do not have:
- `address_enrichment` block
- `package_status` field  
- `structures_enriched.geojson` output
- `address_points.geojson` output

### Gap 3 — Config Contract Fragmentation

Three incompatible config shapes:

| Property | LA `CityConfig` | NYC `CityConfig` | Miami `miami_city_config` |
|---|---|---|---|
| `preserve_raw_laz` | ✗ missing | ✗ missing | ✓ |
| `address_join_radius_m` | ✗ missing | ✗ missing | ✓ `100.0` |
| `structures_enriched` path | ✗ missing | ✗ missing | ✓ |
| `audit_dir` path | ✗ missing | ✗ missing | ✓ |
| `city_audit_json` path | ✗ missing | ✗ missing | ✓ |
| `city_audit_md` path | ✗ missing | ✗ missing | ✓ |
| `pipeline_version` | ✗ missing | ✗ missing | ✓ `"1.0"` |
| Dataclass type | `@dataclass(frozen=True)` | `@dataclass(frozen=True)` | module constants |
| `city_manifest` path | `output_root/{city_id}_manifest.json` | same | `metadata/miami_city_manifest.json` |

LA/NYC also differ from each other in subtle ways (borough metadata, tile discovery strategy, s03 gate behavior) that the refactor must not erase.

---

## Target Architecture After Refactor

```
scripts/
  common/
    ingest_addresses.py        (exists — shared address ingest)
    audit_city.py              (NEW — generic audit writer, Phase 3)
    city_contract.py           (NEW — shared CityConfig base fields, Phase 1)
  la/
    city_config.py             (MODIFIED — adds missing contract fields)
    run_city.py                (MODIFIED — adds ingest + enrichment + audit calls)
  nyc/
    city_config.py             (MODIFIED — adds missing contract fields)
    run_city.py                (MODIFIED — adds ingest + enrichment + audit calls)
  miami/
    miami_city_config.py       (MODIFIED Phase 4 — wraps into CityConfig-compatible shape)
    run_miami_city.py          (unchanged through Phase 3; reviewed Phase 4)
```

**Golden rule for all phases:** every change is additive. No field is removed from any existing config. No existing CLI flag changes. No existing output path changes. Pipelines that were working continue to work.

---

## Shared CityConfig Contract (Target)

After Phase 1, both `scripts/la/city_config.py` and `scripts/nyc/city_config.py` must expose this complete contract. Fields marked `NEW` do not currently exist and must be added.

```python
@dataclass(frozen=True)
class CityConfig:
    # ── identity ────────────────────────────────────────────────────────────
    city_id:          str
    display_name:     str
    usgs_project:     str
    bbox_4326:        dict[str, float] = field(default_factory=dict)
    boundary_sources: tuple[str, ...] = ("bbox",)

    # ── address contract (NEW fields) ────────────────────────────────────────
    address_source:        dict | None = field(default=None)
    address_join_radius_m: float = 100.0           # NEW
    preserve_raw_laz:      bool  = True            # NEW

    # ── pipeline metadata (NEW fields) ───────────────────────────────────────
    pipeline_version: str = "1.0"                  # NEW

    # ── existing path properties (unchanged) ─────────────────────────────────
    @property
    def output_root(self) -> Path: ...
    @property
    def tiles_root(self) -> Path: ...
    @property
    def boundaries_dir(self) -> Path: ...
    @property
    def boundary_cache(self) -> Path: ...
    @property
    def tile_manifest(self) -> Path: ...
    @property
    def city_manifest(self) -> Path: ...
    @property
    def metadata_dir(self) -> Path: ...
    @property
    def address_points(self) -> Path: ...
    def protected_path_check(self) -> list[str]: ...

    # ── NEW path properties ───────────────────────────────────────────────────
    @property
    def structures_enriched(self) -> Path:
        return self.metadata_dir / "structures_enriched.geojson"   # NEW

    @property
    def audit_dir(self) -> Path:
        return self.output_root / "audit"                           # NEW

    @property
    def city_audit_json(self) -> Path:
        return self.audit_dir / "city_audit.json"                   # NEW

    @property
    def city_audit_md(self) -> Path:
        return self.audit_dir / "city_audit.md"                     # NEW
```

**Note on `city_manifest` path discrepancy:** LA/NYC currently write `output_root/{city_id}_manifest.json`. Miami writes `output_root/metadata/miami_city_manifest.json`. Do NOT change the LA/NYC path — this would break existing consumers. The discrepancy is acceptable until Phase 4 when Miami migrates to the dataclass. If you want to harmonize, add a second property `city_manifest_v2` pointing to `metadata/{city_id}_manifest.json` and update only new code to use it.

---

## Phase 1 — Extend CityConfig Contract (LA + NYC Only)

**Goal:** Add missing fields to `CityConfig` in both cities. Zero behavior change. Existing pipelines must continue to work identically.

**Files to change:**

### `scripts/la/city_config.py`

1. Add three dataclass fields after `boundary_sources`:
   ```python
   address_source:        dict | None   = field(default=None)   # already exists, keep it
   address_join_radius_m: float         = 100.0                 # ADD
   preserve_raw_laz:      bool          = True                  # ADD
   pipeline_version:      str           = "1.0"                 # ADD
   ```
   The `address_source` field already exists — do not duplicate it.

2. Add three path properties to the `CityConfig` class body:
   ```python
   @property
   def structures_enriched(self) -> Path:
       return self.metadata_dir / "structures_enriched.geojson"

   @property
   def audit_dir(self) -> Path:
       return self.output_root / "audit"

   @property
   def city_audit_json(self) -> Path:
       return self.audit_dir / "city_audit.json"

   @property
   def city_audit_md(self) -> Path:
       return self.audit_dir / "city_audit.md"
   ```

3. No changes to the `CITIES` registry or any instance values.

### `scripts/nyc/city_config.py`

Identical changes — same four fields, same four properties. NYC's `CityConfig` is structurally identical to LA's; apply the same diff.

**Do NOT change:**
- `scripts/la/run_city.py` — no behavior change yet
- `scripts/nyc/run_city.py` — no behavior change yet
- Any Miami files
- Any `tile_config.py` files
- Any stage files

**Test after Phase 1:**
```bash
# LA dry-run must still work
conda run -n pdal_env python scripts/la/run_city.py los_angeles --dry-run --limit 5

# NYC dry-run must still work
conda run -n pdal_env python scripts/nyc/run_city.py new_york_city --dry-run --limit 5

# Miami execute must still work (unchanged)
conda run -n pdal_env python scripts/miami/run_miami_city.py --execute --limit 1

# Verify new fields are importable
conda run -n pdal_env python -c "
from scripts.la.city_config import CITIES
cfg = CITIES['los_angeles']
print(cfg.address_join_radius_m)   # 100.0
print(cfg.preserve_raw_laz)        # True
print(cfg.structures_enriched)     # .../metadata/structures_enriched.geojson
print(cfg.audit_dir)               # .../audit
print('LA config OK')
"
conda run -n pdal_env python -c "
from scripts.nyc.city_config import CITIES
cfg = CITIES['new_york_city']
print(cfg.address_join_radius_m)
print(cfg.structures_enriched)
print('NYC config OK')
"
```

---

## Phase 2 — Address Ingest + Enrichment for LA and NYC

**Goal:** Wire `ingest_addresses()` and structure enrichment into both `run_city.py` orchestrators, mirroring what Miami already does. City manifests gain the `address_enrichment` block and `package_status`.

**Prerequisite:** Phase 1 complete.

**Files to change:**

### `scripts/la/run_city.py` — inside `execute()`

Add address ingest **before** tile processing begins. Add enrichment **after** all tiles finish. Add `package_status` to city manifest.

Specific insertion points:

**1. After the protected-path check, before tile discovery (around line 344):**
```python
# ── Address ingestion ─────────────────────────────────────────────────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
from ingest_addresses import ingest_addresses as _ingest_addresses

addr_status = "missing_source"
addr_count  = 0

if cfg.address_source is not None:
    src_path = Path(cfg.address_source.get("path", ""))
    if src_path.exists():
        cfg.metadata_dir.mkdir(parents=True, exist_ok=True)
        ok, addr_count = _ingest_addresses(
            source_path = src_path,
            field_map   = cfg.address_source.get("field_map", {}),
            source_name = cfg.address_source.get("source_name", "unknown"),
            input_crs   = cfg.address_source.get("input_crs", "EPSG:4326"),
            output_path = cfg.address_points,
            dst_crs     = f"EPSG:{DST_EPSG}",
            city_name   = cfg.city_id,
        )
        addr_status = "ok" if ok else "failed"
        console.print(f"[dim]Address ingest: {addr_status} ({addr_count:,} pts)[/dim]")
    else:
        console.print(f"[yellow]Address source file not found: {src_path}[/yellow]")
else:
    console.print("[dim]No address_source configured — skipping address ingest.[/dim]")
```

**2. After all tile processing completes, before `_write_city_manifest()` (around line 504):**
```python
# ── Structure address enrichment ──────────────────────────────────────────
enrichment_stats = _run_structures_enrichment(cfg, addr_status, addr_count)
```

**3. Add `_run_structures_enrichment()` as a module-level function** (copy the logic from `scripts/miami/run_miami_city.py:_run_structures_enrichment()` and adapt for LA's `TileConfig` — the tile masses metadata path pattern is different):

LA tile masses metadata is at:
```
cfg.tiles_root / tile_id / "blender_ready" / "masses" / "{tile_id}_masses_metadata.geojson"
```

Miami's is at:
```
cfg.tiles_root / tile_id / "masses" / "{tile_id}_masses_metadata.csv"
```

LA/NYC use `.geojson`; Miami uses `.csv`. The enrichment function must read from GeoJSON `features[].properties` for LA/NYC, not from CSV rows. Centroids are in `centroid_x` / `centroid_y` properties (if written by s04_masses) or from `geometry.coordinates` if Point geometry.

**Check `scripts/la/stages/s04_masses.py`** for the exact property names written to the masses metadata GeoJSON before implementing. Adjust the enrichment reader accordingly.

**4. Update `_write_city_manifest()`** to accept `addr_status`, `addr_count`, `enrichment_stats` and include:
```python
"package_status": _compute_package_status(addr_status, enrichment_stats),
"address_enrichment": {
    "required": cfg.address_source is not None,
    "source":   (cfg.address_source or {}).get("path"),
    "join_radius_m": cfg.address_join_radius_m,
    "structures_count": enrichment_stats.get("structures_count", 0),
    "address_points_count": addr_count,
    "structures_with_address_count": enrichment_stats.get("structures_with_address", 0),
    "structures_without_address_count": enrichment_stats.get("structures_without_address", 0),
    "coverage_pct": enrichment_stats.get("coverage_pct", 0.0),
    "avg_address_distance_m": enrichment_stats.get("avg_distance_m"),
    "max_address_distance_m": enrichment_stats.get("max_distance_m"),
},
```

**5. Add `_compute_package_status()`** (identical logic to Miami's version):
```python
def _compute_package_status(addr_status: str, enrichment_stats: dict) -> str:
    if addr_status == "missing_source":
        return "incomplete_missing_addresses"
    if addr_status == "failed" or enrichment_stats.get("status") == "failed":
        return "incomplete_address_enrichment_failed"
    if (enrichment_stats.get("structures_count", 0) > 0
            and enrichment_stats.get("address_points_count", 0) > 0
            and enrichment_stats.get("status") == "ok"):
        return "complete"
    return "incomplete_missing_addresses"
```

### `scripts/nyc/run_city.py`

Apply the identical changes. NYC and LA `run_city.py` are structurally parallel — the same insertion points apply.

**address_status values (per structure):**
```
"matched"        — KD-tree hit within address_join_radius_m
"unmatched"      — no address within radius
"missing_source" — address_source is None or file not found
"error"          — unexpected failure
```

**Do NOT change:**
- Any stage files (`s0N_*.py`)
- Any `tile_config.py` files
- Any Miami files
- The CLI interface of `run_city.py`
- Existing `_write_city_manifest()` signature — extend it with keyword args that default gracefully so old call sites (e.g., `rerun_missing_masses()`) still work

**Test after Phase 2:**
```bash
# LA with no address source — must give package_status=incomplete_missing_addresses
# (address_source defaults to None in CITIES registry)
conda run -n pdal_env python scripts/la/run_city.py los_angeles --execute --stages 04 05 --limit 2
# Check: city manifest has "package_status" key and "address_enrichment" block

# NYC same
conda run -n pdal_env python scripts/nyc/run_city.py new_york_city --execute --limit 2

# Miami unchanged — smoke test
conda run -n pdal_env python scripts/miami/run_miami_city.py --execute --limit 1

# Verify manifest schema
python3 -c "
import json
m = json.loads(open('/mnt/e/la/data_processed/cities/los_angeles/los_angeles_manifest.json').read())
assert 'package_status' in m, 'missing package_status'
assert 'address_enrichment' in m, 'missing address_enrichment'
print('LA manifest OK:', m['package_status'])
"
```

---

## Phase 3 — Audit for LA and NYC

**Goal:** Write `city_audit.json` and `city_audit.md` at the end of every `--execute` run for LA and NYC, using a shared common audit writer. Miami's separate `audit_miami_city.py` is not touched.

**Prerequisite:** Phase 2 complete.

**New file to create:**

### `scripts/common/audit_city.py`

A generic audit writer that accepts any object satisfying the Phase 1 `CityConfig` contract. Signature:

```python
def build_audit(
    cfg,                          # Any object with the Phase 1 CityConfig properties
    tile_results: dict,           # {tile_id: {status, terrain_only, lod0_prisms, ...}}
    tile_exit_codes: dict,        # {tile_id: int}
    addr_status: str,             # "ok" | "missing_source" | "failed"
    addr_count: int,
    enrichment_stats: dict,
    quiet: bool = False,
) -> dict:
    """
    Write city_audit.json and city_audit.md to cfg.audit_dir.
    Returns the audit dict.
    """
```

Audit fields to include (match Miami's schema version "1.1" where applicable):
```
schema_version          "1.1"
generated_at            ISO-8601 UTC
pipeline_version        cfg.pipeline_version
city_id                 cfg.city_id
display_name            cfg.display_name
package_status          from enrichment_stats or computed
preserve_raw_laz        cfg.preserve_raw_laz
CRS                     city-specific (caller passes as string)
bounds_4326             cfg.bbox_4326
tiles_attempted         len(tile_exit_codes)
tiles_ok                count rc==0
tiles_failed            count rc!=0
terrain_only_count      tiles with terrain_only=True
address_source          cfg.address_source path or null
address_points_count    addr_count
address_join_radius_m   cfg.address_join_radius_m
structures_count        enrichment_stats["structures_count"]
structures_with_address enrichment_stats["structures_with_address"]
structures_without_address enrichment_stats["structures_without_address"]
address_coverage_pct    enrichment_stats["coverage_pct"]
output_files            present/missing key paths
warnings                list of anomalies
```

The function must:
1. `cfg.audit_dir.mkdir(parents=True, exist_ok=True)`
2. Write `cfg.city_audit_json`
3. Write `cfg.city_audit_md` (Markdown table, same style as Miami's `audit_miami_city.py`)
4. If not quiet and Rich is available, print a summary table

### `scripts/la/run_city.py` — add audit call

At the end of `execute()`, after `_write_city_manifest()`:
```python
# ── Audit ─────────────────────────────────────────────────────────────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
from audit_city import build_audit as _build_audit
_build_audit(
    cfg             = cfg,
    tile_results    = tile_results,
    tile_exit_codes = tile_exit_codes,
    addr_status     = addr_status,
    addr_count      = addr_count,
    enrichment_stats = enrichment_stats,
    quiet           = False,
)
```

### `scripts/nyc/run_city.py`

Identical audit call at the end of `execute()`.

**Do NOT change:**
- `scripts/miami/audit_miami_city.py` — Miami has its own audit, leave it alone
- Any stage files
- Any `tile_config.py` files

**Test after Phase 3:**
```bash
# LA audit files must be written
conda run -n pdal_env python scripts/la/run_city.py los_angeles --execute --stages 05 --limit 2
ls /mnt/e/la/data_processed/cities/los_angeles/audit/
# Expect: city_audit.json  city_audit.md

# NYC audit files must be written
conda run -n pdal_env python scripts/nyc/run_city.py new_york_city --execute --limit 2
ls /mnt/t7/nyc/data_processed/cities/new_york_city/audit/

# Validate JSON schema
python3 -c "
import json
a = json.loads(open('/mnt/e/la/data_processed/cities/los_angeles/audit/city_audit.json').read())
assert a['schema_version'] == '1.1'
assert 'package_status' in a
assert 'tiles_ok' in a
print('LA audit OK')
"

# Miami must be UNTOUCHED — still runs and writes its own audit
conda run -n pdal_env python scripts/miami/run_miami_city.py --execute --limit 1
```

---

## Phase 4 — Bridge Miami to the Shared Contract

**Goal:** Make Miami's config participate in the shared `CityConfig` contract so that `scripts/common/audit_city.py` can be called from Miami's pipeline (replacing the Miami-specific `audit_miami_city.py`), and future cities can be added by choosing either the LA/NYC tile-runner pattern or the Miami footprintless-cluster pattern.

**Prerequisite:** Phases 1–3 complete and tested.

**WARNING:** Miami is production-live. This phase has the highest risk. Execute it only after Phases 1–3 are confirmed stable. If any step causes `--execute --limit 1` to fail, stop and revert.

### Step 4a — Create `scripts/miami/miami_city_config_v2.py`

Do NOT modify `miami_city_config.py` yet. Create a parallel file that wraps the flat constants into a `CityConfig`-compatible dataclass:

```python
"""
miami_city_config_v2.py  [GlitchOS — Miami]

CityConfig-compatible dataclass wrapping miami_city_config.py constants.
Drop-in replacement for the flat module in run_miami_city.py Phase 4.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import miami_city_config as _C


@dataclass(frozen=True)
class MiamiCityConfig:
    city_id:               str   = "miami_city"
    display_name:          str   = "City of Miami"
    usgs_project:          str   = _C.USGS_PROJECT_FULL
    bbox_4326:             dict  = field(default_factory=lambda: _C.CITY_BBOX_4326)
    boundary_sources:      tuple = ("arcgis", "census_tiger")
    address_source:        dict | None = field(default_factory=lambda: _C.ADDRESS_SOURCE)
    address_join_radius_m: float = _C.ADDRESS_JOIN_RADIUS_M
    preserve_raw_laz:      bool  = _C.PRESERVE_RAW_LAZ
    pipeline_version:      str   = _C.PIPELINE_VERSION

    # Storage roots (Miami-specific — different from LA/NYC layout)
    _out_root: Path = field(default=_C.OUT_ROOT, compare=False, repr=False)
    _laz_dir:  Path = field(default=_C.LAZ_DIR,  compare=False, repr=False)

    @property
    def output_root(self) -> Path:       return self._out_root
    @property
    def tiles_root(self) -> Path:        return _C.TILES_ROOT
    @property
    def boundaries_dir(self) -> Path:    return _C.BOUNDARIES_DIR
    @property
    def boundary_cache(self) -> Path:    return _C.BOUNDARY_CACHE
    @property
    def tile_manifest(self) -> Path:     return _C.TILE_MANIFEST
    @property
    def city_manifest(self) -> Path:     return _C.CITY_MANIFEST
    @property
    def metadata_dir(self) -> Path:      return _C.METADATA_DIR
    @property
    def address_points(self) -> Path:    return _C.ADDRESS_POINTS
    @property
    def structures_enriched(self) -> Path: return _C.STRUCTURES_ENRICHED
    @property
    def audit_dir(self) -> Path:         return _C.AUDIT_DIR
    @property
    def city_audit_json(self) -> Path:   return _C.CITY_AUDIT_JSON
    @property
    def city_audit_md(self) -> Path:     return _C.CITY_AUDIT_MD

    def protected_path_check(self) -> list[str]:
        return []   # Miami has PRESERVE_RAW_LAZ instead of protected paths


MIAMI_CFG = MiamiCityConfig()
```

### Step 4b — Add `build_audit` call in `run_miami_city.py`

After the existing `build_audit(quiet=True)` call in `execute()`, add a call using the common audit writer as a validation check:

```python
# Also run common audit writer for contract compliance verification
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
    from audit_city import build_audit as _common_audit
    from miami_city_config_v2 import MIAMI_CFG
    _common_audit(
        cfg              = MIAMI_CFG,
        tile_results     = {tid: {"lod0_prisms": r.get("lod0"), "terrain_only": r.get("terrain_only", False)}
                            for tid, r in tile_results.items()},
        tile_exit_codes  = tile_exit_codes,
        addr_status      = addr_status,
        addr_count       = addr_count,
        enrichment_stats = enrichment_stats,
        quiet            = True,
    )
except Exception as exc:
    # Common audit is supplemental — never fail the Miami pipeline for it
    state["log_tail"].append(f"[WARN] common audit writer: {exc}")
```

This is a soft addition — exceptions are caught and suppressed. Miami's own `audit_miami_city.py` continues to run and is the authoritative audit for Miami.

### Step 4c — Update `MIAMI_CFG` imports once verified

Once Step 4b is stable across 5+ tile runs, switch `run_miami_city.py` to use `MIAMI_CFG` in its dashboard header (display_name, pipeline_version) instead of reading constants directly from `miami_city_config`. This is cosmetic and low-risk.

**Do NOT do in Phase 4:**
- Do not rename `miami_city_config.py` — it is imported by `run_tile_miami.py`, `preflight_miami.py`, `audit_miami_city.py`, and `build_miami_catalog.py`
- Do not remove `audit_miami_city.py` — it may write additional Miami-specific audit fields
- Do not change Miami's stage names (`extract`, `clean`, etc.) to `s0N` numbering
- Do not merge `run_tile_miami.py` into the LA/NYC `run_tile.py` pattern — the architectures are fundamentally different (footprintless clustering vs footprint-driven masses)

**Test after Phase 4:**
```bash
# Full Miami pipeline — must produce complete package
conda run -n pdal_env python scripts/miami/run_miami_city.py --execute --limit 3

# Verify both audit files exist and agree on package_status
python3 -c "
import json
miami = json.loads(open('/mnt/t7/miami/data_processed/miami_city/audit/city_audit.json').read())
print('Miami audit package_status:', miami['package_status'])
assert miami['package_status'] == 'complete', 'expected complete'
print('Phase 4 OK')
"

# Verify LA/NYC unaffected
conda run -n pdal_env python scripts/la/run_city.py los_angeles --dry-run
conda run -n pdal_env python scripts/nyc/run_city.py new_york_city --dry-run
```

---

## File Change Summary

### Phase 1 — Config contract

| File | Action |
|---|---|
| `scripts/la/city_config.py` | Add 4 fields + 4 properties to `CityConfig` |
| `scripts/nyc/city_config.py` | Same |

### Phase 2 — Address enrichment

| File | Action |
|---|---|
| `scripts/la/run_city.py` | Add `_run_address_ingest()`, `_run_structures_enrichment()`, `_compute_package_status()`, update `_write_city_manifest()`, add enrichment call in `execute()` |
| `scripts/nyc/run_city.py` | Same |
| `scripts/la/stages/s04_masses.py` | Read-only — check property names for `centroid_x`/`centroid_y` in masses GeoJSON before writing enrichment reader |
| `scripts/nyc/stages/s04_masses.py` | Same |

### Phase 3 — Audit

| File | Action |
|---|---|
| `scripts/common/audit_city.py` | CREATE — generic audit writer |
| `scripts/la/run_city.py` | Add `build_audit()` call at end of `execute()` |
| `scripts/nyc/run_city.py` | Same |

### Phase 4 — Miami bridge

| File | Action |
|---|---|
| `scripts/miami/miami_city_config_v2.py` | CREATE — `MiamiCityConfig` dataclass wrapper |
| `scripts/miami/run_miami_city.py` | Add soft `_common_audit()` call; optionally use `MIAMI_CFG` for display fields |

### Files that must NOT be changed in any phase

```
scripts/miami/miami_city_config.py      (flat constants — do not rewrite)
scripts/miami/run_tile_miami.py         (tile subprocess — do not touch)
scripts/miami/preflight_miami.py        (Miami preflight — do not touch)
scripts/miami/audit_miami_city.py       (Miami-specific audit — do not remove)
scripts/miami/build_miami_catalog.py    (catalog builder — do not touch)
scripts/la/tile_config.py               (storage roots, TileConfig — do not touch)
scripts/nyc/tile_config.py              (same)
scripts/la/tile_discovery.py            (do not touch)
scripts/nyc/tile_discovery.py           (do not touch)
scripts/la/stages/*.py                  (do not touch any stage files)
scripts/nyc/stages/*.py                 (do not touch any stage files)
scripts/common/ingest_addresses.py      (already correct — do not touch)
```

---

## Adding a Future City

After all four phases are complete, adding Houston (for example) is:

1. **Choose architecture:**
   - Has building footprints available → use LA/NYC pattern: add `houston/city_config.py`, `houston/tile_config.py`, copy `stages/` from LA/NYC, add entry to `CITIES` dict
   - No footprints, cluster from point cloud → use Miami pattern: create `houston/houston_city_config.py` (flat constants or `MiamiCityConfig` subclass), adapt `run_tile_miami.py`

2. **Add to CITIES registry:**
   ```python
   "houston": CityConfig(
       city_id="houston",
       display_name="City of Houston",
       usgs_project="TX_Houston_2018",
       bbox_4326={"xmin": -95.77, "ymin": 29.52, "xmax": -95.01, "ymax": 30.11},
       address_source={
           "path": "/mnt/t7/houston/data_raw/addresses/houston_addresses.geojson",
           "source_name": "Harris County Open Addresses",
           "input_crs": "EPSG:4326",
           "field_map": {"house_number": "number", "street": "street", ...},
       },
       address_join_radius_m=100.0,
   )
   ```

3. **No new orchestration code needed** — `run_city.py`, `ingest_addresses.py`, and `audit_city.py` are already generic.

---

## Key Constraints (Repeat for Emphasis)

1. **Raw LAZ files are sacred.** `PRESERVE_RAW_LAZ = True` on every city config. No pipeline stage may delete, rename, overwrite, or move any file under any city's `LAZ_DIR`.

2. **Output isolation.** Derived outputs go under `output_root / ...` only. Per-tile outputs go under `tiles_root / tile_id / ...` only.

3. **Fail-soft on address ingest.** If `address_source` is `None` or file missing or ingest fails, the pipeline continues. `package_status` reflects the failure but tiles still process.

4. **address_status per structure** (four values only): `"matched"` | `"unmatched"` | `"missing_source"` | `"error"`.

5. **package_status** (three values only): `"complete"` | `"incomplete_missing_addresses"` | `"incomplete_address_enrichment_failed"`.

6. **Existing CLI interfaces do not change.** `run_city.py los_angeles --dry-run`, `run_city.py los_angeles --execute --stages 00 01`, and all other existing flags continue to work.

7. **conda environment:** `pdal_env`. All pipeline commands must be run as `conda run -n pdal_env python ...`.

8. **Address file CRS:** Always check the actual geometry coordinates in the source file before assuming `EPSG:4326`. Miami's address file was EPSG:3857 (Web Mercator) despite being a GeoJSON. The `ingest_addresses()` function handles reprojection when `input_crs` is set correctly — it is the caller's responsibility to set it right.
