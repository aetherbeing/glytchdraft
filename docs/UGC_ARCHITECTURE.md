# UGC Architecture

User-generated content is a future first-class GlytchDraft system. It must sit
beside the city model, not inside it. The base tile remains reproducible from
LiDAR, footprints, inferred masses, terrain, water, and official metadata. User
content is an optional overlay that can be hidden, moderated, versioned, removed,
exported, or imported without damaging base data.

This document reserves the model and runtime concepts for later phases. Do not
implement accounts, uploads, moderation workflows, networking, persistence, or
UGC rendering in Phase 1.

## Layer Model

### 1. Base Reality Layer

The Base Reality Layer is the stable spatial substrate.

- LiDAR evidence
- Building footprints
- Inferred building masses
- Terrain and water proxies
- Source provenance such as building `UNIQUEID`

UGC must not be baked into meshes, imported GLBs, terrain, point evidence, or
building metadata generated from source data.

### 2. System Meaning Layer

The System Meaning Layer is authored by GlytchDraft.

- Orders
- AI companion placeholders and later companion behavior
- Official overlays
- Tile metadata
- Curated system landmarks

UGC can reference this layer but should remain separable from it.

### 3. User Contribution Layer

The User Contribution Layer is authored by users or imported from user-owned
sources.

- Building annotations
- Photos and field notes
- Audio notes
- AR walking-tour fragments
- Proposed architectural interventions
- Order-aligned lore fragments
- Claim plaques and user territory notes
- Small models or objects placed in the tile
- Curated routes
- Environmental observations
- Local history and memory entries

This layer is optional, toggleable, attributable, moderated later, versioned,
and exportable/importable as JSON.

## UGC Object Schema

Future C++ names to reserve:

- `UGlytchUGCComponent`
- `FGlytchUGCRecord`

Suggested JSON / struct shape:

```json
{
  "ugc_id": "ugc_01H...",
  "user_id": "user_01H...",
  "display_name": "Contributor name",
  "type": "annotation",
  "title": "Short title",
  "body": "Contribution body text",
  "media_url": null,
  "asset_ref": null,
  "tile_id": "miami_hero_tile_v001",
  "building_uniqueid": "D3_MDC_Building_1",
  "local_position_meters": [2875.19, 2658.08, 1.18],
  "lat_lon": [-80.1658, 25.6924],
  "order_affinity": "pink_opaque",
  "companion_thread_id": null,
  "visibility": "public",
  "moderation_status": "approved",
  "created_at": "2026-05-19T00:00:00Z",
  "updated_at": "2026-05-19T00:00:00Z",
  "version": 1,
  "tags": ["field-note", "memory"],
  "source_quality": "user_submitted",
  "trust_level": "unverified"
}
```

### Core Fields

- `ugc_id`: Stable unique ID for the contribution.
- `user_id`: Stable user/account ID. Anonymous contributions should still use a
  generated contributor ID.
- `display_name`: Public or shared display name at the time of contribution.
- `type`: One of `annotation`, `photo`, `audio`, `model`, `route`,
  `design_proposal`, `lore_fragment`, or `claim_note`.
- `title`: Short label for list views, markers, and inspection panels.
- `body`: Text content, transcript, description, note, or lore fragment.
- `media_url`: Future hosted media URL for photos, audio, or video.
- `asset_ref`: Future asset reference for small models, AR fragments, or design
  proposal geometry.
- `tile_id`: Tile identity, such as `miami_hero_tile_v001`.
- `version`: Monotonic integer version for edits.
- `tags`: User or system tags for filtering.
- `source_quality`: Provenance category, distinct from LiDAR/building quality.
- `trust_level`: Moderation or reputation-derived confidence label.

## Spatial Anchoring Strategy

UGC should attach to one or more stable anchors. Prefer the most stable anchor
available, and keep secondary anchors for recovery if the primary anchor changes.

### Building UNIQUEID

Use `building_uniqueid` when a contribution is about a specific building. This is
the preferred anchor for building annotations, photos, claim plaques, design
proposals, and local history entries tied to a structure.

Rules:

- Store the source `UNIQUEID` exactly as exported.
- Do not infer identity from mesh name alone once backend persistence exists.
- Keep an optional `local_position_meters` offset for marker placement on or near
  the building.

### Tile-Local Coordinates

Use `local_position_meters` for placed objects, environmental observations,
route points, AR fragments, and notes that are not tied to a building.

Rules:

- Store coordinates in tile-local meters.
- Convert to UE centimeters only at runtime.
- Do not store raw UTM coordinates in gameplay actors unless a data asset or
  backend transform layer owns the conversion.

### GPS / Lat-Lon

Use `lat_lon` when contributions originate from phones, field capture, AR walks,
or web maps.

Rules:

- Treat lat/lon as an interchange and capture format.
- Resolve it to `tile_id` plus `local_position_meters` before runtime display.
- Keep the original lat/lon for audit and export.

### Order Overlay

Use `order_affinity` for lore fragments, symbolic annotations, or observations
that intentionally attach to an Order.

Rules:

- Order affinity is semantic, not geometric, unless paired with a position.
- A UGC item may reference an Order and a building at the same time.

### AI Companion Conversation Thread

Use `companion_thread_id` when a contribution emerges from a future AI companion
conversation.

Rules:

- The UGC record should store only the stable thread ID, not the full transcript.
- Transcript storage belongs to the AI/backend layer.
- Generated or AI-assisted content must still have a user attribution and
  moderation status.

### User Claim / Trace Object

Claims and Trace objects are Phase 4+ systems. UGC should reserve the ability to
attach to them later without requiring a schema rewrite.

Future fields may include:

- `claim_id`
- `trace_object_id`
- `territory_id`

## Visibility And Privacy

Use explicit visibility values:

- `private`: Visible only to the author.
- `shared`: Visible to selected collaborators, groups, or sessions.
- `public`: Visible in public city layers after moderation rules allow it.

Future privacy rules:

- Private content must not be loaded into public map sessions.
- Shared content needs an access-control check before streaming.
- Public content can still be hidden by moderation, user block lists, or local
  layer filters.
- Media URLs should be signed or permissioned when visibility is not public.

## Moderation And Status

Use explicit moderation status values:

- `draft`: Local or user-owned draft, not submitted.
- `pending`: Submitted for review or automated checks.
- `approved`: Allowed for its target visibility.
- `hidden`: Previously visible but currently suppressed.
- `rejected`: Not allowed to publish.

Moderation should be able to hide or remove UGC without editing base city data.
Moderation events should be auditable later, but that audit system is not part of
Phase 1.

## Relationship To Existing Systems

### Buildings

Building-linked UGC should reference `building_uniqueid`. The building actor can
later expose an anchor component or query for UGC records associated with its
metadata component.

Potential runtime behavior:

- Selecting a building can show base metadata plus a separate UGC tab.
- UGC markers can cluster around a building centroid or explicit offset.
- Removing a UGC item should never alter `UGlytchBuildingMetadataComponent`.

### Orders

Order-linked UGC should use `order_affinity`. Lore fragments and symbolic notes
can be filtered by Order without being merged into official overlays.

Potential runtime behavior:

- Toggle user lore by Order.
- Show UGC density inside an Order overlay.
- Let official Order overlays and user Order fragments render as separate
  sublayers.

### AI Companions

AI companion conversations may create or reference UGC, but companion behavior is
not part of Phase 1.

Potential runtime behavior:

- Companion-generated prompts can invite a user to save a note.
- Saved notes reference `companion_thread_id`.
- AI-assisted records remain attributable to the user and moderated like other
  UGC.

### Claims

Claims and Trace objects are later systems. UGC claim notes should be modeled as
attachments, not as the claim source of truth.

Potential runtime behavior:

- A claim plaque can be a UGC item attached to a building or coordinate.
- Territory notes can reference future `claim_id` or `trace_object_id`.
- Removing a claim note should not delete the claim.

## UE5 Runtime Ideas

Reserve these class names for later phases:

- `AGlytchUGCAnchorActor`
- `UGlytchUGCComponent`
- `AGlytchUGCMarkerActor`
- `UGlytchUGCLayerManager`

Suggested responsibilities:

- `FGlytchUGCRecord`: Plain data struct mirroring the JSON schema.
- `UGlytchUGCComponent`: Component attached to an anchor, building, marker, or
  route actor. Holds one or more `FGlytchUGCRecord` values.
- `AGlytchUGCAnchorActor`: Invisible or minimal actor representing a stable
  spatial anchor for coordinate-based UGC.
- `AGlytchUGCMarkerActor`: Visible marker for a note, photo, model, route point,
  or design proposal.
- `AGlytchUGCLayerManager`: Loads, filters, toggles, imports, exports, and
  unloads UGC records for the active tile.

Phase 1 may reserve names or interfaces if convenient, but should not make UGC a
dependency of tile loading, building selection, or metadata display.

## Web / Supabase Backend Notes

Future backend storage can map naturally to Supabase tables and buckets.

Potential tables:

- `ugc_records`
- `ugc_versions`
- `ugc_media`
- `ugc_moderation_events`
- `ugc_visibility_grants`
- `ugc_route_points`
- `ugc_model_assets`

Potential storage buckets:

- `ugc-photos`
- `ugc-audio`
- `ugc-models`
- `ugc-ar-fragments`

Backend responsibilities:

- Authentication and attribution
- Row-level security by `visibility`
- Moderation workflow and audit trail
- Version history
- Media upload, virus scanning, and transcoding
- Tile-based queries by `tile_id`
- Spatial queries by local coordinate, lat/lon, or building `UNIQUEID`
- JSON import/export for user-owned archives and project migration

The UE runtime should eventually consume an API response shaped like
`FGlytchUGCRecord`, not direct database rows.

## JSON Import / Export

UGC should be exportable as a standalone JSON document:

```json
{
  "schema_version": "1.0",
  "tile_id": "miami_hero_tile_v001",
  "exported_at": "2026-05-19T00:00:00Z",
  "records": []
}
```

Import rules:

- Validate schema version.
- Validate `tile_id`.
- Validate anchors before rendering.
- Preserve original `ugc_id` when importing trusted project archives.
- Generate new IDs when importing user-local drafts into a shared backend.
- Never write imported UGC into base tile manifests or building metadata files.

## What Not To Implement Yet

Do not implement these in Phase 1:

- User accounts
- Upload flows
- Media hosting
- Moderation queues
- Networking
- Supabase integration
- Persistence
- Runtime UGC marker rendering
- AR capture
- Route authoring
- Claim/Trace economy integration
- AI companion UGC creation
- Baking UGC into GLB, FBX, base meshes, or source metadata

Phase 1 remains focused on the preview 20-building GLB, metadata loading,
selection, layer toggles, camera movement, companion placeholders, and Order
overlay placeholders.
