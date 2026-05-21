@echo off
REM Launch Blender 5.1 headless, run the scene-build script.
REM We must NOT activate the pdal_env conda env here — Blender ships its
REM own Python and gets confused if outer env Python comes first on PATH.

set BLENDER_EXE="C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
set SCRIPT="C:\Users\Glytc\glytchdraft\scripts\hero_tile\05_build_blender_scene.py"

%BLENDER_EXE% --background --python %SCRIPT%
