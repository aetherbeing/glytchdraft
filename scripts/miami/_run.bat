@echo off
:: _run.bat  [Project Bikini — GlitchOS.io]
::
:: Launches the Miami Bikini pipeline with the Rich terminal dashboard.
::
:: Prerequisites:
::   - T7 drive mounted:  wsl sudo mount -t drvfs E: /mnt/t7   (once)
::   - 16 LAZ tiles at T:\miami\data_raw\laz\
::   - conda env "pdal_env" with: pdal numpy scipy scikit-learn shapely rich anthropic
::
:: Usage:
::   _run.bat              full pipeline (s01–s08)
::   _run.bat 01           single stage
::   _run.bat 06 07 08     multiple stages
::
:: Stage map:
::   01  extract building + ground points from LAZ tiles  (~30-60 min)
::   02  statistical outlier removal
::   03  clip county footprints to Bikini bbox
::   04  derive 2D footprints (convex hull / rotated bbox)
::   05  generate extruded mass OBJs  (LOD0 / LOD1 / LOD2)
::   06  apply coordinate shift + export GLBs
::   07  write tile_manifest.json + buildings.json
::   08  AI enrichment via Anthropic API  (requires ANTHROPIC_API_KEY)

setlocal

cd /d "C:\Users\Glytc\glytchdraft"

set ENV_ROOT=C:\Users\Glytc\miniconda3\envs\pdal_env
set PYTHON=%ENV_ROOT%\python.exe

if not exist "%PYTHON%" (
    echo ERROR: pdal_env Python not found at %PYTHON%
    echo Run:  conda create -n pdal_env python=3.10 pdal numpy scipy scikit-learn shapely rich anthropic -c conda-forge
    exit /b 1
)

set PATH=%ENV_ROOT%;%ENV_ROOT%\Library\bin;%ENV_ROOT%\Library\usr\bin;%ENV_ROOT%\Scripts;%PATH%

"%PYTHON%" scripts\miami\run_pipeline.py %*
exit /b %errorlevel%
