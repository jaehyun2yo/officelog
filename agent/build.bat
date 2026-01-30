@echo off
chcp 65001 >nul
echo ========================================
echo   ComputerOff Agent 빌드 스크립트
echo ========================================
echo.

REM Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되지 않았습니다.
    pause
    exit /b 1
)

REM 의존성 설치
echo [1/3] 의존성 설치 중...
pip install -r requirements.txt --quiet

REM PyInstaller 빌드
echo [2/3] exe 파일 빌드 중...
pyinstaller --onefile --windowed --name computeroff-agent ^
    --add-data "agent.py;." ^
    --hidden-import requests ^
    --hidden-import json ^
    --hidden-import socket ^
    --hidden-import tkinter ^
    installer.py

REM 결과물 이동
echo [3/3] 결과물 정리 중...
if exist "..\dist\computeroff-agent.exe" del "..\dist\computeroff-agent.exe"
move "dist\computeroff-agent.exe" "..\dist\" >nul

REM 정리
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del *.spec 2>nul

echo.
echo ========================================
echo   빌드 완료!
echo   결과물: ..\dist\computeroff-agent.exe
echo ========================================
pause
