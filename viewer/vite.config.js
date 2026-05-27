import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { basename } from 'node:path'
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs'

const MIAMI_GLB_PATHS = [
  '/mnt/t7/miami/data_processed/miami_city/blender_ready/miami.glb',
  'E:/miami/data_processed/miami_city/blender_ready/miami.glb',
]

const MIAMI_TILE_ROOTS = [
  '/mnt/t7/miami/data_processed/miami_city/tiles',
  'E:/miami/data_processed/miami_city/tiles',
]

const MIAMI_TILE_MANIFEST_PATHS = [
  '/mnt/t7/miami/data_processed/miami_city/tile_manifest.json',
  'E:/miami/data_processed/miami_city/tile_manifest.json',
]

const MIAMI_CITY_OFFSET_PATHS = [
  '/mnt/t7/miami/data_processed/miami_city/blender_ready/miami_glb_offset.json',
  'E:/miami/data_processed/miami_city/blender_ready/miami_glb_offset.json',
]

function resolveExisting(paths) {
  return paths.find(path => existsSync(path)) ?? paths[0]
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

function readGlbJson(path) {
  const glb = readFileSync(path)
  const jsonLength = glb.readUInt32LE(12)
  return JSON.parse(glb.subarray(20, 20 + jsonLength).toString('utf8'))
}

function safeTileId(id) {
  return /^[A-Za-z0-9_.-]+$/.test(id) ? id : null
}

function tileGlbPath(tileRoot, tileId) {
  return `${tileRoot}/${tileId}/blender_ready/${tileId}.glb`
}

function tileOffsetPath(tileRoot, tileId) {
  return `${tileRoot}/${tileId}/blender_ready/${tileId}_glb_offset.json`
}

function tileManifestPath(tileRoot, tileId) {
  return `${tileRoot}/${tileId}/manifest/${tileId}_manifest.json`
}

function normalizeBbox4326(value) {
  if (!value) return null
  const arrayValue = Array.isArray(value)
    ? value
    : Array.isArray(value.bbox)
      ? value.bbox
      : Array.isArray(value.coordinates)
        ? value.coordinates
        : null
  const minValue = value.min ?? value.minimum
  const maxValue = value.max ?? value.maximum
  const xmin = Number(value.xmin ?? value.min_lon ?? value.west ?? value[0] ?? arrayValue?.[0] ?? minValue?.[0])
  const ymin = Number(value.ymin ?? value.min_lat ?? value.south ?? value[1] ?? arrayValue?.[1] ?? minValue?.[1])
  const xmax = Number(value.xmax ?? value.max_lon ?? value.east ?? value[2] ?? arrayValue?.[2] ?? maxValue?.[0])
  const ymax = Number(value.ymax ?? value.max_lat ?? value.north ?? value[3] ?? arrayValue?.[3] ?? maxValue?.[1])
  if (![xmin, ymin, xmax, ymax].every(Number.isFinite)) return null
  return { xmin, ymin, xmax, ymax }
}

function tileManifestBbox(tileRoot, tileId) {
  const path = tileManifestPath(tileRoot, tileId)
  if (!existsSync(path)) return null
  const manifest = readJson(path)
  return normalizeBbox4326(
    manifest.bbox_4326 ??
    manifest.bbox4326 ??
    manifest.bounds_4326 ??
    manifest.bounds?.bbox_4326
  )
}

function geoExtent(tiles) {
  const boxes = tiles.map(tile => normalizeBbox4326(tile.bbox_4326)).filter(Boolean)
  if (!boxes.length) return null
  return boxes.reduce((extent, bbox) => ({
    xmin: Math.min(extent.xmin, bbox.xmin),
    ymin: Math.min(extent.ymin, bbox.ymin),
    xmax: Math.max(extent.xmax, bbox.xmax),
    ymax: Math.max(extent.ymax, bbox.ymax),
  }), { ...boxes[0] })
}

function lerp(a, b, t) {
  return a + (b - a) * t
}

function mapRange(value, inMin, inMax, outMin, outMax) {
  if (inMax === inMin) return (outMin + outMax) / 2
  return lerp(outMin, outMax, (value - inMin) / (inMax - inMin))
}

function bboxToCullBounds(bbox, extent, sceneBounds) {
  if (!bbox || !extent) return null
  const x0 = mapRange(bbox.xmin, extent.xmin, extent.xmax, sceneBounds.min[0], sceneBounds.max[0])
  const x1 = mapRange(bbox.xmax, extent.xmin, extent.xmax, sceneBounds.min[0], sceneBounds.max[0])
  const z0 = mapRange(bbox.ymin, extent.ymin, extent.ymax, sceneBounds.max[2], sceneBounds.min[2])
  const z1 = mapRange(bbox.ymax, extent.ymin, extent.ymax, sceneBounds.max[2], sceneBounds.min[2])

  return {
    min: [Math.min(x0, x1), sceneBounds.min[1], Math.min(z0, z1)],
    max: [Math.max(x0, x1), sceneBounds.max[1], Math.max(z0, z1)],
    source: 'bbox_4326',
  }
}

function sourceToSceneBounds(localMin, localMax, tileOffset, cityOffset) {
  const position = [
    tileOffset.shift_x - cityOffset.shift_x,
    tileOffset.shift_z - cityOffset.shift_z,
    -(tileOffset.shift_y - cityOffset.shift_y),
  ]

  return {
    min: [position[0] + localMin[0], position[1] + localMin[1], position[2] + localMin[2]],
    max: [position[0] + localMax[0], position[1] + localMax[1], position[2] + localMax[2]],
    position,
    inferred: false,
  }
}

function inferTileBounds(index) {
  const tileSize = 1523.5
  const cols = 10
  const col = index % cols
  const row = Math.floor(index / cols)
  const x0 = col * tileSize
  const z1 = -row * tileSize
  const z0 = z1 - tileSize
  return {
    min: [x0, -20, z0],
    max: [x0 + tileSize, 320, z1],
    position: [x0, 0, z0],
    inferred: true,
  }
}

function buildStreamingManifest() {
  const manifestPath = resolveExisting(MIAMI_TILE_MANIFEST_PATHS)
  const tileRoot = resolveExisting(MIAMI_TILE_ROOTS)
  const cityOffset = readJson(resolveExisting(MIAMI_CITY_OFFSET_PATHS))
  const source = readJson(manifestPath)
  const sourceTiles = Array.isArray(source)
    ? source
    : Array.isArray(source.tiles)
      ? source.tiles
      : Array.isArray(source.tile_manifest?.tiles)
        ? source.tile_manifest.tiles
        : Array.isArray(source.tile_manifest)
          ? source.tile_manifest
          : []
  const extent = geoExtent(sourceTiles)
  const sceneBounds = {
    min: [0, -21, -18282],
    max: [15235, 313, 0],
  }

  const tiles = sourceTiles.map((tile, index) => {
    const tileId = tile.tile_id
    const glbPath = tileGlbPath(tileRoot, tileId)
    const offsetPath = tileOffsetPath(tileRoot, tileId)
    let bounds = inferTileBounds(index)
    const hasGlb = existsSync(glbPath)
    const perTileBbox = tileManifestBbox(tileRoot, tileId)
    const bbox4326 = perTileBbox ?? normalizeBbox4326(tile.bbox_4326)

    if (hasGlb && existsSync(offsetPath)) {
      const gltf = readGlbJson(glbPath)
      const accessorIndex = gltf.meshes?.[0]?.primitives?.[0]?.attributes?.POSITION
      const accessor = gltf.accessors?.[accessorIndex]
      if (accessor?.min && accessor?.max) {
        bounds = sourceToSceneBounds(accessor.min, accessor.max, readJson(offsetPath), cityOffset)
      }
    }

    return {
      tile_id: tileId,
      url: `/models/tiles/${tileId}.glb`,
      has_glb: hasGlb,
      bbox_4326: bbox4326,
      bbox_source: perTileBbox ? 'tile_manifest' : tile.bbox_source ?? 'city_tile_manifest',
      bounds,
      cull_bounds: bboxToCullBounds(bbox4326, extent, sceneBounds),
      center: [
        (bounds.min[0] + bounds.max[0]) / 2,
        (bounds.min[1] + bounds.max[1]) / 2,
        (bounds.min[2] + bounds.max[2]) / 2,
      ],
    }
  })

  return {
    schema_version: '1.0',
    source: basename(manifestPath),
    count: tiles.length,
    max_streamed_tiles: 10,
    tiles,
  }
}

function handleBinaryFile(req, res, path) {
  const stat = statSync(path)
  const range = req.headers.range

  res.setHeader('Accept-Ranges', 'bytes')
  res.setHeader('Content-Type', 'model/gltf-binary')
  res.setHeader('Cache-Control', 'no-store')

  if (range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(range)
    if (!match) {
      res.statusCode = 416
      res.end()
      return
    }

    const start = match[1] ? Number(match[1]) : 0
    const end = match[2] ? Number(match[2]) : stat.size - 1
    if (start >= stat.size || end >= stat.size || start > end) {
      res.statusCode = 416
      res.setHeader('Content-Range', `bytes */${stat.size}`)
      res.end()
      return
    }

    res.statusCode = 206
    res.setHeader('Content-Range', `bytes ${start}-${end}/${stat.size}`)
    res.setHeader('Content-Length', end - start + 1)
    createReadStream(path, { start, end }).pipe(res)
    return
  }

  res.setHeader('Content-Length', stat.size)
  createReadStream(path).pipe(res)
}

function handleMiamiGlb(req, res) {
  handleBinaryFile(req, res, resolveExisting(MIAMI_GLB_PATHS))
}

function handleTileGlb(req, res) {
  const rawId = decodeURIComponent(req.url.split('/').pop()?.replace(/\.glb$/, '') ?? '')
  const tileId = safeTileId(rawId)
  if (!tileId) {
    res.statusCode = 400
    res.end('invalid tile id')
    return
  }

  const glbPath = tileGlbPath(resolveExisting(MIAMI_TILE_ROOTS), tileId)
  if (!existsSync(glbPath)) {
    res.statusCode = 404
    res.end('tile glb not found')
    return
  }

  handleBinaryFile(req, res, glbPath)
}

function handleTileManifest(_req, res) {
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'no-store')
  res.end(JSON.stringify(buildStreamingManifest()))
}

function serveMiamiModels() {
  return {
    name: 'serve-miami-models',
    configureServer(server) {
      server.middlewares.use('/models/miami.glb', handleMiamiGlb)
      server.middlewares.use('/models/tiles', handleTileGlb)
      server.middlewares.use('/models/tile_manifest.json', handleTileManifest)
    },
    configurePreviewServer(server) {
      server.middlewares.use('/models/miami.glb', handleMiamiGlb)
      server.middlewares.use('/models/tiles', handleTileGlb)
      server.middlewares.use('/models/tile_manifest.json', handleTileManifest)
    },
  }
}

export default defineConfig({
  plugins: [react(), serveMiamiModels()],
  server: {
    fs: { allow: ['..', '/mnt/t7'] },
  },
  assetsInclude: ['**/*.f32', '**/*.glb'],
})
