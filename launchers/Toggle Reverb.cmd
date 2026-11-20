@echo off
call "%~dp0_python.cmd"
%AGPY% -B "%~dp0..\src\ag_reverb.py" toggle %*
exit /b %errorlevel%
