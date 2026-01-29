@echo off
REM PSP Controller Server Startup Script for Windows

echo PSP Controller Server for Windows
echo ==================================

REM Check for Python 3
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Python is not installed or not in PATH!
    echo Download Python from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

REM Get the directory of this script
cd /d "%~dp0"

REM Check Python version
python --version

echo.
echo Starting server...
echo.

REM Run the server
python psp_controller_server.py %*

pause
