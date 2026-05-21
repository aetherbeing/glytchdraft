@echo off
:: _run.bat — 3DEP-only massing pipeline runner
::
:: Usage:
::   _run.bat              run the full pipeline (steps 01-06)
::   _run.bat 01           run only step 01
::   _run.bat 01 02 03     run steps 01, 02, 03 in order
::   _run.bat compare      run only step 07 (comparison report)
::
:: Requires: conda environment "pdal_env" with PDAL, numpy, shapely,
::           scikit-learn, scipy installed.
::           Run _install_deps.bat once to set up the environment.

setlocal

:: Change to the project root so relative paths in the scripts resolve correctly
cd /d "C:\Users\Glytc\glytchdraft"

:: pdal_env Python executable and DLL locations
set ENV_ROOT=C:\Users\Glytc\miniconda3\envs\pdal_env
set PYTHON=%ENV_ROOT%\python.exe

if not exist "%PYTHON%" (
    echo ERROR: pdal_env Python not found at %PYTHON%
    echo Run scripts\3dep_only\_install_deps.bat to create the environment.
    exit /b 1
)

:: Prepend Library\bin so GDAL/PDAL DLLs are found at import time.
:: Without this, `import pdal` fails silently on Windows (DLL load error).
set PATH=%ENV_ROOT%;%ENV_ROOT%\Library\bin;%ENV_ROOT%\Library\usr\bin;%ENV_ROOT%\Scripts;%PATH%

set SCRIPTS=scripts\3dep_only

:: Determine which steps to run
if "%~1"=="" (
    :: No args — run full pipeline steps 01-06
    set STEPS=01 02 03 04 05 06
) else if "%~1"=="compare" (
    set STEPS=07
) else (
    set STEPS=%*
)

echo.
echo === 3DEP-only massing pipeline ===
echo Steps: %STEPS%
echo.

for %%S in (%STEPS%) do (
    if "%%S"=="01" (
        echo --- Step 01: extract building + ground points ---
        "%PYTHON%" %SCRIPTS%\01_extract_building_points.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="02" (
        echo --- Step 02: remove outliers ---
        "%PYTHON%" %SCRIPTS%\02_clean_outliers.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="03" (
        echo --- Step 03: cluster building points ---
        "%PYTHON%" %SCRIPTS%\03_cluster_buildings.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="04" (
        echo --- Step 04: derive 2D footprints ---
        "%PYTHON%" %SCRIPTS%\04_derive_footprints.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="05" (
        echo --- Step 05: generate extruded masses ---
        "%PYTHON%" %SCRIPTS%\05_generate_masses.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="06" (
        echo --- Step 06: export shifted Blender/UE copies ---
        "%PYTHON%" %SCRIPTS%\06_export_shifted.py
        if errorlevel 1 goto :error
    )
    if "%%S"=="07" (
        echo --- Step 07: compare 3DEP-only vs footprint-assisted ---
        "%PYTHON%" %SCRIPTS%\07_compare_versions.py
        if errorlevel 1 goto :error
    )
)

echo.
echo === pipeline complete ===
echo.
echo Outputs:
echo   data_processed\miami\hero_tile_3dep_only\pointcloud\
echo   data_processed\miami\hero_tile_3dep_only\clusters\
echo   data_processed\miami\hero_tile_3dep_only\footprints\
echo   data_processed\miami\hero_tile_3dep_only\masses\
echo   data_processed\miami\hero_tile_3dep_only\blender_ready\
echo   data_processed\miami\hero_tile_3dep_only\ue_ready\
echo   data_processed\miami\hero_tile_3dep_only\metadata\
goto :end

:error
echo.
echo ERROR: step failed. Check output above.
exit /b 1

:end
endlocal
