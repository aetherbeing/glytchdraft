@echo off
:: 08_run_blender_compare.bat
:: Builds miami_hero_tile_3dep_only_compare_v001.blend
:: NOTE: do NOT activate pdal_env -- Blender uses its own Python

set BLENDER_EXE="C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
set SCRIPT="C:\Users\Glytc\glytchdraft\scripts\3dep_only\08_build_blender_compare_scene.py"

echo === Step 08: build Blender comparison scene ===
%BLENDER_EXE% --background --python %SCRIPT%
if errorlevel 1 (
    echo Step 08 FAILED
    exit /b 1
)
echo Step 08 complete: blender\scenes\miami_hero_tile_3dep_only_compare_v001.blend
