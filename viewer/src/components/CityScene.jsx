import { useRef, useState, useMemo, useCallback, useEffect } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { GLB_URL, C } from '../config'
import { FloorSlicer } from './FloorSlicer'
import { AtmosphericPoints } from './AtmosphericPoints'
import {
  HOVER_GHOST,
  SELECTED_SOLID,
  CLAIMED_MARKED,
  DIM_CONTEXT,
  COLOR_FIELD,
  PLANE_WIRE,
  DISTRICTS,
  EMERGENCE,
  BEACONS,
  DEBUG_WIRE,
} from '../presets/BUILDING_VISUAL_STATES'

const VISUAL_STATES = {
  hover: HOVER_GHOST,
  selected: SELECTED_SOLID,
  claimed: CLAIMED_MARKED,
  ghost: DIM_CONTEXT,
  colorField: COLOR_FIELD,
  districts: DISTRICTS,
  emergence: EMERGENCE,
  footprintBeams: BEACONS,
  planeWire: PLANE_WIRE,
  mesh: DEBUG_WIRE,
}

const BEACON_SITES = [
  { x: 1220, z: -4040, width: 72, depth: 118, rotation: 0.18, color: 0 },
  { x: 2350, z: -3010, width: 96, depth: 82, rotation: -0.08, color: 1 },
  { x: 3510, z: -2200, width: 124, depth: 74, rotation: 0.32, color: 2 },
  { x: 4640, z: -3580, width: 84, depth: 132, rotation: -0.22, color: 0 },
  { x: 5480, z: -1260, width: 110, depth: 92, rotation: 0.05, color: 3 },
  { x: 6400, z: -2820, width: 72, depth: 146, rotation: 0.28, color: 1 },
  { x: 7120, z: -520, width: 104, depth: 78, rotation: -0.18, color: 2 },
]

function makeBeaconMaterial(color, opacity) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uOpacity: { value: opacity },
      uTime: { value: 0 },
    },
    vertexShader: `
      varying float vY;
      varying vec2 vFootprint;
      void main() {
        vY = position.y + 0.5;
        vFootprint = position.xz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uOpacity;
      uniform float uTime;
      varying float vY;
      varying vec2 vFootprint;
      void main() {
        vec2 edge = abs(vFootprint) * 2.0;
        float footprintFade = smoothstep(1.05, 0.42, max(edge.x, edge.y));
        float baseFade = pow(1.0 - clamp(vY, 0.0, 1.0), 1.45);
        float topFade = smoothstep(1.0, 0.68, vY);
        float pulse = 0.86 + sin(uTime * 0.85 + vY * 5.0) * 0.06;
        float alpha = uOpacity * footprintFade * baseFade * topFade * pulse;
        gl_FragColor = vec4(uColor, alpha);
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  })
}

function resolveFootprintSites(geometry) {
  const src = geometry.attributes.position
  return BEACON_SITES.map(site => {
    const cos = Math.cos(-site.rotation)
    const sin = Math.sin(-site.rotation)
    const halfW = site.width * 0.5
    const halfD = site.depth * 0.5
    let roofY = 0

    for (let i = 0; i < src.count; i += 3) {
      const dx = src.getX(i) - site.x
      const dz = src.getZ(i) - site.z
      const lx = dx * cos - dz * sin
      const lz = dx * sin + dz * cos
      if (Math.abs(lx) <= halfW && Math.abs(lz) <= halfD) {
        roofY = Math.max(roofY, src.getY(i))
      }
    }

    return { ...site, roofY: roofY || 18 }
  })
}

function makeColorFieldMaterial(state) {
  const material = new THREE.MeshBasicMaterial({
    color: new THREE.Color(state.color),
    transparent: state.transparent,
    opacity: state.opacity,
    side: THREE.DoubleSide,
  })

  const palette = state.palette.map(color => new THREE.Color(color))
  material.onBeforeCompile = shader => {
    shader.uniforms.uColorA = { value: palette[0] }
    shader.uniforms.uColorB = { value: palette[1] }
    shader.uniforms.uColorC = { value: palette[2] }
    shader.uniforms.uColorD = { value: palette[3] }
    shader.uniforms.uColorE = { value: palette[4] }
    shader.uniforms.uColorF = { value: palette[5] }

    shader.vertexShader = `
      varying vec3 vLocalPos;
    ` + shader.vertexShader.replace(
      '#include <begin_vertex>',
      `
        #include <begin_vertex>
        vLocalPos = position;
      `
    )

    shader.fragmentShader = `
      uniform vec3 uColorA;
      uniform vec3 uColorB;
      uniform vec3 uColorC;
      uniform vec3 uColorD;
      uniform vec3 uColorE;
      uniform vec3 uColorF;
      varying vec3 vLocalPos;
    ` + shader.fragmentShader.replace(
      '#include <color_fragment>',
      `
        #include <color_fragment>
        float band = sin(vLocalPos.x * 0.0065 + vLocalPos.z * 0.004 + floor(vLocalPos.y / 24.0) * 0.85);
        float drift = sin(vLocalPos.x * 0.0017 - vLocalPos.z * 0.0023);
        float heightMix = smoothstep(0.0, 280.0, vLocalPos.y);
        vec3 lowMix = mix(uColorF, uColorC, smoothstep(-1.0, 1.0, drift));
        vec3 highMix = mix(uColorB, uColorD, smoothstep(-1.0, 1.0, band));
        vec3 fieldColor = mix(lowMix, highMix, heightMix);
        fieldColor = mix(fieldColor, uColorA, 0.18);
        diffuseColor.rgb = mix(diffuseColor.rgb, fieldColor, 0.72);
      `
    )
  }

  return material
}

function makeDistrictMaterial(state) {
  const material = new THREE.MeshBasicMaterial({
    color: new THREE.Color(state.color),
    transparent: state.transparent,
    opacity: state.opacity,
    side: THREE.DoubleSide,
  })

  const districts = state.districtPalette.map(color => new THREE.Color(color))
  const anomalies = state.anomalyPalette.map(color => new THREE.Color(color))

  material.onBeforeCompile = shader => {
    shader.uniforms.uDistrictA = { value: districts[0] }
    shader.uniforms.uDistrictB = { value: districts[1] }
    shader.uniforms.uDistrictC = { value: districts[2] }
    shader.uniforms.uDistrictD = { value: districts[3] }
    shader.uniforms.uDistrictE = { value: districts[4] }
    shader.uniforms.uDistrictF = { value: districts[5] }
    shader.uniforms.uAnomalyA = { value: anomalies[0] }
    shader.uniforms.uAnomalyB = { value: anomalies[1] }
    shader.uniforms.uAnomalyC = { value: anomalies[2] }
    shader.uniforms.uAnomalyD = { value: anomalies[3] }

    shader.vertexShader = `
      varying vec3 vLocalPos;
    ` + shader.vertexShader.replace(
      '#include <begin_vertex>',
      `
        #include <begin_vertex>
        vLocalPos = position;
      `
    )

    shader.fragmentShader = `
      uniform vec3 uDistrictA;
      uniform vec3 uDistrictB;
      uniform vec3 uDistrictC;
      uniform vec3 uDistrictD;
      uniform vec3 uDistrictE;
      uniform vec3 uDistrictF;
      uniform vec3 uAnomalyA;
      uniform vec3 uAnomalyB;
      uniform vec3 uAnomalyC;
      uniform vec3 uAnomalyD;
      varying vec3 vLocalPos;

      float hash12(vec2 p) {
        vec3 p3 = fract(vec3(p.xyx) * 0.1031);
        p3 += dot(p3, p3.yzx + 33.33);
        return fract((p3.x + p3.y) * p3.z);
      }

      vec3 districtColor(float i) {
        vec3 c = uDistrictA;
        c = mix(c, uDistrictB, step(0.5, i));
        c = mix(c, uDistrictC, step(1.5, i));
        c = mix(c, uDistrictD, step(2.5, i));
        c = mix(c, uDistrictE, step(3.5, i));
        c = mix(c, uDistrictF, step(4.5, i));
        return c;
      }
    ` + shader.fragmentShader.replace(
      '#include <color_fragment>',
      `
        #include <color_fragment>
        vec2 districtCell = floor((vLocalPos.xz + vec2(900.0, 5200.0)) / vec2(1700.0, 1450.0));
        float districtHash = hash12(districtCell);
        float districtIndex = mod(districtCell.x * 2.0 + districtCell.y * 3.0, 6.0);
        vec3 fieldColor = districtColor(districtIndex);

        vec2 anomalyCell = floor((vLocalPos.xz + vec2(350.0, 4100.0)) / 155.0);
        float anomalyHash = hash12(anomalyCell + districtCell * 17.0);
        float anomalyMask = step(0.982, anomalyHash);
        float amberMask = step(0.997, anomalyHash);
        float anomalyChoice = hash12(anomalyCell + vec2(19.17, 71.41));
        vec3 anomalyColor = mix(uAnomalyA, uAnomalyB, step(0.33, anomalyChoice));
        anomalyColor = mix(anomalyColor, uAnomalyC, step(0.66, anomalyChoice));
        anomalyColor = mix(anomalyColor, uAnomalyD, amberMask);

        float heightShade = smoothstep(0.0, 260.0, vLocalPos.y);
        float districtShade = mix(0.86, 1.12, districtHash);
        fieldColor = mix(fieldColor * 0.82, fieldColor * 1.22, heightShade) * districtShade;
        fieldColor = mix(fieldColor, anomalyColor, anomalyMask);
        diffuseColor.rgb = mix(diffuseColor.rgb, fieldColor, 0.92);
      `
    )
  }

  return material
}

function makeEmergenceMaterial(state) {
  const material = new THREE.MeshBasicMaterial({
    color: new THREE.Color(state.color),
    transparent: state.transparent,
    opacity: state.opacity,
    side: THREE.DoubleSide,
  })

  material.userData.emergence = { shader: null }
  material.onBeforeCompile = shader => {
    material.userData.emergence.shader = shader
    shader.uniforms.uEmergenceTime = { value: 0 }
    shader.uniforms.uRiseDistance = { value: state.riseDistance }
    shader.uniforms.uDuration = { value: state.duration }
    shader.uniforms.uWaveDelay = { value: state.waveDelay }

    shader.vertexShader = `
      uniform float uEmergenceTime;
      uniform float uRiseDistance;
      uniform float uDuration;
      uniform float uWaveDelay;
      varying float vEmergence;
    ` + shader.vertexShader.replace(
      '#include <begin_vertex>',
      `
        #include <begin_vertex>
        float wave = sin(position.x * 0.0019 + position.z * 0.0024) * 0.5 + 0.5;
        float band = fract((position.x * 0.0007) + (position.z * 0.0005));
        float delay = mix(wave, band, 0.35) * uWaveDelay;
        float p = clamp((uEmergenceTime - delay) / uDuration, 0.0, 1.0);
        float eased = p * p * (3.0 - 2.0 * p);
        transformed.y -= (1.0 - eased) * uRiseDistance;
        vEmergence = eased;
      `
    )

    shader.fragmentShader = `
      varying float vEmergence;
    ` + shader.fragmentShader.replace(
      '#include <color_fragment>',
      `
        #include <color_fragment>
        diffuseColor.rgb = mix(diffuseColor.rgb * 0.55, diffuseColor.rgb, vEmergence);
        diffuseColor.a *= smoothstep(0.05, 1.0, vEmergence);
      `
    )
  }

  return material
}

function FootprintBeams({ active, geometry: buildingGeometry }) {
  const materials = useMemo(
    () => BEACONS.colors.map(color => makeBeaconMaterial(color, BEACONS.opacity)),
    []
  )
  const geometry = useMemo(
    () => new THREE.BoxGeometry(1, 1, 1, 1, 1, 1),
    []
  )
  const sites = useMemo(
    () => resolveFootprintSites(buildingGeometry),
    [buildingGeometry]
  )

  useEffect(() => () => {
    geometry.dispose()
    materials.forEach(material => material.dispose())
  }, [geometry, materials])

  useFrame(({ clock }) => {
    if (!active) return
    materials.forEach((material, i) => {
      material.uniforms.uTime.value = clock.elapsedTime + i * 0.47
    })
  })

  if (!active) return null

  return (
    <group>
      {sites.slice(0, BEACONS.beamCount).map((site, i) => (
        <mesh
          key={i}
          geometry={geometry}
          material={materials[site.color % materials.length]}
          position={[site.x, site.roofY + BEACONS.height / 2, site.z]}
          rotation={[0, site.rotation, 0]}
          scale={[site.width, BEACONS.height, site.depth]}
          renderOrder={2}
        />
      ))}
    </group>
  )
}

function makePreviewMaterials(state) {
  if (state === COLOR_FIELD) {
    return { solid: makeColorFieldMaterial(state), wire: null, debugWire: false }
  }

  if (state === DISTRICTS) {
    return { solid: makeDistrictMaterial(state), wire: null, debugWire: false }
  }

  if (state === EMERGENCE) {
    return { solid: makeEmergenceMaterial(state), wire: null, debugWire: false, emergence: true }
  }

  if (state === BEACONS) {
    return { solid: null, wire: null, debugWire: false }
  }

  const solid = state.wireframe ? null : new THREE.MeshBasicMaterial({
    color: new THREE.Color(state.color),
    transparent: state.transparent,
    opacity: state.opacity,
    side: THREE.DoubleSide,
  })

  const wire = state.wireframe ? new THREE.MeshBasicMaterial({
    color: new THREE.Color(state.edgeColor ?? state.color),
    wireframe: true,
    transparent: true,
    opacity: state.opacity,
  }) : null

  return {
    solid,
    wire,
    debugWire: state.wireframe,
  }
}

// Materials — created once
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
    water: new THREE.MeshStandardMaterial({
      color: new THREE.Color(C.water),
      transparent: true,
      opacity: 0.30,
      roughness: 0.05,
      metalness: 0.4,
      side: THREE.DoubleSide,
    }),
    preview: Object.fromEntries(
      Object.entries(VISUAL_STATES).map(([mode, state]) => [mode, makePreviewMaterials(state)])
    ),
  }), [])
}

function Buildings({ geometry, mats, onHover, onSelect, isSelected, visualMode }) {
  const meshRef    = useRef()
  const wireRef    = useRef()
  const emergenceStartRef = useRef(null)
  const [hovered, setHovered] = useState(false)

  useEffect(() => {
    emergenceStartRef.current = null
  }, [visualMode])

  useFrame(({ clock }) => {
    if (visualMode !== 'emergence') return
    const shader = mats.preview.emergence?.solid?.userData.emergence?.shader
    if (!shader) return
    if (emergenceStartRef.current === null) emergenceStartRef.current = clock.elapsedTime
    shader.uniforms.uEmergenceTime.value = clock.elapsedTime - emergenceStartRef.current
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

  const preview = visualMode === 'base' || visualMode === 'footprintBeams' ? null : mats.preview[visualMode]
  const debugWire = Boolean(preview?.debugWire)
  const solidMat = preview?.solid ?? (isSelected ? mats.buildingSelected : hovered ? mats.buildingHover : mats.buildingBaseMass)
  const wireMat  = debugWire ? preview.wire : null
  const showSolid = !debugWire

  return (
    <group>
      {/* Interaction/massing mesh */}
      {showSolid && (
        <mesh ref={meshRef} geometry={geometry} material={solidMat}
          onPointerOver={handlePointerOver}
          onPointerOut={handlePointerOut}
          onClick={handleClick}
        />
      )}
      {/* TODO: Clean building edges should come later from footprint/roof/per-building metadata, not raw GLB wireframe. */}
      {/* Debug mesh mode keeps the full triangle wireframe. */}
      {debugWire && (
        <mesh ref={wireRef} geometry={geometry} material={wireMat}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
        onClick={handleClick}
        />
      )}
    </group>
  )
}

export function CityScene({ onHover, onSelect, hovered, selected, visualMode = 'base', fogEnabled = false }) {
  const { scene: threeScene } = useThree()
  const { scene } = useGLTF(GLB_URL)
  const mats = useMaterials()

  useEffect(() => {
    if (!fogEnabled) threeScene.fog = null
  }, [fogEnabled, threeScene])

  // Extract geometries by node name
  const { buildingGeo, terrainGeo, waterGeo } = useMemo(() => {
    let buildingGeo = null, terrainGeo = null, waterGeo = null
    scene.traverse(obj => {
      if (!obj.isMesh) return
      const name = obj.name.toLowerCase()
      if (name.includes('bikini') || name.includes('lod')) buildingGeo = obj.geometry
      else if (name === 'terrain') terrainGeo = obj.geometry
      else if (name === 'water')   waterGeo   = obj.geometry
    })
    return { buildingGeo, terrainGeo, waterGeo }
  }, [scene])

  const isSelected = selected !== null

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.15} color="#203050" />
      <directionalLight position={[2000, 800, -1000]} intensity={0.8} color="#80c0ff" />
      <directionalLight position={[-1000, 400, 2000]} intensity={0.3} color="#ff6d00" />
      {fogEnabled && <fog attach="fog" args={['#080b0f', 3000, 18000]} />}

      {/* Buildings */}
      {buildingGeo && (
        <Buildings
          geometry={buildingGeo}
          mats={mats}
          onHover={onHover}
          onSelect={onSelect}
          isSelected={isSelected}
          visualMode={visualMode}
        />
      )}

      {/* Floor slicer — hover or selected */}
      {buildingGeo && (
        <FootprintBeams
          active={visualMode === 'footprintBeams'}
          geometry={buildingGeo}
        />
      )}

      <FloorSlicer
        point={selected?.point ?? hovered?.point ?? null}
        mode={selected ? 'selected' : 'hover'}
      />

      {/* Terrain */}
      {terrainGeo && (
        <mesh geometry={terrainGeo} material={mats.terrain} />
      )}

      {/* Water */}
      {waterGeo && (
        <mesh geometry={waterGeo} material={mats.water} />
      )}

      {/* Atmospheric point cloud */}
      <AtmosphericPoints />
    </>
  )
}

// Preload
useGLTF.preload(GLB_URL)
