@echo off
REM Activate the pdal_env conda environment (needed so GDAL+PDAL DLLs load)
REM then run whichever stage was named as the first argument.
REM
REM Usage:
REM   _run.bat 00              -> runs 00_compute_extent.py
REM   _run.bat 01              -> runs 01_clip_footprints.py
REM   _run.bat 02              -> runs 02_extract_classes.py (all three classes)
REM   _run.bat 02 building     -> runs 02_extract_classes.py building only
REM   _run.bat 02 building 0.1 -> override spacing for one class

call C:\Users\Glytc\miniconda3\condabin\conda.bat activate pdal_env

if "%1"=="00" python C:\Users\Glytc\glytchdraft\scripts\hero_tile\00_compute_extent.py
if "%1"=="01" python C:\Users\Glytc\glytchdraft\scripts\hero_tile\01_clip_footprints.py
if "%1"=="02" python C:\Users\Glytc\glytchdraft\scripts\hero_tile\02_extract_classes.py %2 %3
if "%1"=="03" python C:\Users\Glytc\glytchdraft\scripts\hero_tile\03_extra_lods.py
if "%1"=="04" python C:\Users\Glytc\glytchdraft\scripts\hero_tile\04_building_masses.py
if "%1"=="05" call C:\Users\Glytc\glytchdraft\scripts\hero_tile\05_run_blender.bat
if "%1"=="06" call C:\Users\Glytc\glytchdraft\scripts\hero_tile\06_run_ue5_export.bat
if "%1"=="07" python C:\Users\Glytc\glytchdraft\scripts\hero_tile\07_make_ue5_metadata.py
