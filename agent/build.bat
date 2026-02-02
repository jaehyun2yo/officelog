@echo off
chcp 65001 >nul
echo ========================================
echo   ComputerOff Agent 빌드 스크립트
echo   (64비트 + 32비트 + Windows 7)
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
echo [1/6] 의존성 설치 중 (64비트)...
py -3 -m pip install pyinstaller requests --quiet

echo [2/6] 의존성 설치 중 (32비트)...
py -3.11-32 -m pip install pyinstaller requests --quiet 2>nul
if errorlevel 1 (
    echo [경고] 32비트 Python 3.11이 없습니다.
    set BUILD_32=0
) else (
    set BUILD_32=1
)

echo [3/6] 의존성 설치 중 (Windows 7용 Python 3.8-32)...
py -3.8-32 -m pip install pyinstaller requests --quiet 2>nul
if errorlevel 1 (
    echo [경고] Python 3.8-32가 없습니다. Windows 7용 빌드를 건너뜁니다.
    echo        다운로드: https://www.python.org/ftp/python/3.8.10/python-3.8.10.exe
    set BUILD_WIN7=0
) else (
    set BUILD_WIN7=1
)

REM 64비트 빌드
echo [4/6] 64비트 exe 빌드 중...
py -3 -m PyInstaller --onefile --windowed --name computeroff-agent-x64 ^
    --hidden-import requests ^
    --hidden-import json ^
    --hidden-import socket ^
    --hidden-import tkinter ^
    installer.py

REM 32비트 빌드 (Windows 8+)
if "%BUILD_32%"=="1" (
    echo [5/6] 32비트 exe 빌드 중 (Windows 8+)...
    py -3.11-32 -m PyInstaller --onefile --windowed --name computeroff-agent-x86 ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --hidden-import tkinter ^
        installer.py
) else (
    echo [5/6] 32비트 빌드 건너뜀
)

REM Windows 7 빌드 (Python 3.8-32)
if "%BUILD_WIN7%"=="1" (
    echo [6/6] Windows 7용 exe 빌드 중 (Python 3.8-32)...
    py -3.8-32 -m PyInstaller --onefile --windowed --name computeroff-agent-win7 ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --hidden-import tkinter ^
        installer.py
) else (
    echo [6/6] Windows 7 빌드 건너뜀
)

REM 결과물 이동
echo.
echo 결과물 정리 중...
if not exist "..\dist" mkdir "..\dist"
if exist "dist\computeroff-agent-x64.exe" move /y "dist\computeroff-agent-x64.exe" "..\dist\" >nul
if exist "dist\computeroff-agent-x86.exe" move /y "dist\computeroff-agent-x86.exe" "..\dist\" >nul
if exist "dist\computeroff-agent-win7.exe" move /y "dist\computeroff-agent-win7.exe" "..\dist\" >nul

REM 정리
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del *.spec 2>nul

echo.
echo ========================================
echo   빌드 완료!
echo   결과물:
echo     ..\dist\computeroff-agent-x64.exe (64비트, Windows 8+)
if "%BUILD_32%"=="1" echo     ..\dist\computeroff-agent-x86.exe (32비트, Windows 8+)
if "%BUILD_WIN7%"=="1" echo     ..\dist\computeroff-agent-win7.exe (32비트, Windows 7 호환)
echo ========================================
pause
