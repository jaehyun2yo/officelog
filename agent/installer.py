"""
ComputerOff Agent 설치 프로그램
- 서버 URL 설정 GUI
- Windows Task Scheduler 등록 (부팅/종료 트리거)
- WM_ENDSESSION 실시간 감지 (1차 레이어)
- 부팅 시 이벤트 로그 복구 (3차 레이어)
- Windows 7/8/10/11 호환
"""

import ctypes
import ctypes.wintypes
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

import requests

# ==================== Windows API 상수 ====================
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
WS_EX_TOOLWINDOW = 0x00000080

# ==================== ctypes 구조체 정의 ====================
if sys.platform == 'win32':
    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_void_p
    )

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("style", ctypes.c_uint),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.c_void_p),
            ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", ctypes.c_wchar_p),
            ("lpszClassName", ctypes.c_wchar_p),
            ("hIconSm", ctypes.c_void_p),
        ]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("time", ctypes.c_uint),
            ("pt_x", ctypes.c_long),
            ("pt_y", ctypes.c_long),
        ]

# GUI 제거됨 - 자동 설치 모드만 지원


# ==================== Agent 기능 (통합) ====================

# 종료 이벤트는 Windows 종료 시 빠르게 전송해야 하므로 최소화
MAX_RETRIES = 2
RETRY_DELAY = 1

# 상태 파일 경로
STATE_FILE = "state.json"


def get_computer_name() -> str:
    return socket.gethostname()


def get_local_ip() -> str:
    """로컬 IP 주소 반환

    8.8.8.8에 UDP 소켓 연결을 통해 로컬 IP 획득 (실제 패킷 전송 없음)
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def log_error(message: str):
    """에러 로그 기록"""
    log_path = get_install_dir() / "agent.log"
    timestamp = datetime.now().isoformat()
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
    except:
        pass


def get_ntp_time(ntp_server: str = "time.windows.com", timeout: int = 5) -> datetime:
    """NTP 서버에서 한국 시간 가져오기 (UTC+9)"""
    NTP_DELTA = 2208988800
    try:
        data = b'\x1b' + 47 * b'\0'
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(data, (ntp_server, 123))
        response, _ = sock.recvfrom(1024)
        sock.close()
        timestamp = struct.unpack('!I', response[40:44])[0]
        utc_time = datetime.utcfromtimestamp(timestamp - NTP_DELTA)
        return utc_time + timedelta(hours=9)
    except Exception as e:
        log_error(f"NTP 시간 조회 실패: {e}")
        return datetime.now()


def get_korea_time() -> datetime:
    """한국 시간 반환 (NTP 우선, 실패 시 로컬)"""
    for server in ["time.windows.com", "ntp.kornet.net", "time.google.com"]:
        try:
            return get_ntp_time(server)
        except:
            continue
    return datetime.now()


def send_event(
    server_url: str,
    event_type: str,
    timestamp: datetime = None,
    event_detail: str = None,
    event_source: str = 'realtime',
    event_record_id: int = None
) -> bool:
    """이벤트를 서버로 전송 (재시도 포함)

    Args:
        server_url: 서버 URL
        event_type: 이벤트 타입 (boot/shutdown)
        timestamp: 이벤트 발생 시간
        event_detail: 이벤트 상세 (log_start/kernel_boot/normal/unexpected/user_initiated)
        event_source: 이벤트 소스 (realtime/event_log)
        event_record_id: Windows 이벤트 로그 레코드 ID
    """
    url = f"{server_url.rstrip('/')}/api/events"
    if timestamp is None:
        timestamp = get_korea_time()
    data = {
        "computer_name": get_computer_name(),
        "event_type": event_type,
        "timestamp": timestamp.isoformat()
    }

    # 선택적 필드 추가
    if event_detail:
        data["event_detail"] = event_detail
    if event_source:
        data["event_source"] = event_source
    if event_record_id is not None:
        data["event_record_id"] = event_record_id

    headers = {}

    log_error(f"이벤트 전송 시작: {event_type}, URL={url}, data={data}")

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, json=data, headers=headers, timeout=5)
            log_error(f"서버 응답 (시도 {attempt + 1}): status={response.status_code}, body={response.text[:200]}")
            if response.status_code == 200:
                try:
                    result = response.json()
                    is_duplicate = result.get('duplicate', False)
                    log_error(f"이벤트 전송 성공: {event_type}, id={result.get('id')}, duplicate={is_duplicate}")
                except ValueError:
                    log_error(f"이벤트 전송 성공: {event_type} (non-JSON response)")
                return True
            log_error(f"이벤트 전송 실패 (시도 {attempt + 1}/{MAX_RETRIES}): HTTP {response.status_code}")
        except Exception as e:
            log_error(f"이벤트 전송 실패 (시도 {attempt + 1}/{MAX_RETRIES}): {type(e).__name__}: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    log_error(f"이벤트 전송 최종 실패: {event_type}")
    return False


def send_shutdown_event_sync(server_url: str) -> bool:
    """종료 이벤트 빠른 동기 전송 (WM_ENDSESSION용)

    Windows 종료 시간이 제한적이므로 최소 재시도로 빠르게 전송
    """
    url = f"{server_url.rstrip('/')}/api/events"
    korea_time = get_korea_time()
    data = {
        "computer_name": get_computer_name(),
        "event_type": "shutdown",
        "timestamp": korea_time.isoformat()
    }
    headers = {}

    log_error(f"종료 이벤트 전송 시작: URL={url}")
    log_error(f"종료 이벤트 데이터: {data}")

    try:
        response = requests.post(url, json=data, headers=headers, timeout=3)
        log_error(f"서버 응답: status={response.status_code}, body={response.text[:200]}")
        if response.status_code == 200:
            # 서버 응답 검증
            try:
                result = response.json()
                if result.get('id') or result.get('status') == 'ok':
                    log_error(f"종료 이벤트 전송 성공 (WM_ENDSESSION): id={result.get('id')}")
                    update_state_after_shutdown(korea_time)
                    return True
                else:
                    log_error(f"서버 응답 형식 이상 (상태 업데이트 안함): {result}")
                    return False
            except ValueError:
                # JSON 파싱 실패 시에도 200이면 성공으로 처리
                log_error("종료 이벤트 전송 성공 (WM_ENDSESSION, non-JSON response)")
                update_state_after_shutdown(korea_time)
                return True
        log_error(f"종료 이벤트 전송 실패: HTTP {response.status_code} - 상태 업데이트 안함 (부팅 시 복구 예정)")
    except Exception as e:
        log_error(f"종료 이벤트 전송 예외: {type(e).__name__}: {e} - 상태 업데이트 안함 (부팅 시 복구 예정)")

    return False


# ==================== 상태 파일 관리 ====================

def get_state_path() -> Path:
    """상태 파일 경로 반환"""
    return get_install_dir() / STATE_FILE


def load_state() -> dict:
    """상태 파일 로드"""
    state_path = get_state_path()
    if state_path.exists():
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log_error(f"상태 파일 로드 실패: {e}")
    return {}


def save_state(state: dict):
    """상태 파일 저장"""
    state_path = get_state_path()
    try:
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_error(f"상태 파일 저장 실패: {e}")


def update_state_after_shutdown(timestamp: datetime, record_id: int = None):
    """종료 이벤트 전송 후 상태 업데이트"""
    state = load_state()
    state['last_sent_shutdown'] = timestamp.isoformat()
    if record_id is not None:
        state['last_sent_event_record_id'] = record_id
    save_state(state)


# ==================== 이벤트 로그 복구 ====================

def get_boot_events_from_log(since_timestamp: datetime = None, max_events: int = 5) -> list:
    """Windows 이벤트 로그에서 부팅 이벤트 조회

    EventID:
    - 6005: 이벤트 로그 서비스 시작 (System) -> log_start
    - 12: Kernel-General 부팅 (System) -> kernel_boot
    """
    query = "*[System[(EventID=6005 or EventID=12)]]"

    try:
        result = subprocess.run(
            ['wevtutil', 'qe', 'System',
             '/q:' + query,
             '/c:' + str(max_events),
             '/f:xml',
             '/rd:true'],  # 최신순
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            log_error(f"부팅 이벤트 로그 조회 실패: {result.stderr}")
            return []

        return parse_boot_event_xml(result.stdout, since_timestamp)

    except subprocess.TimeoutExpired:
        log_error("부팅 이벤트 로그 조회 타임아웃")
        return []
    except Exception as e:
        log_error(f"부팅 이벤트 로그 조회 실패: {e}")
        return []


def parse_boot_event_xml(xml_output: str, since_timestamp: datetime = None) -> list:
    """부팅 이벤트 로그 XML 파싱"""
    events = []

    if not xml_output.strip():
        return events

    wrapped_xml = f"<Events>{xml_output}</Events>"

    try:
        root = ElementTree.fromstring(wrapped_xml)
    except ElementTree.ParseError:
        log_error("부팅 이벤트 XML 파싱 실패")
        return events

    ns = {'evt': 'http://schemas.microsoft.com/win/2004/08/events/event'}

    for event_elem in root.findall('.//evt:Event', ns):
        try:
            system = event_elem.find('evt:System', ns)
            if system is None:
                continue

            event_id_elem = system.find('evt:EventID', ns)
            time_created_elem = system.find('evt:TimeCreated', ns)
            event_record_id_elem = system.find('evt:EventRecordID', ns)

            if event_id_elem is None or time_created_elem is None:
                continue

            event_id = int(event_id_elem.text)
            time_str = time_created_elem.get('SystemTime', '')
            record_id = int(event_record_id_elem.text) if event_record_id_elem is not None else 0

            timestamp = parse_event_timestamp(time_str)
            if timestamp is None:
                continue

            # UTC를 KST로 변환
            timestamp_kst = timestamp + timedelta(hours=9)

            # since_timestamp 이후의 이벤트만
            if since_timestamp and timestamp_kst < since_timestamp - timedelta(seconds=1):
                continue

            # 부팅 타입 결정
            if event_id == 6005:
                boot_type = "log_start"
            else:  # 12
                boot_type = "kernel_boot"

            events.append({
                'event_type': 'boot',
                'event_id': event_id,
                'event_detail': boot_type,
                'timestamp': timestamp_kst,
                'record_id': record_id
            })

        except Exception as e:
            log_error(f"부팅 이벤트 파싱 오류: {e}")
            continue

    return events


def get_all_events_from_log(since_timestamp: datetime = None, max_events: int = 20) -> list:
    """부팅/종료 모든 이벤트 수집 (시간순 정렬)

    Returns:
        [{'event_type': 'boot'/'shutdown',
          'event_detail': 'log_start'/'kernel_boot'/'normal'/'unexpected'/'user_initiated',
          'timestamp': datetime,
          'record_id': int}, ...]
    """
    boot_events = get_boot_events_from_log(since_timestamp, max_events)
    shutdown_events = get_shutdown_events_from_log(since_timestamp, max_events)

    # shutdown_events의 shutdown_type을 event_detail로 변환
    for event in shutdown_events:
        event['event_type'] = 'shutdown'
        event['event_detail'] = event.pop('shutdown_type', 'normal')

    all_events = boot_events + shutdown_events
    return sorted(all_events, key=lambda e: e['timestamp'])


def get_shutdown_events_from_log(since_timestamp: datetime = None, max_events: int = 5) -> list:
    """Windows 이벤트 로그에서 종료 이벤트 조회

    EventID:
    - 6006: 정상 종료 (이벤트 로그 서비스 중지)
    - 6008: 비정상 종료 (전원 차단, 크래시)
    - 1074: 사용자 종료 요청
    """
    # EventID 6006, 6008은 EventLog 프로바이더, 1074는 User32 프로바이더
    query = "*[System[(EventID=6006 or EventID=6008 or EventID=1074)]]"

    try:
        result = subprocess.run(
            ['wevtutil', 'qe', 'System',
             '/q:' + query,
             '/c:' + str(max_events),
             '/f:xml',
             '/rd:true'],  # 최신순
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            log_error(f"이벤트 로그 조회 실패: {result.stderr}")
            return []

        return parse_event_xml(result.stdout, since_timestamp)

    except subprocess.TimeoutExpired:
        log_error("이벤트 로그 조회 타임아웃")
        return []
    except Exception as e:
        log_error(f"이벤트 로그 조회 실패: {e}")
        return []


def parse_event_xml(xml_output: str, since_timestamp: datetime = None) -> list:
    """이벤트 로그 XML 파싱"""
    events = []

    if not xml_output.strip():
        return events

    # XML 출력이 여러 Event 요소로 구성됨 (루트 없음)
    # 래퍼 요소로 감싸서 파싱
    wrapped_xml = f"<Events>{xml_output}</Events>"

    try:
        root = ElementTree.fromstring(wrapped_xml)
    except ElementTree.ParseError:
        # 일부 특수 문자로 인한 파싱 실패 시 개별 처리
        log_error("XML 파싱 실패, 개별 이벤트 처리 시도")
        return parse_events_individually(xml_output, since_timestamp)

    # 네임스페이스 처리
    ns = {'evt': 'http://schemas.microsoft.com/win/2004/08/events/event'}

    for event_elem in root.findall('.//evt:Event', ns):
        try:
            system = event_elem.find('evt:System', ns)
            if system is None:
                continue

            event_id_elem = system.find('evt:EventID', ns)
            time_created_elem = system.find('evt:TimeCreated', ns)
            event_record_id_elem = system.find('evt:EventRecordID', ns)

            if event_id_elem is None or time_created_elem is None:
                continue

            event_id = int(event_id_elem.text)
            time_str = time_created_elem.get('SystemTime', '')
            record_id = int(event_record_id_elem.text) if event_record_id_elem is not None else 0

            # ISO 형식 타임스탬프 파싱 (UTC)
            # 형식: 2024-01-15T18:30:45.1234567Z
            timestamp = parse_event_timestamp(time_str)
            if timestamp is None:
                continue

            # UTC를 KST로 변환
            timestamp_kst = timestamp + timedelta(hours=9)

            # since_timestamp 이후의 이벤트만 (1초 여유를 두어 경계 조건 문제 방지)
            if since_timestamp and timestamp_kst < since_timestamp - timedelta(seconds=1):
                continue

            # 종료 타입 결정
            if event_id == 6006:
                shutdown_type = "normal"
            elif event_id == 6008:
                shutdown_type = "unexpected"
            else:  # 1074
                shutdown_type = "user_initiated"

            events.append({
                'event_id': event_id,
                'timestamp': timestamp_kst,
                'record_id': record_id,
                'shutdown_type': shutdown_type
            })

        except Exception as e:
            log_error(f"이벤트 파싱 오류: {e}")
            continue

    return events


def parse_events_individually(xml_output: str, since_timestamp: datetime = None) -> list:
    """개별 이벤트 파싱 (XML 전체 파싱 실패 시 폴백)"""
    events = []
    # <Event xmlns=...>...</Event> 패턴으로 분리
    event_pattern = re.compile(r'<Event[^>]*>.*?</Event>', re.DOTALL)

    for match in event_pattern.finditer(xml_output):
        event_xml = match.group()
        try:
            event_elem = ElementTree.fromstring(event_xml)
            ns = {'evt': 'http://schemas.microsoft.com/win/2004/08/events/event'}

            system = event_elem.find('evt:System', ns)
            if system is None:
                # 네임스페이스 없이 재시도
                system = event_elem.find('System')
                if system is None:
                    continue

            event_id_elem = system.find('evt:EventID', ns) or system.find('EventID')
            time_created_elem = system.find('evt:TimeCreated', ns) or system.find('TimeCreated')
            event_record_id_elem = system.find('evt:EventRecordID', ns) or system.find('EventRecordID')

            if event_id_elem is None or time_created_elem is None:
                continue

            event_id = int(event_id_elem.text)
            time_str = time_created_elem.get('SystemTime', '')
            record_id = int(event_record_id_elem.text) if event_record_id_elem is not None else 0

            timestamp = parse_event_timestamp(time_str)
            if timestamp is None:
                continue

            timestamp_kst = timestamp + timedelta(hours=9)

            if since_timestamp and timestamp_kst <= since_timestamp:
                continue

            if event_id == 6006:
                shutdown_type = "normal"
            elif event_id == 6008:
                shutdown_type = "unexpected"
            else:
                shutdown_type = "user_initiated"

            events.append({
                'event_id': event_id,
                'timestamp': timestamp_kst,
                'record_id': record_id,
                'shutdown_type': shutdown_type
            })

        except Exception:
            continue

    return events


def parse_event_timestamp(time_str: str) -> datetime:
    """이벤트 타임스탬프 문자열 파싱"""
    if not time_str:
        return None

    try:
        # 형식: 2024-01-15T18:30:45.1234567Z
        # 마이크로초 이하 제거
        time_str = time_str.rstrip('Z')
        if '.' in time_str:
            base, frac = time_str.split('.')
            # 마이크로초까지만 (6자리)
            frac = frac[:6]
            time_str = f"{base}.{frac}"
            return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def check_server_connection(server_url: str) -> bool:
    """서버 연결 상태 확인"""
    try:
        url = f"{server_url.rstrip('/')}/api/health"
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except Exception as e:
        log_error(f"서버 연결 확인 실패: {e}")
        # /api/health가 없을 수 있으므로 기본 URL로 재시도
        try:
            response = requests.get(server_url, timeout=5)
            return response.status_code in (200, 404)  # 서버가 응답하면 OK
        except Exception:
            return False


def get_last_event_from_server(server_url: str, event_type: str) -> datetime:
    """서버에서 마지막 전송된 이벤트 시간 조회

    Args:
        server_url: 서버 URL
        event_type: 이벤트 타입 ('boot' 또는 'shutdown')

    Returns:
        마지막 이벤트 timestamp (datetime) 또는 None
    """
    url = f"{server_url.rstrip('/')}/api/events/last"
    params = {
        "computer_name": get_computer_name(),
        "event_type": event_type
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            result = response.json()
            if result.get('found') and result.get('event'):
                timestamp_str = result['event'].get('timestamp')
                if timestamp_str:
                    # ISO 형식 파싱
                    try:
                        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00').replace('+00:00', ''))
                    except ValueError:
                        log_error(f"서버 이벤트 timestamp 파싱 실패: {timestamp_str}")
                        return None
        log_error(f"서버에서 마지막 {event_type} 이벤트 없음")
        return None
    except Exception as e:
        log_error(f"서버 마지막 이벤트 조회 실패: {e}")
        return None


def recover_missed_events(server_url: str) -> int:
    """부팅 시 미전송 이벤트 복구 (부팅/종료 모두)

    개선된 복구 로직:
    1. 서버에서 마지막 전송된 이벤트 시간 조회
    2. 이벤트 로그에서 그 이후의 모든 이벤트 조회 및 전송
    """
    log_error("recover_missed_events 시작")
    state = load_state()
    log_error(f"현재 로컬 상태: {state}")

    # 서버 연결 확인 (연결 안 되면 복구 건너뛰기)
    log_error(f"서버 연결 확인: {server_url}")
    if not check_server_connection(server_url):
        log_error("서버 연결 실패 - 복구 건너뜀 (다음 부팅 시 재시도)")
        return 0
    log_error("서버 연결 확인 완료")

    # 서버에서 마지막 전송된 이벤트 시간 조회
    last_boot_on_server = get_last_event_from_server(server_url, 'boot')
    last_shutdown_on_server = get_last_event_from_server(server_url, 'shutdown')
    log_error(f"서버의 마지막 boot 시간: {last_boot_on_server}")
    log_error(f"서버의 마지막 shutdown 시간: {last_shutdown_on_server}")

    # 로컬 상태에서 마지막 전송 시간 조회
    last_sent_local = None
    if state.get('last_sent_shutdown'):
        try:
            last_sent_local = datetime.fromisoformat(state['last_sent_shutdown'])
            log_error(f"로컬의 마지막 shutdown 시간: {last_sent_local}")
        except ValueError as e:
            log_error(f"로컬 last_sent_shutdown 파싱 실패: {e}")

    # 가장 최신 시간 결정 (모든 소스 중)
    timestamps = [t for t in [last_boot_on_server, last_shutdown_on_server, last_sent_local] if t]
    if timestamps:
        last_sent = max(timestamps)
        log_error(f"비교 기준 시간 (가장 최신): {last_sent}")
    else:
        # 모두 없으면 첫 실행 - 최근 이벤트로 상태 초기화
        log_error("첫 실행 - 서버/로컬 모두 기록 없음, 상태 초기화")
        events = get_all_events_from_log(max_events=1)
        if events:
            if events[0]['event_type'] == 'shutdown':
                state['last_sent_shutdown'] = events[0]['timestamp'].isoformat()
                state['last_sent_event_record_id'] = events[0]['record_id']
                save_state(state)
            log_error(f"상태 초기화 완료: {state}")
        return 0

    # 이벤트 로그에서 last_sent 이후의 모든 이벤트 조회
    events = get_all_events_from_log(since_timestamp=last_sent, max_events=10)
    log_error(f"이벤트 로그에서 조회된 이벤트: {len(events)}개")
    for i, event in enumerate(events):
        log_error(f"  [{i}] {event}")

    if not events:
        log_error("복구할 이벤트 없음")
        return 0

    # 미전송 이벤트 필터링 및 전송
    sent_count = 0
    last_record_id = state.get('last_sent_event_record_id')
    log_error(f"마지막 전송 record_id: {last_record_id}")

    for event in events:
        # 서버로 전송 (event_record_id로 중복 방지)
        log_error(f"미전송 이벤트 복구 시도: {event['event_type']}({event['event_detail']}) at {event['timestamp']} (record_id={event['record_id']})")

        if send_event(
            server_url=server_url,
            event_type=event['event_type'],
            timestamp=event['timestamp'],
            event_detail=event['event_detail'],
            event_source='event_log',
            event_record_id=event['record_id']
        ):
            sent_count += 1
            # 상태 업데이트 (shutdown만)
            if event['event_type'] == 'shutdown':
                update_state_after_shutdown(event['timestamp'], event['record_id'])
            log_error(f"복구 전송 성공: record_id={event['record_id']}")
        else:
            log_error(f"복구 전송 실패: record_id={event['record_id']}")

    if sent_count > 0:
        log_error(f"이전 이벤트 {sent_count}개 복구 완료")
    else:
        log_error("복구된 이벤트 없음")

    return sent_count


def recover_missed_shutdown_events(server_url: str) -> int:
    """부팅 시 미전송 이벤트 복구 (하위 호환성을 위한 래퍼)"""
    return recover_missed_events(server_url)


# ==================== WM_ENDSESSION 모니터 ====================

class ShutdownMonitor:
    """WM_ENDSESSION 감지 백그라운드 모니터

    Windows 종료/재시작 요청 시 즉시 감지하여 서버에 이벤트 전송
    """

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.hwnd = None
        self.shutdown_sent = False
        self._wnd_proc_callback = None
        self._class_atom = None

        # 종료 시 가장 마지막에 처리되도록 설정 (우선순위 낮춤)
        # 0x100 = 낮은 우선순위 (다른 앱보다 늦게 종료 메시지 수신)
        try:
            result = ctypes.windll.kernel32.SetProcessShutdownParameters(0x100, 0)
            log_error(f"SetProcessShutdownParameters 호출: result={result}")
        except Exception as e:
            log_error(f"SetProcessShutdownParameters 실패: {e}")

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """윈도우 프로시저"""
        if msg == WM_QUERYENDSESSION:
            log_error("WM_QUERYENDSESSION 수신 - 종료 요청 감지!")
            if not self.shutdown_sent:
                self._send_shutdown()
            return 1  # 종료 허용

        elif msg == WM_ENDSESSION:
            log_error(f"WM_ENDSESSION 수신 (wparam={wparam}) - 실제 종료 진행!")
            if wparam and not self.shutdown_sent:
                self._send_shutdown()
            return 0

        elif msg == WM_CLOSE:
            ctypes.windll.user32.DestroyWindow(hwnd)
            return 0

        elif msg == WM_DESTROY:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0

        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _send_shutdown(self):
        """종료 이벤트 전송 (종료 지연 API 사용)"""
        # 종료 지연 요청 (Windows에게 "작업 중" 알림)
        if self.hwnd:
            try:
                reason = "ComputerOff: 종료 이벤트 전송 중..."
                result = ctypes.windll.user32.ShutdownBlockReasonCreate(
                    self.hwnd,
                    ctypes.c_wchar_p(reason)
                )
                log_error(f"ShutdownBlockReasonCreate 호출: result={result}")
            except Exception as e:
                log_error(f"ShutdownBlockReasonCreate 실패: {e}")

        self.shutdown_sent = True
        log_error("종료 이벤트 전송 시작 (WM_ENDSESSION)")

        # 종료 이벤트 전송
        result = send_shutdown_event_sync(self.server_url)
        log_error(f"종료 이벤트 전송 결과: {result}")

        # 종료 지연 해제
        if self.hwnd:
            try:
                result = ctypes.windll.user32.ShutdownBlockReasonDestroy(self.hwnd)
                log_error(f"ShutdownBlockReasonDestroy 호출: result={result}")
            except Exception as e:
                log_error(f"ShutdownBlockReasonDestroy 실패: {e}")

    def create_window(self) -> bool:
        """숨겨진 윈도우 생성"""
        try:
            # 콜백 함수 참조 유지 (GC 방지)
            self._wnd_proc_callback = WNDPROC(self._wnd_proc)

            hinstance = ctypes.windll.kernel32.GetModuleHandleW(None)
            class_name = "ComputerOffShutdownMonitor"

            # 윈도우 클래스 등록
            wndclass = WNDCLASSEXW()
            wndclass.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wndclass.style = CS_HREDRAW | CS_VREDRAW
            wndclass.lpfnWndProc = self._wnd_proc_callback
            wndclass.cbClsExtra = 0
            wndclass.cbWndExtra = 0
            wndclass.hInstance = hinstance
            wndclass.hIcon = None
            wndclass.hCursor = None
            wndclass.hbrBackground = None
            wndclass.lpszMenuName = None
            wndclass.lpszClassName = class_name
            wndclass.hIconSm = None

            self._class_atom = ctypes.windll.user32.RegisterClassExW(ctypes.byref(wndclass))
            if not self._class_atom:
                error = ctypes.get_last_error()
                log_error(f"RegisterClassExW 실패: {error}")
                return False

            # 숨겨진 윈도우 생성
            self.hwnd = ctypes.windll.user32.CreateWindowExW(
                WS_EX_TOOLWINDOW,  # 작업 표시줄에 표시 안 함
                class_name,
                "ComputerOff Shutdown Monitor",
                0,  # WS_OVERLAPPED
                0, 0, 0, 0,  # x, y, width, height
                None,  # parent
                None,  # menu
                hinstance,
                None   # lpParam
            )

            if not self.hwnd:
                error = ctypes.get_last_error()
                log_error(f"CreateWindowExW 실패: {error}")
                return False

            log_error(f"모니터 윈도우 생성 완료: hwnd={self.hwnd}")
            return True

        except Exception as e:
            log_error(f"윈도우 생성 실패: {e}")
            return False

    def run_message_loop(self):
        """메시지 루프 실행 (블로킹)"""
        log_error("메시지 루프 시작")
        msg = MSG()

        while True:
            ret = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0:  # WM_QUIT
                log_error("WM_QUIT 수신, 메시지 루프 종료")
                break
            elif ret == -1:  # 에러
                error = ctypes.get_last_error()
                log_error(f"GetMessageW 에러: {error}")
                break
            else:
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

    def cleanup(self):
        """리소스 정리"""
        if self.hwnd:
            ctypes.windll.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self._class_atom:
            hinstance = ctypes.windll.kernel32.GetModuleHandleW(None)
            ctypes.windll.user32.UnregisterClassW("ComputerOffShutdownMonitor", hinstance)
            self._class_atom = None


def run_shutdown_monitor(server_url: str):
    """종료 모니터 실행"""
    log_error("종료 모니터 시작")

    monitor = ShutdownMonitor(server_url)
    if not monitor.create_window():
        log_error("모니터 윈도우 생성 실패")
        return

    try:
        monitor.run_message_loop()
    except Exception as e:
        log_error(f"메시지 루프 에러: {e}")
    finally:
        monitor.cleanup()
        log_error("종료 모니터 종료")


def sync_event_logs(server_url: str) -> int:
    """이벤트 로그를 서버와 동기화

    1. 서버에서 마지막 전송된 이벤트 조회
    2. 이벤트 로그에서 그 이후의 새 이벤트 수집
    3. 새 이벤트만 서버로 전송

    Returns: 전송된 이벤트 수
    """
    state = load_state()

    # 서버에서 마지막 전송된 boot/shutdown 이벤트 시간 조회
    last_boot = get_last_event_from_server(server_url, 'boot')
    last_shutdown = get_last_event_from_server(server_url, 'shutdown')

    # 둘 중 더 오래된 시간 사용 (그 이후의 모든 이벤트 수집)
    if last_boot and last_shutdown:
        since_timestamp = min(last_boot, last_shutdown)
    elif last_boot:
        since_timestamp = last_boot
    elif last_shutdown:
        since_timestamp = last_shutdown
    else:
        # 서버에 이벤트가 없으면 최근 1시간 이벤트만 수집
        since_timestamp = datetime.now() - timedelta(hours=1)

    # 이벤트 로그에서 새 이벤트 수집
    events = get_all_events_from_log(since_timestamp=since_timestamp, max_events=20)

    if not events:
        return 0

    sent_count = 0

    for event in events:
        # 이벤트 전송 (event_record_id로 중복 방지)
        success = send_event(
            server_url=server_url,
            event_type=event['event_type'],
            timestamp=event['timestamp'],
            event_detail=event['event_detail'],
            event_source='event_log',
            event_record_id=event['record_id']
        )

        if success:
            sent_count += 1
            # 상태 업데이트
            if event['event_type'] == 'shutdown':
                update_state_after_shutdown(event['timestamp'], event['record_id'])

    if sent_count > 0:
        log_error(f"[SYNC] 이벤트 로그 동기화: {sent_count}개 전송")

    return sent_count


def send_heartbeat(server_url: str) -> bool:
    """하트비트를 서버로 전송 (실시간 온라인 상태용)

    구조화된 에러 처리:
    - 500+ 서버 오류: 로깅 후 재시도
    - 네트워크 오류: 로깅 후 재시도

    하트비트 전송 후 이벤트 로그 동기화도 수행
    """
    url = f"{server_url.rstrip('/')}/api/heartbeat"
    params = {
        "computer_name": get_computer_name(),
        "ip_address": get_local_ip()
    }
    headers = {}

    heartbeat_success = False

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                heartbeat_success = True
                break

            elif response.status_code >= 500:
                log_error(f"[SERVER] 서버 오류 (HTTP {response.status_code})")
            else:
                log_error(f"[HTTP] 예상치 못한 응답: HTTP {response.status_code}")

        except requests.exceptions.Timeout as e:
            log_error(f"[TIMEOUT] 하트비트 타임아웃: {e}")
        except requests.exceptions.ConnectionError as e:
            log_error(f"[NETWORK] 연결 실패: {e}")
        except Exception as e:
            log_error(f"[ERROR] 예상치 못한 오류: {type(e).__name__}: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(1)

    # 하트비트 성공 시 이벤트 로그 동기화
    if heartbeat_success:
        try:
            sync_event_logs(server_url)
        except Exception as e:
            log_error(f"[SYNC] 이벤트 로그 동기화 실패: {e}")

    return heartbeat_success


# ==================== 설치 관련 기능 ====================

def is_admin() -> bool:
    """관리자 권한 확인"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """관리자 권한으로 재실행"""
    if sys.platform != 'win32':
        return False

    try:
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = sys.executable
            script = sys.argv[0]
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe_path, f'"{script}"', None, 1
            )
            return True

        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe_path, "", None, 1
        )
        return True
    except:
        return False


def get_exe_path() -> str:
    """실행 파일 경로 반환"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def get_install_dir() -> Path:
    """설치 디렉토리 반환"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def get_bundled_config_path() -> Path:
    """PyInstaller 번들 내 config.json 경로 반환"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 번들 내부 (_MEIPASS)
        return Path(sys._MEIPASS) / "config.json"
    return Path(__file__).parent / "config.json"


def save_config(server_url: str):
    """설정 파일 저장 (설치 디렉토리에)"""
    config_path = get_install_dir() / "config.json"
    config = {"server_url": server_url}
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_config() -> dict:
    """설정 파일 로드

    우선순위:
    1. 설치 디렉토리의 config.json (이미 설치된 경우)
    2. PyInstaller 번들 내 config.json (첫 설치 시)
    """
    # 1. 설치 디렉토리 확인
    install_config_path = get_install_dir() / "config.json"
    if install_config_path.exists():
        try:
            with open(install_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    # 2. PyInstaller 번들 확인
    bundled_config_path = get_bundled_config_path()
    if bundled_config_path.exists():
        try:
            with open(bundled_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    return {}


def create_task_scheduler_xml(event_type: str) -> str:
    """Task Scheduler XML 생성 (Windows 7 호환)"""
    exe_path = get_exe_path()

    # 기본 설정
    execution_time_limit = "PT30S"
    allow_hard_terminate = "true"

    if event_type == 'boot':
        trigger = """
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>"""
    elif event_type == 'heartbeat':
        # 1분마다 반복 실행 (실시간 온라인 상태 확인용)
        trigger = """
    <TimeTrigger>
      <Enabled>true</Enabled>
      <StartBoundary>2020-01-01T00:00:00</StartBoundary>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>"""
    elif event_type == 'monitor':
        # 로그온 시 시작, 무제한 실행 (종료 모니터)
        trigger = """
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>"""
        execution_time_limit = "PT0S"  # 무제한
        allow_hard_terminate = "false"  # 강제 종료 방지
    else:
        # shutdown - EventID 1074 트리거 (폴백)
        trigger = """
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;&lt;Select Path="System"&gt;*[System[Provider[@Name='User32'] and (EventID=1074)]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>"""

    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ComputerOff Agent - {event_type} event</Description>
  </RegistrationInfo>
  <Triggers>{trigger}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>{allow_hard_terminate}</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>{execution_time_limit}</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{exe_path}"</Command>
      <Arguments>--run {event_type}</Arguments>
    </Exec>
  </Actions>
</Task>'''
    return xml


def register_task(task_name: str, event_type: str) -> bool:
    """Task Scheduler에 작업 등록"""
    try:
        xml_content = create_task_scheduler_xml(event_type)
        xml_path = get_install_dir() / f"{task_name}.xml"

        with open(xml_path, 'w', encoding='utf-16') as f:
            f.write(xml_content)

        result = subprocess.run(
            ['schtasks', '/Create', '/TN', task_name, '/XML', str(xml_path), '/F'],
            capture_output=True,
            text=True
        )

        try:
            xml_path.unlink()
        except FileNotFoundError:
            pass

        return result.returncode == 0

    except Exception as e:
        print(f"작업 등록 실패: {e}")
        return False


def unregister_task(task_name: str) -> bool:
    """Task Scheduler에서 작업 제거"""
    try:
        result = subprocess.run(
            ['schtasks', '/Delete', '/TN', task_name, '/F'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def register_to_server(server_url: str) -> bool:
    """서버에 PC 등록 (설치 시 호출)"""
    url = f"{server_url.rstrip('/')}/api/computers/register"
    params = {
        "computer_name": get_computer_name(),
        "ip_address": get_local_ip()
    }
    try:
        response = requests.post(url, params=params, timeout=10)
        if response.status_code == 200:
            log_error("서버 등록 성공")
            return True
        log_error(f"서버 등록 실패: HTTP {response.status_code}")
        return False
    except Exception as e:
        log_error(f"서버 등록 실패: {e}")
        return False


def install_agent(server_url: str) -> tuple:
    """Agent 설치"""
    results = []

    # 설치 디렉토리에 config.json 저장
    try:
        save_config(server_url)
        results.append(("설정 저장", True))
    except Exception as e:
        log_error(f"설정 저장 실패: {e}")
        results.append(("설정 저장", False))

    # 서버에 PC 등록 (즉시 관리자 페이지에 표시)
    register_result = register_to_server(server_url)
    results.append(("서버 등록", register_result))

    boot_result = register_task("ComputerOff-Boot", "boot")
    results.append(("부팅 작업 등록", boot_result))

    # 1차: WM_ENDSESSION 모니터 (종료 요청 시 즉시 감지)
    monitor_result = register_task("ComputerOff-Monitor", "monitor")
    results.append(("종료 모니터 등록", monitor_result))

    # 2차: EventID 1074 트리거 (폴백)
    shutdown_result = register_task("ComputerOff-Shutdown", "shutdown")
    results.append(("종료 작업 등록 (폴백)", shutdown_result))

    # 실시간 상태 확인용 하트비트 (1분마다)
    heartbeat_result = register_task("ComputerOff-Heartbeat", "heartbeat")
    results.append(("실시간 상태 확인 등록", heartbeat_result))

    return results


def uninstall_agent() -> tuple:
    """Agent 완전 제거 (모든 설정 파일 삭제)"""
    results = []
    install_dir = get_install_dir()

    # Task Scheduler 작업 제거
    boot_result = unregister_task("ComputerOff-Boot")
    results.append(("부팅 작업 제거", boot_result))

    monitor_result = unregister_task("ComputerOff-Monitor")
    results.append(("종료 모니터 제거", monitor_result))

    shutdown_result = unregister_task("ComputerOff-Shutdown")
    results.append(("종료 작업 제거", shutdown_result))

    heartbeat_result = unregister_task("ComputerOff-Heartbeat")
    results.append(("실시간 상태 확인 제거", heartbeat_result))

    # 설정 파일 제거
    config_path = install_dir / "config.json"
    if config_path.exists():
        config_path.unlink()
        results.append(("설정 파일 제거", True))

    # 상태 파일 제거
    state_path = install_dir / STATE_FILE
    if state_path.exists():
        try:
            state_path.unlink()
            results.append(("상태 파일 제거", True))
        except Exception:
            results.append(("상태 파일 제거", False))

    # 로그 파일 제거
    log_path = install_dir / "agent.log"
    if log_path.exists():
        try:
            log_path.unlink()
            results.append(("로그 파일 제거", True))
        except Exception:
            results.append(("로그 파일 제거", False))

    # 임시 XML 파일들 제거
    for xml_file in install_dir.glob("ComputerOff-*.xml"):
        try:
            xml_file.unlink()
            results.append((f"{xml_file.name} 제거", True))
        except Exception:
            results.append((f"{xml_file.name} 제거", False))

    return results


def is_agent_installed() -> bool:
    """기존 Agent 설치 여부 확인 (Task Scheduler 기준)"""
    try:
        result = subprocess.run(
            ['schtasks', '/Query', '/TN', 'ComputerOff-Boot'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def load_bundled_config() -> dict:
    """PyInstaller 번들 내 config.json만 로드 (설치 시 사용)"""
    bundled_config_path = get_bundled_config_path()
    if bundled_config_path.exists():
        try:
            with open(bundled_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def alloc_console():
    """콘솔 창 동적 생성 (windowed 모드에서 설치 시 사용)"""
    try:
        ctypes.windll.kernel32.AllocConsole()
        # 표준 출력 재연결
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
    except:
        pass


def free_console():
    """콘솔 창 해제"""
    try:
        ctypes.windll.kernel32.FreeConsole()
    except:
        pass


def print_progress(current: int, total: int, prefix: str = ""):
    """진행바 출력"""
    bar_length = 30
    filled = int(bar_length * current / total)
    bar = "█" * filled + "░" * (bar_length - filled)
    percent = int(100 * current / total)
    print(f"\r{prefix} [{bar}] {percent}%", end="", flush=True)
    if current == total:
        print()  # 완료 시 줄바꿈


def auto_install():
    """자동 설치 (config.json의 설정 사용)

    빌드 시 포함된 config.json의 server_url과 api_key를 사용하여 자동 설치
    기존 설치가 있으면 자동으로 제거 후 재설치
    """
    # 관리자 권한 확인
    if not is_admin():
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "관리자 권한이 필요합니다.\n프로그램을 마우스 우클릭 후 '관리자 권한으로 실행'을 선택하세요.",
                "ComputerOff Agent",
                0x30  # MB_ICONWARNING
            )
        except:
            pass
        return False

    # 콘솔 창 생성 (windowed 모드에서 진행바 표시용)
    alloc_console()

    print("ComputerOff Agent 설치")
    print()

    # 번들된 config.json에서 설정 로드 (기존 설치 config 무시)
    config = load_bundled_config()
    server_url = config.get('server_url')

    if not server_url:
        print("오류: 설정 파일을 찾을 수 없습니다.")
        return False

    total_steps = 8  # 제거 2 + 설치 6
    current_step = 0

    # 기존 설치 확인 및 제거
    if is_agent_installed():
        print_progress(current_step, total_steps, "제거 중...")
        uninstall_agent()
        current_step += 2
        print_progress(current_step, total_steps, "제거 완료")

    # 새로 설치
    print_progress(current_step, total_steps, "설치 중...")

    # 상태 파일 초기화 (이전 오류 상태 클리어 - api_key_fail_count 등)
    state_path = get_install_dir() / STATE_FILE
    if state_path.exists():
        try:
            state_path.unlink()
            log_error("[INSTALL] 이전 상태 파일 초기화됨")
        except Exception:
            pass

    # 설정 저장
    try:
        save_config(server_url)
        current_step += 1
        print_progress(current_step, total_steps, "설치 중...")
    except:
        pass

    # 서버 등록
    register_to_server(server_url)
    current_step += 1
    print_progress(current_step, total_steps, "설치 중...")

    # Task Scheduler 등록 및 결과 수집
    task_results = {}

    task_results['boot'] = register_task("ComputerOff-Boot", "boot")
    current_step += 1
    print_progress(current_step, total_steps, "설치 중...")

    task_results['monitor'] = register_task("ComputerOff-Monitor", "monitor")
    current_step += 1
    print_progress(current_step, total_steps, "설치 중...")

    task_results['shutdown'] = register_task("ComputerOff-Shutdown", "shutdown")
    current_step += 1
    print_progress(current_step, total_steps, "설치 중...")

    task_results['heartbeat'] = register_task("ComputerOff-Heartbeat", "heartbeat")
    current_step += 1
    print_progress(current_step, total_steps, "설치 완료")

    # 필수 작업 검증 (shutdown은 복구 로직이 대체하므로 선택적)
    critical_tasks = ['boot', 'monitor', 'heartbeat']
    failed = [name for name in critical_tasks if not task_results.get(name)]

    if failed:
        log_error(f"[INSTALL] 필수 작업 등록 실패: {failed}")
        print()
        print(f"경고: 일부 작업 등록 실패 - {', '.join(failed)}")
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                f"필수 작업 등록 실패: {', '.join(failed)}\n\n관리자 권한으로 다시 실행하세요.",
                "ComputerOff Agent - 오류",
                0x10  # MB_ICONERROR
            )
        except:
            pass
        free_console()
        return False

    print()
    print("설치가 완료되었습니다.")
    time.sleep(2)

    # 콘솔 창 해제
    free_console()

    return True


def hide_console():
    """콘솔 창 숨기기 (백그라운드 실행용)"""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except:
        pass


def run_agent(event_type: str):
    """Agent 실행 (이벤트/하트비트 전송)"""
    # 콘솔 창 숨기기 (Task Scheduler 실행 시)
    hide_console()

    config = load_config()
    server_url = config.get('server_url')

    if not server_url:
        log_error("서버 URL이 설정되지 않았습니다")
        return

    if event_type == 'boot':
        # 3차 레이어: 이전 종료 이벤트 복구 (미전송분)
        try:
            recovered = recover_missed_shutdown_events(server_url)
            if recovered > 0:
                log_error(f"이전 종료 이벤트 {recovered}개 복구")
        except Exception as e:
            log_error(f"종료 이벤트 복구 실패: {e}")

        # 부팅 이벤트 전송
        send_event(server_url, 'boot')

    elif event_type == 'monitor':
        # 1차 레이어: WM_ENDSESSION 실시간 감지
        run_shutdown_monitor(server_url)

    elif event_type == 'heartbeat':
        send_heartbeat(server_url)

    else:
        # 2차 레이어: shutdown (EventID 1074 폴백)
        send_event(server_url, event_type)


def cli_uninstall():
    """명령줄 제거"""
    if not is_admin():
        print("오류: 관리자 권한이 필요합니다.")
        sys.exit(1)

    print("제거 중...")
    results = uninstall_agent()
    for name, success in results:
        status = "성공" if success else "실패"
        print(f"  {name}: {status}")
    print("\n제거 완료!")


def main():
    # --run 모드면 즉시 콘솔 숨기기 (Task Scheduler 실행 시)
    if len(sys.argv) > 1 and sys.argv[1] == '--run':
        hide_console()

    # 이벤트 실행 모드 (Task Scheduler에서 호출)
    if len(sys.argv) > 1:
        if sys.argv[1] == '--run' and len(sys.argv) > 2:
            event_type = sys.argv[2]
            if event_type in ('boot', 'shutdown', 'heartbeat', 'monitor'):
                run_agent(event_type)
            return

        if sys.argv[1] == '--uninstall':
            cli_uninstall()
            return

        if sys.argv[1] == '--help':
            print("ComputerOff Agent")
            print("")
            print("사용법:")
            print("  agent_windows.exe              자동 설치 (관리자 권한 필요)")
            print("  agent_windows.exe --uninstall  제거")
            print("  agent_windows.exe --run <type> 이벤트 실행 (내부용)")
            print("")
            print("이벤트 타입:")
            print("  boot       부팅 이벤트")
            print("  shutdown   종료 이벤트")
            print("  monitor    종료 모니터")
            print("  heartbeat  하트비트")
            return

    # 기본 동작: 자동 설치
    success = auto_install()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
