// Scene coordinate extents (from GLB accessor bounds)
export const SCENE = {
  // Buildings LOD1 extents in GLB Y-up space
  xMin: -0,   xMax: 7661,
  yMin:  0,   yMax: 308,
  zMin: -4826, zMax: 949,
  // Convenient center
  cx: 3500, cy: 60, cz: -2000,
}

// GLB URL — served from public/models symlink
export const GLB_URL = '/models/MIAMI_BIKINI/MIAMI_BIKINI_LOD1.glb'

// Decimated point cloud (float32 XYZ, GLB-space coords)
export const POINTS_URL = '/models/building_points.f32'

export const ENABLE_VISUAL_LANGUAGE_PREVIEW = true
export const ENABLE_SCENE_FOG = false
export const ENABLE_FOG_TOGGLE = true

export const NAVIGATION = {
  orbitZoomSpeed: 2.5,
  orbitPanSpeed: 1.5,
  orbitRotateSpeed: 0.8,
  orbitMinDistance: 20,
  orbitMaxDistance: 12000,
  fpvMoveSpeed: 80,
  fpvFastMultiplier: 4,
  fpvSlowMultiplier: 0.25,
}

// Neon dark palette
export const C = {
  bg:           '#080b0f',
  buildingWire: '#00e5ff',   // cyan neon
  buildingEmit: '#003d4f',
  floorPlate:   '#7c3aed',   // purple
  floorAccent:  '#06b6d4',   // cyan
  terrain:      '#0f2318',
  terrainWire:  '#1a472a',
  water:        '#0369a1',
  points:       '#ff6d00',   // orange
  pointsB:      '#00e5ff',
  hud:          'rgba(0,229,255,0.08)',
  hudBorder:    'rgba(0,229,255,0.25)',
  hudText:      '#00e5ff',
}

// Floor plate spacing (meters)
export const FLOOR_HEIGHT = 4
export const FLOOR_ABOVE  = 20   // plates shown above hover Y
export const FLOOR_BELOW  = 5    // plates shown below hover Y
