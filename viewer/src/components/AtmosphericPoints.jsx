import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { POINTS_URL, C } from '../config'

export function AtmosphericPoints() {
  const pointsRef = useRef()
  const geoRef    = useRef(new THREE.BufferGeometry())

  useEffect(() => {
    let cancelled = false
    fetch(POINTS_URL)
      .then(r => r.arrayBuffer())
      .then(buf => {
        if (cancelled) return
        const f32 = new Float32Array(buf)
        geoRef.current.setAttribute('position', new THREE.BufferAttribute(f32, 3))
        if (pointsRef.current) pointsRef.current.geometry = geoRef.current
      })
      .catch(e => console.warn('point cloud load failed', e))
    return () => { cancelled = true }
  }, [])

  const material = useMemo(() => new THREE.PointsMaterial({
    color: new THREE.Color(C.points),
    size: 3.5,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.22,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  }), [])

  return (
    <points ref={pointsRef} geometry={geoRef.current} material={material} />
  )
}
