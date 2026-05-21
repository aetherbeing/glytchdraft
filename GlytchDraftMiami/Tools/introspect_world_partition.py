from pathlib import Path

import unreal

OUT = Path(unreal.Paths.project_dir()) / "world_partition_introspection.txt"
LINES = []

def log(value):
    LINES.append(str(value))
    unreal.log(str(value))

log(("WorldPartitionEditorSubsystem", hasattr(unreal, "WorldPartitionEditorSubsystem")))
if hasattr(unreal, "WorldPartitionEditorSubsystem"):
    obj = unreal.get_editor_subsystem(unreal.WorldPartitionEditorSubsystem)
    log([name for name in dir(obj) if "load" in name.lower() or "region" in name.lower() or "actor" in name.lower()])

log(("WorldPartitionBlueprintLibrary", hasattr(unreal, "WorldPartitionBlueprintLibrary")))
if hasattr(unreal, "WorldPartitionBlueprintLibrary"):
    log([name for name in dir(unreal.WorldPartitionBlueprintLibrary) if "load" in name.lower() or "actor" in name.lower()])
    for name in ["get_actor_descs", "load_actors", "get_intersecting_actor_descs"]:
        obj = getattr(unreal.WorldPartitionBlueprintLibrary, name)
        log((name, getattr(obj, "__doc__", None)))

log(("EditorActorSubsystem", hasattr(unreal, "EditorActorSubsystem")))
if hasattr(unreal, "EditorActorSubsystem"):
    obj = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    log([name for name in dir(obj) if "actor" in name.lower() or "level" in name.lower()])

OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
