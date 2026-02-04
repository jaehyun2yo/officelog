# Windows 이벤트 로그 기반 부팅/종료 이벤트 수집 업데이트

## 개요

Agent가 온라인 상태일 때 주기적으로 Windows 이벤트 로그에서 부팅/종료 이벤트를 수집하여 서버로 전송하고,
관리자 페이지에서 이벤트 상세 정보를 표시합니다.

## 변경 사항

### 1. Database 스키마 확장 (`server/database.py`)

**events 테이블 신규 컬럼:**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `event_detail` | TEXT | 이벤트 상세 (log_start/kernel_boot/normal/unexpected/user_initiated) |
| `event_source` | TEXT | 이벤트 소스 (realtime/event_log) |
| `event_record_id` | INTEGER | Windows 이벤트 로그 레코드 ID (중복 방지용) |

**중복 방지 인덱스:**
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_record
ON events(computer_name, event_record_id) WHERE event_record_id IS NOT NULL;
```

**insert_event 함수 변경:**
- 반환값: `(event_id, is_duplicate)` 튜플
- `event_record_id`로 중복 체크

---

### 2. Server API 수정 (`server/main.py`)

**EventCreate 모델 확장:**

```python
class EventCreate(BaseModel):
    computer_name: str
    event_type: str
    timestamp: Optional[datetime] = None
    event_detail: Optional[str] = None      # 신규
    event_source: Optional[str] = 'realtime' # 신규
    event_record_id: Optional[int] = None    # 신규
```

**POST /api/events 응답 확장:**
```json
{"id": 123, "status": "ok", "duplicate": false}
```

---

### 3. Agent 이벤트 로그 수집 (`agent/installer.py`)

**신규 함수:**

| 함수 | 설명 |
|------|------|
| `get_boot_events_from_log()` | Windows 이벤트 로그에서 부팅 이벤트 조회 (EventID 6005, 12) |
| `get_all_events_from_log()` | 부팅/종료 모든 이벤트 수집 (시간순 정렬) |
| `sync_event_logs()` | 이벤트 로그를 서버와 동기화 |
| `recover_missed_events()` | 부팅 시 미전송 이벤트 복구 (부팅/종료 모두) |

**send_event 함수 확장:**
```python
def send_event(
    server_url: str,
    event_type: str,
    timestamp: datetime = None,
    event_detail: str = None,       # 신규
    event_source: str = 'realtime', # 신규
    event_record_id: int = None     # 신규
) -> bool:
```

**하트비트에 이벤트 로그 수집 통합:**
- 하트비트 전송 성공 후 `sync_event_logs()` 호출
- 1분마다 새 이벤트 자동 동기화

---

### 4. 관리자 페이지 UI (`server/static/`)

**전체 이벤트 타임라인 개선:**
- 이벤트 상세 배지 표시: (이벤트 로그), (정상), (비정상), (사용자 요청)

**일별 요약 테이블 개선:**
- 종료 상태 컬럼 추가
- 상태별 색상 배지: 정상(녹색), 비정상(빨강), 사용자(노랑), 실시간(파랑)

---

## 이벤트 상세 값 정의

| event_type | event_detail | Windows EventID | 설명 |
|------------|--------------|-----------------|------|
| boot | log_start | 6005 | 이벤트 로그 서비스 시작 |
| boot | kernel_boot | 12 | Kernel-General 부팅 |
| boot | realtime | - | 실시간 감지 |
| shutdown | normal | 6006 | 정상 종료 |
| shutdown | unexpected | 6008 | 비정상 종료 (전원 차단) |
| shutdown | user_initiated | 1074 | 사용자 종료 요청 |
| shutdown | realtime | - | 실시간 감지 |

---

## 데이터 흐름

```
Windows PC (Agent)
     │
     ├── 부팅 시 ──▶ recover_missed_events() [오프라인 중 누락 복구]
     │
     ├── 1분마다 ──▶ send_heartbeat()
     │    (온라인)        │
     │                    ├── 하트비트 전송
     │                    └── sync_event_logs()
     │                          │
     │                          ├── 서버에서 마지막 전송 시간 조회
     │                          ├── get_all_events_from_log()
     │                          └── 새 이벤트만 전송 (중복 방지)
     │
     └── POST /api/events
            {computer_name, event_type, timestamp,
             event_detail, event_source, event_record_id}
                  │
                  ▼
           FastAPI Server
                  │
                  ├── 중복 체크 (event_record_id)
                  └── events 테이블 저장
                  │
                  ▼
           관리자 페이지
                  │
                  ├── 전체 타임라인: event_detail 표시
                  └── 일별 요약: 종료 상태 표시
```

---

## 테스트 방법

### 1. Agent 이벤트 수집 테스트

```python
# Python에서 직접 테스트
from installer import get_all_events_from_log
events = get_all_events_from_log(max_events=10)
for e in events:
    print(f"{e['event_type']} ({e['event_detail']}): {e['timestamp']}")
```

### 2. 서버 API 테스트

```bash
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "computer_name": "test-pc",
    "event_type": "shutdown",
    "event_detail": "normal",
    "event_source": "event_log",
    "event_record_id": 12345
  }'
```

### 3. 중복 방지 테스트

동일 `event_record_id`로 재전송 시:
```json
{"id": 123, "status": "ok", "duplicate": true}
```

### 4. 관리자 페이지 확인

- 전체 이벤트 타임라인에 이벤트 상세 배지 표시 확인
- 일별 요약 테이블에 종료 상태 컬럼 표시 확인

---

## 호환성

- 기존 데이터와 완벽 호환 (새 컬럼은 NULL 허용)
- 기존 Agent 버전과 호환 (새 필드 없어도 동작)
- 32비트/64비트 Windows 모두 지원

---

## 작성일

2026-02-04
