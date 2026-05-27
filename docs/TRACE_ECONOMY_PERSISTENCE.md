# Trace Economy Persistence Scaffold

## Backend Target

The project now has a Supabase/Postgres scaffold under `backend/supabase`.

This is fiat-compliant first:

- `$1 = 1 Trace`
- Initial structure claim cost is `1 Trace`
- Charity allocation is stored as a user preference capped at `0-50%`
- No Stripe/payment fulfillment is implemented here
- Crypto/token rails are not implemented; `future_external` is only a reserved ledger rail

## Tables

- `users`: app profile linked to `auth.users`, with `charity_allocation_percentage`
- `orders`: optional order metadata keyed by stable text ids
- `structures`: real city structure records from pipeline/address imports, keyed by `structure_id`
- `trace_balances`: current available Trace per user
- `trace_transactions`: append-only Trace ledger entries with `transaction_type`, `amount_trace`, `source`, `provenance`, `created_at`, and `user_id`
- `claimed_structures`: active/released/revoked structure claims
- `claim_history`: status history for claims
- `geosocial_posts`: lightweight posts tied to `structure_id`, `tile_id`, or coordinates

The `claimed_structures_one_active_claim_per_structure` partial unique index prevents duplicate active claims for the same structure.

## Views

`structure_claim_status` gives the frontend a claim-viewer friendly shape:

- `structure_id`
- `tile_id`
- `address`
- `label`
- `latitude`
- `longitude`
- `trace_cost`
- `claim_id`
- `owner_user_id`
- `owner_display_name`
- `order_id`
- `claim_status`
- `claim_cost_trace`
- `claimed_at`
- `released_at`

## Edge Functions

All functions expect an authenticated Supabase request.

### `create-claim`

`POST /functions/v1/create-claim`

Request:

```json
{
  "structure_id": "mia_struct_00041",
  "tile_id": "miami_hero_tile_v001",
  "address": "101 Biscayne Blvd",
  "label": "Bayfront edge structure",
  "order_id": "signal-choir",
  "coordinates": { "lat": 25.7752, "lng": -80.1868 },
  "structure_provenance": { "source": "pipeline" }
}
```

Response:

```json
{ "claim": { "id": "...", "structure_id": "mia_struct_00041", "claim_status": "active" } }
```

Behavior:

- Upserts a minimal `structures` row if pipeline data is not present yet
- Debits the user by the structure `trace_cost`
- Inserts a Trace transaction
- Inserts a claim history row
- Fails if the user has insufficient Trace
- Fails if another active claim exists for the structure

### `get-user-balance`

`GET /functions/v1/get-user-balance`

Response:

```json
{
  "user_id": "...",
  "available_trace": 24,
  "updated_at": "2026-05-27T15:28:00Z"
}
```

### `list-claimed-structures`

`GET /functions/v1/list-claimed-structures`

Returns the authenticated user's active/released/revoked claims using the `structure_claim_status` shape.

### `get-structure-social-state`

`GET /functions/v1/get-structure-social-state?structure_id=mia_struct_00041`

or

`GET /functions/v1/get-structure-social-state?tile_id=miami_hero_tile_v001`

Response:

```json
{
  "structures": [],
  "selected_structure": null,
  "nearby_posts": [],
  "claim_history": []
}
```

Use this as the backend replacement for `getClaimViewerSnapshot`.

### `create-geosocial-post`

`POST /functions/v1/create-geosocial-post`

Request:

```json
{
  "body": "Claim marker is readable from the bay side.",
  "visibility": "public",
  "structure_id": "mia_struct_00041",
  "tile_id": "miami_hero_tile_v001",
  "coordinates": { "lat": 25.7752, "lng": -80.1868 },
  "media": [],
  "provenance": { "source": "claim_viewer" }
}
```

`structure_id`, `tile_id`, or coordinates are required.

### `create-transaction-record`

Internal/admin scaffold for crediting or debiting Trace through the ledger RPC. It requires non-zero `amount_trace`, `transaction_type`, `source`, and non-empty `provenance`.

This route also requires `TRACE_ADMIN_API_KEY` in the function environment and a matching `x-trace-admin-key` request header. It is not a user-facing purchase endpoint.

### `update-charity-allocation`

`PATCH /functions/v1/update-charity-allocation`

Request:

```json
{ "charity_allocation_percentage": 12 }
```

Values below `0` or above `50` are rejected by both the Edge Function and database constraint.

## Frontend Integration Notes

The current frontend mock shape maps directly:

- `structure.structure_id` maps to `structures.id` / `structure_claim_status.structure_id`
- `structure.trace_cost` maps to `trace_cost`
- `claim.owner_display_name` maps to `owner_display_name`
- post `coordinates.lat/lng` maps to `latitude` / `longitude`
- `nearby_posts` comes from `geosocial_posts`

Coordinate with Instance 1 so pipeline/address import writes stable `structures.id`, `tile_id`, `address`, `label`, `latitude`, `longitude`, and provenance.

## Stripe TODO

- Add Stripe checkout/payment intent creation only after product and fulfillment rules are finalized.
- Record Stripe ids in `trace_transactions.payment_provider = 'stripe'` and `payment_provider_reference`.
- Convert completed fiat payments into positive Trace ledger entries through `create_trace_transaction`.
- Add webhook verification and idempotency before crediting Trace.
- Decide whether charity allocation is calculated at purchase time, claim time, or settlement/reporting time.
- Add reconciliation reports for fiat received, Trace credited, Trace spent, and charity allocation totals.
