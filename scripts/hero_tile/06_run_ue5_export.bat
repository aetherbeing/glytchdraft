@echo off
set BLENDER_EXE="C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
set SCRIPT="C:\Users\Glytc\glytchdraft\scripts\hero_tile\06_export_for_ue5.py"
%BLENDER_EXE% --background --python %SCRIPT%
