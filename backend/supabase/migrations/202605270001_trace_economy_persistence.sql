create extension if not exists pgcrypto;

create table if not exists public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  charity_allocation_percentage numeric(5,2) not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint users_charity_allocation_range
    check (charity_allocation_percentage >= 0 and charity_allocation_percentage <= 50)
);

create table if not exists public.orders (
  id text primary key,
  name text not null,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.structures (
  id text primary key,
  tile_id text,
  address text,
  label text,
  latitude double precision,
  longitude double precision,
  trace_cost numeric(14,2) not null default 1,
  source text not null default 'pipeline',
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint structures_trace_cost_non_negative
    check (trace_cost >= 0),
  constraint structures_latitude_range
    check (latitude is null or (latitude >= -90 and latitude <= 90)),
  constraint structures_longitude_range
    check (longitude is null or (longitude >= -180 and longitude <= 180))
);

create table if not exists public.trace_balances (
  user_id uuid primary key references public.users(id) on delete cascade,
  available_trace numeric(14,2) not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint trace_balances_non_negative
    check (available_trace >= 0)
);

create table if not exists public.trace_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  amount_trace numeric(14,2) not null,
  transaction_type text not null,
  source text not null,
  provenance jsonb not null,
  payment_rail text not null default 'fiat',
  payment_provider text,
  payment_provider_reference text,
  settlement_currency text not null default 'USD',
  settlement_amount numeric(14,2),
  status text not null default 'posted',
  created_at timestamptz not null default now(),
  constraint trace_transactions_non_zero_amount
    check (amount_trace <> 0),
  constraint trace_transactions_required_provenance
    check (jsonb_typeof(provenance) = 'object' and provenance <> '{}'::jsonb),
  constraint trace_transactions_payment_rail
    check (payment_rail in ('fiat', 'internal', 'future_external')),
  constraint trace_transactions_status
    check (status in ('pending', 'posted', 'voided')),
  constraint trace_transactions_settlement_amount
    check (settlement_amount is null or settlement_amount >= 0)
);

create table if not exists public.claimed_structures (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  structure_id text not null references public.structures(id) on delete restrict,
  order_id text references public.orders(id),
  transaction_id uuid references public.trace_transactions(id),
  claim_status text not null default 'active',
  claim_cost_trace numeric(14,2) not null default 1,
  structure_provenance jsonb not null default '{}'::jsonb,
  claimed_at timestamptz not null default now(),
  released_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint claimed_structures_cost_non_negative
    check (claim_cost_trace >= 0),
  constraint claimed_structures_status
    check (claim_status in ('active', 'released', 'revoked')),
  constraint claimed_structures_release_timestamp
    check ((claim_status = 'active' and released_at is null) or (claim_status <> 'active'))
);

create unique index if not exists claimed_structures_one_active_claim_per_structure
  on public.claimed_structures (structure_id)
  where claim_status = 'active';

create index if not exists claimed_structures_user_id_idx
  on public.claimed_structures (user_id);

create index if not exists claimed_structures_structure_id_idx
  on public.claimed_structures (structure_id);

create table if not exists public.claim_history (
  id uuid primary key default gen_random_uuid(),
  claim_id uuid not null references public.claimed_structures(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  structure_id text not null references public.structures(id) on delete restrict,
  previous_status text,
  new_status text not null,
  event_type text not null,
  transaction_id uuid references public.trace_transactions(id),
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint claim_history_event_type
    check (event_type in ('created', 'status_changed', 'released', 'revoked'))
);

create index if not exists claim_history_claim_id_idx
  on public.claim_history (claim_id, created_at desc);

create index if not exists claim_history_structure_id_idx
  on public.claim_history (structure_id, created_at desc);

create table if not exists public.geosocial_posts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  structure_id text references public.structures(id) on delete set null,
  tile_id text,
  latitude double precision,
  longitude double precision,
  body text not null,
  visibility text not null default 'public',
  media jsonb not null default '[]'::jsonb,
  reactions jsonb not null default '{}'::jsonb,
  comments_count integer not null default 0,
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint geosocial_posts_body_not_blank
    check (length(trim(body)) > 0),
  constraint geosocial_posts_visibility
    check (visibility in ('public', 'unlisted', 'friends', 'private')),
  constraint geosocial_posts_media_array
    check (jsonb_typeof(media) = 'array'),
  constraint geosocial_posts_reactions_object
    check (jsonb_typeof(reactions) = 'object'),
  constraint geosocial_posts_comments_non_negative
    check (comments_count >= 0),
  constraint geosocial_posts_latitude_range
    check (latitude is null or (latitude >= -90 and latitude <= 90)),
  constraint geosocial_posts_longitude_range
    check (longitude is null or (longitude >= -180 and longitude <= 180)),
  constraint geosocial_posts_has_location_anchor
    check (structure_id is not null or tile_id is not null or (latitude is not null and longitude is not null))
);

create index if not exists geosocial_posts_structure_id_idx
  on public.geosocial_posts (structure_id, created_at desc);

create index if not exists geosocial_posts_tile_id_idx
  on public.geosocial_posts (tile_id, created_at desc);

create or replace view public.structure_claim_status as
select
  s.id as structure_id,
  s.tile_id,
  s.address,
  s.label,
  s.latitude,
  s.longitude,
  s.trace_cost,
  s.source,
  s.provenance as structure_provenance,
  c.id as claim_id,
  c.user_id as owner_user_id,
  u.display_name as owner_display_name,
  c.order_id,
  c.claim_status,
  c.claim_cost_trace,
  c.claimed_at,
  c.released_at
from public.structures s
left join public.claimed_structures c
  on c.structure_id = s.id
 and c.claim_status = 'active'
left join public.users u
  on u.id = c.user_id;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists users_set_updated_at on public.users;
create trigger users_set_updated_at
before update on public.users
for each row execute function public.set_updated_at();

drop trigger if exists orders_set_updated_at on public.orders;
create trigger orders_set_updated_at
before update on public.orders
for each row execute function public.set_updated_at();

drop trigger if exists structures_set_updated_at on public.structures;
create trigger structures_set_updated_at
before update on public.structures
for each row execute function public.set_updated_at();

drop trigger if exists trace_balances_set_updated_at on public.trace_balances;
create trigger trace_balances_set_updated_at
before update on public.trace_balances
for each row execute function public.set_updated_at();

drop trigger if exists claimed_structures_set_updated_at on public.claimed_structures;
create trigger claimed_structures_set_updated_at
before update on public.claimed_structures
for each row execute function public.set_updated_at();

drop trigger if exists geosocial_posts_set_updated_at on public.geosocial_posts;
create trigger geosocial_posts_set_updated_at
before update on public.geosocial_posts
for each row execute function public.set_updated_at();

create or replace function public.record_claim_history()
returns trigger
language plpgsql
as $$
declare
  v_event_type text;
begin
  if tg_op = 'INSERT' then
    v_event_type := 'created';
  elsif old.claim_status is distinct from new.claim_status then
    v_event_type := case new.claim_status
      when 'released' then 'released'
      when 'revoked' then 'revoked'
      else 'status_changed'
    end;
  else
    return new;
  end if;

  insert into public.claim_history (
    claim_id,
    user_id,
    structure_id,
    previous_status,
    new_status,
    event_type,
    transaction_id,
    provenance
  )
  values (
    new.id,
    new.user_id,
    new.structure_id,
    case when tg_op = 'INSERT' then null else old.claim_status end,
    new.claim_status,
    v_event_type,
    new.transaction_id,
    new.structure_provenance
  );

  return new;
end;
$$;

drop trigger if exists claimed_structures_record_history on public.claimed_structures;
create trigger claimed_structures_record_history
after insert or update on public.claimed_structures
for each row execute function public.record_claim_history();

create or replace function public.create_trace_transaction(
  p_user_id uuid,
  p_amount_trace numeric,
  p_transaction_type text,
  p_source text,
  p_provenance jsonb,
  p_payment_rail text default 'fiat',
  p_payment_provider text default null,
  p_payment_provider_reference text default null,
  p_settlement_currency text default 'USD',
  p_settlement_amount numeric default null
)
returns public.trace_transactions
language plpgsql
security definer
set search_path = public
as $$
declare
  v_transaction public.trace_transactions;
  v_balance numeric(14,2);
begin
  if p_amount_trace = 0 then
    raise exception 'Trace transaction amount must be non-zero';
  end if;

  if p_transaction_type is null or length(trim(p_transaction_type)) = 0 then
    raise exception 'Trace transaction type is required';
  end if;

  if p_source is null or length(trim(p_source)) = 0 then
    raise exception 'Trace transaction source is required';
  end if;

  if p_provenance is null or jsonb_typeof(p_provenance) <> 'object' or p_provenance = '{}'::jsonb then
    raise exception 'Trace transaction provenance is required';
  end if;

  insert into public.users (id)
  values (p_user_id)
  on conflict (id) do nothing;

  insert into public.trace_balances (user_id, available_trace)
  values (p_user_id, 0)
  on conflict (user_id) do nothing;

  select available_trace
  into v_balance
  from public.trace_balances
  where user_id = p_user_id
  for update;

  if v_balance + p_amount_trace < 0 then
    raise exception 'Insufficient Trace balance';
  end if;

  insert into public.trace_transactions (
    user_id,
    amount_trace,
    transaction_type,
    source,
    provenance,
    payment_rail,
    payment_provider,
    payment_provider_reference,
    settlement_currency,
    settlement_amount
  )
  values (
    p_user_id,
    p_amount_trace,
    trim(p_transaction_type),
    trim(p_source),
    p_provenance,
    coalesce(p_payment_rail, 'fiat'),
    p_payment_provider,
    p_payment_provider_reference,
    coalesce(p_settlement_currency, 'USD'),
    p_settlement_amount
  )
  returning * into v_transaction;

  update public.trace_balances
  set available_trace = available_trace + p_amount_trace
  where user_id = p_user_id;

  return v_transaction;
end;
$$;

create or replace function public.record_trace_transaction(
  p_user_id uuid,
  p_amount_trace numeric,
  p_transaction_type text,
  p_source text,
  p_provenance jsonb,
  p_payment_rail text default 'fiat',
  p_payment_provider text default null,
  p_payment_provider_reference text default null,
  p_settlement_currency text default 'USD',
  p_settlement_amount numeric default null
)
returns public.trace_transactions
language sql
security definer
set search_path = public
as $$
  select public.create_trace_transaction(
    p_user_id,
    p_amount_trace,
    p_transaction_type,
    p_source,
    p_provenance,
    p_payment_rail,
    p_payment_provider,
    p_payment_provider_reference,
    p_settlement_currency,
    p_settlement_amount
  );
$$;

create or replace function public.create_structure_claim(
  p_user_id uuid,
  p_structure_id text,
  p_order_id text default null,
  p_structure_provenance jsonb default '{}'::jsonb,
  p_tile_id text default null,
  p_address text default null,
  p_label text default null,
  p_latitude double precision default null,
  p_longitude double precision default null
)
returns public.claimed_structures
language plpgsql
security definer
set search_path = public
as $$
declare
  v_transaction public.trace_transactions;
  v_claim public.claimed_structures;
  v_trace_cost numeric(14,2);
begin
  if p_structure_id is null or length(trim(p_structure_id)) = 0 then
    raise exception 'Structure id is required';
  end if;

  if p_latitude is not null and (p_latitude < -90 or p_latitude > 90) then
    raise exception 'Latitude must be between -90 and 90';
  end if;

  if p_longitude is not null and (p_longitude < -180 or p_longitude > 180) then
    raise exception 'Longitude must be between -180 and 180';
  end if;

  insert into public.structures (
    id,
    tile_id,
    address,
    label,
    latitude,
    longitude,
    trace_cost,
    source,
    provenance
  )
  values (
    trim(p_structure_id),
    nullif(trim(coalesce(p_tile_id, '')), ''),
    nullif(trim(coalesce(p_address, '')), ''),
    nullif(trim(coalesce(p_label, '')), ''),
    p_latitude,
    p_longitude,
    1,
    coalesce(nullif(p_structure_provenance->>'source', ''), 'claim_api'),
    coalesce(p_structure_provenance, '{}'::jsonb)
  )
  on conflict (id) do update
  set
    tile_id = coalesce(excluded.tile_id, public.structures.tile_id),
    address = coalesce(excluded.address, public.structures.address),
    label = coalesce(excluded.label, public.structures.label),
    latitude = coalesce(excluded.latitude, public.structures.latitude),
    longitude = coalesce(excluded.longitude, public.structures.longitude),
    provenance = public.structures.provenance || excluded.provenance;

  select trace_cost
  into v_trace_cost
  from public.structures
  where id = trim(p_structure_id);

  v_transaction := public.create_trace_transaction(
    p_user_id,
    -v_trace_cost,
    'structure_claim',
    'trace_balance',
    jsonb_build_object(
      'structure_id', trim(p_structure_id),
      'order_id', p_order_id,
      'claim_cost_trace', v_trace_cost,
      'pricing_model', 'initial_1_trace_per_structure'
    ),
    'internal',
    null,
    null,
    'USD',
    null
  );

  insert into public.claimed_structures (
    user_id,
    structure_id,
    order_id,
    transaction_id,
    claim_cost_trace,
    structure_provenance
  )
  values (
    p_user_id,
    trim(p_structure_id),
    p_order_id,
    v_transaction.id,
    v_trace_cost,
    coalesce(p_structure_provenance, '{}'::jsonb)
  )
  returning * into v_claim;

  return v_claim;
exception
  when unique_violation then
    raise exception 'Structure already has an active claim';
end;
$$;

create or replace function public.create_geosocial_post(
  p_user_id uuid,
  p_body text,
  p_structure_id text default null,
  p_tile_id text default null,
  p_latitude double precision default null,
  p_longitude double precision default null,
  p_visibility text default 'public',
  p_media jsonb default '[]'::jsonb,
  p_provenance jsonb default '{}'::jsonb
)
returns public.geosocial_posts
language plpgsql
security definer
set search_path = public
as $$
declare
  v_post public.geosocial_posts;
begin
  if p_body is null or length(trim(p_body)) = 0 then
    raise exception 'Post body is required';
  end if;

  if p_structure_id is null and p_tile_id is null and (p_latitude is null or p_longitude is null) then
    raise exception 'Post requires a structure_id, tile_id, or coordinates';
  end if;

  if p_visibility not in ('public', 'unlisted', 'friends', 'private') then
    raise exception 'Invalid post visibility';
  end if;

  if p_latitude is not null and (p_latitude < -90 or p_latitude > 90) then
    raise exception 'Latitude must be between -90 and 90';
  end if;

  if p_longitude is not null and (p_longitude < -180 or p_longitude > 180) then
    raise exception 'Longitude must be between -180 and 180';
  end if;

  insert into public.users (id)
  values (p_user_id)
  on conflict (id) do nothing;

  if p_structure_id is not null and length(trim(p_structure_id)) > 0 then
    insert into public.structures (
      id,
      tile_id,
      latitude,
      longitude,
      source,
      provenance
    )
    values (
      trim(p_structure_id),
      nullif(trim(coalesce(p_tile_id, '')), ''),
      p_latitude,
      p_longitude,
      'social_api',
      jsonb_build_object('source', 'social_api_placeholder')
    )
    on conflict (id) do update
    set
      tile_id = coalesce(excluded.tile_id, public.structures.tile_id),
      latitude = coalesce(excluded.latitude, public.structures.latitude),
      longitude = coalesce(excluded.longitude, public.structures.longitude),
      provenance = public.structures.provenance || excluded.provenance;
  end if;

  insert into public.geosocial_posts (
    user_id,
    body,
    structure_id,
    tile_id,
    latitude,
    longitude,
    visibility,
    media,
    provenance
  )
  values (
    p_user_id,
    trim(p_body),
    nullif(trim(coalesce(p_structure_id, '')), ''),
    nullif(trim(coalesce(p_tile_id, '')), ''),
    p_latitude,
    p_longitude,
    p_visibility,
    coalesce(p_media, '[]'::jsonb),
    coalesce(p_provenance, '{}'::jsonb)
  )
  returning * into v_post;

  return v_post;
end;
$$;

revoke execute on function public.create_trace_transaction(
  uuid,
  numeric,
  text,
  text,
  jsonb,
  text,
  text,
  text,
  text,
  numeric
) from public, anon, authenticated;

revoke execute on function public.record_trace_transaction(
  uuid,
  numeric,
  text,
  text,
  jsonb,
  text,
  text,
  text,
  text,
  numeric
) from public, anon, authenticated;

revoke execute on function public.create_structure_claim(
  uuid,
  text,
  text,
  jsonb,
  text,
  text,
  text,
  double precision,
  double precision
) from public, anon, authenticated;

revoke execute on function public.create_geosocial_post(
  uuid,
  text,
  text,
  text,
  double precision,
  double precision,
  text,
  jsonb,
  jsonb
) from public, anon, authenticated;

grant execute on function public.create_trace_transaction(
  uuid,
  numeric,
  text,
  text,
  jsonb,
  text,
  text,
  text,
  text,
  numeric
) to service_role;

grant execute on function public.record_trace_transaction(
  uuid,
  numeric,
  text,
  text,
  jsonb,
  text,
  text,
  text,
  text,
  numeric
) to service_role;

grant execute on function public.create_structure_claim(
  uuid,
  text,
  text,
  jsonb,
  text,
  text,
  text,
  double precision,
  double precision
) to service_role;

grant execute on function public.create_geosocial_post(
  uuid,
  text,
  text,
  text,
  double precision,
  double precision,
  text,
  jsonb,
  jsonb
) to service_role;

alter table public.users enable row level security;
alter table public.orders enable row level security;
alter table public.structures enable row level security;
alter table public.trace_balances enable row level security;
alter table public.trace_transactions enable row level security;
alter table public.claimed_structures enable row level security;
alter table public.claim_history enable row level security;
alter table public.geosocial_posts enable row level security;

drop policy if exists "Users can read own profile" on public.users;
create policy "Users can read own profile"
on public.users for select
using (auth.uid() = id);

drop policy if exists "Users can update own charity allocation" on public.users;
create policy "Users can update own charity allocation"
on public.users for update
using (auth.uid() = id)
with check (auth.uid() = id);

drop policy if exists "Orders are readable" on public.orders;
create policy "Orders are readable"
on public.orders for select
using (true);

drop policy if exists "Structures are readable" on public.structures;
create policy "Structures are readable"
on public.structures for select
using (true);

drop policy if exists "Users can read own Trace balance" on public.trace_balances;
create policy "Users can read own Trace balance"
on public.trace_balances for select
using (auth.uid() = user_id);

drop policy if exists "Users can read own Trace transactions" on public.trace_transactions;
create policy "Users can read own Trace transactions"
on public.trace_transactions for select
using (auth.uid() = user_id);

drop policy if exists "Claim status is readable" on public.claimed_structures;
create policy "Claim status is readable"
on public.claimed_structures for select
using (true);

drop policy if exists "Claim history is readable for own claims" on public.claim_history;
create policy "Claim history is readable for own claims"
on public.claim_history for select
using (auth.uid() = user_id);

drop policy if exists "Visible geosocial posts are readable" on public.geosocial_posts;
create policy "Visible geosocial posts are readable"
on public.geosocial_posts for select
using (
  visibility in ('public', 'unlisted')
  or auth.uid() = user_id
);
