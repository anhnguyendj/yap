@echo off
cd /d "%~dp0"

REM Resolve the interpreter via the py launcher FIRST. A bare "python" picks
REM whatever is first on PATH, which on this machine is an unrelated venv
REM without Yap's packages - the app then dies on "No module named sounddevice".
set "PY=py -3"
py -3 --version >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 goto nopython

echo Starting Yap...
%PY% app.py
if errorlevel 1 (
    echo.
    echo ERROR: Make sure you ran setup.bat first.
    echo If "Access denied" - right-click and Run as administrator
    pause
)
exit /b 0

:nopython
echo ERROR: Python not found!
echo Download at: https://www.python.org/downloads/
echo Make sure to tick "Add Python to PATH"
pause
exit /b 1
