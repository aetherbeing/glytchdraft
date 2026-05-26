import { Suspense, useState, useCallback, useEffect, useRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, AdaptiveDpr, AdaptiveEvents } from '@react-three/drei'
import { createXRStore, XR } from '@react-three/xr'
import { CityScene } from './components/CityScene'
import { FPVController } from './components/FPVController'
import { HUD } from './components/HUD'
import { SCENE, C, ENABLE_SCENE_FOG, NAVIGATION } from './config'
import './index.css'

const CAMERA = {
  position: [SCENE.cx + 400, 600, SCENE.cz + 3200],
  fov: 55,
  near: 1,
  far: 40000,
}

const ORBIT_TARGET = [SCENE.cx, 40, SCENE.cz]

const xrStore = createXRStore({ emulate: false })

const XR_ROW = {
  position: 'fixed',
  bottom: 80,
  left: '50%',
  transform: 'translateX(-50%)',
  display: 'flex',
  gap: 10,
  pointerEvents: 'auto',
}

const XR_BTN = {
  background: 'rgba(0,229,255,0.06)',
  border: '1px solid rgba(0,229,255,0.35)',
  borderRadius: 4,
  color: '#00e5ff',
  fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  fontSize: 10,
  letterSpacing: '0.12em',
  padding: '7px 16px',
  cursor: 'pointer',
  backdropFilter: 'blur(8px)',
}

const CROSSHAIR = {
  position: 'fixed',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  pointerEvents: 'none',
  zIndex: 10,
}

export default function App() {
  const cameraRef = useRef(null)
  const controlsRef = useRef(null)
  const [hovered,  setHovered]  = useState(null)
  const [selected, setSelected] = useState(null)
  const [fpvMode,  setFpvMode]  = useState(false)
  const [visualMode, setVisualMode] = useState('base')
  const [fogEnabled, setFogEnabled] = useState(ENABLE_SCENE_FOG)

  const handleHover  = useCallback(info => setHovered(info), [])
  const handleSelect = useCallback(fn => setSelected(fn), [])
  const handleFPV    = useCallback(entering => setFpvMode(entering), [])

  const applyView = useCallback((position, target, enterFpv = false) => {
    const camera = cameraRef.current
    const controls = controlsRef.current
    if (!camera) return

    camera.position.set(position[0], position[1], position[2])
    camera.lookAt(target[0], target[1], target[2])
    if (controls) {
      controls.target.set(target[0], target[1], target[2])
      controls.update()
    }
    setFpvMode(enterFpv)
  }, [])

  const resetView = useCallback(() => {
    applyView(CAMERA.position, ORBIT_TARGET, false)
  }, [applyView])

  const topView = useCallback(() => {
    applyView([SCENE.cx, 9000, SCENE.cz], [SCENE.cx, 0, SCENE.cz], false)
  }, [applyView])

  const streetView = useCallback(() => {
    applyView([SCENE.cx, 28, SCENE.cz + 520], [SCENE.cx, 24, SCENE.cz], true)
  }, [applyView])

  const zoomBy = useCallback(amount => {
    const camera = cameraRef.current
    const controls = controlsRef.current
    if (!camera || !controls) return

    const dx = camera.position.x - controls.target.x
    const dy = camera.position.y - controls.target.y
    const dz = camera.position.z - controls.target.z
    const scale = amount < 0 ? 0.72 : 1.28
    camera.position.set(
      controls.target.x + dx * scale,
      controls.target.y + dy * scale,
      controls.target.z + dz * scale
    )
    controls.update()
  }, [])

  useEffect(() => {
    const onKeyDown = e => {
      if (e.repeat || e.target?.tagName === 'INPUT' || e.target?.tagName === 'TEXTAREA') return
      if (e.code === 'KeyR') resetView()
      if (e.code === 'KeyT') topView()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [resetView, topView])

  return (
    <div style={{ width: '100vw', height: '100vh', background: C.bg }}>
      <Canvas
        camera={CAMERA}
        gl={{ antialias: true, toneMapping: 1 }}
        shadows={false}
        onCreated={({ camera }) => { cameraRef.current = camera }}
        onPointerMissed={() => { if (!fpvMode) setSelected(null) }}
      >
        <XR store={xrStore}>
          <color attach="background" args={[C.bg]} />

          <Suspense fallback={null}>
            <CityScene
              onHover={handleHover}
              onSelect={handleSelect}
              hovered={hovered}
              selected={selected}
              visualMode={visualMode}
              fogEnabled={fogEnabled}
            />
          </Suspense>

          <FPVController active={fpvMode} onToggle={handleFPV} />

          <OrbitControls
            ref={controlsRef}
            enabled={!fpvMode}
            target={ORBIT_TARGET}
            maxDistance={NAVIGATION.orbitMaxDistance}
            minDistance={NAVIGATION.orbitMinDistance}
            maxPolarAngle={Math.PI / 2 - 0.02}
            enableDamping
            dampingFactor={0.06}
            zoomSpeed={NAVIGATION.orbitZoomSpeed}
            panSpeed={NAVIGATION.orbitPanSpeed}
            rotateSpeed={NAVIGATION.orbitRotateSpeed}
          />
          <AdaptiveDpr pixelated />
          <AdaptiveEvents />
        </XR>
      </Canvas>

      <HUD
        hovered={hovered}
        selected={selected}
        fpvMode={fpvMode}
        visualMode={visualMode}
        onVisualModeChange={setVisualMode}
        fogEnabled={fogEnabled}
        onFogToggle={() => setFogEnabled(enabled => !enabled)}
        onResetView={resetView}
        onTopView={topView}
        onStreetView={streetView}
        onZoomIn={() => zoomBy(-1)}
        onZoomOut={() => zoomBy(1)}
      />

      {/* FPV crosshair */}
      {fpvMode && (
        <div style={CROSSHAIR}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <line x1="10" y1="3"  x2="10" y2="17" stroke="rgba(0,229,255,0.75)" strokeWidth="1" />
            <line x1="3"  y1="10" x2="17" y2="10" stroke="rgba(0,229,255,0.75)" strokeWidth="1" />
            <circle cx="10" cy="10" r="1.5" fill="rgba(0,229,255,0.9)" />
          </svg>
        </div>
      )}

      <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none' }}>
        <div style={XR_ROW}>
          <button style={XR_BTN} onClick={() => xrStore.enterVR()}>ENTER VR</button>
          <button style={XR_BTN} onClick={() => xrStore.enterAR()}>ENTER AR</button>
        </div>
      </div>
    </div>
  )
}
