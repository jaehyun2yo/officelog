"""
ComputerOff Agent 자동 업데이트
- 서버 API에서 최신 버전 확인
- 새 EXE 다운로드
- 배치 스크립트로 자체 교체
"""

import json
import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, NamedTuple

import requests


class UpdateInfo(NamedTuple):
    version: str
    download_url: str


def compare_versions(current: str, latest: str) -> bool:
    """latest가 current보다 새로운지 비교 (semantic versioning)"""
    try:
        current_parts = [int(x) for x in current.split('.')]
        latest_parts = [int(x) for x in latest.split('.')]
        return latest_parts > current_parts
    except (ValueError, AttributeError):
        return False


def check_for_update(server_url: str, current_version: str, variant: str) -> Optional[UpdateInfo]:
    """서버에서 최신 버전 확인

    Returns:
        UpdateInfo if update available, None otherwise
    """
    try:
        url = f"{server_url.rstrip('/')}/api/agent/version"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        latest_version = data.get('version', '')

        if not latest_version or not compare_versions(current_version, latest_version):
            return None

        # Verify variant exists
        variants = data.get('variants', {})
        if variant not in variants:
            return None

        download_url = f"/api/agent/download/{variant}"
        return UpdateInfo(version=latest_version, download_url=download_url)
    except Exception:
        return None


def download_update(server_url: str, download_url: str, install_dir: Path) -> Optional[Path]:
    """새 EXE 다운로드

    Args:
        server_url: 서버 URL
        download_url: 다운로드 경로 (/api/agent/download/x64)
        install_dir: 설치 디렉토리

    Returns:
        다운로드된 파일 경로, 실패 시 None
    """
    update_dir = install_dir / "_update"
    update_dir.mkdir(exist_ok=True)

    tmp_path = update_dir / "agent_new.exe.tmp"
    final_path = update_dir / "agent_new.exe"

    try:
        url = f"{server_url.rstrip('/')}{download_url}"
        response = requests.get(url, timeout=120, stream=True)
        if response.status_code != 200:
            return None

        content_length = int(response.headers.get('content-length', 0))

        downloaded = 0
        with open(tmp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

        # Verify size
        if content_length > 0 and downloaded != content_length:
            tmp_path.unlink(missing_ok=True)
            return None

        # Rename tmp to final
        if final_path.exists():
            final_path.unlink()
        tmp_path.rename(final_path)

        return final_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        return None


def create_update_script(new_exe_path: Path, current_exe_path: Path, install_dir: Path) -> Optional[Path]:
    """업데이트 배치 스크립트 생성

    배치 스크립트가 하는 일:
    1. 모든 ComputerOff 작업 비활성화
    2. Monitor 프로세스 강제 종료
    3. heartbeat PID 종료 대기
    4. EXE 교체 (5회 재시도)
    5. 작업 재활성화
    6. Monitor 재시작
    7. 정리
    """
    update_dir = install_dir / "_update"
    script_path = update_dir / "do_update.bat"
    log_path = update_dir / "update_log.txt"

    exe_name = current_exe_path.name
    pid = os.getpid()

    script_content = f'''@echo off
chcp 65001 >nul 2>&1
echo [%date% %time%] Update script started >> "{log_path}"

REM Step 1: Disable all tasks
echo [%date% %time%] Disabling tasks... >> "{log_path}"
schtasks /Change /TN "ComputerOff-Monitor" /DISABLE >nul 2>&1
schtasks /Change /TN "ComputerOff-Heartbeat" /DISABLE >nul 2>&1
schtasks /Change /TN "ComputerOff-Boot" /DISABLE >nul 2>&1
schtasks /Change /TN "ComputerOff-Shutdown" /DISABLE >nul 2>&1

REM Step 2: Stop monitor task gracefully then force
echo [%date% %time%] Stopping monitor... >> "{log_path}"
schtasks /End /TN "ComputerOff-Monitor" >nul 2>&1
timeout /t 2 /nobreak >nul

REM Step 3: Wait for heartbeat process (PID {pid}) to release EXE lock
REM tasklist | find 파이프라인이 숨김 콘솔에서 새 창을 띄우는 문제를 피하기 위해
REM 단순 타임아웃으로 대체. 남은 프로세스는 Step 4의 taskkill /F로 정리됨.
echo [%date% %time%] Waiting 5 seconds for PID {pid} to exit... >> "{log_path}"
timeout /t 5 /nobreak >nul

REM Step 4: Kill any remaining agent processes
echo [%date% %time%] Killing remaining processes... >> "{log_path}"
taskkill /F /IM "{exe_name}" >nul 2>&1
timeout /t 3 /nobreak >nul

REM Step 5: Replace EXE (retry 5 times)
echo [%date% %time%] Replacing EXE... >> "{log_path}"
set RETRY=0
:copy_retry
if %RETRY% GEQ 5 (
    echo [%date% %time%] ERROR: Failed to copy after 5 retries >> "{log_path}"
    goto enable_tasks
)
copy /Y "{new_exe_path}" "{current_exe_path}" >nul 2>&1
if %errorlevel% NEQ 0 (
    set /a RETRY+=1
    echo [%date% %time%] Copy failed, retry %RETRY%/5 >> "{log_path}"
    timeout /t 2 /nobreak >nul
    goto copy_retry
)

REM Step 6: Verify file size
for %%A in ("{new_exe_path}") do set NEW_SIZE=%%~zA
for %%A in ("{current_exe_path}") do set CUR_SIZE=%%~zA
if "%NEW_SIZE%" NEQ "%CUR_SIZE%" (
    echo [%date% %time%] ERROR: Size mismatch NEW=%NEW_SIZE% CUR=%CUR_SIZE% >> "{log_path}"
    goto enable_tasks
)
echo [%date% %time%] EXE replaced successfully (%CUR_SIZE% bytes) >> "{log_path}"

:enable_tasks
REM Step 7: Re-enable all tasks
echo [%date% %time%] Re-enabling tasks... >> "{log_path}"
schtasks /Change /TN "ComputerOff-Monitor" /ENABLE >nul 2>&1
schtasks /Change /TN "ComputerOff-Heartbeat" /ENABLE >nul 2>&1
schtasks /Change /TN "ComputerOff-Boot" /ENABLE >nul 2>&1
schtasks /Change /TN "ComputerOff-Shutdown" /ENABLE >nul 2>&1

REM Step 8: Restart monitor
echo [%date% %time%] Restarting monitor... >> "{log_path}"
schtasks /Run /TN "ComputerOff-Monitor" >nul 2>&1

REM Step 9: Cleanup (delete the downloaded new exe, keep log)
echo [%date% %time%] Cleanup... >> "{log_path}"
del /F /Q "{new_exe_path}" >nul 2>&1

echo [%date% %time%] Update complete >> "{log_path}"
'''

    try:
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        return script_path
    except Exception:
        return None


def execute_update(script_path: Path, log_func=None):
    """업데이트 배치 스크립트 실행 후 현재 프로세스 종료

    Args:
        script_path: 배치 스크립트 경로
        log_func: 로그 함수 (installer.py의 log_error)
    """
    try:
        if log_func:
            log_func("[UPDATE] 업데이트 스크립트 실행 중...")

        # Run batch script with no console window.
        # CREATE_NO_WINDOW와 DETACHED_PROCESS는 MSDN상 상호 배타적이라
        # 같이 쓰면 Windows가 기본값으로 폴백하여 자식 파이프라인에 콘솔이 생길 수 있음.
        # CREATE_NO_WINDOW 단독 + STARTUPINFO.SW_HIDE 조합이 가장 확실하게 창을 숨긴다.
        CREATE_NO_WINDOW = 0x08000000
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.Popen(
            ['cmd', '/c', str(script_path)],
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
            startupinfo=startupinfo
        )

        if log_func:
            log_func("[UPDATE] 업데이트 프로세스 시작됨, 에이전트 종료")

        # Exit current process - batch script will wait for this PID
        sys.exit(0)
    except SystemExit:
        raise  # Let sys.exit propagate
    except Exception as e:
        if log_func:
            log_func(f"[UPDATE] 업데이트 실행 실패: {e}")


def is_update_locked(install_dir: Path, max_age_minutes: int = 10) -> bool:
    """업데이트 잠금 확인 (중복 업데이트 방지)"""
    lock_file = install_dir / "_update" / "update.lock"
    if not lock_file.exists():
        return False

    try:
        mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
        age = (datetime.now() - mtime).total_seconds() / 60
        if age > max_age_minutes:
            lock_file.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        return False


def acquire_update_lock(install_dir: Path) -> bool:
    """업데이트 잠금 획득"""
    try:
        update_dir = install_dir / "_update"
        update_dir.mkdir(exist_ok=True)
        lock_file = update_dir / "update.lock"
        lock_file.write_text(str(os.getpid()))
        return True
    except Exception:
        return False


def release_update_lock(install_dir: Path):
    """업데이트 잠금 해제"""
    try:
        lock_file = install_dir / "_update" / "update.lock"
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass


def trigger_auto_update(server_url: str, current_version: str, variant: str,
                         install_dir: Path, log_func=None):
    """자동 업데이트 전체 프로세스

    Args:
        server_url: 서버 URL
        current_version: 현재 버전
        variant: 에이전트 variant (x64/x86/win7_x64)
        install_dir: 설치 디렉토리
        log_func: 로그 함수
    """
    if is_update_locked(install_dir):
        if log_func:
            log_func("[UPDATE] 이미 업데이트 진행 중 (잠금됨)")
        return

    # Check for update
    update_info = check_for_update(server_url, current_version, variant)
    if not update_info:
        return

    if log_func:
        log_func(f"[UPDATE] 새 버전 발견: {current_version} → {update_info.version}")

    if not acquire_update_lock(install_dir):
        return

    try:
        # Download
        new_exe = download_update(server_url, update_info.download_url, install_dir)
        if not new_exe:
            if log_func:
                log_func("[UPDATE] 다운로드 실패")
            release_update_lock(install_dir)
            return

        if log_func:
            log_func(f"[UPDATE] 다운로드 완료: {new_exe}")

        # Get current EXE path
        if getattr(sys, 'frozen', False):
            current_exe = Path(sys.executable)
        else:
            if log_func:
                log_func("[UPDATE] 개발 모드에서는 업데이트 불가")
            release_update_lock(install_dir)
            return

        # Create update script
        script = create_update_script(new_exe, current_exe, install_dir)
        if not script:
            if log_func:
                log_func("[UPDATE] 업데이트 스크립트 생성 실패")
            release_update_lock(install_dir)
            return

        # Execute (this will exit the current process)
        execute_update(script, log_func)
    except SystemExit:
        raise
    except Exception as e:
        if log_func:
            log_func(f"[UPDATE] 업데이트 오류: {e}")
        release_update_lock(install_dir)
