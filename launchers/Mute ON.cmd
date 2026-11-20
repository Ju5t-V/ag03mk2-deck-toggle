@echo off
call "%~dp0_python.cmd"
%AGPY% -B "%~dp0..\src\ag_mute.py" on %*
exit /b %errorlevel%
