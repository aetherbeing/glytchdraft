@echo off
:: _run.bat  [Project Bikini — GlitchOS.io]
::
:: Run the Bikini processing pipeline: Downtown Miami + South Beach.
::
:: Prerequisites:
::   - T7 drive mounted as E:\ (run once: wsl sudo mount -t drvfs E: /mnt/t7)
::   - 16 LAZ tiles downloaded to T:\miami\data_raw\laz\
::     (run: python scripts/miami/download_bikini_tiles.py)
::   - conda environment "pdal_env" with PDAL, numpy, sklearn, scipy, shapely
::
:: Usage:
::   _run.bat              full pipeline (s01-s07)
::   _run.bat 01           single step
::   _run.bat 01 02 03     multiple steps in order
::   _run.bat 03 04 05     re-run from clustering onward
::
:: Step map:
::   01  extract building + ground points from all 16 LAZ tiles (slow, ~30-60 min)
::   02  statistical outlier removal
::   03  DBSCAN clustering
::   04  derive 2D footprints (convex hull / rotated bbox / alpha shape)
::   05  generate extruded mass OBJs (LOD0 / LOD1 / LOD2)
::   06  apply coordinate shift + export GLBs for web viewer
::   07  write tile_manifest.json + buildings.json

setlocal

cd /d "C:\Users\Glytc\glytchdraft"

set ENV_ROOT=C:\Users\Glytc\miniconda3\envs\pdal_env
set PYTHON=%ENV_ROOT%\python.exe

if not exist "%PYTHON%" (
    echo ERROR: pdal_env Python not found at %PYTHON%
    echo Run:  conda create -n pdal_env python=3.10 pdal numpy scipy scikit-learn shapely -c conda-forge
    exit /b 1
)

set PATH=%ENV_ROOT%;%ENV_ROOT%\Library\bin;%ENV_ROOT%\Library\usr\bin;%ENV_ROOT%\Scripts;%PATH%

set S=scripts\miami

if "%~1"=="" (
    set STEPS=01 02 03 04 05 06 07
) else (
    set STEPS=%*
)

echo.
echo === Project Bikini pipeline ===
echo Steps: %STEPS%
echo.

for %%S in (%STEPS%) do (
    if "%%S"=="01" (
        echo --- Step 01: extract points from 16 LAZ tiles ---
        "%PYTHON%" %S%\s01_extract.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="02" (
        echo --- Step 02: outlier removal ---
        "%PYTHON%" %S%\s02_clean.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="03" (
        echo --- Step 03: DBSCAN clustering ---
        "%PYTHON%" %S%\s03_cluster.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="04" (
        echo --- Step 04: derive footprints ---
        "%PYTHON%" %S%\s04_footprints.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="05" (
        echo --- Step 05: generate mass OBJs ---
        "%PYTHON%" %S%\s05_masses.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="06" (
        echo --- Step 06: shift + GLB export ---
        "%PYTHON%" %S%\s06_export.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="07" (
        echo --- Step 07: write tile manifest + buildings JSON ---
        "%PYTHON%" %S%\s07_metadata.py
        if errorlevel 1 goto :error
    )
)

echo.
echo === Bikini pipeline complete ===
echo.
echo Outputs:
echo   data_processed\miami\bikini\pointcloud\
echo   data_processed\miami\bikini\clusters\
echo   data_processed\miami\bikini\footprints\
echo   data_processed\miami\bikini\masses\
echo   data_processed\miami\bikini\blender_ready\
echo   exports\miami_bikini\  (GLBs + JSON — feed to Three.js / R3F viewer)
echo.
echo Viewer seed files:
echo   exports\miami_bikini\tile_manifest.json
echo   exports\miami_bikini\buildings.json
echo   exports\miami_bikini\bikini_masses_LOD0.glb
echo   exports\miami_bikini\bikini_masses_LOD2.glb
goto :end

:error
echo.
echo ERROR: step failed. Check output above.
exit /b 1

:end
endlocal
