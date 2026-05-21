# PIPELINE

How raw city data becomes Blender-ready assets in GlytchDraft / Miami Slice.

The pipeline has two tracks that converge in Blender:

```
SHP / SHX / DBF / PRJ / CPG  ─┐
GeoJSON                       ├─► QGIS ─► reprojected + cleaned GeoJSON / GeoPackage / DXF / OBJ ─┐
                              │                                                                    │
LAS / LAZ / COPC ─────────────┴─► CloudCompare ─► cropped + decimated + colorized PLY / E57 / OBJ ─┴─► Blender
```

Everything flows **out of** `data_raw/` and **into** `data_processed/`. `data_raw/` is read-only by convention. If you need to fix a raw file, copy it first.

---

## Preservation rules (read before doing anything)

These are non-negotiable.

1. **Never overwrite a file in `data_raw/`.** Source data is the contract with reality. If you need to fix encoding, projection, or a typo, copy the file into a working folder first.
2. **Never reproject without recording it.** Every reprojection becomes a new file with the EPSG code in its name: `footprints_3857.geojson`, `tile_A_32617.laz`. The DATA_INVENTORY row gets an updated `source_crs` column for the new file.
3. **Never decimate the only copy.** A decimated point cloud is a derivative. Keep the full-density LAZ in `data_raw/` and put the thinned one in `cloudcompare_exports/` with a suffix like `_dec50.ply` (50% retained) or `_1m.ply` (1m subsampled).
4. **Never invent a CRS.** A shapefile without a `.prj` has no CRS. Mark it `companions: missing_prj` and stop. Find the source documentation before reprojecting.
5. **Never silently drop attributes.** When you export from QGIS, write the full attribute table even if Blender can't read it. The DBF / GeoJSON properties are the lore hooks — they will be read by the AI companion layer later.
6. **Document every coordinate shift.** If you translate a Blender scene's origin (you will — see BLENDER_IMPORT_NOTES), record the easting/northing translation in the scene's sidecar `.txt` so the shift is reversible.

---

## Track A — Vector data (SHP, GeoJSON) → QGIS → Blender

### A1. Stage
Put the file in `data_raw/<city>/shp/` or `data_raw/<city>/geojson/`. For shapefiles, **stage the whole set** (.shp, .shx, .dbf, .prj, .cpg, …). Run `python scripts/inspect_files.py data_raw/<city>/` to confirm the set is complete.

### A2. Open in QGIS
- New project → **Project → Properties → CRS** → pick the **target city CRS in meters** (Miami: `EPSG:32617`, LA: `EPSG:32611`).
- **Layer → Add Layer → Add Vector Layer**. Browse to the file.
- If QGIS asks "select transformation," accept the default unless you have a specific datum reason to override.
- Check the layer's CRS in the bottom-right of the canvas. If it differs from the project CRS, QGIS is reprojecting on the fly — that's fine for viewing, but exports below will force it to be permanent.

### A3. Inspect
- **Right-click layer → Open Attribute Table.** Confirm the schema matches what DATA_INVENTORY says.
- **Right-click layer → Properties → Information.** Note the source CRS, feature count, extent. Update DATA_INVENTORY.
- **Identify tool (i icon)** — click a feature, confirm coordinates look sane for the city.

### A4. Clean
Typical operations (use Processing Toolbox, search by name):
- **Reproject Layer** → output in the target UTM zone if not already.
- **Fix Geometries** → resolves self-intersections that will break Blender mesh import.
- **Clip** → keep only the area of interest (e.g., Brickell, South Beach, Hollywood).
- **Simplify Geometries** (Douglas-Peucker, tolerance in meters) — only for road or coastline densities that are absurdly heavy. Footprints: do not simplify.
- **Dissolve** → merge polygons by attribute (e.g., dissolve building footprints by block).

Save the cleaned result to `data_processed/<city>/qgis_exports/`. Name with the EPSG: `brickell_footprints_32617.geojson`.

### A5. Export for Blender
Three viable formats out of QGIS:

| format | how | when to use |
|---|---|---|
| **GeoJSON (UTM)** | `Export → Save Features As → GeoJSON`, CRS = target UTM | preferred — Blender's BlenderGIS addon reads it directly and preserves attributes |
| **DXF** | `Export → Save Features As → DXF` | when you want raw 2D linework; loses non-geometric attributes |
| **OBJ via extrusion** | `Processing → Extrude → 3D Vector → Save as OBJ` | when you want the footprints already extruded by a HEIGHT attribute |

Output goes to `data_processed/<city>/blender_ready/` once you confirm units are meters.

### A6. Hand off to Blender
See `BLENDER_IMPORT_NOTES.md` for the Blender-side steps. The contract from this track: **meters, target UTM zone, attributes preserved.**

---

## Track B — Point clouds (LAS, LAZ, COPC) → CloudCompare → Blender

### B1. Stage
Put the file in `data_raw/<city>/laz/` (or `/las/`). COPC `.copc.laz` files live with the LAZ.

### B2. Open in CloudCompare
- **File → Open** → select the LAZ. CloudCompare will show a "Global Shift / Scale" dialog because LiDAR coordinates are huge (Eastings in the hundreds of thousands, Northings in millions). **Accept the suggested shift** — it offsets the cloud to near-origin for floating-point precision. Write the offset down in a sidecar `.txt` (CloudCompare prints it in the console).
- After opening, click the cloud in the DB Tree → check the **Properties** panel for: point count, bounding box (in shifted coords), and the original CRS if embedded.

### B3. Inspect
- **Display → Color Scale** → set to height (Z) ramp. You will see the city in profile.
- Rotate (right-mouse drag). Confirm: ground is roughly flat, buildings stick up, no obvious artifacts.
- Note the point density: under "Properties → Average density" or by running `Tools → Other → Compute density`.

### B4. Crop
- **Tools → Segmentation → Segment** (or shortcut `S`).
- Draw a polygon around the area you actually need. Press `Spacebar` to confirm, then export the segmented result.
- Cropping is the **single highest-leverage operation** — a Miami-Dade LiDAR tile is gigabytes; the area you actually want for a Brickell scene might be 1/100 of that.

### B5. Decimate (point reduction)
You almost always need this for Blender. Choose one strategy:

| method | how | when |
|---|---|---|
| **Random subsample** | `Edit → Subsample → Random` → keep N% | quickest; uniform reduction |
| **Spatial subsample** | `Edit → Subsample → Spatial` → set min distance (e.g., 0.25 m, 0.5 m, 1.0 m) | preferred — preserves features, gives even density |
| **Octree level** | `Edit → Subsample → Octree` | when you need predictable cell sizes |

Spatial subsample at **0.5 m** is a reliable starting point for whole-block scenes. **0.1 m** for hero buildings. **2.0 m** for entire neighborhoods. Record the chosen spacing in the output filename: `brickell_block_0.5m.ply`.

### B6. Colorize (optional but recommended)
- If the LAZ has RGB: it's already colored. Confirm with `Edit → Colors → Convert → RGB`.
- If it has intensity but no RGB: `Edit → Colors → Convert → Intensity to RGB`. Cinematic. Slightly uncanny in a good way.
- If it has classifications (ground / building / vegetation): `Edit → Colors → Convert → Classification to RGB`. Useful for layer separation in Blender.

### B7. Export for Blender
| format | when |
|---|---|
| **PLY (binary)** | preferred — Blender reads it natively, keeps colors |
| **E57** | when you want to keep multiple scans + metadata in one file |
| **OBJ** | only when you've already meshed the cloud (`Plugins → PoissonRecon`) |

Save to `data_processed/<city>/cloudcompare_exports/` with the global shift recorded in a sidecar `.txt`. When you move to `blender_ready/`, you decide whether to keep the shift or undo it (usually keep — see BLENDER_IMPORT_NOTES).

### B8. Hand off to Blender
Contract: **meters, target UTM zone (or shifted UTM), color present, density appropriate to scene scale.**

---

## What can be simplified vs. what must be preserved

| layer | preserve | safe to simplify |
|---|---|---|
| building footprints | exact corners, hole geometry, attribute table | nothing — leave the polygons alone |
| roads | centerline topology, road class, name | densified vertices on long straight runs |
| coastline / waterways | shoreline form, named bodies | very high-frequency wiggle on cartoonish source data |
| terrain (DEM) | elevation values | resolution can be downsampled per scene |
| LiDAR — ground | density needed to read terrain | uniform decimation OK |
| LiDAR — buildings | edges, openings | bulk interior points (rare to need) |
| LiDAR — vegetation | volumetric "blob" | individual points — random decimation OK |
| symbolic / Order overlays | the alignment to real coords | the visual treatment (style per Order) |

---

## Converging in Blender

Both tracks should land in `data_processed/<city>/blender_ready/` with the same CRS and units. From there, `BLENDER_IMPORT_NOTES.md` takes over.

The handoff contract:
- Units: **meters**
- CRS: **city UTM zone**
- Origin shift (if any) is recorded in a sibling `.txt`
- Attribute tables are preserved (for vector) or color/classification channels are preserved (for point cloud)
- Filenames carry EPSG and density: `brickell_footprints_32617.geojson`, `brickell_block_32617_0.5m.ply`
