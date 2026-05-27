import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { C, MAX_STREAMED_TILES, TILE_MANIFEST_URL } from '../config'
import { FloorSlicer } from './FloorSlicer'
import { AtmosphericPoints } from './AtmosphericPoints'
import {
  HOVER_GHOST,
  SELECTED_SOLID,
  CLAIMED_MARKED,
  DIM_CONTEXT,
  COLOR_FIELD,
  PLANE_WIRE,
  DEBUG_WIRE,
} from '../presets/BUILDING_VISUAL_STATES'

const STREAM_UPDATE_INTERVAL = 0.15

const VISUAL_STATES = {
  hover: HOVER_GHOST,
  selected: SELECTED_SOLID,
  claimed: CLAIMED_MARKED,
  ghost: DIM_CONTEXT,
  colorField: COLOR_FIELD,
  planeWire: PLANE_WIRE,
  mesh: DEBUG_WIRE,
}

function makeMaterial(state, fallbackColor, fallbackOpacity = 0.18) {
  return new THREE.MeshBasicMaterial({
    color: new THREE.Color(state?.color ?? fallbackColor),
    transparent: state?.transparent ?? true,
    opacity: state?.opacity ?? fallbackOpacity,
    side: THREE.DoubleSide,
    wireframe: Boolean(state?.wireframe),
  })
}

function useMaterials() {
  return useMemo(() => ({
    buildingBaseMass: new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.buildingEmit),
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide,
    }),
    buildingHover: new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.buildingEmit),
      transparent: true,
      opacity: 0.45,
      side: THREE.DoubleSide,
    }),
    buildingSelected: new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.floorPlate),
      transparent: true,
      opacity: 0.75,
      side: THREE.DoubleSide,
    }),
    terrain: new THREE.MeshStandardMaterial({
      color: new THREE.Color(C.terrain),
      roughness: 0.95,
      metalness: 0.0,
      side: THREE.DoubleSide,
    }),
    vegetation: new THREE.MeshBasicMaterial({
      color: new THREE.Color('#28a745'),
      transparent: true,
      opacity: 0.36,
      side: THREE.DoubleSide,
    }),
    preview: Object.fromEntries(
      Object.entries(VISUAL_STATES).map(([mode, state]) => [mode, makeMaterial(state, C.buildingEmit)])
    ),
  }), [])
}

function Buildings({ geometry, mats, onHover, onSelect, isSelected, visualMode }) {
  const [hovered, setHovered] = useState(false)

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

  const preview = visualMode === 'base' ? null : mats.preview[visualMode]
  const material = preview ?? (isSelected ? mats.buildingSelected : hovered ? mats.buildingHover : mats.buildingBaseMass)

  return (
    <mesh
      geometry={geometry}
      material={material}
      onPointerOver={handlePointerOver}
      onPointerOut={handlePointerOut}
      onClick={handleClick}
    />
  )
}

function TilePlaceholder({ tile, material }) {
  const min = tile.bounds.min
  const max = tile.bounds.max
  const position = [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ]
  const scale = [
    Math.max(1, max[0] - min[0]),
    Math.max(1, max[1] - min[1]),
    Math.max(1, max[2] - min[2]),
  ]

  return (
    <mesh position={position} scale={scale} material={material}>
      <boxGeometry args={[1, 1, 1]} />
    </mesh>
  )
}

function StreamedTile({ tile, mats, onHover, onSelect, isSelected, visualMode }) {
  const { scene } = useGLTF(tile.url)
  const cloned = useMemo(() => scene.clone(true), [scene])

  const { buildings, terrain, vegetation } = useMemo(() => {
    const buildings = []
    const terrain = []
    const vegetation = []
    cloned.traverse(obj => {
      if (!obj.isMesh) return
      const name = obj.name.toLowerCase()
      if (name === 'terrain') terrain.push(obj.geometry)
      else if (name === 'vegetation') vegetation.push(obj.geometry)
      else buildings.push(obj.geometry)
    })
    return { buildings, terrain, vegetation }
  }, [cloned])

  useEffect(() => () => {
    useGLTF.clear(tile.url)
    cloned.traverse(obj => {
      if (!obj.isMesh) return
      obj.geometry?.dispose?.()
      if (Array.isArray(obj.material)) obj.material.forEach(material => material.dispose?.())
      else obj.material?.dispose?.()
    })
  }, [tile.url, cloned])

  return (
    <group position={tile.bounds.position}>
      {buildings.map((geometry, i) => (
        <Buildings
          key={`${tile.tile_id}-building-${i}`}
          geometry={geometry}
          mats={mats}
          onHover={onHover}
          onSelect={onSelect}
          isSelected={isSelected}
          visualMode={visualMode}
        />
      ))}
      {terrain.map((geometry, i) => (
        <mesh key={`${tile.tile_id}-terrain-${i}`} geometry={geometry} material={mats.terrain} />
      ))}
      {vegetation.map((geometry, i) => (
        <mesh key={`${tile.tile_id}-vegetation-${i}`} geometry={geometry} material={mats.vegetation} />
      ))}
    </group>
  )
}

function normalizeTile(tile) {
  const id = tile.tile_id ?? tile.id
  const bounds = tile.bounds ?? tile.cull_bounds
  const cullBounds = tile.cull_bounds ?? tile.bounds
  if (!id || !bounds?.min || !bounds?.max || !cullBounds?.min || !cullBounds?.max) return null

  return {
    ...tile,
    tile_id: id,
    url: tile.url ?? `/models/tiles/${id}.glb`,
    has_glb: tile.has_glb !== false,
    bounds,
    cull_bounds: cullBounds,
  }
}

function TileStreamer({ mats, onHover, onSelect, selected, visualMode }) {
  const { camera } = useThree()
  const [tiles, setTiles] = useState([])
  const [activeIds, setActiveIds] = useState([])
  const matrixRef = useRef(new THREE.Matrix4())
  const frustumRef = useRef(new THREE.Frustum())
  const lastKeyRef = useRef('')
  const lastUpdateRef = useRef(0)

  const tileById = useMemo(() => new Map(tiles.map(tile => [tile.tile_id, tile])), [tiles])
  const entries = useMemo(() => tiles
    .filter(tile => tile.cull_bounds)
    .map(tile => {
      const cullBounds = tile.cull_bounds
      return {
        tile,
        center: new THREE.Vector3(
          (cullBounds.min[0] + cullBounds.max[0]) / 2,
          (cullBounds.min[1] + cullBounds.max[1]) / 2,
          (cullBounds.min[2] + cullBounds.max[2]) / 2
        ),
        box: new THREE.Box3(
          new THREE.Vector3(...cullBounds.min),
          new THREE.Vector3(...cullBounds.max)
        ),
      }
    }), [tiles])

  const placeholderMaterial = useMemo(() => new THREE.MeshBasicMaterial({
    color: new THREE.Color(C.buildingWire),
    wireframe: true,
    transparent: true,
    opacity: 0.18,
    depthWrite: false,
  }), [])

  useEffect(() => {
    let cancelled = false
    fetch(TILE_MANIFEST_URL)
      .then(res => {
        if (!res.ok) throw new Error(`tile manifest ${res.status}`)
        return res.json()
      })
      .then(data => {
        if (!cancelled) setTiles((data.tiles ?? []).map(normalizeTile).filter(Boolean))
      })
      .catch(err => console.error('tile manifest load failed', err))
    return () => {
      cancelled = true
      placeholderMaterial.dispose()
    }
  }, [placeholderMaterial])

  useFrame(({ clock }) => {
    if (!entries.length || clock.elapsedTime - lastUpdateRef.current < STREAM_UPDATE_INTERVAL) return
    lastUpdateRef.current = clock.elapsedTime

    camera.updateMatrixWorld()
    matrixRef.current.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
    frustumRef.current.setFromProjectionMatrix(matrixRef.current)

    const nextIds = entries
      .filter(entry => frustumRef.current.intersectsBox(entry.box))
      .sort((a, b) => (
        a.center.distanceToSquared(camera.position) - b.center.distanceToSquared(camera.position)
      ))
      .slice(0, MAX_STREAMED_TILES)
      .map(entry => entry.tile.tile_id)

    const key = nextIds.join('|')
    if (key !== lastKeyRef.current) {
      lastKeyRef.current = key
      setActiveIds(nextIds)
    }
  })

  const activeTiles = activeIds.map(id => tileById.get(id)).filter(Boolean)
  const isSelected = selected !== null

  return (
    <group>
      {activeTiles.filter(tile => !tile.has_glb).map(tile => (
        <TilePlaceholder key={`${tile.tile_id}-placeholder`} tile={tile} material={placeholderMaterial} />
      ))}
      {activeTiles.filter(tile => tile.has_glb).map(tile => (
        <Suspense
          key={tile.tile_id}
          fallback={<TilePlaceholder tile={tile} material={placeholderMaterial} />}
        >
          <StreamedTile
            tile={tile}
            mats={mats}
            onHover={onHover}
            onSelect={onSelect}
            isSelected={isSelected}
            visualMode={visualMode}
          />
        </Suspense>
      ))}
    </group>
  )
}

export function CityScene({ onHover, onSelect, hovered, selected, visualMode = 'base', fogEnabled = false }) {
  const mats = useMaterials()

  return (
    <>
      <ambientLight intensity={0.15} color="#203050" />
      <directionalLight position={[2000, 800, -1000]} intensity={0.8} color="#80c0ff" />
      <directionalLight position={[-1000, 400, 2000]} intensity={0.3} color="#ff6d00" />
      {fogEnabled && <fog attach="fog" args={['#080b0f', 3000, 18000]} />}

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
