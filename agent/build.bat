@echo off
chcp 65001 >nul

REM Change to script directory
cd /d "%~dp0"

echo ========================================
echo   ComputerOff Agent Build Script
echo   (32-bit / 64-bit / Windows7)
echo ========================================
echo.
echo Working directory: %cd%
echo.

REM Server settings
set SERVER_URL=http://34.64.116.152:8000
set API_KEY=Rk60sPWdkZSFNLLEH71n2iOO1BzEKPUqMVIgl2dIIms

echo Settings:
echo   Server URL: %SERVER_URL%
echo   API Key: %API_KEY%
echo.

REM Create config.json
echo [1/6] Creating config.json...
echo {"server_url": "%SERVER_URL%", "api_key": "%API_KEY%"} > config.json
echo       Done

REM Check Python
py -0 >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python Launcher not installed.
    pause
    exit /b 1
)

REM Install dependencies
echo [2/6] Installing dependencies...
echo       - 64-bit Python...
py -3 -m pip install pyinstaller requests --quiet

echo       - 32-bit Python 3.8...
py -3.8-32 -m pip install pyinstaller requests --quiet 2>nul
if errorlevel 1 (
    echo [WARNING] Python 3.8-32 not found. Skipping 32-bit build.
    set BUILD_32=0
) else (
    set BUILD_32=1
)

echo       - 64-bit Python 3.8 (for Windows 7)...
py -3.8 -m pip install pyinstaller requests --quiet 2>nul
if errorlevel 1 (
    echo [WARNING] Python 3.8 64-bit not found. Skipping Win7 64-bit build.
    set BUILD_WIN7_64=0
) else (
    set BUILD_WIN7_64=1
)

REM Create output directory
if not exist "..\dist" mkdir "..\dist"

REM ==================== 64-bit Build (Latest Python) ====================
echo.
echo [3/6] Building 64-bit (Windows 10/11)...
py -3 -m PyInstaller --onefile --windowed --name agent_windows_x64 ^
    --hidden-import requests ^
    --hidden-import json ^
    --hidden-import socket ^
    --add-data "config.json;." ^
    installer.py
echo       Done

REM ==================== 32-bit Build (Python 3.8) ====================
echo.
echo [4/6] Building 32-bit...
if "%BUILD_32%"=="1" (
    py -3.8-32 -m PyInstaller --onefile --windowed --name agent_windows_x86 ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --add-data "config.json;." ^
        installer.py
    echo       Done
) else (
    echo       Skipped (Python 3.8-32 not found)
)

REM ==================== Windows 7 Build (Python 3.8 64-bit) ====================
echo.
echo [5/6] Building Windows 7 compatible 64-bit...
if "%BUILD_WIN7_64%"=="1" (
    py -3.8 -m PyInstaller --onefile --windowed --name agent_windows_win7_x64 ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --add-data "config.json;." ^
        installer.py
    echo       Done
) else (
    echo       Skipped (Python 3.8 64-bit not found)
)

REM ==================== Move results ====================
echo.
echo [6/6] Organizing output files...

REM Move results
if exist "dist\agent_windows_x64.exe" move /y "dist\agent_windows_x64.exe" "..\dist\" >nul
if exist "dist\agent_windows_x86.exe" move /y "dist\agent_windows_x86.exe" "..\dist\" >nul
if exist "dist\agent_windows_win7_x64.exe" move /y "dist\agent_windows_win7_x64.exe" "..\dist\" >nul

REM Cleanup
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del *.spec 2>nul
del config.json 2>nul

echo.
echo ========================================
echo   Build Complete!
echo.
echo   Output files in ..\dist\:
echo.
echo   [64-bit] Windows 10/11 (Latest Python)
echo     - agent_windows_x64.exe
echo.
echo   [32-bit] Windows 7/8/10/11 (Python 3.8)
if "%BUILD_32%"=="1" echo     - agent_windows_x86.exe
if not "%BUILD_32%"=="1" echo     - Not built (Python 3.8-32 required)
echo.
echo   [Windows 7 64-bit] Python 3.8 based
if "%BUILD_WIN7_64%"=="1" echo     - agent_windows_win7_x64.exe
if not "%BUILD_WIN7_64%"=="1" echo     - Not built (Python 3.8 required)
echo.
echo   Note: Windows 7 does not support Python 3.9+
echo         32-bit and win7_x64 use Python 3.8
echo ========================================
pause
