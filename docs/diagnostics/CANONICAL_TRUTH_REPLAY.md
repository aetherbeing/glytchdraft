# Canonical Truth Replay

**Reviewed commit:** `f4bedb65c9612c5e3eaa19bec2103b22dfe98cc1`
**Baseline for replay:** `origin/master` at `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1`
**Replay branch:** `integration/miami-truth-and-fixture`
**Review date:** 2026-06-27

This file records the conservative replay of the provisional canonical-truth
commit. The commit was reviewed, not cherry-picked, because applying it directly
against the current baseline would overwrite newer repository work and delete
current roof, material, facade, schema, script, and test files.

## Retained

- `glytchdraft` is Phase 1 pipeline infrastructure. The public viewer/product
  boundary remains outside this repository and belongs to `glytchOS`.
- Phase 1 excludes economy, social, claims, UGC, Supabase product logic,
  monetization, Atlas/NFT/crypto output formats, and public viewer UX work.
- New Orleans remains documented as the Phase 1 reference city and pipeline
  proof: production-ready, open city footprint source, low legal risk, explicit
  fallback provenance, and visual certification ready.
- Miami remains documented as the Phase 1 viewer pilot, not a production-ready
  city. Miami-Dade footprint licensing remains unconfirmed for production use.
- Documentation must use evidence labels instead of converting assumptions into
  facts. Useful labels from the reviewed commit include `VERIFIED`, `INFERRED`,
  `CONTRADICTORY`, `SUPERSEDED`, `MISSING`, and
  `FOUNDER-CONFIRMATION-REQUIRED`.
- `docs/GLYTCHOS_SPEC.md` and
  `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` were identified as duplicate
  or competing specification surfaces in the reviewed commit. The current
  integration branch does not resolve that governance question.
- Cloudflare R2 geometry hosting was retained only as a specified architecture
  target with deployment status unknown unless separately verified.
- The repository should keep a stable pipeline-to-viewer asset contract:
  GLB tile assets, manifests, mesh-building maps, building metadata, and audit
  outputs are produced by Phase 1 for consumption by `glytchOS`.

## Rewritten

- The reviewed commit's broad `PROJECT_CONSTITUTION.md`, README, and ADR draft
  replacements were rewritten as this narrow replay record. The current branch
  already has stronger Phase 1 boundary instructions in `AGENTS.md` and the
  newly added diagnostics, so broad canonical-document replacement is not part
  of this integration.
- The reviewed commit's older baseline references to `b319b91` were rewritten
  to the current integration baseline `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1`.
- The reviewed commit's "founder confirmation required" framing for New Orleans
  was rewritten to match current instructions: New Orleans is the Phase 1
  reference city and pipeline proof; Miami is the viewer pilot.
- The reviewed commit's infrastructure notes were narrowed to status language
  that remains accurate without requiring live deployment verification.

## Omitted

- The direct changes to `AGENTS.md`, `README.md`, `PROJECT_CONSTITUTION.md`,
  top-level canonical docs, and ADR files were omitted. Replaying them wholesale
  would be a broad documentation rewrite outside this integration's limited
  purpose.
- Any deletion of current roof, material, facade, schema, script, or test files
  was omitted.
- Any statement implying the viewer repository or legacy `viewer/` should be
  modified was omitted.
- Any statement that would promote Phase 2+ economy, claims, social, UGC,
  Supabase product, or monetization concepts into Phase 1 was omitted.
- Any claim that Key Biscayne is clean was omitted.
- Any claim that South Beach is safe to promote was omitted.
- Any claim that 1601 Collins Avenue has been fixed was omitted.
- Any claim that viewer camera or vertical-scale changes solve the Miami unit
  defect was omitted.

## Superseded

- The reviewed commit's warning that its baseline did not include newer remote
  commits is superseded here by the fresh `origin/master` baseline recorded
  above.
- The reviewed commit's provisional draft banners remain useful as cautionary
  language, but their exact file-by-file draft set is superseded by this
  integration branch's diagnostic audit documents.
- The reviewed commit's broad canonical-document hierarchy is superseded for
  this branch by the narrower integration plan in
  `docs/diagnostics/REPOSITORY_INTEGRATION_PLAN.md`.

## Non-Claims

This replay does not certify Key Biscayne, South Beach, or any Miami output as
production-safe. It does not repair 1601 Collins Avenue. It does not modify
normal pipeline behavior, viewer behavior, generated assets, or production
outputs.
