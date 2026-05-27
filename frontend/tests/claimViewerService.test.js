import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildSupabaseFunctionUrl,
  getClaimViewerSnapshot,
  loadClaimViewerSnapshot,
  submitStructureClaim,
} from '../src/services/claimSocialService.js'

test('buildSupabaseFunctionUrl normalizes trailing slashes and query params', () => {
  const url = buildSupabaseFunctionUrl(
    'https://demo.supabase.co/',
    'create-claim',
    { structure_id: 'mia_struct_00041' },
  )

  assert.equal(
    url,
    'https://demo.supabase.co/functions/v1/create-claim?structure_id=mia_struct_00041',
  )
})

test('loadClaimViewerSnapshot falls back to mock state when Supabase config is missing', async () => {
  const result = await loadClaimViewerSnapshot({
    selectedStructureId: 'mia_struct_00077',
    env: {},
    fetchImpl: async () => {
      throw new Error('should not be called')
    },
  })

  assert.equal(result.source, 'mock')
  assert.equal(result.snapshot.selectedStructure.structure_id, 'mia_struct_00077')
})

test('loadClaimViewerSnapshot falls back to mock state when the Edge Function request fails', async () => {
  const result = await loadClaimViewerSnapshot({
    selectedStructureId: 'mia_struct_00041',
    env: {
      VITE_SUPABASE_URL: 'https://demo.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'anon-test-key',
      VITE_SUPABASE_ACCESS_TOKEN: 'access-token',
    },
    fetchImpl: async () => {
      throw new Error('offline')
    },
  })

  assert.equal(result.source, 'mock')
  assert.ok(result.error.includes('offline'))
  assert.equal(result.snapshot.selectedStructure.structure_id, 'mia_struct_00041')
})

test('submitStructureClaim sends the selected structure payload to create-claim', async () => {
  const fallback = getClaimViewerSnapshot('mia_struct_00041')
  let calledUrl = null
  let calledOptions = null

  const result = await submitStructureClaim({
    structure: fallback.selectedStructure,
    currentUser: fallback.currentUser,
    env: {
      VITE_SUPABASE_URL: 'https://demo.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'anon-test-key',
      VITE_SUPABASE_ACCESS_TOKEN: 'access-token',
    },
    fetchImpl: async (url, options) => {
      calledUrl = url
      calledOptions = options

      return {
        ok: true,
        status: 201,
        text: async () =>
          JSON.stringify({
            claim: {
              id: 'claim_001',
              user_id: fallback.currentUser.id,
              owner_display_name: fallback.currentUser.display_name,
              structure_id: fallback.selectedStructure.structure_id,
              claim_status: 'active',
              claim_cost_trace: 1,
              structure_provenance: { source: 'claim_viewer' },
              claimed_at: '2026-05-27T18:00:00Z',
              released_at: null,
            },
          }),
      }
    },
  })

  assert.equal(calledUrl, 'https://demo.supabase.co/functions/v1/create-claim')
  assert.equal(calledOptions.method, 'POST')
  assert.equal(calledOptions.headers.Authorization, 'Bearer access-token')

  const payload = JSON.parse(calledOptions.body)
  assert.equal(payload.structure_id, 'mia_struct_00041')
  assert.equal(payload.tile_id, 'miami_hero_tile_v001')
  assert.equal(result.source, 'remote')
  assert.equal(result.claim.id, 'claim_001')
})
