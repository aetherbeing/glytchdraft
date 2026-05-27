import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { C, MAX_STREAMED_TILES, TILE_MANIFEST_URL } from '../config'
import { WAVE_UNIFORMS, MINIMAP_DATA } from '../waveState'
import { FloorSlicer } from './FloorSlicer'
import { AtmosphericPoints } from './AtmosphericPoints'
import {
  HOVER_GHOST, SELECTED_SOLID, CLAIMED_MARKED, DIM_CONTEXT,
  COLOR_FIELD, PLANE_WIRE, DEBUG_WIRE,
} from '../presets/BUILDING_VISUAL_STATES'

const STREAM_UPDATE_INTERVAL = 0.15
const WAVE_SPEED = 300       // m/s
const MAX_WAVE_RADIUS = 2500 // meters — caps ~8 s after arrival
const WAVE_ORIGIN_LERP = 0.04
const WAVE_EDGE_SOFT = 300.0 // smoothstep half-width in meters
const FOG_DENSITY = 0.002

const VISUAL_STATES = {
  hover: HOVER_GHOST,
  selected: SELECTED_SOLID,
  claimed: CLAIMED_MARKED,
  ghost: DIM_CONTEXT,
  colorField: COLOR_FIELD,
  planeWire: PLANE_WIRE,
  mesh: DEBUG_WIRE,
}

// --- fog shader injection -------------------------------------------
// fog_pars_vertex / fog_pars_fragment have NO leading tab in Three.js r184.
// fog_vertex / fog_fragment DO have a leading tab — replacements must match exactly.
const FOG_VERT_PARS_SEARCH = '#include <fog_pars_vertex>'
const FOG_VERT_SEARCH      = '\t#include <fog_vertex>'
const FOG_FRAG_PARS_SEARCH = '#include <fog_pars_fragment>'
const FOG_FRAG_SEARCH      = '\t#include <fog_fragment>'

const FOG_VERT_PARS_REPLACE = `#include <fog_pars_vertex>
varying vec2 vWorldXZ;`

const FOG_VERT_REPLACE = `\t#include <fog_vertex>
\tvWorldXZ = (modelMatrix * vec4(position, 1.0)).xz;`

const FOG_FRAG_PARS_REPLACE = `#include <fog_pars_fragment>
varying vec2 vWorldXZ;
uniform vec2 uCamXZ;
uniform float uWaveRadius;`

// Wave clearing: per-fragment XZ distance from camera origin,
// with a soft gaussian-like edge. vWorldXZ is interpolated per-fragment
// so each building face clears individually — no tile-block appearance.
const FOG_FRAG_REPLACE = `\t#ifdef USE_FOG
\t  float fogDist = length(vWorldXZ - uCamXZ);
\t  #ifdef FOG_EXP2
\t    float fogFactor = 1.0 - exp(-fogDensity * fogDensity * fogDist * fogDist);
\t  #else
\t    float fogFactor = smoothstep(fogNear, fogFar, fogDist);
\t  #endif
\t  float clearing = 1.0 - smoothstep(
\t    uWaveRadius - ${WAVE_EDGE_SOFT.toFixed(1)},
\t    uWaveRadius + ${WAVE_EDGE_SOFT.toFixed(1)},
\t    fogDist);
\t  fogFactor *= (1.0 - clearing);
\t  gl_FragColor.rgb = mix(gl_FragColor.rgb, fogColor, fogFactor);
\t#endif`

function injectWaveFog(mat) {
  mat.fog = true
  mat.onBeforeCompile = shader => {
    shader.uniforms.uCamXZ = WAVE_UNIFORMS.uCamXZ
    shader.uniforms.uWaveRadius = WAVE_UNIFORMS.uWaveRadius
    shader.vertexShader = shader.vertexShader
      .replace(FOG_VERT_PARS_SEARCH, FOG_VERT_PARS_REPLACE)
      .replace(FOG_VERT_SEARCH, FOG_VERT_REPLACE)
    shader.fragmentShader = shader.fragmentShader
      .replace(FOG_FRAG_PARS_SEARCH, FOG_FRAG_PARS_REPLACE)
      .replace(FOG_FRAG_SEARCH, FOG_FRAG_REPLACE)
  }
  return mat
}
// -------------------------------------------------------------------

function makeMaterial(state, fallbackColor, fallbackOpacity = 0.18) {
  return injectWaveFog(new THREE.MeshBasicMaterial({
    color: new THREE.Color(state?.color ?? fallbackColor),
    transparent: state?.transparent ?? true,
    opacity: state?.opacity ?? fallbackOpacity,
    side: THREE.DoubleSide,
    wireframe: Boolean(state?.wireframe),
  }))
}

function useMaterials() {
  return useMemo(() => ({
    buildingBaseMass: injectWaveFog(new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.buildingEmit),
      transparent: true, opacity: 0.18, side: THREE.DoubleSide,
    })),
    buildingHover: injectWaveFog(new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.buildingEmit),
      transparent: true, opacity: 0.45, side: THREE.DoubleSide,
    })),
    buildingSelected: injectWaveFog(new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.floorPlate),
      transparent: true, opacity: 0.75, side: THREE.DoubleSide,
    })),
    terrain: injectWaveFog(new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.terrain),
      side: THREE.DoubleSide,
    })),
    vegetation: injectWaveFog(new THREE.MeshBasicMaterial({
      color: new THREE.Color('#28a745'),
      transparent: true, opacity: 0.36, side: THREE.DoubleSide,
    })),
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

function StreamedTile({ tile, mats, onHover, onSelect, isSelected, visualMode }) {
  const { scene } = useGLTF(tile.url)
  const cloned = useMemo(() => scene.clone(true), [scene])

  const { buildings, terrain, vegetation } = useMemo(() => {
    const buildings = [], terrain = [], vegetation = []
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
      if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose?.())
      else obj.material?.dispose?.()
    })
  }, [tile.url, cloned])

  return (
    <group position={tile.bounds?.position}>
      {buildings.map((geometry, i) => (
        <Buildings
          key={`${tile.tile_id}-b-${i}`}
          geometry={geometry}
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

  // Wave origin state (local, drives WAVE_UNIFORMS every frame)
  const waveOriginRef = useRef(new THREE.Vector2(WAVE_UNIFORMS.uCamXZ.value.x, WAVE_UNIFORMS.uCamXZ.value.y))
  const waveStartTimeRef = useRef(-1) // set to clock.elapsedTime on first frame
  const tmpXZ = useRef(new THREE.Vector2())

  const tileById = useMemo(() => new Map(tiles.map(t => [t.tile_id, t])), [tiles])
  const entries = useMemo(() => tiles
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

  // Invisible placeholder — tiles are data containers only
  const ghostMat = useMemo(() => new THREE.MeshBasicMaterial({ visible: false }), [])

  useEffect(() => {
    let cancelled = false
    fetch(TILE_MANIFEST_URL)
      .then(r => { if (!r.ok) throw new Error(`manifest ${r.status}`); return r.json() })
      .then(data => { if (!cancelled) setTiles((data.tiles ?? []).map(normalizeTile).filter(Boolean)) })
      .catch(err => console.error('tile manifest load failed', err))
    return () => { cancelled = true; ghostMat.dispose() }
  }, [ghostMat])

  useFrame(({ clock }) => {
    // Seed wave origin and start time on very first frame
    if (waveStartTimeRef.current < 0) {
      waveOriginRef.current.set(camera.position.x, camera.position.z)
      waveStartTimeRef.current = clock.elapsedTime
    }

    // Wave origin trails camera — debounces rapid movement naturally
    tmpXZ.current.set(camera.position.x, camera.position.z)
    waveOriginRef.current.lerp(tmpXZ.current, WAVE_ORIGIN_LERP)

    // Wave radius: strictly monotonic using absolute elapsed time — never oscillates.
    // Math.max ensures it never decreases even across HMR reloads in dev.
    const elapsed = clock.elapsedTime - waveStartTimeRef.current
    WAVE_UNIFORMS.uWaveRadius.value = Math.max(
      WAVE_UNIFORMS.uWaveRadius.value,
      Math.min(elapsed * WAVE_SPEED, MAX_WAVE_RADIUS),
    )
    WAVE_UNIFORMS.uCamXZ.value.copy(waveOriginRef.current)

    // Minimap data (read by Minimap component via RAF)
    MINIMAP_DATA.camX = camera.position.x
    MINIMAP_DATA.camZ = camera.position.z
    MINIMAP_DATA.waveRadius = WAVE_UNIFORMS.uWaveRadius.value

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
  const isSelected = selected !== null

  return (
    <group>
      {activeTiles.map(tile => (
        tile.has_glb
          ? (
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
          )
          : null
      ))}
    </group>
  )
}

export function CityScene({ onHover, onSelect, hovered, selected, visualMode = 'base', fogEnabled = true }) {
  const mats = useMaterials()

  return (
    <>
      <ambientLight intensity={0.15} color="#203050" />
      <directionalLight position={[2000, 800, -1000]} intensity={0.8} color="#80c0ff" />
      <directionalLight position={[-1000, 400, 2000]} intensity={0.3} color="#ff6d00" />

      {/* FogExp2 drives the scene background fade; building shaders override with wave-clearing version */}
      {fogEnabled && <fogExp2 attach="fog" args={[C.bg, FOG_DENSITY]} />}

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
