@echo off
rem Picks the Python interpreter used by the other launchers.
rem Order: AG03_PYTHON env var, repo .venv, C:\ag03mk2-re\.venv, then the py launcher.
if defined AG03_PYTHON (set "AGPY=%AG03_PYTHON%" & exit /b 0)
if exist "%~dp0..\.venv\Scripts\python.exe" (set "AGPY=%~dp0..\.venv\Scripts\python.exe" & exit /b 0)
if exist "C:\ag03mk2-re\.venv\Scripts\python.exe" (set "AGPY=C:\ag03mk2-re\.venv\Scripts\python.exe" & exit /b 0)
set "AGPY=py -3"
exit /b 0
