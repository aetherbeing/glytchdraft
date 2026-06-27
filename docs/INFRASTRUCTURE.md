# Infrastructure
**Authority:** `docs/CANONICAL_TRUTH_AUDIT.md §10`, `docs/GLYTCHOS_SPEC.md §7`.  
**Last verified:** 2026-06-27.

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

---

## Hosting Split (SPECIFIED per spec §7.1 — deployment status UNKNOWN)

The spec describes two separate hosting targets:

| Component | Specified Target | Reason |
|-----------|-----------------|--------|
| Viewer shell (React app) | Vercel | Fast CDN delivery of the JS/HTML shell |
| GLB geometry tiles | Cloudflare R2 + CDN | Cheap/zero egress — Vercel bills bandwidth hard; R2 does not |

Per the spec, serving three cities' geometry tiles through Vercel = 3× the bill.
Geometry on R2 + manifest-driven fetch = cost ≈ storage + near-zero egress.
Whether this split is currently deployed requires founder confirmation (FC-6).

**Vercel deployment:** `vercel.json` committed at root. Status: INFERRED present but
deployment state (whether it is live) is UNKNOWN.

**R2 GLB hosting:** Specified in spec; deployment status MISSING. FC-6 (see audit).

---

## Pipeline Operating Environment

| Resource | Location | Details |
|----------|----------|---------|
| Primary machine | `jaDeFireLoom1` | WSL2 on Windows |
| Pipeline environment | `conda pdal_env` | Python 3.11.15, PDAL 2.10.1, pyproj 3.7.2, jsonschema 4.26.0 |
| LAZ raw data | `/mnt/e/` (primary), `/mnt/t7/` (T7 SSD) | Never deleted |
| Processed outputs | `/mnt/e/` and `/mnt/t7/` | Per machine-local `paths.local.json` |
| GitHub | `aetherbeing/glytchdraft` | Only source of truth |

---

## Operating Scripts (VERIFIED — R2 work, commit `468e706`)

Three executable scripts at `scripts/`:

```bash
./scripts/preflight.sh    # Run before any work session
./scripts/save.sh "msg"   # Commit + push; session is not done until this prints PUSHED
./scripts/agnostic_gate.sh  # Verify no city-hardcoded logic in viewer/src/
```

**Session discipline (from spec §2.3):**
1. Run `preflight.sh` before any work
2. Work only in `~/glytchdraft` (WSL-native, not `/mnt/c/`)
3. Session is not done until `save.sh` prints **PUSHED**

---

## Conda Environment Management

All pipeline commands run as:

```bash
conda run -n pdal_env python scripts/phases/phase_NN_*.py --city configs/cities/<city>.json [flags]
```

The `pdal_env` environment must not be modified without recording the change in `docs/HANDOFF.md`.
The R11 environment change (adding `jsonschema 4.26.0`) is the documented model for this.

---

## Backend / Database (Phase 2+ — not active in Phase 1)

`SUPABASE_SETUP.md` documents a Supabase/Postgres scaffold for the Phase 2+ economy.
Tables: `users`, `orders`, `structures`, `trace_balances`, `trace_transactions`,
`claimed_structures`, `claim_history`, `geosocial_posts`.

This backend is **not active** in Phase 1. No pipeline phase reads from or writes to it.
It lives in `backend/supabase/` and is reserved for `glytchOS` Phase 2+.

---

## Data Lifecycle

```
Raw LAZ files (sacred — read-only forever)
  ↓ PDAL processing
Per-tile PLY outputs (building, ground, vegetation point clouds)
  ↓ DBSCAN + footprint join
Per-tile footprint GeoJSON + mass OBJ files
  ↓ GLB export
Per-tile GLB (viewer asset)
  + structures_enriched.geojson (per-building metadata)
  + viewer_manifest.json (schema-validated)
  + audit_report.json (computed, never hand-authored)
  ↓ glytchOS consumes
Viewer loads manifest → fetches GLBs → displays city
```

**Egress strategy:** Only tiles in Zone 0–2 (within `reveal_radius_m` of the camera)
are fetched. Zone 3 (beyond fog) = no geometry fetched = no egress charged.
See `docs/ARCHITECTURE.md §Cost Architecture`.

---

## Recovery Protocol (from spec §2.4)

If work may be stranded or missing:

```bash
# Check for unpushed commits
git log --branches --not --remotes --oneline --decorate -30

# Check for uncommitted changes
git status -sb && git diff --stat

# Check for untracked outputs
git ls-files --others --exclude-standard

# Only if the official repo lacks the work, search machine by mtime
# Never copy scratch blindly — diff -ru first
```

---

*For data locations by drive and path, see `docs/RESOURCE_MAP.md`.*  
*For the GLB coordinate contract, see `docs/DATA_CONTRACTS.md §GLB Coordinate Contract`.*
