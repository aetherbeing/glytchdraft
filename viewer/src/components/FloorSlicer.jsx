import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { C, FLOOR_HEIGHT, FLOOR_ABOVE, FLOOR_BELOW, SCENE } from '../config'

// Animated horizontal floor plates that materialize at the hover/click point.
// Plates span SCENE_WIDTH × SCENE_DEPTH so they cut through the whole city.
const PLATE_W = SCENE.xMax - SCENE.xMin + 800
const PLATE_D = Math.abs(SCENE.zMin - SCENE.zMax) + 800
const HOVER_OPACITY   = 0.045
const SELECTED_OPACITY = 0.10

export function FloorSlicer({ point, mode }) {
  const groupRef = useRef()

  // Y positions of floor plates around the hover/selected point
  const floorYs = useMemo(() => {
    if (!point) return []
    const base = Math.round(point.y / FLOOR_HEIGHT) * FLOOR_HEIGHT
    const ys = []
    for (let i = -FLOOR_BELOW; i <= FLOOR_ABOVE; i++) {
      const y = base + i * FLOOR_HEIGHT
      if (y >= 0 && y <= SCENE.yMax + FLOOR_HEIGHT) ys.push(y)
    }
    return ys
  }, [point])

  // Animate in on mount via opacity ramp
  const opRef = useRef(0)
  const targetOp = mode === 'selected' ? SELECTED_OPACITY : HOVER_OPACITY
  useFrame((_, dt) => {
    opRef.current = THREE.MathUtils.lerp(opRef.current, point ? targetOp : 0, 8 * dt)
    if (groupRef.current) {
      groupRef.current.children.forEach(m => {
        if (m.material) m.material.opacity = opRef.current
      })
    }
  })

  if (!point || floorYs.length === 0) return null

  const cx = (SCENE.xMin + SCENE.xMax) / 2
  const cz = (SCENE.zMin + SCENE.zMax) / 2

  return (
    <group ref={groupRef}>
      {floorYs.map(y => {
        const dist = Math.abs(y - point.y)
        const fade = 1 - dist / (FLOOR_HEIGHT * (FLOOR_ABOVE + FLOOR_BELOW))
        const color = mode === 'selected'
          ? new THREE.Color(C.floorPlate).lerp(new THREE.Color(C.floorAccent), fade)
          : new THREE.Color(C.floorAccent)
        return (
          <mesh key={y} position={[cx, y, cz]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[PLATE_W, PLATE_D]} />
            <meshBasicMaterial
              color={color}
              transparent
              opacity={0}
              side={THREE.DoubleSide}
              depthWrite={false}
            />
          </mesh>
        )
      })}
    </group>
  )
}
