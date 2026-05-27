import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { C, MAX_STREAMED_TILES, TILE_MANIFEST_URL } from '../config'
import { MINIMAP_DATA } from '../waveState'
import { FloorSlicer } from './FloorSlicer'
import { AtmosphericPoints } from './AtmosphericPoints'
import {
  HOVER_GHOST, SELECTED_SOLID, CLAIMED_MARKED, DIM_CONTEXT,
  COLOR_FIELD, PLANE_WIRE, DEBUG_WIRE,
} from '../presets/BUILDING_VISUAL_STATES'

const STREAM_UPDATE_INTERVAL = 0.15
const EMERGE_Y_START  = -50   // meters below ground
const EMERGE_DURATION = 0.6   // seconds
const EMERGE_STAGGER  = 0.020 // seconds between buildings (20 ms)

const VISUAL_STATES = {
  hover:      HOVER_GHOST,
  selected:   SELECTED_SOLID,
  claimed:    CLAIMED_MARKED,
  ghost:      DIM_CONTEXT,
  colorField: COLOR_FIELD,
  planeWire:  PLANE_WIRE,
  mesh:       DEBUG_WIRE,
}

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3)
}

function makeMaterial(state, fallbackColor, fallbackOpacity = 0.18) {
  return new THREE.MeshBasicMaterial({
    color:      new THREE.Color(state?.color ?? fallbackColor),
    transparent: state?.transparent ?? true,
    opacity:    state?.opacity ?? fallbackOpacity,
    side:       THREE.DoubleSide,
    wireframe:  Boolean(state?.wireframe),
  })
}

function useMaterials() {
  return useMemo(() => ({
    buildingBaseMass: new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.buildingEmit),
      transparent: true, opacity: 0.18, side: THREE.DoubleSide,
    }),
    buildingHover: new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.buildingEmit),
      transparent: true, opacity: 0.45, side: THREE.DoubleSide,
    }),
    buildingSelected: new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.floorPlate),
      transparent: true, opacity: 0.75, side: THREE.DoubleSide,
    }),
    terrain: new THREE.MeshStandardMaterial({
      color: new THREE.Color(C.terrain),
      roughness: 0.95, metalness: 0.0, side: THREE.DoubleSide,
    }),
    vegetation: new THREE.MeshBasicMaterial({
      color: new THREE.Color('#28a745'),
      transparent: true, opacity: 0.36, side: THREE.DoubleSide,
    }),
    preview: Object.fromEntries(
      Object.entries(VISUAL_STATES).map(([mode, state]) => [mode, makeMaterial(state, C.buildingEmit)])
    ),
  }), [])
}

// One building mesh. Starts at Y = EMERGE_Y_START, rises to Y = 0 over
// EMERGE_DURATION seconds, beginning after delayS seconds have elapsed.
function BuildingEmergence({ geometry, delayS, mats, onHover, onSelect, isSelected, visualMode }) {
  const groupRef  = useRef()
  const startRef  = useRef(-1)   // clock.elapsedTime when animation begins; -1 = not yet set
  const [hovered, setHovered] = useState(false)

  useFrame(({ clock }) => {
    if (!groupRef.current) return
    const now = clock.elapsedTime

    if (startRef.current < 0) {
      startRef.current = now + delayS
    }

    const elapsed = now - startRef.current
    if (elapsed <= 0) {
      groupRef.current.position.y = EMERGE_Y_START
      return
    }

    const t = easeOutCubic(Math.min(1, elapsed / EMERGE_DURATION))
    groupRef.current.position.y = EMERGE_Y_START * (1 - t)
  })

  const handlePointerOver = useCallback(e => {
    e.stopPropagation()
    setHovered(true)
    onHover({ point: e.point.clone(), normal: e.face?.normal?.clone() })
    document.body.style.cursor = 'crosshair'
  }, [onHover])

  const handlePointerOut = useCallback(() => {
    setHovered(false)
    onHover(null)
    document.body.style.cursor = ''
  }, [onHover])

  const handleClick = useCallback(e => {
    e.stopPropagation()
    onSelect(prev => prev ? null : { point: e.point.clone() })
  }, [onSelect])

  const preview  = visualMode === 'base' ? null : mats.preview[visualMode]
  const material = preview ?? (isSelected ? mats.buildingSelected : hovered ? mats.buildingHover : mats.buildingBaseMass)

  return (
    <group ref={groupRef}>
      <mesh
        geometry={geometry}
        material={material}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
        onClick={handleClick}
      />
    </group>
  )
}

// Loads one tile GLB and renders its buildings with radial stagger animation.
// Camera XZ is captured once at mount time — this is the sort reference.
function StreamedTile({ tile, mats, onHover, onSelect, isSelected, visualMode }) {
  const { camera } = useThree()
  // Capture camera XZ at mount — never re-reads, so sort is stable.
  const camXZ = useRef([camera.position.x, camera.position.z])

  const { scene } = useGLTF(tile.url)
  const cloned = useMemo(() => scene.clone(true), [scene])

  const { terrain, vegetation, sortedBuildings } = useMemo(() => {
    const buildings = [], terrain = [], vegetation = []
    cloned.traverse(obj => {
      if (!obj.isMesh) return
      const name = obj.name.toLowerCase()
      if (name === 'terrain')    terrain.push(obj.geometry)
      else if (name === 'vegetation') vegetation.push(obj.geometry)
      else buildings.push(obj.geometry)
    })

    // Sort by XZ distance from camera at load time — nearest rises first.
    const [cx, cz] = camXZ.current
    const offX = tile.bounds?.position?.[0] ?? 0
    const offZ = tile.bounds?.position?.[2] ?? 0

    const sorted = buildings
      .map((geom, origIdx) => {
        geom.computeBoundingBox()
        const center = new THREE.Vector3()
        geom.boundingBox.getCenter(center)
        const dx = (center.x + offX) - cx
        const dz = (center.z + offZ) - cz
        return { geom, origIdx, distSq: dx * dx + dz * dz }
      })
      .sort((a, b) => a.distSq - b.distSq)

    return { terrain, vegetation, sortedBuildings: sorted }
  }, [cloned, tile])

  useEffect(() => () => {
    useGLTF.clear(tile.url)
    cloned.traverse(obj => {
      if (!obj.isMesh) return
      obj.geometry?.dispose?.()
      if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose?.())
      else obj.material?.dispose?.()
    })
  }, [tile.url, cloned])

  return (
    <group position={tile.bounds?.position}>
      {sortedBuildings.map(({ geom, origIdx }, sortedIdx) => (
        <BuildingEmergence
          key={`${tile.tile_id}-b-${origIdx}`}
          geometry={geom}
          delayS={sortedIdx * EMERGE_STAGGER}
          mats={mats}
          onHover={onHover}
          onSelect={onSelect}
          isSelected={isSelected}
          visualMode={visualMode}
        />
      ))}
      {terrain.map((geometry, i) => (
        <mesh key={`${tile.tile_id}-t-${i}`} geometry={geometry} material={mats.terrain} />
      ))}
      {vegetation.map((geometry, i) => (
        <mesh key={`${tile.tile_id}-v-${i}`} geometry={geometry} material={mats.vegetation} />
      ))}
    </group>
  )
}

function normalizeTile(tile) {
  const id = tile.tile_id ?? tile.id
  const bounds     = tile.bounds     ?? tile.cull_bounds
  const cullBounds = tile.cull_bounds ?? tile.bounds
  if (!id || !bounds?.min || !bounds?.max || !cullBounds?.min || !cullBounds?.max) return null
  return {
    ...tile,
    tile_id:     id,
    url:         tile.url ?? `/models/tiles/${id}.glb`,
    has_glb:     tile.has_glb !== false,
    bounds,
    cull_bounds: cullBounds,
  }
}

function TileStreamer({ mats, onHover, onSelect, selected, visualMode }) {
  const { camera } = useThree()
  const [tiles, setTiles]       = useState([])
  const [activeIds, setActiveIds] = useState([])
  const matrixRef    = useRef(new THREE.Matrix4())
  const frustumRef   = useRef(new THREE.Frustum())
  const lastKeyRef   = useRef('')
  const lastUpdateRef = useRef(0)

  const tileById = useMemo(() => new Map(tiles.map(t => [t.tile_id, t])), [tiles])
  const entries  = useMemo(() => tiles
    .filter(t => t.cull_bounds)
    .map(tile => {
      const cb = tile.cull_bounds
      return {
        tile,
        center: new THREE.Vector3(
          (cb.min[0] + cb.max[0]) / 2,
          (cb.min[1] + cb.max[1]) / 2,
          (cb.min[2] + cb.max[2]) / 2,
        ),
        box: new THREE.Box3(new THREE.Vector3(...cb.min), new THREE.Vector3(...cb.max)),
      }
    }), [tiles])

  useEffect(() => {
    let cancelled = false
    fetch(TILE_MANIFEST_URL)
      .then(r => { if (!r.ok) throw new Error(`manifest ${r.status}`); return r.json() })
      .then(data => { if (!cancelled) setTiles((data.tiles ?? []).map(normalizeTile).filter(Boolean)) })
      .catch(err => console.error('tile manifest load failed', err))
    return () => { cancelled = true }
  }, [])

  useFrame(({ clock }) => {
    // Update minimap every frame
    MINIMAP_DATA.camX = camera.position.x
    MINIMAP_DATA.camZ = camera.position.z

    // Tile streaming — throttled
    if (!entries.length || clock.elapsedTime - lastUpdateRef.current < STREAM_UPDATE_INTERVAL) return
    lastUpdateRef.current = clock.elapsedTime

    camera.updateMatrixWorld()
    matrixRef.current.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
    frustumRef.current.setFromProjectionMatrix(matrixRef.current)

    const nextIds = entries
      .filter(e => frustumRef.current.intersectsBox(e.box))
      .sort((a, b) => a.center.distanceToSquared(camera.position) - b.center.distanceToSquared(camera.position))
      .slice(0, MAX_STREAMED_TILES)
      .map(e => e.tile.tile_id)

    const key = nextIds.join('|')
    if (key !== lastKeyRef.current) {
      lastKeyRef.current = key
      setActiveIds(nextIds)
    }
  })

  const activeTiles = activeIds.map(id => tileById.get(id)).filter(Boolean)
  const isSelected  = selected !== null

  return (
    <group>
      {activeTiles.map(tile => (
        tile.has_glb ? (
          <Suspense key={tile.tile_id} fallback={null}>
            <StreamedTile
              tile={tile}
              mats={mats}
              onHover={onHover}
              onSelect={onSelect}
              isSelected={isSelected}
              visualMode={visualMode}
            />
          </Suspense>
        ) : null
      ))}
    </group>
  )
}

export function CityScene({ onHover, onSelect, hovered, selected, visualMode = 'base' }) {
  const mats = useMaterials()

  return (
    <>
      <ambientLight intensity={0.15} color="#203050" />
      <directionalLight position={[2000, 800, -1000]} intensity={0.8} color="#80c0ff" />
      <directionalLight position={[-1000, 400, 2000]} intensity={0.3} color="#ff6d00" />

      <TileStreamer
        mats={mats}
        onHover={onHover}
        onSelect={onSelect}
        selected={selected}
        visualMode={visualMode}
      />

      <FloorSlicer
        point={selected?.point ?? hovered?.point ?? null}
        mode={selected ? 'selected' : 'hover'}
      />

      <AtmosphericPoints />
    </>
  )
}
