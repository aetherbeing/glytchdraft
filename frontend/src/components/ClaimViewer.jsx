import React, { useMemo, useState } from 'react'
import {
  createMockClaim,
  formatTrace,
  getClaimViewerSnapshot,
} from '../services/claimSocialService.js'

const VISIBILITY_LABELS = {
  public: 'Public',
  private: 'Private',
  friends: 'Friends',
  unlisted: 'Unlisted',
}

export default function ClaimViewer() {
  const initial = useMemo(() => getClaimViewerSnapshot(), [])
  const [selectedId, setSelectedId] = useState(initial.selectedStructure.structure_id)
  const [localClaims, setLocalClaims] = useState([])

  const snapshot = getClaimViewerSnapshot(selectedId)
  const selectedStructure = snapshot.selectedStructure
  const localClaim = localClaims.find((claim) => claim.structure_id === selectedStructure.structure_id)
  const claim = localClaim ?? snapshot.claim
  const isClaimed = claim?.claim_status === 'active'
  const charityTrace = selectedStructure.trace_cost * (snapshot.currentUser.charity_allocation_percentage / 100)

  function handleClaim() {
    if (isClaimed) return
    setLocalClaims((claims) => [
      createMockClaim(selectedStructure, snapshot.currentUser),
      ...claims,
    ])
  }

  return (
    <main className="claim-page">
      <header className="claim-hero">
        <p className="claim-kicker">GlitchOS MVP / claims + geosocial</p>
        <h1>Claim Viewer</h1>
        <p>
          Select a structure, read its claim state, then scan nearby posts tied to the
          structure, tile, or coordinate. This is a mock surface aligned to the Trace schema.
        </p>
      </header>

      <section className="claim-layout" aria-label="Claim viewer">
        <StructureList
          structures={snapshot.structures}
          selectedId={selectedStructure.structure_id}
          onSelect={setSelectedId}
        />

        <SelectedStructurePanel
          claim={claim}
          currentUser={snapshot.currentUser}
          charityTrace={charityTrace}
          isClaimed={isClaimed}
          onClaim={handleClaim}
          structure={selectedStructure}
        />

        <NearbyActivityFeed posts={snapshot.nearbyPosts} />
      </section>
    </main>
  )
}

function StructureList({ structures, selectedId, onSelect }) {
  return (
    <aside className="structure-list" aria-label="Mock structures">
      <div className="panel-heading">
        <span>Structures</span>
        <strong>{structures.length}</strong>
      </div>
      {structures.map((structure) => (
        <button
          className={structure.structure_id === selectedId ? 'structure-row active' : 'structure-row'}
          key={structure.structure_id}
          type="button"
          onClick={() => onSelect(structure.structure_id)}
        >
          <span>{structure.structure_id}</span>
          <strong>{structure.address ?? structure.label}</strong>
          <small>{structure.tile_id}</small>
        </button>
      ))}
    </aside>
  )
}

function SelectedStructurePanel({
  structure,
  claim,
  currentUser,
  charityTrace,
  isClaimed,
  onClaim,
}) {
  return (
    <section className="claim-panel" aria-labelledby="selected-structure-title">
      <div className="panel-heading">
        <span>Selected structure</span>
        <ClaimBadge claimed={isClaimed} status={claim?.claim_status} />
      </div>

      <h2 id="selected-structure-title">{structure.label}</h2>

      <dl className="claim-facts">
        <Fact label="Structure ID" value={structure.structure_id} />
        <Fact label="Address" value={structure.address ?? 'Address unavailable'} />
        <Fact label="Tile ID" value={structure.tile_id} />
        <Fact label="Owner" value={claim?.owner_display_name ?? 'Unclaimed'} />
        <Fact label="Trace cost" value={formatTrace(structure.trace_cost)} />
        <Fact
          label="Charity allocation"
          value={`${currentUser.charity_allocation_percentage}% / ${formatTrace(charityTrace)}`}
        />
      </dl>

      <div className="claim-action-row">
        <div>
          <span>Readable before payment activation</span>
          <strong>{isClaimed ? `Claimed ${formatDate(claim.claimed_at)}` : 'Ready for claim intent'}</strong>
        </div>
        <button className="claim-button" type="button" disabled={isClaimed} onClick={onClaim}>
          {isClaimed ? 'Claimed' : 'Claim structure'}
        </button>
      </div>

      <div className="provenance-box">
        <span>Provenance</span>
        <code>{JSON.stringify(claim?.structure_provenance ?? { source: 'mock_structure', tile_id: structure.tile_id })}</code>
      </div>
    </section>
  )
}

function NearbyActivityFeed({ posts }) {
  return (
    <aside className="activity-panel" aria-label="Nearby activity feed">
      <div className="panel-heading">
        <span>Nearby activity</span>
        <strong>{posts.length}</strong>
      </div>

      <div className="post-composer">
        <span>Post scaffold</span>
        <p>Attach text, media, visibility, and provenance to a structure, tile, or coordinate.</p>
      </div>

      <div className="post-list">
        {posts.map((post) => (
          <article className="post-card" key={post.id}>
            <div className="post-meta">
              <strong>{post.author.display_name}</strong>
              <span>{formatDate(post.created_at)}</span>
            </div>
            <p>{post.body}</p>
            <div className="post-tags">
              <span>{VISIBILITY_LABELS[post.visibility]}</span>
              <span>{post.structure_id ?? post.tile_id}</span>
              <span>{post.media.length ? 'Media placeholder' : 'No media'}</span>
            </div>
            <div className="post-footer">
              <span>{post.reactions.trace} Trace reactions</span>
              <span>{post.comments_count} comments</span>
            </div>
          </article>
        ))}
      </div>
    </aside>
  )
}

function ClaimBadge({ claimed, status }) {
  return (
    <strong className={claimed ? 'claim-badge claimed' : 'claim-badge'}>
      {claimed ? status : 'unclaimed'}
    </strong>
  )
}

function Fact({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function formatDate(value) {
  if (!value) return 'Not claimed'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}
