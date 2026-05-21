@echo off
call C:\Users\Glytc\miniconda3\condabin\conda.bat activate pdal_env
python -m pip install --quiet shapely scipy
python -c "import shapely, scipy; print('shapely', shapely.__version__); print('scipy', scipy.__version__)"
