import { C } from '../config'

export const DEFAULT_WIRE = {
  color: C.buildingWire,
  opacity: 0.18,
  wireframe: false,
  transparent: true,
  emissive: C.buildingWire,
  emissiveIntensity: 0.08,
  roughness: 0.8,
  metalness: 0.0,
}

export const HOVER_GHOST = {
  color: C.buildingEmit,
  opacity: 0.45,
  emissive: C.buildingWire,
  emissiveIntensity: 0.18,
  wireframe: false,
  transparent: true,
  roughness: 0.65,
  metalness: 0.0,
}

export const SELECTED_SOLID = {
  color: '#0a1a2a',
  opacity: 0.75,
  emissive: C.floorPlate,
  emissiveIntensity: 0.28,
  wireframe: false,
  transparent: true,
  roughness: 0.55,
  metalness: 0.0,
}

export const CLAIMED_MARKED = {
  color: '#071f24',
  opacity: 0.72,
  emissive: '#ff6d00',
  emissiveIntensity: 0.22,
  wireframe: false,
  transparent: true,
  roughness: 0.6,
  metalness: 0.05,
  markerColor: '#ff6d00',
}

export const DIM_CONTEXT = {
  color: '#062129',
  opacity: 0.22,
  emissive: C.buildingWire,
  emissiveIntensity: 0.04,
  wireframe: false,
  transparent: true,
  roughness: 0.9,
  metalness: 0.0,
}

export const ACTIVE_SLICED = {
  color: '#101036',
  opacity: 0.68,
  emissive: C.floorAccent,
  emissiveIntensity: 0.24,
  wireframe: false,
  transparent: true,
  roughness: 0.5,
  metalness: 0.0,
  markerColor: C.floorAccent,
}

export const COLOR_FIELD = {
  color: '#09283a',
  opacity: 0.46,
  emissive: '#001923',
  emissiveIntensity: 0.16,
  wireframe: false,
  transparent: true,
  roughness: 0.72,
  metalness: 0.0,
  palette: [
    '#00e5ff',
    '#0369a1',
    '#0f766e',
    '#4338ca',
    '#312e81',
    '#172554',
  ],
}

export const PLANE_WIRE = {
  color: '#061f2c',
  opacity: 0.34,
  emissive: C.buildingWire,
  emissiveIntensity: 0.1,
  wireframe: false,
  transparent: true,
  roughness: 0.82,
  metalness: 0.0,
}

export const DISTRICTS = {
  color: '#071a24',
  opacity: 0.68,
  emissive: '#001a26',
  emissiveIntensity: 0.2,
  wireframe: false,
  transparent: true,
  roughness: 0.76,
  metalness: 0.0,
  districtPalette: [
    '#07575f',
    '#0284c7',
    '#243c8f',
    '#4f46e5',
    '#1e3a5f',
    '#14705f',
  ],
  anomalyPalette: [
    '#b8f7ff',
    '#dbeafe',
    '#8b5cf6',
    '#f59e0b',
  ],
}

// TODO: Point-cloud building anomalies deferred until cleaner per-building metadata or dedicated point datasets are available.
export const POINT_ANOMALIES = {
  pointSize: 4.2,
  pointOpacity: 0.5,
  zoneSize: 420,
  zoneThreshold: 0.965,
  vertexThreshold: 0.58,
  sampleStride: 4,
  maxPoints: 60000,
  palette: [
    '#b8f7ff',
    '#dbeafe',
    '#67e8f9',
    '#2dd4bf',
    '#8b5cf6',
  ],
}

export const EMERGENCE = {
  color: '#063044',
  opacity: 0.42,
  emissive: C.buildingWire,
  emissiveIntensity: 0.16,
  wireframe: false,
  transparent: true,
  roughness: 0.78,
  metalness: 0.0,
  riseDistance: 34,
  duration: 3.2,
  waveDelay: 1.6,
}

export const BEACONS = {
  beamCount: 7,
  height: 1350,
  opacity: 0.18,
  colors: [
    '#b8f7ff',
    '#dbeafe',
    '#67e8f9',
    '#8b5cf6',
  ],
}

export const DEBUG_WIRE = {
  color: C.buildingWire,
  opacity: 0.55,
  wireframe: true,
  transparent: true,
  edgeColor: C.buildingWire,
}
