@echo off
:: _install_deps.bat
::
:: Installs Python dependencies for the 3DEP-only massing pipeline into the
:: shared "pdal_env" conda environment.
::
:: Run this once before using _run.bat.
::
:: Assumes:
::   - conda / mamba is on PATH
::   - pdal_env already has PDAL, numpy, scipy, shapely (from the hero_tile pipeline)
::
:: This script adds:
::   - scikit-learn  (DBSCAN clustering)
::   - alphashape    (concave hull / alpha shape; optional but recommended)

setlocal

call conda activate pdal_env
if errorlevel 1 (
    echo ERROR: could not activate pdal_env.
    echo Create it first with the hero_tile pipeline's _install_deps.bat.
    exit /b 1
)

echo Installing scikit-learn...
pip install scikit-learn

echo.
echo Installing alphashape (optional — convex hull used as fallback if absent)...
pip install alphashape

echo.
echo Verifying key imports...
python -c "import pdal; import numpy; import scipy; import shapely; import sklearn; print('all core imports OK')"
python -c "import alphashape; print('alphashape OK')" || echo "alphashape not available (will use convex hull)"

echo.
echo Done. Run scripts\3dep_only\_run.bat to execute the pipeline.
endlocal
