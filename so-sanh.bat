@echo off
cd /d "%~dp0"
set "PY=py -3"
py -3 --version >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% so-sanh.py
echo.
pause
