# Claim Viewer + GeoSocial Notes

## Instance 4 Schema Alignment

The frontend mock uses the existing Trace/claims scaffold where possible:

- `users.id`
- `users.display_name`
- `users.charity_allocation_percentage`
- `trace_balances.available_trace`
- `claimed_structures.id`
- `claimed_structures.user_id`
- `claimed_structures.structure_id`
- `claimed_structures.order_id`
- `claimed_structures.claim_status`
- `claimed_structures.claim_cost_trace`
- `claimed_structures.structure_provenance`
- `claimed_structures.claimed_at`
- `claimed_structures.released_at`

The claim button is mock-only. It creates a local object shaped like
`claimed_structures`; it does not call payments, Stripe, or any token rail.

## Minimal GeoSocial Additions

If Instance 4 adds persistence for place-tied posts, keep it small:

```sql
create table public.geosocial_posts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  structure_id text,
  tile_id text,
  coordinates jsonb,
  body text not null,
  visibility text not null default 'public',
  media jsonb not null default '[]'::jsonb,
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint geosocial_posts_anchor_required
    check (structure_id is not null or tile_id is not null or coordinates is not null),
  constraint geosocial_posts_visibility
    check (visibility in ('public', 'private', 'friends', 'unlisted'))
);
```

Optional later tables:

- `geosocial_comments`: post id, user id, body, provenance, created at.
- `geosocial_reactions`: post id, user id, reaction type, created at.

Keep comments and reactions as counts or placeholders for MVP unless product needs
write flows immediately.

## Instance 2 Integration Notes

The MVP frontend currently exposes `ClaimViewer` from:

- `frontend/src/components/ClaimViewer.jsx`
- `frontend/src/data/claimSocialMock.js`
- `frontend/src/services/claimSocialService.js`

For the 3D viewer, pass the selected mesh/tile payload into the same component
shape:

```js
{
  structure_id,
  tile_id,
  address,
  label,
  order_id,
  coordinates,
  trace_cost
}
```

If the GLB does not expose per-building ids yet, use `tile_id` plus a local mesh
index as a temporary `structure_id`, and write that limitation into
`structure_provenance`.

## API Handoff

Suggested read endpoints:

- `GET /claims/by-structure/:structure_id`
- `GET /geosocial/nearby?structure_id=...&tile_id=...`

Suggested write endpoints:

- Existing `create-claim` edge function for claim intent/finalization.
- Future `create-geosocial-post` edge function for text/media metadata only.

Media files should be uploaded to storage first; posts should store references,
not raw media blobs.

## Handoff Note

### Exactly Built

- `frontend/src/components/ClaimViewer.jsx` is the active MVP surface in the
  frontend app. It renders a selected structure panel, claim status, owner
  placeholder, Trace cost, charity allocation, claim button state, provenance,
  and nearby activity feed.
- `frontend/src/data/claimSocialMock.js` provides mock current user, structures,
  active claim state, and geosocial posts.
- `frontend/src/services/claimSocialService.js` provides local mock selectors:
  selected-structure snapshot, active-claim lookup, nearby-post filtering, local
  claim creation, and Trace formatting.
- `docs/CLAIM_VIEWER_GEOSOCIAL_NOTES.md` documents schema alignment and handoff
  expectations.

### Still Mock

- The claim button only creates local in-memory claim state. It does not call
  Supabase, Stripe, payment functions, or any settlement process.
- Nearby activity is mock data. Posts, media attachments, comments, reactions,
  visibility, and provenance are displayed as scaffolded fields only.
- Owner display is a placeholder derived from mock claim/user records.
- Charity allocation is displayed from mock `users.charity_allocation_percentage`;
  no reporting or settlement calculation is implemented.

### Instance 2 Requirements

To wire the viewer selection into `ClaimViewer`, pass the selected structure or
tile payload with these minimum fields:

```js
{
  structure_id: 'stable-building-or-structure-id',
  tile_id: 'source-tile-id',
  bbox: {
    min: [xMin, yMin, zMin],
    max: [xMax, yMax, zMax]
  },
  address: 'optional address string',
  label: 'optional display label',
  order_id: 'optional-order-id',
  coordinates: { lat, lng },
  trace_cost: 1
}
```

`structure_id`, `tile_id`, and `bbox` are the critical fields. `address`,
`label`, `order_id`, and `coordinates` can be null or approximate during MVP,
but should be recorded in provenance when uncertain.

### Instance 4 Requirements

For real persistence, Instance 4 should:

- Keep `claimed_structures` as the claim source of truth.
- Add a read path for claims by `structure_id`, not only claims owned by the
  current user.
- Implement `geosocial_posts` with anchors for `structure_id`, `tile_id`, or
  `coordinates`, plus `visibility`, `media`, and `provenance`.
- Add small read endpoints for nearby posts by structure/tile.
- Add write endpoint validation for visibility values:
  `public`, `private`, `friends`, `unlisted`.
- Store media references, not raw media blobs, in post rows.
- Keep reactions/comments optional or count-only until the MVP needs write flows.

### Stable Building ID Problem

The streamed GLB/mesh layer may not expose stable per-building IDs yet. Claims
cannot safely depend on transient mesh order alone, because mesh index can shift
when tiles are regenerated, optimized, or split.

Proposed MVP solution:

1. Generate a deterministic `structure_id` during tile build from stable source
   attributes when available: parcel id, footprint id, source feature id, or
   normalized address.
2. If source attributes are missing, derive a provisional id from
   `city + tile_id + quantized bbox centroid + quantized bbox size`.
3. Store the full derivation in `structure_provenance`, including `tile_id`,
   `bbox`, source dataset, build version, and whether the id is provisional.
4. When a stronger source id arrives later, write an explicit alias/migration
   table instead of silently changing existing `claimed_structures.structure_id`.

This keeps MVP claims readable now while preserving a migration path to durable
building identity.

## Commit Handoff - Claim Viewer MVP + GeoSocial Scaffold

### Exactly Built

- Public frontend MVP shell work exists in `viewer/src/App.jsx` and
  `viewer/src/App.css`: GlitchOS entry screen, Orders section, helm/map
  placeholder, and enter-world gate into the existing R3F viewer.
- City tile streaming scaffold exists in `viewer/src/components/CityScene.jsx`:
  the viewer fetches `/models/tile_manifest.json`, builds frustum entries from
  bbox-derived `cull_bounds`, sorts visible tiles by camera distance, and caps
  active streamed tiles at `MAX_STREAMED_TILES` / 10.
- Local Vite model middleware exists in `viewer/vite.config.js`: it serves the
  city/tile GLBs from `/mnt/t7` or `E:/`, emits a populated streaming manifest,
  supports range requests, and reports 108 Miami tiles with 108 GLBs,
  108 `bbox_4326` values, and 108 `cull_bounds`.
- Claim Viewer MVP scaffold exists in the frontend app through
  `frontend/src/components/ClaimViewer.jsx`,
  `frontend/src/data/claimSocialMock.js`, and
  `frontend/src/services/claimSocialService.js`.

### What Is Mock

- Claim creation is local/mock only. It does not persist to Supabase, does not
  call payment rails, and does not finalize ownership.
- GeoSocial posts/activity are mock records. Comments, reactions, visibility,
  media, and provenance are represented as product/data shape only.
- Any owner, Trace cost, charity allocation, or nearby activity shown in the MVP
  should be treated as UI/data contract scaffolding until Instance 4 wires real
  persistence.
- The landing helm/map is a placeholder when the real map layer is not ready.

### Instance 2 -> ClaimViewer Payload

When the R3F viewer opens `ClaimViewer`, pass the selected structure/tile using
this minimum shape:

```js
{
  structure_id: 'stable-or-provisional-building-id',
  tile_id: 'USGS_LPC_FL_MiamiDade_D23_LID2024_316646_0901',
  bbox: {
    min: [xMin, yMin, zMin],
    max: [xMax, yMax, zMax]
  },
  address: null,
  label: 'optional display label',
  order_id: null,
  coordinates: { lat, lng },
  trace_cost: 1,
  structure_provenance: {
    city_id: 'miami',
    source: 'viewer_tile_stream',
    id_strategy: 'source_id_or_quantized_bbox',
    provisional: true
  }
}
```

Critical fields for the claim/GeoSocial join are `structure_id`, `tile_id`, and
`bbox`. `coordinates`, `address`, `label`, `order_id`, and `trace_cost` can be
null or approximate for MVP, but uncertainty must be recorded in provenance.

### Instance 4 Persistence Work

- Persist claims in `claimed_structures` keyed by `structure_id`, with
  `tile_id`, `bbox`, and the ID derivation stored in `structure_provenance`.
- Add read endpoints for claim state by `structure_id` and nearby activity by
  `structure_id`/`tile_id`.
- Implement `geosocial_posts` with anchors for `structure_id`, `tile_id`, or
  coordinates; include `visibility`, `media`, `provenance`, timestamps, and
  user ownership.
- Validate writes server-side. Visibility should stay constrained to `public`,
  `private`, `friends`, and `unlisted`.
- Store media as storage references/metadata, not raw blobs in the post row.
- Keep comments/reactions optional or count-only until product requires write
  flows.

### Stable Building ID Problem

The current streamed GLB flow can identify tiles reliably, but per-building
identity is not durable unless the export embeds stable source IDs. Mesh order,
draw order, and generated geometry indexes can change after rebuilds, tile
splits, simplification, or exporter changes. A claim tied only to mesh index can
silently point at the wrong building later.

Proposed solution:

1. Prefer source IDs embedded during tile export: parcel id, footprint id,
   source feature id, normalized address id, or another stable upstream key.
2. If no source ID exists, generate a provisional deterministic ID from
   `city_id + tile_id + quantized bbox centroid + quantized bbox size`.
3. Store the full `bbox`, `tile_id`, source dataset, pipeline build version, and
   `id_strategy` in `structure_provenance`.
4. Add a future `structure_id_aliases` or migration table so provisional IDs can
   map to stronger source IDs without rewriting historical claims in place.
