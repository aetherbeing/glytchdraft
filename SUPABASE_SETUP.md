# Supabase Setup

This repo uses Supabase/Postgres as the first persistence layer for Trace Economy, structure ownership, and geosocial state.

## 1. Create the Supabase Project

Create a new Supabase project in the Supabase dashboard. Use a standard Postgres database and keep the default auth provider unless your broader app already requires something else.

The scaffold assumes:

- `auth.users` exists and user profiles link to it
- Postgres extensions can be enabled
- Edge Functions are deployed from `backend/supabase/functions`

## 2. Apply the Migration

Apply the SQL migration in `backend/supabase/migrations/202605270001_trace_economy_persistence.sql`.

In practice, that means either:

1. Running the migration through the Supabase CLI against your project, or
2. Copying the SQL into the Supabase SQL editor for the initial bootstrap, then keeping future changes as migrations

The migration creates:

- `users`
- `structures`
- `trace_balances`
- `trace_transactions`
- `claimed_structures`
- `claim_history`
- `geosocial_posts`
- `structure_claim_status`

It also creates the RPCs used by the app:

- `create_structure_claim`
- `record_trace_transaction`
- `create_geosocial_post`

## 3. Deploy Edge Functions

Deploy the functions from `backend/supabase/functions` as Supabase Edge Functions.

Relevant endpoints:

- `create-claim`
- `get-user-balance`
- `list-claimed-structures`
- `get-structure-social-state`
- `create-geosocial-post`
- `update-charity-allocation`
- `create-transaction-record`

The function wrappers are thin. They validate request shape, then call the SQL RPCs for safe persistence.

## 4. Required Environment Variables / Secrets

Set these for the Edge Functions:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `TRACE_ADMIN_API_KEY`

The first three are needed for auth and server-side database access. `TRACE_ADMIN_API_KEY` gates the internal transaction-recording route so user-facing code cannot mint Trace directly.

For frontend integration, expose only the public client values used by your frontend build system. Do not ship the service role key to the browser.

## 5. Local Development Assumptions

This scaffold assumes:

- Trace is fiat-first
- `$1 = 1 Trace`
- One Trace initially claims one structure
- Charity allocation is a user preference between `0` and `50`
- Crypto is intentionally deferred
- Stripe is intentionally deferred
- AI companions and ritual logic are intentionally out of scope

If the Supabase project is not yet connected, the frontend may keep using its mock claim/social service until the real endpoints are wired in.

## 6. Frontend Connection

The ClaimViewer can switch from mock data to `get-structure-social-state` with the same identifiers it already uses:

- `structure_id`
- `tile_id`
- `address`
- `label`
- `trace_cost`
- `claimed_at`
- `released_at`
- nearby posts tied to `structure_id`, `tile_id`, or coordinates

Recommended flow:

1. Load the selected structure from `get-structure-social-state`
2. Render the returned `selected_structure` and `nearby_posts`
3. Call `create-claim` when the user claims a structure
4. Call `update-charity-allocation` from the user settings panel
5. Call `get-user-balance` to keep the Trace balance live after refresh

The data model is designed so claim state and geosocial posts persist across refreshes without requiring the frontend to rebuild local state.

## 7. Out of Scope

Not implemented here:

- Stripe/payment processing
- crypto/tokenomics
- AI companion or ritual logic

Those can be layered on later without changing the core persistence model.
