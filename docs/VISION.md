# Vision
**Authority:** `docs/GLYTCHOS_SPEC.md §0–§1`, `docs/CANONICAL_TRUTH_AUDIT.md §5`.  
**Last verified:** 2026-06-27.

---

## Core Thesis (VERIFIED)

> GlitchOS.io turns public spatial data into a living interface for real places.

Source: `docs/GLYTCHOS_SPEC.md §1`.

The first product is not a game economy, not ownership speculation, not a generic map. It is:

> **A web-native spatial body of a real city that users can explore, inspect, and eventually design into.**

---

## What GlitchOS.io Does (Phase 1 MVP)

GlitchOS.io transforms real-world public spatial data into deployable spatial artifacts:
web-viewable, AR/VR-ready, metadata-rich digital bodies of physical places.

The goal is not 3D tiles. The goal is a stable, inspectable, portable **city simulacrum**
— usable on the web, in AR/VR, in a presentation, in a planning workflow, or as design context.

### MVP demonstration requirements (per spec §8)

A Phase 1 MVP must demonstrate:

- Real city-derived geometry from public spatial data
- Multiple tiles with smooth navigation across them
- Readable building masses with visible top surfaces
- Stable lighting — buildings visible, atmospheric
- Hover state on buildings
- Selected state on buildings
- Metadata panel showing traceable per-building information
- Manifest-driven tile loading (no hardcoded single-city trap)
- Provenance and audit awareness (data completeness visible)

The MVP does not require: multiplayer, economy, ownership, crypto, payments, full UGC,
full civic integration, perfect roofs, full city-scale streaming, native AR/VR, or engine deployment.

**Status: INFERRED-SUPPORTED from spec §8. FOUNDER-CONFIRMATION-REQUIRED to confirm
this is the current go-to-market target.** See audit FC-10.

---

## Build Order (VERIFIED)

Build order is strict. Every layer assumes the one beneath it.

```
1. Fabric            — trustworthy city geometry, provenance, metadata
2. Artifact sales    — the city simulacrum as a sellable B2B deliverable
3. Design-into-fabric — users can propose modifications to the built environment
4. Builder           — tools for designing within the fabric
5. Cherries          — curated landmark and cultural content
6. Cultural layer    — community, events, place memory
```

Source: `docs/GLYTCHOS_SPEC.md §1`.

Phase 1 builds the fabric. The artifact is the first sellable deliverable. Everything
above Layer 2 is Phase 2+.

---

## First Markets (VERIFIED)

Per `docs/GLYTCHOS_SPEC.md`: Miami → Los Angeles → New York.

Baltimore is the warm go-to-market lead (placemaker contact via NDC) and the likely
first *sold* district.

---

## Phase 2+ Vision (NOT Phase 1 — do not implement in glytchdraft)

The following describes the intended Phase 2+ product direction. It is recorded here
as direction only. Nothing below this line should be implemented in `glytchdraft`.

Source: `GLITCHOS_VISION.md` (present in this repo with Phase 2+ scope note),
`docs/ORDERS.md`, `ai/README.md`.

**Place-indexed media:** Content geo-tagged to specific buildings and floors.
A genuinely new content format — nobody has built this yet.

**The 12 Orders:** Symbolic lenses for reading a city. Companion AI behavior, UI filter
tints, ambient audio, and landmark assignments all flow from Order identity.
Defined in `docs/ORDERS.md` (12 Orders including Cornucopians, Planar Witnesses,
Mirrorsweat, Signal Choir, Cradle Mold, The Pink Opaque, etc.).

**AI Companion system:** 8-agent companion stack (Field Guide, Atmosphere Voice, Order
Chronicler, Architectural Envisioner, Building Doper, Data Steward, Cinematic Director,
Market/Claims Agent). Designed in `ai/`. Not built in Phase 1.

**Economy:** Trace currency, structure claims, geosocial posts. Supabase scaffold exists.
Not active in Phase 1 pipeline.

> These Phase 2+ features must not be silently reintroduced into `glytchdraft`. Any
> PR that adds economy, claims, UGC, or companion logic to the Phase 1 pipeline is a
> constitution violation. See `PROJECT_CONSTITUTION.md §2`.

---

*For current implementation status, see `docs/CURRENT_STATE.md`.*  
*For what is explicitly out of scope in Phase 1, see `docs/PRODUCT_SCOPE.md`.*
