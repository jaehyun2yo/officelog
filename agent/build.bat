@echo off
chcp 65001 >nul
echo ========================================
echo   ComputerOff Agent 빌드 스크립트
echo   (64비트 + 32비트)
echo ========================================
echo.

REM Python 확인
py -0 >nul 2>&1
if errorlevel 1 (
    echo [오류] Python Launcher(py)가 설치되지 않았습니다.
    pause
    exit /b 1
)

REM 의존성 설치
echo [1/5] 의존성 설치 중 (64비트)...
py -3 -m pip install pyinstaller requests --quiet

echo [2/5] 의존성 설치 중 (32비트)...
py -3.11-32 -m pip install pyinstaller requests --quiet 2>nul
if errorlevel 1 (
    echo [경고] 32비트 Python이 없습니다. 64비트만 빌드합니다.
    set BUILD_32=0
) else (
    set BUILD_32=1
)

REM 64비트 빌드
echo [3/5] 64비트 exe 빌드 중...
py -3 -m PyInstaller --onefile --windowed --name computeroff-agent-x64 ^
    --add-data "agent.py;." ^
    --hidden-import requests ^
    --hidden-import json ^
    --hidden-import socket ^
    --hidden-import tkinter ^
    installer.py

REM 32비트 빌드
if "%BUILD_32%"=="1" (
    echo [4/5] 32비트 exe 빌드 중...
    py -3.11-32 -m PyInstaller --onefile --windowed --name computeroff-agent-x86 ^
        --add-data "agent.py;." ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --hidden-import tkinter ^
        installer.py
) else (
    echo [4/5] 32비트 빌드 건너뜀
)

REM 결과물 이동
echo [5/5] 결과물 정리 중...
if not exist "..\dist" mkdir "..\dist"
if exist "dist\computeroff-agent-x64.exe" move /y "dist\computeroff-agent-x64.exe" "..\dist\" >nul
if exist "dist\computeroff-agent-x86.exe" move /y "dist\computeroff-agent-x86.exe" "..\dist\" >nul

REM 정리
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del *.spec 2>nul

echo.
echo ========================================
echo   빌드 완료!
echo   결과물:
echo     ..\dist\computeroff-agent-x64.exe (64비트)
if "%BUILD_32%"=="1" echo     ..\dist\computeroff-agent-x86.exe (32비트)
echo ========================================
pause
