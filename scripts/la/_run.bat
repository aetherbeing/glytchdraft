@echo off
REM _run.bat  [LA pipeline — Windows]
REM
REM Usage:
REM   _run.bat 00              -> 00_compute_extent.py
REM   _run.bat 01              -> 01_clip_footprints.py
REM   _run.bat 02              -> 02_extract_classes.py (all classes)
REM   _run.bat 02 building     -> building class only
REM   _run.bat 02 building 0.1 -> override spacing

call C:\Users\Glytc\miniconda3\condabin\conda.bat activate pdal_env

if "%1"=="00" python C:\Users\Glytc\glytchdraft\scripts\la\00_compute_extent.py
if "%1"=="01" python C:\Users\Glytc\glytchdraft\scripts\la\01_clip_footprints.py
if "%1"=="02" python C:\Users\Glytc\glytchdraft\scripts\la\02_extract_classes.py %2 %3
