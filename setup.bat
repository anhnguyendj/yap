@echo off
cd /d "%~dp0"
echo ===============================================
echo   Yap for Windows v3 - Installing dependencies
echo ===============================================
echo.

REM Same interpreter resolution as run.bat, and for the same reason: installing
REM with a bare "pip" can put the packages in a different Python than the one
REM that ends up running the app. Keep these two files in step.
set "PY=py -3"
py -3 --version >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 goto nopython

%PY% --version
echo.
echo Installing packages...
echo.

%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Installation failed.
    echo Try: right-click this file, Run as administrator
    pause
    exit /b 1
)

echo.
echo ===============================================
echo   Done! Run run.bat to start Yap.
echo ===============================================
echo.
pause
exit /b 0

:nopython
echo ERROR: Python not found!
echo Download at: https://www.python.org/downloads/
echo Make sure to tick "Add Python to PATH"
pause
exit /b 1
