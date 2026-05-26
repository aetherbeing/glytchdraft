import { useEffect, useRef } from 'react'
import { useThree, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { NAVIGATION } from '../config'

const SENS      = 0.0022      // rad / px
const PITCH_MAX = Math.PI / 2 - 0.01
const EYE_MIN   = 1.7         // metres, absolute floor

// Pre-allocated to avoid per-frame allocations
const _dir   = new THREE.Vector3()
const _euler = new THREE.Euler()
const _up    = new THREE.Vector3(0, 1, 0)

export function FPVController({ active, onToggle }) {
  const { camera, gl } = useThree()

  // Refs so event listeners registered once always read current values
  const activeRef   = useRef(active)
  const onToggleRef = useRef(onToggle)
  useEffect(() => { activeRef.current = active },     [active])
  useEffect(() => { onToggleRef.current = onToggle }, [onToggle])

  const keys   = useRef({})
  const yaw    = useRef(0)
  const pitch  = useRef(0)
  const locked = useRef(false)
  const ready  = useRef(false)

  // Register all event listeners once
  useEffect(() => {
    const onKeyDown = e => {
      keys.current[e.code] = true

      if (e.code === 'KeyF' && !e.repeat) {
        const entering = !activeRef.current
        onToggleRef.current(entering)
        if (entering) {
          // requestPointerLock must happen in the user-gesture handler
          gl.domElement.requestPointerLock()
        } else {
          document.exitPointerLock()
          ready.current  = false
          keys.current   = {}
        }
      }
    }

    const onKeyUp = e => { delete keys.current[e.code] }

    const onMouseMove = e => {
      if (!locked.current || !activeRef.current) return
      yaw.current   -= e.movementX * SENS
      pitch.current -= e.movementY * SENS
      pitch.current  = Math.max(-PITCH_MAX, Math.min(PITCH_MAX, pitch.current))
    }

    const onLockChange = () => {
      locked.current = document.pointerLockElement === gl.domElement
    }

    // Re-lock on canvas click if FPV active but lock escaped (Esc key)
    const onClick = () => {
      if (activeRef.current && !locked.current) gl.domElement.requestPointerLock()
    }

    window.addEventListener('keydown',  onKeyDown)
    window.addEventListener('keyup',    onKeyUp)
    document.addEventListener('mousemove',          onMouseMove)
    document.addEventListener('pointerlockchange',  onLockChange)
    gl.domElement.addEventListener('click', onClick)

    return () => {
      window.removeEventListener('keydown',  onKeyDown)
      window.removeEventListener('keyup',    onKeyUp)
      document.removeEventListener('mousemove',         onMouseMove)
      document.removeEventListener('pointerlockchange', onLockChange)
      gl.domElement.removeEventListener('click', onClick)
    }
  }, [gl]) // stable — refs handle the rest

  useFrame((_, dt) => {
    if (!activeRef.current) return

    // Sync yaw/pitch from camera quaternion on first FPV frame
    if (!ready.current) {
      _euler.setFromQuaternion(camera.quaternion, 'YXZ')
      yaw.current   = _euler.y
      pitch.current = _euler.x
      ready.current = true
    }

    // Apply look direction (YXZ: yaw around world-Y, pitch around local-X)
    camera.rotation.order = 'YXZ'
    camera.rotation.y = yaw.current
    camera.rotation.x = pitch.current
    camera.rotation.z = 0

    const cdt    = Math.min(dt, 0.05)
    const fast = keys.current['ShiftLeft'] || keys.current['ShiftRight']
    const slow = keys.current['AltLeft'] || keys.current['AltRight'] ||
      keys.current['ControlLeft'] || keys.current['ControlRight']
    const mult = slow ? NAVIGATION.fpvSlowMultiplier : fast ? NAVIGATION.fpvFastMultiplier : 1
    const spd  = NAVIGATION.fpvMoveSpeed * mult * cdt
    const spdV = NAVIGATION.fpvMoveSpeed * 0.6 * mult * cdt

    // Horizontal WASD — move in the camera's horizontal plane
    _dir.set(0, 0, 0)
    if (keys.current['KeyW'] || keys.current['ArrowUp'])    _dir.z -= 1
    if (keys.current['KeyS'] || keys.current['ArrowDown'])  _dir.z += 1
    if (keys.current['KeyA'] || keys.current['ArrowLeft'])  _dir.x -= 1
    if (keys.current['KeyD'] || keys.current['ArrowRight']) _dir.x += 1
    if (_dir.lengthSq() > 0) {
      _dir.normalize().applyAxisAngle(_up, yaw.current)
      camera.position.addScaledVector(_dir, spd)
    }

    // Vertical — Space up, C / Ctrl down
    if (keys.current['Space'])                                      camera.position.y += spdV
    if (keys.current['KeyC'])                                      camera.position.y -= spdV

    if (camera.position.y < EYE_MIN) camera.position.y = EYE_MIN
  })

  return null
}
