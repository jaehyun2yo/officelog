@echo off
chcp 65001 >nul
echo ========================================
echo   ComputerOff Agent 빌드 스크립트
echo   (서버 URL + API 키 포함 빌드)
echo ========================================
echo.

REM config.json 확인 (있으면 자동 사용)
if exist "config.json" (
    echo [자동] config.json 파일 발견 - 자동 빌드 모드
    echo.
    type config.json
    echo.
    goto :build
)

REM config.json이 없으면 수동 입력
echo config.json 파일이 없습니다. 수동으로 입력하세요.
echo (자동 빌드: config.json 파일을 미리 생성하세요)
echo.

REM 서버 URL 입력
set /p SERVER_URL="서버 URL (예: http://34.64.116.152:8000): "
if "%SERVER_URL%"=="" (
    echo [오류] 서버 URL을 입력하세요.
    pause
    exit /b 1
)

REM API 키 입력
set /p API_KEY="API 키: "
if "%API_KEY%"=="" (
    echo [오류] API 키를 입력하세요.
    pause
    exit /b 1
)

echo.
echo 설정 확인:
echo   서버 URL: %SERVER_URL%
echo   API 키: %API_KEY%
echo.

REM config.json 생성
echo [1/5] config.json 생성 중...
echo {"server_url": "%SERVER_URL%", "api_key": "%API_KEY%"} > config.json
echo       config.json 생성 완료

:build
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

REM 64비트 빌드 (windowed 모드 - 하트비트 실행 시 콘솔 창 표시 안 함)
echo [4/5] 64비트 exe 빌드 중...
py -3 -m PyInstaller --onefile --windowed --name agent_windows_x64 ^
    --hidden-import requests ^
    --hidden-import json ^
    --hidden-import socket ^
    --add-data "config.json;." ^
    installer.py

REM 32비트 빌드 (Windows 7 호환, Python 3.8-32)
if "%BUILD_32%"=="1" (
    echo [5/5] 32비트 exe 빌드 중 (Windows 7 호환)...
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
echo     ..\dist\agent_windows_x64.exe (64비트, Windows 10/11)
if "%BUILD_32%"=="1" echo     ..\dist\agent_windows_x86.exe (32비트, Windows 7/8/10/11)
echo.
echo   사용법:
echo     1. 각 PC에 exe 파일 복사
echo     2. 관리자 권한으로 실행
echo     3. 자동 설치 완료
echo ========================================
pause
