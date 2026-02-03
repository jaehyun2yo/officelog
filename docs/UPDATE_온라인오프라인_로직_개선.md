# ComputerOff 온라인/오프라인 판단 로직 개선

## 업데이트 날짜
2026-02-03

## 개요
온라인/오프라인 정보 수집 문제의 근본적 해결책을 적용했습니다. 기존 Agent와 완전 호환됩니다.

---

## 변경 사항

### 1. SQLite WAL 모드 활성화 (server/database.py:31-34)

```python
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn
```

**효과:**
- 동시 읽기/쓰기 성능 향상
- `database is locked` 오류 방지
- 30초 타임아웃 및 busy_timeout 설정으로 안정성 강화

---

### 2. 온라인 판단 기준 변경 (server/database.py:26-28, 223)

```python
# 온라인 판단 기준 (초) - 하트비트 60초 * 3 = 180초
ONLINE_THRESHOLD_SECONDS = 180

data['status'] = 'online' if seconds_ago < ONLINE_THRESHOLD_SECONDS else 'offline'
```

**변경 내용:**
- 기존: 120초 (하트비트 60초 * 2)
- 변경: 180초 (하트비트 60초 * 3)

**이유:**
- 1회 하트비트 누락 허용
- Task Scheduler 지연 고려
- 온라인 깜빡임 현상 해소

---

### 3. 복구 로직 중복 방지 (server/database.py:853-879)

```python
# NOT EXISTS 조건 추가로 중복 삽입 방지
cursor.execute("""
    SELECT ...
    FROM heartbeats h
    JOIN events e ON h.computer_name = e.computer_name
    WHERE NOT EXISTS (
        SELECT 1 FROM events e2
        WHERE e2.computer_name = h.computer_name
        AND e2.event_type = 'shutdown'
        AND datetime(e2.timestamp) = datetime(h.last_seen)
    )
    ...
""", (ONLINE_THRESHOLD_SECONDS,))
```

**효과:**
- 동시 요청 시에도 같은 시간의 shutdown 중복 삽입 방지
- ONLINE_THRESHOLD_SECONDS 상수 사용으로 일관성 유지

---

### 4. 하트비트 에러 처리 강화 (agent/installer.py:802-859)

```python
def send_heartbeat(server_url: str) -> bool:
    """하트비트를 서버로 전송 (실시간 온라인 상태용)

    구조화된 에러 처리:
    - 401 인증 실패: 연속 3회 실패 시 하트비트 건너뛰기 (자동 복구 지원)
    - 500+ 서버 오류: 로깅 후 재시도
    - 네트워크 오류: 로깅 후 재시도
    """
    # API 키 무효 상태 확인 (연속 실패 기반)
    if state.get('api_key_fail_count', 0) >= 3:
        log_error("[SKIP] API 키 연속 3회 실패 - 하트비트 건너뜀")
        return False
    ...
```

**핵심 설계:**
- 연속 3회 401 실패 시에만 하트비트 건너뛰기 (일시적 오류 허용)
- 성공 시 카운터 자동 리셋 (자동 복구)
- 재설치 시 state.json 초기화로 카운터 리셋
- 상세 에러 로깅으로 문제 원인 추적 가능

---

### 5. 설치 시 상태 파일 초기화 (agent/installer.py:1290-1297)

```python
# 상태 파일 초기화 (이전 오류 상태 클리어 - api_key_fail_count 등)
state_path = get_install_dir() / STATE_FILE
if state_path.exists():
    try:
        state_path.unlink()
        log_error("[INSTALL] 이전 상태 파일 초기화됨")
    except Exception:
        pass
```

**효과:**
- 재설치 시 `api_key_fail_count` 등 이전 오류 상태 자동 클리어
- 잘못된 API 키로 3회 실패 후에도 재설치로 복구 가능

---

### 6. 설치 결과 검증 (agent/installer.py:1312-1345)

```python
# Task Scheduler 등록 및 결과 수집
task_results = {}
task_results['boot'] = register_task("ComputerOff-Boot", "boot")
task_results['monitor'] = register_task("ComputerOff-Monitor", "monitor")
task_results['shutdown'] = register_task("ComputerOff-Shutdown", "shutdown")
task_results['heartbeat'] = register_task("ComputerOff-Heartbeat", "heartbeat")

# 필수 작업 검증 (shutdown은 복구 로직이 대체하므로 선택적)
critical_tasks = ['boot', 'monitor', 'heartbeat']
failed = [name for name in critical_tasks if not task_results.get(name)]

if failed:
    # 오류 메시지 표시
    ...
```

**효과:**
- 필수 작업(boot, monitor, heartbeat) 등록 실패 시 명확한 오류 메시지 표시
- shutdown은 서버 복구 로직이 대체하므로 선택적으로 처리

---

## 수정된 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `server/database.py` | WAL 모드, 180초 기준, 복구 중복 방지 |
| `agent/installer.py` | 에러 처리, 상태 초기화, 설치 검증 |

---

## 사이드이펙트 분석

| 변경 | 영향 | 위험도 |
|------|------|--------|
| 180초 판단 기준 | 오프라인 전환 최대 60초 지연 | **낮음** |
| WAL 모드 | `-wal`, `-shm` 파일 생성 | **낮음** |
| 복구 중복 방지 | 기존 중복 데이터는 그대로 | **없음** |
| 에러 로깅 강화 | 로그 파일 크기 증가 | **낮음** |
| 연속 3회 401 체크 | 일시적 오류 허용, 자동 복구 | **없음** |

---

## 하위 호환성

| 시나리오 | 호환성 |
|----------|--------|
| 서버만 업데이트 | **완전 호환** - 기존 Agent 정상 동작 |
| Agent만 업데이트 | **완전 호환** - 기존 서버 정상 동작 |
| 기존 DB | **완전 호환** - 스키마 변경 없음 |

**배포 순서:** 서버 먼저 → Agent 선택적 업데이트

---

## 테스트 절차

### test_gui.py로 수동 테스트

```
1. python agent/test_gui.py 실행
2. "연결 테스트" → 성공 확인
3. "하트비트 전송" → HTTP 200 확인
4. 관리자 페이지에서 온라인 상태 확인
5. 3분 대기 후 오프라인 확인 (180초 기준)
```

### 검증 체크리스트

| # | 테스트 | 예상 결과 |
|---|--------|-----------|
| 1 | 하트비트 전송 | 온라인 표시, 180초 이내 유지 |
| 2 | 3분 대기 | 180초 후 오프라인 전환 |
| 3 | 잘못된 API 키 3회 | 로그에 실패 횟수 기록, 4번째부터 건너뜀 |
| 4 | 재설치 후 하트비트 | 카운터 리셋, 정상 전송 |
| 5 | 동시 복구 요청 | shutdown 이벤트 1개만 생성 |

---

## 성공 기준

1. **온라인 깜빡임 해소** - 정상 PC가 오프라인으로 표시되지 않음
2. **에러 추적 가능** - 로그로 하트비트 실패 원인 파악 가능
3. **자동 복구** - 일시적 오류 후 자동으로 정상화
4. **중복 방지** - 동일 시간 shutdown 중복 없음
5. **하위 호환** - 기존 시스템 영향 없음
