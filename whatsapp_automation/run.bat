@echo off
title WhatsApp Bulk Messaging Automation
color 0A
setlocal

pushd "%~dp0"

echo.
echo =====================================================
echo   WhatsApp Bulk Messaging Automation
echo =====================================================
echo.

REM Check Python launcher
py -3.10 --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10 is not installed or the py launcher is unavailable.
    echo Download from: https://www.python.org/downloads/
    pause
    popd
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing dependencies...
py -3.10 -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    popd
    exit /b 1
)

echo [2/3] Dependencies ready.
echo.

REM Launch automation script
py -3.10 -u "%~dp0whatsapp_blast.py" %*
if errorlevel 1 (
    echo.
    echo [ERROR] Campaign failed.
    popd
    pause
    exit /b 1
)

echo.
echo [3/3] Campaign complete. Check reports\ folder for results.
echo.
popd
pause
