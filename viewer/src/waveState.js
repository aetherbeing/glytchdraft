import * as THREE from 'three'
import { SCENE } from './config'

// Mutated each frame by TileStreamer — read by all building shader uniforms and Minimap
export const WAVE_UNIFORMS = {
  uCamXZ: { value: new THREE.Vector2(SCENE.cx, SCENE.cz) },
  uWaveRadius: { value: 0 },
}

export const MINIMAP_DATA = {
  camX: SCENE.cx,
  camZ: SCENE.cz,
  waveRadius: 0,
}
