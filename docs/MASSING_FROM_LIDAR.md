# MASSING_FROM_LIDAR

How the GlytchDraft pipeline turns 2,819 building footprints + 4.9 M
building-class LiDAR points + 2.3 M ground-class LiDAR points into a
lightweight extruded-prism mesh that can stand in for the city in
navigation, BIM workflows, and the AI Companion layer.

Implementation: `scripts/hero_tile/04_building_masses.py`.

Outputs (in `data_processed/miami/hero_tile/blender_ready/masses/`):
- `hero_tile_building_masses_LOD0_individual.obj`
- `hero_tile_building_masses_LOD1_simplified.obj`
- `hero_tile_building_masses_metadata.geojson`

---

## Inputs

| Input | Source | CRS | What we read |
|---|---|---|---|
| Footprints | `footprints/hero_tile_footprints_32617.geojson` | EPSG:32617 | exterior ring of every Polygon |
| Building points | `pointcloud/hero_tile_building_32617_0p25m.ply` | EPSG:32617 | X, Y, Z |
| Ground points | `pointcloud/hero_tile_ground_32617_1m.ply` | EPSG:32617 | X, Y, Z |

All three are already in the project's metric CRS, so we can run
spatial joins directly without per-feature reprojection.

---

## The algorithm

For each footprint polygon $P$:

```
1. ESTIMATE GROUND_Z
   - Buffer P outward by 5 m to make a ring R = buffer(P, 5) \ P
   - Find ground-class points inside R
   - ground_z = median(z_i)  for those points
   - If R has no ground points (rare; happens at the tile edge):
       ground_z = median(z) of the nearest 8 ground points
         (KD-tree query at the polygon centroid)

2. FIND BUILDING POINTS INSIDE THE FOOTPRINT
   - KD-tree query on the polygon's bounding-circle radius
   - exact point-in-polygon test using shapely.prepared.prep(P).contains_properly
   - call the result inside (an N x 3 array)

3. CLASSIFY THE FOOTPRINT BY HOW MUCH EVIDENCE IT HAS
   - source_quality = "good"     if len(inside) >= 8 (default threshold)
   - source_quality = "sparse"   if 0 < len(inside) < 8
   - source_quality = "fallback" if len(inside) == 0  (no building points)
   - source_quality = "empty"    if KD-tree found NO building points
                                  within the search radius — usually means
                                  the footprint is at the tile edge

4. COMPUTE HEIGHT STATS
   - height_p50  = percentile(inside.z, 50)
   - height_p90  = percentile(inside.z, 90)   <-- PRIMARY: see below
   - height_max  = max(inside.z)
   - estimated_height = max(0.0, height_p90 - ground_z)

5. EXTRUDE
   - LOD0: exact footprint polygon, top z = height_p90, bottom z = ground_z
   - LOD1: minimum-rotated-rectangle of the footprint, same z range
   - footprints with source_quality "empty" are EXCLUDED from the OBJs
   - footprints with source_quality "fallback" are EXCLUDED from the OBJs
     (the GeoJSON keeps them so the agent layer can decide what to do)
```

---

## Why `p90`, not `max`

LiDAR returns over a building include:

- **Real roof points** (the bulk of the cloud — these are what we want)
- **Antennas, satellite dishes, parapet equipment** — real but tall
  and not representative of the building's mass
- **Cranes, scaffolding** at the time of capture — temporary
- **Bird, debris, or other airborne returns** mis-classified as
  building — noise

`max_z` is the tallest point of any of the above. For 90% of
buildings it's fine; for the other 10%, it makes the building 15-30 m
taller than it actually is. The penthouse with a 12 m antenna becomes
a 12 m taller penthouse.

`p90_z` (the 90th percentile of point heights inside the footprint)
treats the top 10% of points as noise and reports the height that
**90% of the cloud is at or below**. That's the building's true mass
top. Visually, it looks correct on almost every building.

We still **record** `max_z` in metadata so any future agent that wants
the literal-tallest-point can ask for it explicitly. We just don't
**use** it for the extruded mesh.

---

## Why ground from a **ring**, not from inside

Inside a footprint is the building. Any ground points inside the
footprint are misclassified (or are basement floors visible through
windows in some weird LiDAR scans — rare).

A 5 m ring around the footprint:

- captures the actual surrounding terrain
- is small enough to not pick up the next building over (usually)
- handles sloped sites: the median z of the ring is a stable estimate
  of "what's the ground right next to this building?"
- gracefully degrades — if a footprint is at the tile edge with no
  ring coverage, the fallback is the nearest 8 ground points overall

A 5 m buffer is a project-wide constant. For a denser-than-Miami
city (e.g. Manhattan), 2-3 m would be more appropriate to avoid
catching adjacent building footprints' ring points. For a sparser
city, 10 m. Adjustable in the script as `RING_BUFFER_M`.

---

## `source_quality` field

Reported in the metadata GeoJSON. Drives downstream agent behavior.

| Value | Meaning | Use in renders / agents |
|---|---|---|
| `good` | ≥ 8 building points inside the footprint | safe to render LOD0; agent can quote heights confidently |
| `sparse` | 1–7 building points inside | LOD0 OK but heights are noisy; mark with "approximate" if quoted |
| `fallback` | 0 points inside, but the footprint exists in the source SHP | NOT rendered in LOD0; consider showing as a flat outline at ground_z. Often a small structure (shed, awning) the LiDAR missed |
| `empty` | KD-tree search radius found no nearby building points at all | NOT rendered; usually at the tile boundary. The Data Steward should flag these to `project_memory.known_gaps` |

The Architectural Envisioner agent (`ai/agents/architectural_envisioner.md`)
already follows the rule "mark every assumption explicitly." When it
references a building's height, it should check
`source_quality` first and:

- `good` → quote the height as a fact
- `sparse` → quote with "approximately"
- `fallback` / `empty` → say "height is unknown; the data didn't capture
  this footprint"

The Data Steward (`ai/agents/data_steward.md`) audits these.

---

## Handling polygons with no building points

Three cases, three responses:

1. **Tiny footprint missed by LiDAR classification** (shed, porch,
   gazebo). Often classified as vegetation or unclassified rather
   than building, even though the structure exists. The default
   fallback height (`DEFAULT_FALLBACK_HEIGHT = 6.0 m`) is reasonable
   for these but is not applied to LOD0 — we'd rather show nothing
   than fabricate. The GeoJSON still carries the polygon so the
   Field Guide can describe "there is something here at ground
   level, height unknown."

2. **Demolished building still in the SHP** (the SHP is from 2018;
   the LiDAR is later). No building points because there is no
   building. Treat as `fallback` and trust the LiDAR. A future
   pipeline could explicitly **remove** the footprint from the
   rendered set, but for now we keep it in metadata for traceability
   and exclude it from the OBJ.

3. **Tile-edge footprint with no LiDAR coverage at all.** Marked
   `empty`. Excluded from rendering. Flagged for the Data Steward.

The metadata GeoJSON is the audit trail: every footprint accounted
for, every decision recorded.

---

## Roof complexity (optional, future)

The schema reserves a `roof_complexity_score` field. Computation
options:

- **Z stdev of building points inside**: `np.std(inside.z)`. Roof
  with parapet + clerestory + dome → high stdev. Flat warehouse roof
  → low stdev.
- **Range / mean ratio**: scale-independent — useful for comparing a
  small house with a varied roof against a large flat warehouse.

Not in the current pipeline. Easy to add when needed. Would help the
LOD2 simplifier decide which buildings deserve a more elaborate
silhouette card vs. a plain box.

---

## Computational profile

For the hero tile:

- footprints: 2,819
- building points: 4.9 M
- ground points: 2.3 M
- KD-tree builds: ~5 s each
- per-footprint pass: ~2 s for all 2,819 polygons
- OBJ write: ~3 s
- total runtime: well under 30 s end-to-end on a typical desktop CPU

The 2D bounding-circle KD-tree query is the right shape — we don't
need a full 3D tree because the polygon contains-test is 2D and z
becomes a statistic after we have the membership mask.

---

## Future moves

- **Roof types.** Pitched vs. flat: detect by per-footprint z
  variance and skew. Generate a pitched-roof prism (gable / hip)
  instead of a flat top.
- **Building-merging at LOD2.** Cluster adjacent footprints into
  blocks; produce one prism per block. Cheaper for the skyline tier.
- **Per-floor decomposition.** Long-term — for the Architectural
  Envisioner to propose floor-by-floor interventions.
- **DEM integration.** When a real DEM is staged, ground_z can come
  from the DEM directly rather than from LiDAR ring points. Faster
  and more uniform.
