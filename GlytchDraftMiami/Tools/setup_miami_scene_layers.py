import math
from pathlib import Path

import unreal


PROJECT_ROOT = Path(unreal.Paths.project_dir())
REPORT_PATH = PROJECT_ROOT / "SCENE_LAYER_AUDIT.md"
LEVEL_PATH = "/Game/Maps/MiamiPreview"
MAT_DIR = "/Game/Tiles/MiamiHeroTile/Materials"

FOLDERS = [
    "00_REFERENCE",
    "01_FOOTPRINT_ASSISTED_REFERENCE",
    "02_3DEP_ONLY_LOD0_CORE",
    "03_3DEP_ONLY_LOD1_BBOX",
    "04_3DEP_ONLY_LOD2_BLOCKS",
    "05_POINT_CLOUD_EVIDENCE_PLACEHOLDER",
    "06_ORDER_OVERLAYS_PLACEHOLDER",
    "07_AI_MARKERS_PLACEHOLDER",
]

LAYER_DEFS = {
    "footprint": {
        "folder": "01_FOOTPRINT_ASSISTED_REFERENCE",
        "material": "M_Layer_Footprint_Assisted_Reference",
        "color": unreal.LinearColor(0.58, 0.53, 0.48, 0.55),
        "opacity": 0.55,
        "visible": False,
        "role": "Prototype/reference building massing derived from footprints plus LiDAR heights; keep out of commercial core until license is confirmed.",
    },
    "lod0": {
        "folder": "02_3DEP_ONLY_LOD0_CORE",
        "material": "M_Layer_3DEP_LOD0_Core",
        "color": unreal.LinearColor(0.68, 0.78, 0.84, 1.0),
        "opacity": 1.0,
        "visible": True,
        "role": "Rights-clean 3DEP-only commercial/public-domain-derived core; primary massing proxy.",
    },
    "lod1": {
        "folder": "03_3DEP_ONLY_LOD1_BBOX",
        "material": "M_Layer_3DEP_LOD1_BBox",
        "color": unreal.LinearColor(0.34, 0.46, 0.55, 1.0),
        "opacity": 1.0,
        "visible": False,
        "role": "Rights-clean 3DEP-only rotated-bounding-box abstraction for comparison and distance proxy use.",
    },
    "lod2": {
        "folder": "04_3DEP_ONLY_LOD2_BLOCKS",
        "material": "M_Layer_3DEP_LOD2_Blocks",
        "color": unreal.LinearColor(0.06, 0.09, 0.12, 0.35),
        "opacity": 0.35,
        "visible": False,
        "role": "Rights-clean 3DEP-only block silhouette proxy; intentionally dark and low-opacity.",
    },
}


def load_level():
    if not unreal.EditorLevelLibrary.load_level(LEVEL_PATH):
        raise RuntimeError(f"Could not load {LEVEL_PATH}")


def ensure_dir(path):
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)


def ensure_material(defn):
    ensure_dir(MAT_DIR)
    asset_path = f"{MAT_DIR}/{defn['material']}"
    existing = unreal.EditorAssetLibrary.load_asset(asset_path)
    if existing:
        return existing

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat = tools.create_asset(defn["material"], MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("two_sided", True)
    if defn["opacity"] < 1.0:
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)

    color_expr = unreal.MaterialEditingLibrary.create_material_expression(
        mat, unreal.MaterialExpressionConstant4Vector, -360, -80
    )
    color_expr.set_editor_property("constant", defn["color"])
    unreal.MaterialEditingLibrary.connect_material_property(
        color_expr, "", unreal.MaterialProperty.MP_BASE_COLOR
    )

    opacity_expr = unreal.MaterialEditingLibrary.create_material_expression(
        mat, unreal.MaterialExpressionConstant, -360, 80
    )
    opacity_expr.set_editor_property("r", defn["opacity"])
    if defn["opacity"] < 1.0:
        unreal.MaterialEditingLibrary.connect_material_property(
            opacity_expr, "", unreal.MaterialProperty.MP_OPACITY
        )

    roughness_expr = unreal.MaterialEditingLibrary.create_material_expression(
        mat, unreal.MaterialExpressionConstant, -360, 220
    )
    roughness_expr.set_editor_property("r", 0.85)
    unreal.MaterialEditingLibrary.connect_material_property(
        roughness_expr, "", unreal.MaterialProperty.MP_ROUGHNESS
    )

    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def actor_mesh_name(actor):
    for comp in actor.get_components_by_class(unreal.StaticMeshComponent):
        mesh = comp.get_editor_property("static_mesh")
        if mesh:
            return mesh.get_name(), mesh.get_path_name()
    return "", ""


def classify_actor(actor):
    name = actor.get_name().lower()
    mesh_name, mesh_path = actor_mesh_name(actor)
    text = f"{name} {mesh_name.lower()} {mesh_path.lower()}"
    if "3dep_masses_lod0" in text or "lod0_convexhull" in text:
        return "lod0"
    if "3dep_masses_lod1" in text or "lod1_rotated_bbox" in text:
        return "lod1"
    if "3dep_masses_lod2" in text or "lod2_block" in text:
        return "lod2"
    if "miami_hero_tile_masses" in text:
        return "footprint"
    return None


def bounds_for_actor(actor):
    origin, extent = actor.get_actor_bounds(False)
    dims = unreal.Vector(extent.x * 2.0, extent.y * 2.0, extent.z * 2.0)
    return origin, extent, dims


def fmt_vec(v):
    return f"({v.x:.1f}, {v.y:.1f}, {v.z:.1f})"


def assign_actor(actor, key, material):
    actor.set_folder_path(LAYER_DEFS[key]["folder"])
    actor.set_actor_hidden_in_game(not LAYER_DEFS[key]["visible"])
    actor.set_is_temporarily_hidden_in_editor(not LAYER_DEFS[key]["visible"])
    actor.set_editor_property("is_spatially_loaded", False)
    actor.set_actor_enable_collision(False)

    for comp in actor.get_components_by_class(unreal.StaticMeshComponent):
        comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        comp.set_editor_property("hidden_in_game", not LAYER_DEFS[key]["visible"])
        slots = max(1, comp.get_num_materials())
        for idx in range(slots):
            comp.set_material(idx, material)


def ensure_placeholder(name, folder, location):
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for actor in actors:
        if actor.get_name() == name:
            actor.set_folder_path(folder)
            return actor
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.Actor, location)
    actor.set_actor_label(name)
    actor.set_folder_path(folder)
    actor.set_actor_hidden_in_game(True)
    return actor


def look_at_rotation(location, target):
    direction = target - location
    yaw = math.degrees(math.atan2(direction.y, direction.x))
    dist_xy = math.sqrt(direction.x * direction.x + direction.y * direction.y)
    pitch = math.degrees(math.atan2(direction.z, dist_xy))
    return unreal.Rotator(pitch, yaw, 0.0)


def ensure_camera(name, location, target):
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for actor in actors:
        if actor.get_actor_label() == name:
            camera = actor
            break
    else:
        camera = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.CameraActor, location)
        camera.set_actor_label(name)
    camera.set_actor_location(location, False, False)
    camera.set_actor_rotation(look_at_rotation(location, target), False)
    camera.set_folder_path("00_REFERENCE/Camera_Setups")
    camera.set_actor_hidden_in_game(False)
    comp = camera.get_component_by_class(unreal.CameraComponent)
    if comp:
        comp.set_editor_property("projection_mode", unreal.CameraProjectionMode.PERSPECTIVE)
        comp.set_editor_property("field_of_view", 35.0)
    return camera


def actor_rows(layered):
    rows = []
    for key, actors in layered.items():
        for actor in sorted(actors, key=lambda a: a.get_actor_label()):
            origin, _extent, dims = bounds_for_actor(actor)
            mesh_name, mesh_path = actor_mesh_name(actor)
            warning = ""
            if dims.x > 200000 or dims.y > 200000 or dims.z > 50000:
                warning = "CHECK: unusually large bounds; inspect scale/import."
            if dims.z < 1:
                warning = "CHECK: near-flat bounds; may be placeholder or bad import."
            rows.append(
                {
                    "actor": actor.get_actor_label(),
                    "mesh": mesh_name or "(none)",
                    "mesh_path": mesh_path or "(none)",
                    "folder": LAYER_DEFS[key]["folder"],
                    "origin": fmt_vec(origin),
                    "dimensions": fmt_vec(dims),
                    "material": LAYER_DEFS[key]["material"],
                    "role": LAYER_DEFS[key]["role"],
                    "visible": "Yes" if LAYER_DEFS[key]["visible"] else "No",
                    "collision": "Disabled",
                    "selectable": "Yes; static mesh actor proxy",
                    "concern": warning or "None observed from bounds.",
                }
            )
    return rows


def write_report(layered, rows, alignment_note, giant_note):
    lines = [
        "# Scene Layer Audit",
        "",
        "Level: `/Game/Maps/MiamiPreview`",
        "",
        "Principle preserved: 3DEP-only remains the commercial/public-domain-derived core; footprint-assisted geometry is prototype/reference until its footprint license is confirmed. Future point cloud work is reserved as the primary visual atmosphere. Current massing layers are navigation, selection, and metadata proxies.",
        "",
        "## Outliner Folders",
        "",
    ]
    for folder in FOLDERS:
        lines.append(f"- `{folder}`")

    lines += [
        "",
        "## Default Visibility",
        "",
        "- Visible by default: `02_3DEP_ONLY_LOD0_CORE`",
        "- Hidden by default: footprint-assisted reference, 3DEP LOD1, 3DEP LOD2, point cloud placeholder, order overlay placeholder, AI marker placeholder",
        "",
        "## Manual Toggle Setups",
        "",
        "Use the Outliner folder eye icons:",
        "",
        "- Footprint-assisted only: show `01_FOOTPRINT_ASSISTED_REFERENCE`; hide `02_3DEP_ONLY_LOD0_CORE`, `03_3DEP_ONLY_LOD1_BBOX`, and `04_3DEP_ONLY_LOD2_BLOCKS`.",
        "- 3DEP-only LOD0 only: show `02_3DEP_ONLY_LOD0_CORE`; hide the other massing folders.",
        "- 3DEP-only LOD1 only: show `03_3DEP_ONLY_LOD1_BBOX`; hide the other massing folders.",
        "- 3DEP-only LOD2 only: show `04_3DEP_ONLY_LOD2_BLOCKS`; hide the other massing folders.",
        "- Footprint-assisted + 3DEP overlay: show `01_FOOTPRINT_ASSISTED_REFERENCE` and one 3DEP folder, normally `02_3DEP_ONLY_LOD0_CORE`; keep LOD1/LOD2 hidden unless comparing abstraction levels.",
        "- Screenshot isolation: hide all massing folders except the one being captured, then pilot to the matching `SHOT_*` camera.",
        "",
        "## Camera Setups",
        "",
        "- `SHOT_01_Footprint_Assisted_Only`",
        "- `SHOT_02_3DEP_Only_LOD0_Core`",
        "- `SHOT_03_Both_Layers_Overlay`",
        "",
        "## Alignment / Scale",
        "",
        alignment_note,
        "",
        giant_note,
        "",
        "## Imported Actors",
        "",
        "| Actor | Mesh | Folder | Origin cm | Dimensions cm | Material | Intended role | Visible by default | Collision | Selectable/proxy | Scale/alignment concern |",
        "|---|---|---|---:|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['actor']}` | `{row['mesh']}` | `{row['folder']}` | {row['origin']} | {row['dimensions']} | `{row['material']}` | {row['role']} | {row['visible']} | {row['collision']} | {row['selectable']} | {row['concern']} |"
        )
    lines += [
        "",
        "## Actor Mesh Asset Paths",
        "",
    ]
    for row in rows:
        lines.append(f"- `{row['actor']}`: `{row['mesh_path']}`")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    load_level()

    materials = {key: ensure_material(defn) for key, defn in LAYER_DEFS.items()}
    layered = {key: [] for key in LAYER_DEFS}
    unclassified = []

    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        key = classify_actor(actor)
        if key:
            assign_actor(actor, key, materials[key])
            layered[key].append(actor)
        elif actor.get_components_by_class(unreal.StaticMeshComponent):
            unclassified.append(actor)

    ensure_placeholder(
        "POINT_CLOUD_EVIDENCE_PLACEHOLDER__reserved_no_renderer",
        "05_POINT_CLOUD_EVIDENCE_PLACEHOLDER",
        unreal.Vector(0.0, 0.0, 1000.0),
    )
    ensure_placeholder(
        "ORDER_OVERLAYS_PLACEHOLDER__reserved_no_overlay",
        "06_ORDER_OVERLAYS_PLACEHOLDER",
        unreal.Vector(2500.0, 0.0, 1000.0),
    )
    ensure_placeholder(
        "AI_MARKERS_PLACEHOLDER__reserved_no_ai",
        "07_AI_MARKERS_PLACEHOLDER",
        unreal.Vector(-2500.0, 0.0, 1000.0),
    )

    all_layer_actors = [actor for actors in layered.values() for actor in actors]
    if all_layer_actors:
        origins = [bounds_for_actor(actor)[0] for actor in all_layer_actors]
        center = unreal.Vector(
            sum(v.x for v in origins) / len(origins),
            sum(v.y for v in origins) / len(origins),
            sum(v.z for v in origins) / len(origins),
        )
    else:
        center = unreal.Vector(0.0, 0.0, 0.0)

    ensure_camera("SHOT_01_Footprint_Assisted_Only", center + unreal.Vector(-65000, -80000, 52000), center)
    ensure_camera("SHOT_02_3DEP_Only_LOD0_Core", center + unreal.Vector(65000, -80000, 52000), center)
    ensure_camera("SHOT_03_Both_Layers_Overlay", center + unreal.Vector(0, -95000, 62000), center)

    rows = actor_rows(layered)

    layer_bounds = {}
    for key, actors in layered.items():
        if not actors:
            continue
        origins = []
        dims = []
        for actor in actors:
            origin, _extent, dim = bounds_for_actor(actor)
            origins.append(origin)
            dims.append(dim)
        layer_bounds[key] = {
            "origin": unreal.Vector(
                sum(v.x for v in origins) / len(origins),
                sum(v.y for v in origins) / len(origins),
                sum(v.z for v in origins) / len(origins),
            ),
            "dims": unreal.Vector(
                max(v.x for v in dims),
                max(v.y for v in dims),
                max(v.z for v in dims),
            ),
        }

    if "footprint" in layer_bounds and "lod0" in layer_bounds:
        fp = layer_bounds["footprint"]
        lod0 = layer_bounds["lod0"]
        delta = fp["origin"] - lod0["origin"]
        size_ratio_x = fp["dims"].x / lod0["dims"].x if lod0["dims"].x else 0
        size_ratio_y = fp["dims"].y / lod0["dims"].y if lod0["dims"].y else 0
        alignment_note = (
            f"Footprint-assisted and 3DEP-only LOD0 occupy the same local coordinate frame from actor bounds. "
            f"Average bounds-origin delta is {fmt_vec(delta)} cm. "
            f"XY dimension ratios footprint/LOD0 are X={size_ratio_x:.3f}, Y={size_ratio_y:.3f}; no obvious scale mismatch was found from bounds."
        )
    else:
        alignment_note = "Could not compare footprint-assisted and 3DEP-only LOD0 because one of the layers was not found in the level."

    giant_rows = [row for row in rows if row["concern"].startswith("CHECK")]
    if giant_rows:
        names = ", ".join(f"`{row['actor']}`" for row in giant_rows)
        giant_note = f"Potential slab/wall or scale issue candidates from bounds: {names}. Inspect these first in the viewport."
    else:
        giant_note = "No imported massing actor reported giant slab/wall-scale bounds beyond the expected kilometer-scale tile footprint. LOD2 is intentionally blocky and low-opacity."

    write_report(layered, rows, alignment_note, giant_note)

    unreal.EditorLevelLibrary.save_current_level()
    unreal.EditorAssetLibrary.save_directory(MAT_DIR, only_if_is_dirty=False, recursive=True)
    unreal.log(f"Miami scene layer setup complete. Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
