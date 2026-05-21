# POINT_CLOUD_VISIBILITY_NOTES

What we learned (the hard way) about rendering LiDAR-derived
point clouds in Blender. The same lessons apply to UE5, doubled.

---

## The core fact

A PLY imported into Blender 5.x via `wm.ply_import` creates a
**vertex-only mesh** — no faces, no edges. Vertex-only meshes:

- **Workbench / Solid shading**: render as small dots. Visible.
- **Material Preview**: invisible.
- **Rendered (EEVEE/Cycles)**: invisible.

This is *not* a bug. Eevee and Cycles render *primitives* (triangles).
Vertices without triangles have nothing to render. The workbench
viewport draws verts explicitly because workbench is a
debug/inspection renderer.

## What the headless renders looked like

The first renders in `data_processed/miami/hero_tile/renders/` were
done with the Workbench engine specifically so the point clouds would
show. The masses (which DO have faces) show in any engine. So the
images show buildings on a featureless gray field — the point clouds
are technically present as dots but the matcap shading makes them
hard to see at small sizes.

## To make point clouds render properly in Blender (when you want to)

**Option A: Geometry Nodes "Mesh to Points"**
1. Select the point-cloud object.
2. Properties → Modifiers → Add Modifier → Geometry Nodes.
3. New geometry node group. Add a "Mesh to Points" node, wire it.
4. Add a "Set Material" node, choose a small emissive material.
5. The mesh now renders as point primitives in Cycles + Eevee.

**Option B: Convert to instances of a small mesh**
1. Geometry Nodes → "Instance on Points" with an icosphere of radius
   0.05 m as the instance source.
2. Heavier but allows lit, shadowed point primitives.

**Option C: Use the Eevee point-cloud-specific shader (5.x)**
Blender 4.2+ has a `Point Info` node and partial native point-cloud
support. Investigate when actually needed.

For the MVP this was deliberately deferred. The masses carry visual
form; the point clouds are evidence/reserve.

## UE5 implications

UE5 has no "point cloud" primitive in the rendering pipeline. Every
visible thing is a triangle, an instanced mesh, a particle, or a
volumetric. Strategies for getting points into UE5:

1. **Niagara particles** — read positions from a CSV / data buffer,
   spawn one particle per point. Good up to ~1M particles. Material
   = simple emissive.
2. **Instanced Static Meshes (ISM / HISM)** — instance a tiny sphere
   per point. Heavier than Niagara but better at distance culling.
3. **Custom C++ point renderer** — full GPU buffer + custom material
   + view-dependent point size. Highest perf, highest cost.
4. **Pre-bake to a textured plane / heightfield** — convert the
   point cloud to a height-map or sparse RGB-texture-on-plane and
   skip points entirely. Loses 3D-ness but is fast.
5. **Use UE5.4+ "Cloud Particles"** in Niagara if available — newer
   versions have GPU-accelerated point rendering.

### Recommended deferred plan

- **Phase 1 (MVP):** no points. Masses only.
- **Phase 2:** add a Niagara emitter with the LOD2 (1 m) buildings
  PLY → CSV converted positions. 555K particles max. Toggleable.
- **Phase 3:** if needed, Niagara with LOD1 (0.5 m) or LOD0 (0.25 m)
  via streaming.

A PLY → CSV converter for UE Niagara consumption is trivial to
write when the time comes:

```python
import pdal, json, csv
pipeline = pdal.Pipeline(json.dumps({"pipeline": ["file.ply"]}))
pipeline.execute()
arr = pipeline.arrays[0]
with open("file.csv", "w") as f:
    w = csv.writer(f); w.writerow(["X","Y","Z","Cls"])
    for x,y,z,c in zip(arr["X"], arr["Y"], arr["Z"], arr["Classification"]):
        w.writerow([x, y, z, int(c)])
```

## The "you can see them at certain angles" thing

This was the user's observation on the Blender hero tile scene.
What they were seeing:

- At top-down angles, points dense over a small screen area = visible
  as dots
- At low oblique angles, the same points are at glancing angles
  where each dot's screen footprint is sub-pixel — invisible
- In rendered (non-Workbench) modes, never visible regardless

This isn't a defect in the data. It's the nature of single-pixel
point primitives. The fix is making points have *size* — Geometry
Nodes Mesh→Points with a non-zero radius, or instancing small
spheres, or using a shader that scales point size with distance.

## Don't:

- Import raw LAZ / LAS into UE5 in any phase
- Try to render all 4.9M buildings-LOD0 points in UE5 viewport-style
- Use raw vertex-only meshes for any visible asset in UE5

## Do:

- Treat the PLYs as **upstream data** that gets converted (CSV,
  Niagara binary, instance buffer) when you finally render them
- Default to **masses for the city** and **evidence for the
  optional reveal**
- Keep the point-cloud layer toggle disabled by default in UE5
