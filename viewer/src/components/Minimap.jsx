import { useEffect, useRef } from 'react'
import { SCENE, C } from '../config'
import { MINIMAP_DATA } from '../waveState'

const SIZE = 200
const PAD = 12 // world-space margin around city bounds

// World → canvas coordinate mapping
const xRange = SCENE.xMax - SCENE.xMin + PAD * 2
const zRange = SCENE.zMax - SCENE.zMin + PAD * 2

function toCanvas(wx, wz) {
  return [
    ((wx - SCENE.xMin + PAD) / xRange) * SIZE,
    ((wz - SCENE.zMin + PAD) / zRange) * SIZE,
  ]
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
  const rafRef = useRef()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    // Pre-compute city extent rect in canvas space
    const [x0, z0] = toCanvas(SCENE.xMin, SCENE.zMin)
    const [x1, z1] = toCanvas(SCENE.xMax, SCENE.zMax)

    function draw() {
      ctx.clearRect(0, 0, SIZE, SIZE)

      // Clip to circle
      ctx.save()
      ctx.beginPath()
      ctx.arc(SIZE / 2, SIZE / 2, SIZE / 2, 0, Math.PI * 2)
      ctx.clip()

      // City extent outline
      ctx.strokeStyle = 'rgba(0,229,255,0.10)'
      ctx.lineWidth = 1
      ctx.strokeRect(
        Math.min(x0, x1), Math.min(z0, z1),
        Math.abs(x1 - x0), Math.abs(z1 - z0),
      )

      // Wave clearing radius ring
      const [cx, cz] = toCanvas(MINIMAP_DATA.camX, MINIMAP_DATA.camZ)
      const waveR = (MINIMAP_DATA.waveRadius / xRange) * SIZE

      if (waveR > 2) {
        const grad = ctx.createRadialGradient(cx, cz, Math.max(0, waveR - 40), cx, cz, waveR + 40)
        grad.addColorStop(0, 'rgba(0,229,255,0.00)')
        grad.addColorStop(0.45, 'rgba(0,229,255,0.06)')
        grad.addColorStop(0.7, 'rgba(0,229,255,0.18)')
        grad.addColorStop(1, 'rgba(0,229,255,0.00)')
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.arc(cx, cz, waveR + 40, 0, Math.PI * 2)
        ctx.fill()
      }

      // Camera position dot
      ctx.fillStyle = '#00e5ff'
      ctx.shadowColor = '#00e5ff'
      ctx.shadowBlur = 8
      ctx.beginPath()
      ctx.arc(cx, cz, 4, 0, Math.PI * 2)
      ctx.fill()
      ctx.shadowBlur = 0

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
