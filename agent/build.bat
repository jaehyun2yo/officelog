@echo off
chcp 65001 >nul

REM Change to script directory
cd /d "%~dp0"

REM ==================== Configuration ====================
set SERVER_URL=http://office.yjlaser.net:8000
set API_KEY=Rk60sPWdkZSFNLLEH71n2iOO1BzEKPUqMVIgl2dIIms
set INNO_SETUP="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set NAS_PATH=\\192.168.0.6\home\데이터\유진MAIN\0. 자동화 프로그램\ComputerOff

REM 서버 자동 배포 (자동 업데이트 엔드포인트가 읽어가는 위치)
set SERVER_HOST=ubuntu@office.yjlaser.net
set SERVER_DEPLOY_PATH=/opt/computeroff/agent_updates/

REM Read version from version.py
for /f "usebackq tokens=*" %%a in (`python -c "import re; m=re.search(r'AGENT_VERSION\s*=\s*[\x22\x27](.+?)[\x22\x27]', open('version.py','rb').read().decode('utf-8')); print(m.group(1))"`) do set VERSION=%%a

REM ==================== Flag Parsing ====================
set AUTO_MODE=0
set DEPLOY_SERVER=1
:parse_args
if "%~1"=="" goto parse_done
if /i "%~1"=="--auto" (set AUTO_MODE=1) & shift & goto parse_args
if /i "%~1"=="--no-deploy" (set DEPLOY_SERVER=0) & shift & goto parse_args
if /i "%~1"=="--deploy" (set DEPLOY_SERVER=1) & shift & goto parse_args
echo [WARNING] Unknown flag: %~1
shift
goto parse_args
:parse_done

echo ========================================
echo   ComputerOff Agent Build Script
echo   Version: %VERSION%
echo   (32-bit / 64-bit / Windows7)
echo ========================================
echo.
echo Working directory: %cd%
echo Server URL: %SERVER_URL%
if "%DEPLOY_SERVER%"=="1" (
    echo Server auto-deploy: ENABLED -^> %SERVER_HOST%:%SERVER_DEPLOY_PATH%
) else (
    echo Server auto-deploy: DISABLED (--no-deploy)
)
echo.

REM Check Python
py -0 >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python Launcher not installed.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM ==================== [1/8] Dependencies ====================
echo [1/8] Installing dependencies...
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

REM ==================== [2/8] Config Files ====================
echo.
echo [2/8] Creating variant config files...

echo {"server_url": "%SERVER_URL%", "api_key": "%API_KEY%", "agent_variant": "x64", "version": "%VERSION%"} > config_x64.json
echo {"server_url": "%SERVER_URL%", "api_key": "%API_KEY%", "agent_variant": "x86", "version": "%VERSION%"} > config_x86.json
echo {"server_url": "%SERVER_URL%", "api_key": "%API_KEY%", "agent_variant": "win7_x64", "version": "%VERSION%"} > config_win7_x64.json
echo       Done

REM ==================== [3/8] 64-bit Build ====================
echo.
echo [3/8] Building 64-bit (Windows 10/11)...
copy /y config_x64.json config.json >nul
py -3 -m PyInstaller --onefile --windowed --name agent_windows_x64 ^
    --hidden-import requests ^
    --hidden-import json ^
    --hidden-import socket ^
    --add-data "config.json;." ^
    --add-data "version.py;." ^
    --add-data "auto_updater.py;." ^
    installer.py
echo       Done

REM ==================== [4/8] 32-bit Build ====================
echo.
echo [4/8] Building 32-bit...
if "%BUILD_32%"=="1" (
    copy /y config_x86.json config.json >nul
    py -3.8-32 -m PyInstaller --onefile --windowed --name agent_windows_x86 ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --add-data "config.json;." ^
        --add-data "version.py;." ^
        --add-data "auto_updater.py;." ^
        installer.py
    echo       Done
) else (
    echo       Skipped (Python 3.8-32 not found)
)

REM ==================== [5/8] Windows 7 Build ====================
echo.
echo [5/8] Building Windows 7 compatible 64-bit...
if "%BUILD_WIN7_64%"=="1" (
    copy /y config_win7_x64.json config.json >nul
    py -3.8 -m PyInstaller --onefile --windowed --name agent_windows_win7_x64 ^
        --hidden-import requests ^
        --hidden-import json ^
        --hidden-import socket ^
        --add-data "config.json;." ^
        --add-data "version.py;." ^
        --add-data "auto_updater.py;." ^
        installer.py
    echo       Done
) else (
    echo       Skipped (Python 3.8 64-bit not found)
)

REM Move EXE results
if exist "dist\agent_windows_x64.exe" move /y "dist\agent_windows_x64.exe" "..\dist\" >nul
if exist "dist\agent_windows_x86.exe" move /y "dist\agent_windows_x86.exe" "..\dist\" >nul
if exist "dist\agent_windows_win7_x64.exe" move /y "dist\agent_windows_win7_x64.exe" "..\dist\" >nul

REM Cleanup build artifacts
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del *.spec 2>nul
del config.json 2>nul
del config_x64.json 2>nul
del config_x86.json 2>nul
del config_win7_x64.json 2>nul

REM ==================== [6/8] Inno Setup ====================
echo.
echo [6/8] Building Inno Setup installer...
if exist %INNO_SETUP% (
    %INNO_SETUP% /DMyAppVersion=%VERSION% installer.iss
    echo       Done
) else (
    echo [WARNING] Inno Setup not found at %INNO_SETUP%
    echo       Skipped
)

REM ==================== [7/8] version.json ====================
echo.
echo [7/8] Generating version.json...

REM Generate via Python for ISO 8601 timestamp (locale-independent) and proper JSON formatting.
py -3 -c "import json, datetime; json.dump({'version':'%VERSION%','variants':{'x64':'agent_windows_x64.exe','x86':'agent_windows_x86.exe','win7_x64':'agent_windows_win7_x64.exe'},'installer_filename':'Agent_Setup_v%VERSION%.exe','updated_at':datetime.datetime.now().isoformat(timespec='seconds')}, open(r'..\dist\version.json','w',encoding='utf-8'), indent=2, ensure_ascii=False)"
if errorlevel 1 (
    echo       [ERROR] Failed to generate version.json
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
echo       Done

REM ==================== [8/8] Deploy ====================
echo.
echo [8/8] Deploying...

REM Deploy to NAS
echo       - NAS deploy...
if exist "%NAS_PATH%" (
    copy /y "..\dist\agent_windows_x64.exe" "%NAS_PATH%\" >nul 2>&1
    copy /y "..\dist\agent_windows_x86.exe" "%NAS_PATH%\" >nul 2>&1
    copy /y "..\dist\agent_windows_win7_x64.exe" "%NAS_PATH%\" >nul 2>&1
    if exist "..\dist\Agent_Setup_v%VERSION%.exe" copy /y "..\dist\Agent_Setup_v%VERSION%.exe" "%NAS_PATH%\" >nul 2>&1
    copy /y "..\dist\version.json" "%NAS_PATH%\" >nul 2>&1
    echo         NAS deploy done
) else (
    echo [WARNING] NAS path not accessible: %NAS_PATH%
    echo         NAS deploy skipped
)

REM Deploy to server (agent_updates dir — auto-update endpoints read from here)
echo       - Server deploy...
if "%DEPLOY_SERVER%"=="0" (
    echo         Skipped (--no-deploy flag set)
    goto server_deploy_done
)

where scp >nul 2>&1
if errorlevel 1 (
    echo         [WARNING] SCP not found. Install OpenSSH client to enable auto-deploy.
    goto server_deploy_done
)

REM Upload EXE files first, then version.json last
REM (Agents poll version.json; upload it only after new EXEs are in place)
set SCP_FAILED=0
set SCP_OPTS=-o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new -o BatchMode=yes

echo         Uploading x64 EXE...
scp %SCP_OPTS% "..\dist\agent_windows_x64.exe" "%SERVER_HOST%:%SERVER_DEPLOY_PATH%"
if errorlevel 1 set SCP_FAILED=1

if exist "..\dist\agent_windows_x86.exe" (
    echo         Uploading x86 EXE...
    scp %SCP_OPTS% "..\dist\agent_windows_x86.exe" "%SERVER_HOST%:%SERVER_DEPLOY_PATH%"
    if errorlevel 1 set SCP_FAILED=1
)

if exist "..\dist\agent_windows_win7_x64.exe" (
    echo         Uploading Win7 x64 EXE...
    scp %SCP_OPTS% "..\dist\agent_windows_win7_x64.exe" "%SERVER_HOST%:%SERVER_DEPLOY_PATH%"
    if errorlevel 1 set SCP_FAILED=1
)

if "%SCP_FAILED%"=="0" (
    echo         Uploading version.json (triggers auto-update)...
    scp %SCP_OPTS% "..\dist\version.json" "%SERVER_HOST%:%SERVER_DEPLOY_PATH%"
    if errorlevel 1 set SCP_FAILED=1
) else (
    echo         [WARNING] EXE upload failed, skipping version.json to prevent broken rollout.
)

if "%SCP_FAILED%"=="0" (
    echo         Server deploy done — Agents will auto-update on next heartbeat
) else (
    echo.
    echo         [ERROR] Server deploy failed. Check:
    echo            1. SSH key is set up for %SERVER_HOST%
    echo               ^(ssh-keygen ^&^& ssh-copy-id %SERVER_HOST%^)
    echo            2. %SERVER_DEPLOY_PATH% exists and is writable
    echo            3. Network/VPN connectivity to the server
    echo         Manual fallback:
    echo            scp ..\dist\agent_windows_*.exe ..\dist\version.json %SERVER_HOST%:%SERVER_DEPLOY_PATH%
)
:server_deploy_done

echo.
echo ========================================
echo   Build Complete! v%VERSION%
echo.
echo   Output files in ..\dist\:
echo.
echo   [64-bit] agent_windows_x64.exe
if "%BUILD_32%"=="1" echo   [32-bit] agent_windows_x86.exe
if not "%BUILD_32%"=="1" echo   [32-bit] Not built (Python 3.8-32 required)
if "%BUILD_WIN7_64%"=="1" echo   [Win7-64] agent_windows_win7_x64.exe
if not "%BUILD_WIN7_64%"=="1" echo   [Win7-64] Not built (Python 3.8 required)
if exist "..\dist\Agent_Setup_v%VERSION%.exe" echo   [Setup] Agent_Setup_v%VERSION%.exe
echo   [JSON]  version.json
echo ========================================
if not "%AUTO_MODE%"=="1" pause
