"""
ComputerOff Agent - 부팅/종료 이벤트 전송 스크립트
Windows 7/8/10/11 호환 (Python 3.8)
"""

import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


# 재시도 설정
MAX_RETRIES = 3
RETRY_DELAY = 2  # 초


def get_config_path() -> Path:
    return Path(__file__).parent / "config.json"


def load_config() -> dict:
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_computer_name() -> str:
    return socket.gethostname()


def send_event(server_url: str, event_type: str) -> bool:
    """이벤트를 서버로 전송 (재시도 포함)"""
    url = f"{server_url.rstrip('/')}/api/events"
    data = {
        "computer_name": get_computer_name(),
        "event_type": event_type,
        "timestamp": datetime.now().isoformat()
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, json=data, timeout=15)
            if response.status_code == 200:
                return True
            log_error(f"이벤트 전송 실패 (시도 {attempt + 1}/{MAX_RETRIES}): HTTP {response.status_code}")
        except Exception as e:
            log_error(f"이벤트 전송 실패 (시도 {attempt + 1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    return False


def send_heartbeat(server_url: str) -> bool:
    """하트비트를 서버로 전송 (실시간 온라인 상태용, 재시도 포함)"""
    url = f"{server_url.rstrip('/')}/api/heartbeat"
    params = {
        "computer_name": get_computer_name()
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, params=params, timeout=10)
            if response.status_code == 200:
                return True
        except Exception as e:
            # 하트비트는 로그 남기지 않음 (너무 자주 실행됨)
            pass

        if attempt < MAX_RETRIES - 1:
            time.sleep(1)

    return False


def log_error(message: str):
    """에러 로그 기록"""
    log_path = Path(__file__).parent / "agent.log"
    timestamp = datetime.now().isoformat()
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")


def main():
    if len(sys.argv) < 2:
        print("사용법: agent.py <boot|shutdown>")
        sys.exit(1)

    event_type = sys.argv[1].lower()
    if event_type not in ('boot', 'shutdown'):
        print("이벤트 타입은 'boot' 또는 'shutdown'이어야 합니다")
        sys.exit(1)

    config = load_config()
    server_url = config.get('server_url')

    if not server_url:
        log_error("서버 URL이 설정되지 않았습니다")
        sys.exit(1)

    success = send_event(server_url, event_type)

    if success:
        print(f"이벤트 전송 완료: {event_type}")
    else:
        print(f"이벤트 전송 실패: {event_type}")
        sys.exit(1)


if __name__ == "__main__":
    main()
