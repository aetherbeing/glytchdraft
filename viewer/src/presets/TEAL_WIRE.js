/**
 * TEAL_WIRE — GlytchOS viewer preset
 * Captured: 2026-05-25
 *
 * Dark neon cyberpunk palette. Cyan wireframe buildings, purple→cyan floor
 * slices on hover/select, dark green terrain, translucent blue water, orange
 * additive point cloud. All values are exact snapshots from:
 *   src/config.js            → colors
 *   src/components/CityScene.jsx   → materials, lighting, fog
 *   src/components/FloorSlicer.jsx → floor plate behaviour
 *   src/components/AtmosphericPoints.jsx → point cloud material
 *   src/App.jsx              → camera, orbit controls
 */

export const TEAL_WIRE = {

  // ── Palette (src/config.js → C) ──────────────────────────────────────────
  colors: {
    bg:           '#080b0f',
    buildingWire: '#00e5ff',   // cyan neon — default wireframe
    buildingEmit: '#003d4f',   // dark teal — hover solid base color
    floorPlate:   '#7c3aed',   // purple — selected floor plate near
    floorAccent:  '#06b6d4',   // cyan — hover plates + selected far
    terrain:      '#0f2318',   // very dark green
    terrainWire:  '#1a472a',   // unused in current scene, kept for reference
    water:        '#0369a1',   // deep blue
    points:       '#ff6d00',   // orange — additive point cloud
    pointsB:      '#00e5ff',   // alternate points color (unused)
    hud:          'rgba(0,229,255,0.08)',
    hudBorder:    'rgba(0,229,255,0.25)',
    hudText:      '#00e5ff',
  },

  // ── Materials (src/components/CityScene.jsx → useMaterials) ──────────────
  materials: {
    buildingWire: {
      type:        'MeshBasicMaterial',
      color:       '#00e5ff',    // C.buildingWire
      wireframe:   true,
      transparent: true,
      opacity:     0.55,
    },
    buildingHover: {
      type:             'MeshStandardMaterial',
      color:            '#003d4f',  // C.buildingEmit
      emissive:         '#00e5ff',  // C.buildingWire
      emissiveIntensity: 0.18,
      transparent:      true,
      opacity:          0.45,
      side:             'DoubleSide',
    },
    buildingSelected: {
      type:             'MeshStandardMaterial',
      color:            '#0a1a2a',  // hardcoded dark navy
      emissive:         '#7c3aed',  // C.floorPlate
      emissiveIntensity: 0.28,
      transparent:      true,
      opacity:          0.75,
      side:             'DoubleSide',
    },
    buildingWireSelected: {
      type:        'MeshBasicMaterial',
      color:       '#06b6d4',   // C.floorAccent
      wireframe:   true,
      transparent: true,
      opacity:     0.9,
    },
    terrain: {
      type:      'MeshStandardMaterial',
      color:     '#0f2318',  // C.terrain
      roughness: 0.95,
      metalness: 0.0,
      side:      'DoubleSide',
    },
    water: {
      type:        'MeshStandardMaterial',
      color:       '#0369a1',  // C.water
      transparent: true,
      opacity:     0.30,
      roughness:   0.05,
      metalness:   0.4,
      side:        'DoubleSide',
    },
  },

  // ── Lighting (src/components/CityScene.jsx) ───────────────────────────────
  lighting: {
    ambient: {
      color:     '#203050',  // cool dark blue
      intensity: 0.15,
    },
    directional: [
      {
        position:  [2000, 800, -1000],
        intensity: 0.8,
        color:     '#80c0ff',  // cool blue — key light from SE
      },
      {
        position:  [-1000, 400, 2000],
        intensity: 0.3,
        color:     '#ff6d00',  // warm orange — fill from NW
      },
    ],
  },

  // ── Fog (src/components/CityScene.jsx) ────────────────────────────────────
  fog: {
    color: '#080b0f',  // matches bg exactly
    near:  3000,
    far:   18000,
  },

  // ── Floor slicer (src/components/FloorSlicer.jsx) ─────────────────────────
  floorSlicer: {
    floorHeight:     4,     // metres per floor (config.js FLOOR_HEIGHT)
    platesAbove:     20,    // config.js FLOOR_ABOVE
    platesBelow:     5,     // config.js FLOOR_BELOW
    hoverOpacity:    0.045,
    selectedOpacity: 0.10,
    lerpSpeed:       8,     // lerp factor in useFrame (8 * dt)
    // hover mode: solid cyan (C.floorAccent) at all plates
    // selected mode: purple (C.floorPlate) near → cyan (C.floorAccent) far
    depthWrite:      false,
    blending:        'NormalBlending',
    side:            'DoubleSide',
  },

  // ── Atmospheric point cloud (src/components/AtmosphericPoints.jsx) ────────
  points: {
    type:            'PointsMaterial',
    color:           '#ff6d00',  // C.points — orange
    size:            3.5,
    sizeAttenuation: true,
    transparent:     true,
    opacity:         0.22,
    depthWrite:      false,
    blending:        'AdditiveBlending',
  },

  // ── Camera & orbit controls (src/App.jsx) ─────────────────────────────────
  camera: {
    fov:      55,
    near:     1,
    far:      40000,
    // position expressed as offsets from SCENE center (cx=3500, cz=-2000)
    position: { dx: 400, y: 600, dz: 3200 },
    // resolved: [3900, 600, 1200]
  },

  orbit: {
    target:       [3500, 40, -2000],  // [SCENE.cx, 40, SCENE.cz]
    maxDistance:  15000,
    minDistance:  20,
    maxPolarAngle: Math.PI / 2 - 0.02,
    enableDamping: true,
    dampingFactor: 0.06,
    zoomSpeed:    1.4,
  },

}
