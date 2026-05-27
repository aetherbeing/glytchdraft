import {
  MOCK_CLAIMS,
  MOCK_CURRENT_USER,
  MOCK_GEOSOCIAL_POSTS,
  MOCK_STRUCTURES,
} from '../data/claimSocialMock.js'

const ACCESS_TOKEN_STORAGE_KEY = 'glytchdraft.supabase.access_token'

function resolveEnv(env) {
  if (env) return env

  if (typeof import.meta !== 'undefined' && import.meta.env) {
    return import.meta.env
  }

  return {}
}

function resolveStorage(storage) {
  if (storage) return storage
  if (typeof globalThis !== 'undefined' && globalThis.localStorage) return globalThis.localStorage
  return null
}

function trimEnvValue(value) {
  return typeof value === 'string' ? value.trim() : ''
}

export function getSupabaseConfig(env) {
  const runtimeEnv = resolveEnv(env)
  const url = trimEnvValue(runtimeEnv.VITE_SUPABASE_URL)
  const anonKey = trimEnvValue(runtimeEnv.VITE_SUPABASE_ANON_KEY)
  const accessToken = trimEnvValue(runtimeEnv.VITE_SUPABASE_ACCESS_TOKEN)

  return {
    url,
    anonKey,
    accessToken,
    enabled: Boolean(url && anonKey),
  }
}

export function hasSupabaseClaimingEnabled(env) {
  return getSupabaseConfig(env).enabled
}

export function buildSupabaseFunctionUrl(baseUrl, functionName, query = {}) {
  const url = new URL(
    `/functions/v1/${functionName}`,
    String(baseUrl).replace(/\/+$/, '') + '/',
  )

  Object.entries(query).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') return
    url.searchParams.set(key, String(value))
  })

  return url.toString()
}

function readStoredAccessToken(storage) {
  const runtimeStorage = resolveStorage(storage)

  if (!runtimeStorage) return ''

  try {
    return trimEnvValue(runtimeStorage.getItem(ACCESS_TOKEN_STORAGE_KEY))
  } catch {
    return ''
  }
}

function getAccessToken(env, storage) {
  const runtimeEnv = resolveEnv(env)
  const envToken = trimEnvValue(runtimeEnv.VITE_SUPABASE_ACCESS_TOKEN)

  return envToken || readStoredAccessToken(storage)
}

async function requestSupabaseFunction({
  baseUrl,
  functionName,
  query,
  method = 'GET',
  body,
  accessToken,
  fetchImpl = globalThis.fetch,
}) {
  const response = await fetchImpl(buildSupabaseFunctionUrl(baseUrl, functionName, query), {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  let payload = null
  const rawText = await response.text()

  if (rawText) {
    try {
      payload = JSON.parse(rawText)
    } catch {
      payload = { raw: rawText }
    }
  }

  if (!response.ok) {
    throw new Error(payload?.error ?? `Request to ${functionName} failed with ${response.status}`)
  }

  return payload ?? {}
}

function mapRemoteStructure(row) {
  return {
    structure_id: row.structure_id,
    tile_id: row.tile_id ?? null,
    address: row.address ?? null,
    label: row.label ?? row.address ?? row.structure_id,
    order_id: row.order_id ?? null,
    coordinates:
      row.latitude !== null && row.longitude !== null
        ? { lat: Number(row.latitude), lng: Number(row.longitude) }
        : null,
    trace_cost: Number(row.trace_cost ?? row.claim_cost_trace ?? 1),
    claim_id: row.claim_id ?? null,
    owner_user_id: row.owner_user_id ?? null,
    owner_display_name: row.owner_display_name ?? null,
    claim_status: row.claim_status ?? 'unclaimed',
    claim_cost_trace: Number(row.claim_cost_trace ?? row.trace_cost ?? 1),
    structure_provenance: row.structure_provenance ?? {},
    claimed_at: row.claimed_at ?? null,
    released_at: row.released_at ?? null,
    source: row.source ?? 'supabase',
  }
}

function mapRemoteClaim(row) {
  if (!row || !row.claim_status || row.claim_status === 'unclaimed') {
    return null
  }

  return {
    id: row.claim_id ?? `${row.structure_id}_claim`,
    user_id: row.owner_user_id,
    owner_display_name: row.owner_display_name ?? 'Unknown owner',
    structure_id: row.structure_id,
    order_id: row.order_id ?? null,
    claim_status: row.claim_status,
    claim_cost_trace: Number(row.claim_cost_trace ?? row.trace_cost ?? 1),
    structure_provenance: row.structure_provenance ?? {},
    claimed_at: row.claimed_at ?? null,
    released_at: row.released_at ?? null,
  }
}

function mapRemotePost(post, currentUser) {
  return {
    id: post.id,
    author: {
      user_id: post.user_id,
      display_name:
        post.user_id === currentUser.id ? currentUser.display_name : post.provenance?.author_display_name ?? post.user_id,
    },
    body: post.body,
    visibility: post.visibility,
    structure_id: post.structure_id ?? null,
    tile_id: post.tile_id ?? null,
    coordinates:
      post.latitude !== null && post.longitude !== null
        ? { lat: Number(post.latitude), lng: Number(post.longitude) }
        : null,
    media: Array.isArray(post.media) ? post.media : [],
    reactions: post.reactions && typeof post.reactions === 'object' ? post.reactions : {},
    comments_count: Number(post.comments_count ?? 0),
    provenance: post.provenance ?? {},
    created_at: post.created_at,
  }
}

function normalizeRemoteSnapshot(remote, selectedStructureId, fallbackSnapshot) {
  const structures = Array.isArray(remote?.structures) ? remote.structures.map(mapRemoteStructure) : []
  const remoteSelectedStructure = remote?.selected_structure ? mapRemoteStructure(remote.selected_structure) : null
  const selectedStructure =
    structures.find((structure) => structure.structure_id === selectedStructureId) ??
    remoteSelectedStructure ??
    structures[0] ??
    fallbackSnapshot.selectedStructure

  if (!structures.length || !selectedStructure) {
    return fallbackSnapshot
  }

  const claim = mapRemoteClaim(selectedStructure)
  const nearbyPosts = Array.isArray(remote?.nearby_posts)
    ? remote.nearby_posts.map((post) => mapRemotePost(post, fallbackSnapshot.currentUser))
    : fallbackSnapshot.nearbyPosts

  return {
    ...fallbackSnapshot,
    structures,
    selectedStructure,
    claim,
    nearbyPosts,
    claimHistory: Array.isArray(remote?.claim_history) ? remote.claim_history : [],
    currentUser: {
      ...fallbackSnapshot.currentUser,
      available_trace:
        Number.isFinite(Number(remote?.available_trace)) || remote?.available_trace === 0
          ? Number(remote.available_trace)
          : fallbackSnapshot.currentUser.available_trace,
    },
    source: 'remote',
  }
}

export function getClaimViewerSnapshot(selectedStructureId = MOCK_STRUCTURES[0].structure_id) {
  const structures = MOCK_STRUCTURES
  const selectedStructure =
    structures.find((structure) => structure.structure_id === selectedStructureId) ?? structures[0]
  const claim = getActiveClaimForStructure(selectedStructure.structure_id)
  const nearbyPosts = getNearbyPosts(selectedStructure)

  return {
    currentUser: { ...MOCK_CURRENT_USER },
    structures,
    selectedStructure,
    claim,
    nearbyPosts,
    claimHistory: [],
    source: 'mock',
  }
}

export function getActiveClaimForStructure(structureId) {
  return (
    MOCK_CLAIMS.find(
      (claim) => claim.structure_id === structureId && claim.claim_status === 'active',
    ) ?? null
  )
}

export function getNearbyPosts(structure) {
  return MOCK_GEOSOCIAL_POSTS.filter(
    (post) => post.structure_id === structure.structure_id || post.tile_id === structure.tile_id,
  ).sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
}

export function createMockClaim(structure, currentUser) {
  return {
    id: `claim_local_${structure.structure_id}`,
    user_id: currentUser.id,
    owner_display_name: currentUser.display_name,
    structure_id: structure.structure_id,
    order_id: structure.order_id,
    claim_status: 'active',
    claim_cost_trace: structure.trace_cost,
    structure_provenance: {
      source: 'frontend_mock',
      tile_id: structure.tile_id,
      selected_from: 'claim_viewer',
    },
    claimed_at: new Date().toISOString(),
    released_at: null,
  }
}

export async function loadClaimViewerSnapshot({
  selectedStructureId = MOCK_STRUCTURES[0].structure_id,
  env,
  storage,
  fetchImpl = globalThis.fetch,
  fallbackSnapshot = getClaimViewerSnapshot(selectedStructureId),
} = {}) {
  const config = getSupabaseConfig(env)

  if (!config.enabled) {
    return { snapshot: fallbackSnapshot, source: 'mock', error: null }
  }

  const accessToken = getAccessToken(env, storage)
  if (!accessToken) {
    return { snapshot: fallbackSnapshot, source: 'mock', error: null, reason: 'missing_access_token' }
  }

  try {
    const [structureState, balanceState] = await Promise.all([
      requestSupabaseFunction({
        baseUrl: config.url,
        functionName: 'get-structure-social-state',
        method: 'GET',
        query: { structure_id: selectedStructureId },
        accessToken,
        fetchImpl,
      }),
      requestSupabaseFunction({
        baseUrl: config.url,
        functionName: 'get-user-balance',
        method: 'GET',
        accessToken,
        fetchImpl,
      }),
    ])

    const normalized = normalizeRemoteSnapshot(structureState, selectedStructureId, fallbackSnapshot)

    return {
      snapshot: {
        ...normalized,
        currentUser: {
          ...normalized.currentUser,
          available_trace:
            balanceState?.available_trace !== undefined
              ? Number(balanceState.available_trace)
              : normalized.currentUser.available_trace,
        },
      },
      source: 'remote',
      error: null,
    }
  } catch (error) {
    return {
      snapshot: fallbackSnapshot,
      source: 'mock',
      error: error instanceof Error ? error.message : 'Failed to load Supabase claim state',
    }
  }
}

export async function submitStructureClaim({
  structure,
  currentUser,
  env,
  storage,
  fetchImpl = globalThis.fetch,
} = {}) {
  const config = getSupabaseConfig(env)
  const fallbackClaim = createMockClaim(structure, currentUser)

  if (!config.enabled) {
    return { claim: fallbackClaim, source: 'mock' }
  }

  const accessToken = getAccessToken(env, storage)
  if (!accessToken) {
    return { claim: fallbackClaim, source: 'mock', reason: 'missing_access_token' }
  }

  const response = await requestSupabaseFunction({
    baseUrl: config.url,
    functionName: 'create-claim',
    method: 'POST',
    accessToken,
    fetchImpl,
    body: {
      structure_id: structure.structure_id,
      tile_id: structure.tile_id ?? null,
      address: structure.address ?? null,
      label: structure.label ?? null,
      order_id: structure.order_id ?? null,
      coordinates: structure.coordinates ?? null,
      structure_provenance: {
        source: 'claim_viewer',
        tile_id: structure.tile_id ?? null,
        selected_from: 'claim_viewer',
      },
    },
  })

  if (!response?.claim) {
    throw new Error('Supabase claim response did not include claim data')
  }

  return {
    claim: {
      ...response.claim,
      owner_display_name: response.claim.owner_display_name ?? currentUser.display_name,
    },
    source: 'remote',
  }
}

export function formatTrace(value) {
  return `${Number(value).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })} Trace`
}
