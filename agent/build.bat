@echo off
chcp 65001 >nul
echo ========================================
echo   ComputerOff Agent 빌드 스크립트
echo ========================================
echo.

REM 서버 설정 (자동 빌드용)
set SERVER_URL=http://34.64.116.152:8000
set API_KEY=Rk60sPWdkZSFNLLEH71n2iOO1BzEKPUqMVIgl2dIIms

echo 설정:
echo   서버 URL: %SERVER_URL%
echo   API 키: %API_KEY%
echo.

REM config.json 생성
echo [1/5] config.json 생성 중...
echo {"server_url": "%SERVER_URL%", "api_key": "%API_KEY%"} > config.json
echo       완료

REM Python 확인
py -0 >nul 2>&1
if errorlevel 1 (
    echo [오류] Python Launcher(py)가 설치되지 않았습니다.
    pause
    exit /b 1
)

REM 의존성 설치
echo [2/5] 의존성 설치 중 (64비트)...
py -3 -m pip install pyinstaller requests --quiet

echo [3/5] 의존성 설치 중 (32비트)...
py -3.8-32 -m pip install pyinstaller requests --quiet 2>nul
if errorlevel 1 (
    echo [경고] Python 3.8-32가 없습니다. 32비트 빌드를 건너뜁니다.
    set BUILD_32=0
) else (
    set BUILD_32=1
)

REM 64비트 빌드
echo [4/5] 64비트 exe 빌드 중...
py -3 -m PyInstaller --onefile --windowed --name agent_windows_x64 ^
    --hidden-import requests ^
    --hidden-import json ^
    --hidden-import socket ^
    --add-data "config.json;." ^
    installer.py

REM 32비트 빌드
if "%BUILD_32%"=="1" (
    echo [5/5] 32비트 exe 빌드 중...
    py -3.8-32 -m PyInstaller --onefile --windowed --name agent_windows_x86 ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --add-data "config.json;." ^
        installer.py
) else (
    echo [5/5] 32비트 빌드 건너뜀
)

REM 결과물 이동
echo.
echo 결과물 정리 중...
if not exist "..\dist" mkdir "..\dist"
if exist "dist\agent_windows_x64.exe" move /y "dist\agent_windows_x64.exe" "..\dist\" >nul
if exist "dist\agent_windows_x86.exe" move /y "dist\agent_windows_x86.exe" "..\dist\" >nul

REM 정리
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del *.spec 2>nul
del config.json 2>nul

echo.
echo ========================================
echo   빌드 완료!
echo   결과물:
echo     ..\dist\agent_windows_x64.exe (64비트)
if "%BUILD_32%"=="1" echo     ..\dist\agent_windows_x86.exe (32비트)
echo ========================================
pause
