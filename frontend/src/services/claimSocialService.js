import {
  MOCK_CLAIMS,
  MOCK_CURRENT_USER,
  MOCK_GEOSOCIAL_POSTS,
  MOCK_STRUCTURES,
} from '../data/claimSocialMock.js'

export function getClaimViewerSnapshot(selectedStructureId = MOCK_STRUCTURES[0].structure_id) {
  const structures = MOCK_STRUCTURES
  const selectedStructure =
    structures.find((structure) => structure.structure_id === selectedStructureId) ?? structures[0]
  const claim = getActiveClaimForStructure(selectedStructure.structure_id)
  const nearbyPosts = getNearbyPosts(selectedStructure)

  return {
    currentUser: MOCK_CURRENT_USER,
    structures,
    selectedStructure,
    claim,
    nearbyPosts,
  }
}

export function getActiveClaimForStructure(structureId) {
  return MOCK_CLAIMS.find(
    (claim) => claim.structure_id === structureId && claim.claim_status === 'active',
  ) ?? null
}

export function getNearbyPosts(structure) {
  return MOCK_GEOSOCIAL_POSTS.filter((post) => (
    post.structure_id === structure.structure_id || post.tile_id === structure.tile_id
  )).sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
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

export function formatTrace(value) {
  return `${Number(value).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })} Trace`
}
