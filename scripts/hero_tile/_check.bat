@echo off
call C:\Users\Glytc\miniconda3\condabin\conda.bat activate pdal_env
python -c "import numpy; print('numpy', numpy.__version__)" 2>&1
python -c "import shapely; print('shapely', shapely.__version__)" 2>&1
python -c "import scipy; print('scipy', scipy.__version__)" 2>&1
