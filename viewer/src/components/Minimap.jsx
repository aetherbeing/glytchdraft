import { useEffect, useRef } from 'react'
import { SCENE, TILE_MANIFEST_URL } from '../config'
import { MINIMAP_DATA } from '../waveState'

const SIZE = 200

// World X [SCENE.xMin..SCENE.xMax] → lon [extent.xmin..extent.xmax]
function worldXToLon(wx, ext) {
  return ext.xmin + ((wx - SCENE.xMin) / (SCENE.xMax - SCENE.xMin)) * (ext.xmax - ext.xmin)
}

// World Z: SCENE.zMax(0) = south(ext.ymin), SCENE.zMin(-18282) = north(ext.ymax)
function worldZToLat(wz, ext) {
  return ext.ymin + ((wz - SCENE.zMax) / (SCENE.zMin - SCENE.zMax)) * (ext.ymax - ext.ymin)
}

// Lon/lat → canvas pixel (lat is flipped: north = canvas top)
function lonToCanvasX(lon, ext) {
  return ((lon - ext.xmin) / (ext.xmax - ext.xmin)) * SIZE
}
function latToCanvasY(lat, ext) {
  return (1 - (lat - ext.ymin) / (ext.ymax - ext.ymin)) * SIZE
}

const STYLE = {
  position: 'fixed',
  bottom: 24,
  right: 24,
  width: SIZE,
  height: SIZE,
  borderRadius: '50%',
  border: '1px solid rgba(0,229,255,0.28)',
  background: 'rgba(8,11,15,0.82)',
  boxShadow: '0 4px 32px rgba(0,0,0,0.55)',
  pointerEvents: 'none',
  zIndex: 30,
  overflow: 'hidden',
}

export function Minimap() {
  const canvasRef = useRef()
  const rafRef    = useRef()
  const tilesRef  = useRef([])   // pre-computed { x, y, w, h } in canvas px
  const extentRef = useRef(null) // lat/lon extent of all tiles

  // Fetch manifest once, compute canvas rects for all tiles with bbox_4326
  useEffect(() => {
    let cancelled = false
    fetch(TILE_MANIFEST_URL)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return
        const raw = data.tiles ?? []
        let lonMin = Infinity, lonMax = -Infinity
        let latMin = Infinity, latMax = -Infinity
        let missing = 0

        for (const t of raw) {
          const b = t.bbox_4326
          if (!b) { missing++; continue }
          lonMin = Math.min(lonMin, b.xmin)
          lonMax = Math.max(lonMax, b.xmax)
          latMin = Math.min(latMin, b.ymin)
          latMax = Math.max(latMax, b.ymax)
        }

        if (!isFinite(lonMin)) return
        if (missing) console.log(`[Minimap] ${missing}/${raw.length} tiles missing bbox_4326 — skipped`)

        const ext = { xmin: lonMin, ymin: latMin, xmax: lonMax, ymax: latMax }
        extentRef.current = ext

        tilesRef.current = raw
          .filter(t => t.bbox_4326)
          .map(t => {
            const b = t.bbox_4326
            const x = lonToCanvasX(b.xmin, ext)
            const y = latToCanvasY(b.ymax, ext) // ymax = north = canvas top
            const w = lonToCanvasX(b.xmax, ext) - x
            const h = latToCanvasY(b.ymin, ext) - y // ymin = south = canvas bottom
            return { x, y, w, h }
          })
      })
      .catch(err => console.error('[Minimap] manifest fetch failed', err))
    return () => { cancelled = true }
  }, [])

  // RAF draw loop — reads tilesRef and extentRef directly, no React state churn
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    function draw() {
      ctx.clearRect(0, 0, SIZE, SIZE)

      ctx.save()
      ctx.beginPath()
      ctx.arc(SIZE / 2, SIZE / 2, SIZE / 2, 0, Math.PI * 2)
      ctx.clip()

      // Tile bboxes
      const tiles = tilesRef.current
      if (tiles.length) {
        ctx.fillStyle   = 'rgba(0,229,255,0.05)'
        ctx.strokeStyle = 'rgba(0,229,255,0.20)'
        ctx.lineWidth   = 0.5
        for (const { x, y, w, h } of tiles) {
          ctx.fillRect(x, y, w, h)
          ctx.strokeRect(x, y, w, h)
        }
      }

      // Camera dot
      const ext = extentRef.current
      if (ext) {
        const lon = worldXToLon(MINIMAP_DATA.camX, ext)
        const lat = worldZToLat(MINIMAP_DATA.camZ, ext)
        const cx  = lonToCanvasX(lon, ext)
        const cy  = latToCanvasY(lat, ext)
        ctx.fillStyle   = '#00e5ff'
        ctx.shadowColor = '#00e5ff'
        ctx.shadowBlur  = 8
        ctx.beginPath()
        ctx.arc(cx, cy, 4, 0, Math.PI * 2)
        ctx.fill()
        ctx.shadowBlur = 0
      }

      ctx.restore()
      rafRef.current = requestAnimationFrame(draw)
    }

    rafRef.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      width={SIZE}
      height={SIZE}
      style={STYLE}
      aria-label="City minimap"
    />
  )
}
