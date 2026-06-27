# Repository Integration Plan

Audit timestamp: `2026-06-27T17:47:50-04:00`

## 1. Executive Summary

`origin/master` at audit time is `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1` (`merge: integrate roofs, materials, and facades pipeline lanes`). It is the canonical production baseline supported by current Git evidence. Future integration must begin from a freshly fetched `origin/master`, because this ref can move after this audit.

Local `master` at `b319b9187166b236b7dd906b3709d909c6b38231` is a strict ancestor of `origin/master` and must not be used as an integration base. Local `main` is unrelated history, no `origin/main` exists, and neither local branch should be used as the canonical base.

The ten commits missing from local `master` are the current remote roof, material, and facade integration lane. `integration/quad-lanes`, `codex/roof-diagnostic-prototype`, and `codex/material-evidence-adapters` are already represented in `origin/master`; `codex/facade-diagnostic-prototype` is patch-equivalent and superseded.

Safest integration path:

1. Fetch and create a fresh integration branch from the current `origin/master`.
2. Cherry-pick approved isolated audit documents.
3. Review `docs/canonical-truth` file-by-file and replay only still-valid content.
4. Cherry-pick the Miami two-tile fixture commit.
5. Run focused fixture tests and broader Miami regressions.
6. Keep fixture feature flags disabled in normal production processing.
7. Design production XYZ-in-meters migration separately.
8. Defer viewer camera/default-scene changes until corrected metric assets exist.

## 2. Canonical Branch Finding

Evidence commands:

```bash
git remote -v
git branch -a -vv
git show-ref
git log --graph --decorate --oneline --all --date-order -n 150
```

Findings:

- `origin/master` exists at `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1`.
- `audit/repository-integration-plan` is currently based at the same commit and tracks `origin/master`; its report is still uncommitted in this worktree.
- Local `master` exists at `b319b9187166b236b7dd906b3709d909c6b38231` and tracks `origin/master`, but is behind by ten commits.
- No `refs/remotes/origin/main` exists.
- Local `main` exists at `d6e1635df5f4b2e5a5ad710ae53fc3c777690ee3` and is unrelated to `origin/master`.

Canonical production baseline at audit time: `origin/master` at `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1`.

## 3. `main` Versus `master`

`main` and `origin/master` have no merge base:

```bash
git merge-base main origin/master
# no output
```

Symmetric count:

```bash
git rev-list --left-right --count origin/master...main
# 128  9
```

`main` unique commits:

```text
d6e1635 feat: pipeline hardening v0.3 - PID lock, retry/backoff, threaded downloads
3adcaa0 feat: production-critical pipeline stages and architecture v0.2
5ba10b4 feat: master end-to-end pipeline with hot-pink rich progress bars
b0a7efe feat: headless Blender extrusion pipeline for building footprints
0aae6a3 feat: add Atlas Protocol LiDAR output - 1667 enriched building JSONs
476098f fix: correct CRS alignment and replace per-building LAS scan with single-pass STRtree extraction
8816111 fix: replace GeoSeries.from_bbox with shapely box for geopandas compatibility
aa04189 fix: use standard setuptools build backend; add setup.py for editable installs
f713879 feat: initial Atlas Protocol LiDAR extraction pipeline
```

These commits are not present on `origin/master`, but the branch is from unrelated history. It contains generated `atlas_output/*.json` files and `glytchos/` pipeline code, both outside the current Phase 1 boundary.

Recommendation for local `main`: `DO NOT INTEGRATE`.

## 4. Remote/Local Divergence

Local `master` is behind `origin/master` by ten commits:

```bash
git rev-list --left-right --count origin/master...master
# 10  0
```

This means `origin/master` has ten commits not present in local `master`; local `master` has no commits missing from `origin/master`.

Merge base:

```bash
git merge-base master origin/master
# b319b9187166b236b7dd906b3709d909c6b38231
```

Cause: local `master` is parked at `b319b91` (`pipeline: validate footprint cleanup and rooftop candidates`). Remote `origin/master` has since integrated materials, roof, and facade branches on top of that commit.

## 5. Ten-Commit `origin/master` Delta

Commits in `master..origin/master`:

```text
7bcaab1 merge: integrate roofs, materials, and facades pipeline lanes
0dbc2c1 pipeline: add diagnostic facade geometry prototype
906f724 pipeline: add deterministic facade synthesis contract
03e365c merge: integrate materials lane (codex/material-evidence-adapters @ db614c47)
f7b7bd6 merge: integrate roofs lane (codex/roof-diagnostic-prototype @ 1e5aa4f)
1e5aa4f pipeline: add roof real-data smoke adapter
db614c4 pipeline: add external material evidence adapters
2eaeab4 pipeline: add diagnostic two-plane roof prototype
1b94b95 pipeline: add deterministic roof feasibility analyzer
60f286b pipeline: add provenance-aware material clue system
```

File areas added by this delta:

- `docs/MATERIAL_CLUE_SYSTEM.md`
- `docs/MATERIAL_EVIDENCE_ADAPTERS.md`
- `docs/ROOF_RECONSTRUCTION_FEASIBILITY.md`
- `docs/ROOF_DIAGNOSTIC_PROTOTYPE.md`
- `docs/ROOF_REAL_DATA_SMOKE_VALIDATION.md`
- `docs/FACADE_SYNTHESIS_SYSTEM.md`
- `docs/FACADE_DIAGNOSTIC_PROTOTYPE.md`
- `docs/FACADE_PHASER_ROADMAP.md`
- `schemas/*roof*`, `schemas/*material*`, `schemas/*facade*`
- `scripts/roofs/*`
- `scripts/materials/*`
- `scripts/facades/*`
- corresponding `tests/*`

## 6. Branch Ancestry Matrix

| Branch | Merge base with `origin/master` | Ahead/behind (`origin/master...branch`) | Type | Ancestry | Recommendation |
|---|---:|---:|---|---|---|
| `audit/infrastructure-truth` | `7bcaab1` | `0 / 1` | documentation-only | current | `CHERRY-PICK COMMIT` |
| `audit/key-biscayne-provenance` | `7bcaab1` | `0 / 1` | documentation-only | current | `CHERRY-PICK COMMIT` |
| `audit/miami-four-tile-preflight` | `7bcaab1` | `0 / 2` | documentation-only | current | `CHERRY-PICK COMMIT` |
| `audit/repository-integration-plan` | `7bcaab1` | report uncommitted | documentation-only | current | `KEEP AS AUDIT ONLY` |
| `docs/canonical-truth` | `b319b91` | `10 / 3` | documentation-only | stale | `REPLAY ON FRESH BRANCH` |
| `codex/miami-two-tile-unit-fixture` | `7bcaab1` | `0 / 1` | implementation + tests | current | `CHERRY-PICK COMMIT` |
| `codex/roof-diagnostic-prototype` | `1e5aa4f` | `8 / 0` | implementation + tests | already integrated | `SUPERSEDED` |
| `codex/facade-diagnostic-prototype` | `6a023c9` | `11 / 4` | implementation + tests | stale, patch-equivalent | `SUPERSEDED` |
| `codex/material-evidence-adapters` | `db614c4` | `9 / 0` | implementation + tests | already integrated | `SUPERSEDED` |
| `integration/quad-lanes` | `0dbc2c1` | `1 / 0` | integration branch | already integrated except merge commit | `SUPERSEDED` |
| local `main` | none | `128 / 9` | unrelated implementation/generated history | unrelated | `DO NOT INTEGRATE` |
| local stale `master` | `b319b91` | `10 / 0` | local tracking branch | stale local pointer | `DO NOT INTEGRATE` |

## 7. Unique Commits By Branch

### `audit/infrastructure-truth`

```text
e6a727b docs: add infrastructure truth audit
```

Files:

```text
docs/diagnostics/INFRASTRUCTURE_TRUTH_AUDIT.md
```

Disposition: `CHERRY-PICK COMMIT`. Cherry-picking `e6a727b` avoids an unnecessary merge commit and imports only the intended audit document.

### `audit/key-biscayne-provenance`

```text
52f513d docs: add Key Biscayne provenance audit
```

Files:

```text
docs/diagnostics/KEY_BISCAYNE_PROVENANCE_AUDIT.md
```

Disposition: `CHERRY-PICK COMMIT`. Cherry-picking `52f513d` avoids an unnecessary merge commit and imports only the intended audit document.

### `audit/miami-four-tile-preflight`

Merge base:

```text
7bcaab1cfa239fb68ead4dacf7b627e5d05505c1
```

Divergence:

```text
origin/master...audit/miami-four-tile-preflight = 0 / 2
```

Unique commits:

```text
87ce71d docs: add Miami four-tile preflight audit
b3abbae docs: clean Miami preflight whitespace
```

Files:

```text
docs/diagnostics/MIAMI_FOUR_TILE_PREFLIGHT.md
```

Disposition: `CHERRY-PICK COMMIT`. Both commits should remain in order unless later deliberately squashed on a fresh integration branch:

```bash
git cherry-pick 87ce71d b3abbae
```

### `audit/repository-integration-plan`

This branch is the current audit worktree. The report is still uncommitted, so no future integration SHA should be invented in this document.

Disposition before review and commit: `KEEP AS AUDIT ONLY`. After approval, its eventual single documentation commit should be cherry-picked into the integration branch with the other accepted audits.

### `docs/canonical-truth`

```text
f4bedb6 docs: checkpoint provisional canonical drafts
3154e02 docs: establish canonical documentation system
6c366c9 docs: add canonical truth audit
```

This branch adds broad root and docs files:

```text
PROJECT_CONSTITUTION.md
docs/ARCHITECTURE.md
docs/CANONICAL_TRUTH_AUDIT.md
docs/CHANGELOG.md
docs/CURRENT_STATE.md
docs/DATA_CONTRACTS.md
docs/GLOSSARY.md
docs/INFRASTRUCTURE.md
docs/NEXT_ACTION.md
docs/PRODUCT_SCOPE.md
docs/RESOURCE_MAP.md
docs/ROADMAP.md
docs/VISION.md
docs/decisions/*
```

Risk: docs are stale by ten `origin/master` commits and include broader product references. Replay only still-valid content after file-level review; do not blindly merge the branch or full cherry-pick all commits.

### `codex/miami-two-tile-unit-fixture`

```text
ef6e698 pipeline: add Miami two-tile unit fixture
```

Full commit:

```text
ef6e698a42112eeea140b83b4996b972d66af928
```

Files:

```text
docs/diagnostics/MIAMI_TWO_TILE_UNIT_FIXTURE.md
scripts/miami/bikini_config.py
scripts/miami/run_two_tile_unit_fixture.py
scripts/miami/s01_extract.py
tests/test_miami_two_tile_unit_fixture.py
```

This branch is current and contains one implementation commit. Prefer cherry-pick onto a new integration branch from the current `origin/master`, then review the two modified Miami scripts before merging. Do not enable the fixture feature flag in normal production processing.

### `codex/roof-diagnostic-prototype`

No unique commits relative to `origin/master`. Its tip `1e5aa4f` is already in `origin/master`.

### `codex/facade-diagnostic-prototype`

Nominal unique commits:

```text
8d03702 pipeline: add diagnostic facade geometry prototype
48150bf pipeline: add deterministic facade synthesis contract
98b6bdf pipeline: add deterministic roof feasibility analyzer
17f3c3f pipeline: add provenance-aware material clue system
```

`git cherry -v origin/master codex/facade-diagnostic-prototype` marks all four as patch-equivalent:

```text
- 17f3c3f pipeline: add provenance-aware material clue system
- 98b6bdf pipeline: add deterministic roof feasibility analyzer
- 48150bf pipeline: add deterministic facade synthesis contract
- 8d03702 pipeline: add diagnostic facade geometry prototype
```

The equivalent changes are already represented on `origin/master` as `60f286b`, `1b94b95`, `906f724`, and `0dbc2c1`.

### `codex/material-evidence-adapters`

No unique commits relative to `origin/master`. Its tip `db614c4` is already in `origin/master`.

### `integration/quad-lanes`

No unique commits relative to `origin/master`. Its tip `0dbc2c1` is already in `origin/master`; `origin/master` only adds the final merge commit `7bcaab1` on top.

### local `main`

Nine unique commits, unrelated to `origin/master`; do not merge. Generated assets include `atlas_output/D3_MDC_Building_*.json`. Unrelated/quarantined areas include `glytchos/pipeline/*`.

## 8. File-Overlap And Conflict Risks

Highest conflict risk:

- `codex/miami-two-tile-unit-fixture` modifies existing Miami scripts:
  - `scripts/miami/bikini_config.py`
  - `scripts/miami/s01_extract.py`

Moderate content risk:

- `docs/canonical-truth` adds many broad documentation files. It does not directly overlap the ten-commit pipeline delta by path, but it may conflict semantically with the current Phase 1 boundary and newer roof/material/facade documentation.

Low conflict risk:

- `audit/infrastructure-truth`, `audit/key-biscayne-provenance`, and `audit/miami-four-tile-preflight` add isolated diagnostics files. Cherry-picking is still preferred over direct merge because it avoids unnecessary merge commits and imports only intended audit documents.

Already resolved or obsolete:

- `codex/roof-diagnostic-prototype`
- `codex/material-evidence-adapters`
- `codex/facade-diagnostic-prototype`
- `integration/quad-lanes`

Do not integrate:

- local `main`, because of unrelated history, generated `atlas_output`, and obsolete `glytchos/` paths.
- local stale `master`, because it is ten commits behind `origin/master`.

## 9. Recommended Integration Order

1. Fetch and create a fresh integration branch from the current `origin/master`.
2. Cherry-pick the approved documentation audits:
   - infrastructure;
   - Key Biscayne;
   - Miami four-tile preflight;
   - repository integration plan after it is committed.
3. Run documentation and repository checks.
4. Review `docs/canonical-truth` file-by-file and replay only still-valid content on a fresh branch.
5. Cherry-pick the Miami fixture commit:
   - `ef6e698a42112eeea140b83b4996b972d66af928`
6. Run the focused fixture tests and broader Miami regression tests.
7. Do not enable the fixture feature flag in normal production processing.
8. Design the production XYZ-in-meters migration as a separate branch.
9. Defer viewer camera/default-scene changes until corrected metric assets exist.

Do not integrate `integration/quad-lanes`; it is obsolete because `origin/master` already contains its work.

## 10. Exact Commands For Future Integration Steps

Do not run these from this audit branch. These are future integration commands.

Establish canonical base:

```bash
git fetch origin
git switch -c integration/miami-truth-and-fixture origin/master
```

Cherry-pick approved audit documents:

```bash
git cherry-pick e6a727b
git cherry-pick 52f513d
git cherry-pick 87ce71d b3abbae

# Add the repository integration-plan commit later, after it exists.
```

Canonical-truth replay must happen through file-level review, not a blind branch merge or full cherry-pick:

```bash
git switch -c integration/canonical-truth-docs origin/master
# Review docs/canonical-truth file-by-file and copy or replay only still-valid content.
git status --short
git diff --name-status
git diff --check
```

Miami two-tile fixture:

```bash
git cherry-pick ef6e698a42112eeea140b83b4996b972d66af928
git diff --check
pytest tests/test_miami_two_tile_unit_fixture.py
pytest tests/test_nola_phase_fixes.py tests/test_run_roof_real_data_smoke.py tests/test_normalize_material_evidence.py
```

Check obsolete branch equivalence before deletion later:

```bash
git branch --contains 1e5aa4f
git branch --contains db614c4
git branch --contains 0dbc2c1
git cherry -v origin/master codex/facade-diagnostic-prototype
```

## 11. Branches To Preserve But Not Merge

- local `main`: preserve for archaeology only; do not merge.
- `docs/canonical-truth`: preserve until selected docs are replayed or consciously rejected.
- `audit/repository-integration-plan`: preserve as audit evidence until reviewed and committed.
- local stale `master`: preserve until the owner decides whether to fast-forward it to `origin/master`.

## 12. Branches That May Be Deleted Later

Only after owner approval and after confirming no worktrees require them:

- `codex/roof-diagnostic-prototype`
- `codex/material-evidence-adapters`
- `codex/facade-diagnostic-prototype`
- `integration/quad-lanes`

Also check remote branch policy before deleting remote refs.

## 13. Stop Conditions

Stop future integration if any of these occur:

- A branch introduces generated LAZ, LAS, GLB, large binary, or `atlas_output/*` files.
- A branch modifies `viewer/`, `frontend/`, `backend/`, `glytchos/`, economy, claims, social, UGC, crypto, or monetization paths.
- A branch changes Phase 1 provenance rules without audit coverage.
- `git diff --check` fails.
- Miami fixture changes alter production Miami behavior beyond the two-tile fixture scope.
- Documentation contradicts the Phase 1 boundary or New Orleans canonical reference-city status.
- Any future integration branch is not created from a freshly fetched `origin/master`.

## 14. Safest Single Next Action

> Review, commit, and push this integration-plan audit without performing integration; then create a fresh integration branch from the current `origin/master` and cherry-pick only the approved documentation commits.
