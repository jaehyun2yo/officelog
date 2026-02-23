# ComputerOff - PC 부팅/종료 모니터링 시스템

## 1. 프로그램 개요

ComputerOff는 여러 대의 Windows PC의 부팅 및 종료 시간을 자동으로 수집하고, 웹 대시보드를 통해 실시간으로 모니터링하는 시스템이다. 사무실이나 공장 등에서 PC 사용 현황을 관리자가 한눈에 파악할 수 있도록 설계되었다.

**핵심 기능:**
- Windows PC의 부팅/종료 이벤트 자동 감지 및 서버 전송
- 실시간 온라인/오프라인 상태 확인 (하트비트 기반)
- 웹 대시보드를 통한 전체 PC 현황 조회
- 일별 사용 요약, 타임라인, 통계 차트 제공
- 비정상 종료(전원 차단) 시 이벤트 로그 기반 자동 복구

**지원 환경:**
- Agent(클라이언트): Windows 7, 8, 10, 11 (32비트/64비트 모두 지원)
- Server: Python 3.8 이상, Linux/Windows 모두 가능

---

## 2. 시스템 구조

### 전체 아키텍처

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Windows PC 1  │     │   Windows PC 2  │     │   Windows PC N  │
│   (Agent)       │     │   (Agent)       │     │   (Agent)       │
│                 │     │                 │     │                 │
│ - 부팅 감지     │     │ - 부팅 감지     │     │ - 부팅 감지     │
│ - 종료 감지     │     │ - 종료 감지     │     │ - 종료 감지     │
│ - 하트비트 전송 │     │ - 하트비트 전송 │     │ - 하트비트 전송 │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │       HTTP POST       │       HTTP POST       │
         │    (API Key 인증)     │    (API Key 인증)     │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │    FastAPI Server       │
                    │                        │
                    │  - REST API 제공       │
                    │  - SQLite DB 저장      │
                    │  - 웹 대시보드 호스팅  │
                    │  - 세션/CSRF 인증      │
                    │  - Rate Limiting       │
                    └────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Web Dashboard        │
                    │                        │
                    │  - PC 목록/상태 표시   │
                    │  - 일별 요약           │
                    │  - 사용 타임라인       │
                    │  - 이벤트 히스토리     │
                    └────────────────────────┘
```

### 프로젝트 파일 구조

```
computeroff/
├── server/                      # 서버 (FastAPI)
│   ├── main.py                  # API 엔드포인트 및 앱 설정
│   ├── database.py              # SQLite DB 관리 및 비즈니스 로직
│   ├── computeroff.db           # SQLite 데이터베이스 (자동 생성)
│   ├── requirements.txt         # 서버 의존성
│   └── static/                  # 웹 대시보드 프론트엔드
│       ├── index.html           # 대시보드 메인 페이지
│       ├── style.css            # 스타일시트
│       └── script.js            # 클라이언트 로직
├── agent/                       # Windows Agent
│   ├── agent.py                 # 단순 이벤트 전송 스크립트
│   ├── installer.py             # 자동 설치 + 종료 모니터 + 복구 로직
│   ├── build.bat                # PyInstaller 빌드 스크립트
│   └── requirements.txt         # Agent 의존성
├── deploy/                      # 서버 배포 스크립트 (Oracle/Ubuntu VM용)
│   ├── deploy.sh                # 코드 업로드 스크립트
│   ├── install-service.sh       # systemd 서비스 등록
│   ├── setup-vm.sh              # VM 초기 설정
│   ├── setup-firewall.sh        # 방화벽 설정
│   └── *.service                # systemd 서비스 파일
├── dist/                        # 빌드 결과물
│   ├── agent_windows_x64.exe    # 64비트 (Windows 10/11)
│   ├── agent_windows_x86.exe    # 32비트 (Windows 7/8/10/11)
│   ├── agent_windows_win7_x64.exe  # Windows 7 64비트 전용
│   └── config.json              # 빌드에 포함되는 서버 설정
├── docs/                        # 문서
├── Procfile                     # Railway 배포용
├── railway.json                 # Railway 배포 설정
├── requirements.txt             # 루트 의존성
└── README.md                    # 이 문서
```

---

## 3. 주요 기능 상세 설명

### 3.1 Agent (Windows 클라이언트)

Agent는 Windows PC에 설치되어 부팅/종료 이벤트를 서버로 전송하는 프로그램이다. `installer.py`가 핵심 파일이며, 설치/실행/모니터링 기능을 모두 포함한다.

#### 3.1.1 종료 감지 3단계 레이어

종료 이벤트를 놓치지 않기 위해 3단계 감지 구조를 사용한다.

| 레이어 | 방식 | 설명 |
|--------|------|------|
| 1차 | WM_ENDSESSION 실시간 감지 | 숨겨진 윈도우를 생성하여 Windows 종료 메시지를 직접 수신. `ShutdownBlockReasonCreate`로 종료를 잠시 지연시키고 이벤트를 전송한다. |
| 2차 | EventID 1074 트리거 (폴백) | Windows Task Scheduler의 이벤트 트리거를 사용하여 사용자 종료 요청(EventID 1074) 감지 시 실행된다. |
| 3차 | 부팅 시 이벤트 로그 복구 | 다음 부팅 시 Windows 이벤트 로그(EventID 6006, 6008, 1074)를 조회하여 미전송된 종료 이벤트를 복구 전송한다. |

#### 3.1.2 하트비트 (실시간 상태 확인)

- Task Scheduler를 통해 **1분마다** 하트비트를 서버에 전송한다.
- 하트비트에는 컴퓨터 이름과 IP 주소가 포함된다.
- 서버는 마지막 하트비트로부터 **180초(3분)** 이내이면 온라인, 초과하면 오프라인으로 판단한다.
- API 키 인증 실패가 연속 3회 발생하면 하트비트 전송을 중단한다(재설치 시 초기화).

#### 3.1.3 NTP 시간 동기화

이벤트 타임스탬프의 정확성을 위해 NTP 서버에서 한국 시간(UTC+9)을 조회한다.

- 1순위: `time.windows.com`
- 2순위: `ntp.kornet.net`
- 3순위: `time.google.com`
- 모두 실패 시: 로컬 시스템 시간 사용

#### 3.1.4 자동 설치 (`auto_install`)

`installer.py`를 PyInstaller로 빌드한 exe 파일을 실행하면 자동 설치가 진행된다.

1. 관리자 권한 확인 (없으면 안내 메시지 표시)
2. 기존 설치가 있으면 자동 제거 후 재설치
3. 번들된 `config.json`에서 서버 URL과 API 키 로드
4. 설치 디렉토리에 `config.json` 저장
5. 서버에 PC 등록 (`POST /api/computers/register`)
6. Task Scheduler에 4개 작업 등록:
   - `ComputerOff-Boot`: 로그온 시 부팅 이벤트 전송 + 미전송 종료 복구
   - `ComputerOff-Monitor`: 로그온 시 WM_ENDSESSION 모니터 시작 (무제한 실행)
   - `ComputerOff-Shutdown`: EventID 1074 트리거 (폴백)
   - `ComputerOff-Heartbeat`: 1분 간격 반복 실행

#### 3.1.5 상태 파일 (`state.json`)

Agent는 상태 파일을 통해 마지막 전송된 종료 이벤트를 추적한다.

```json
{
  "last_sent_shutdown": "2026-02-19T18:30:00",
  "last_sent_event_record_id": 12345,
  "api_key_fail_count": 0
}
```

- `last_sent_shutdown`: 마지막 전송된 종료 이벤트 시간 (복구 시 기준)
- `last_sent_event_record_id`: Windows 이벤트 로그 Record ID (중복 전송 방지)
- `api_key_fail_count`: API 키 인증 연속 실패 횟수 (3회 초과 시 하트비트 중단)

#### 3.1.6 설정 파일 (`config.json`)

```json
{
  "server_url": "http://서버IP:8000",
  "api_key": "서버에서_발급된_API_키"
}
```

설정 로드 우선순위:
1. 설치 디렉토리의 `config.json` (이미 설치된 경우)
2. PyInstaller 번들 내 `config.json` (첫 설치 시)

### 3.2 서버 (FastAPI)

#### 3.2.1 보안 기능

| 기능 | 설명 |
|------|------|
| API Key 인증 | Agent 엔드포인트에 `X-API-Key` 헤더 필수. `secrets.compare_digest`로 타이밍 안전 비교 |
| 세션 인증 | 대시보드 엔드포인트에 쿠키 기반 세션 필수. 24시간 만료, 슬라이딩 갱신 |
| CSRF 토큰 | PUT/DELETE 요청에 `X-CSRF-Token` 헤더 필수 |
| 비밀번호 정책 | 최소 8자, 대문자/소문자/숫자 각 1개 이상 포함 |
| 비밀번호 해싱 | bcrypt 12라운드 (미설치 시 SHA-256 폴백, 자동 마이그레이션) |
| Rate Limiting | slowapi 기반, 엔드포인트별 분당 요청 제한 |
| 보안 헤더 | X-Content-Type-Options, X-Frame-Options, CSP 등 |
| 입력 검증 | Pydantic 모델 기반, 컴퓨터 이름 정규식 검증, 타임스탬프 범위 검증 |

#### 3.2.2 오프라인 종료 이벤트 자동 복구

서버 측에서도 종료 이벤트 복구 로직이 있다. PC 목록 조회(`GET /api/computers`) 시 다음 조건을 모두 만족하는 PC에 대해 자동으로 shutdown 이벤트를 생성한다:

1. 하트비트가 180초 이상 지남 (오프라인 전환)
2. 마지막 boot 이후 shutdown 이벤트가 없음
3. last_seen이 last_boot 이후임 (안전장치)
4. 같은 시간에 이미 shutdown 이벤트가 없음 (중복 방지)

복구된 shutdown 이벤트의 타임스탬프는 마지막 하트비트 시간(`last_seen`)을 사용한다.

#### 3.2.3 API 키 관리

- 서버 최초 실행 시 API 키가 자동 생성되고 콘솔에 1회만 표시된다.
- `secrets.token_urlsafe(32)` 사용 (43자 URL-safe 문자열)
- 대시보드에서 API 키 순환(rotation) 가능 (CSRF 보호)

### 3.3 웹 대시보드

대시보드는 `/server/static/index.html`에 구현된 단일 페이지 애플리케이션(SPA)이다.

#### 3.3.1 주요 화면 구성

| 섹션 | 설명 |
|------|------|
| 컴퓨터 목록 | 등록된 모든 PC의 온라인/오프라인 상태, IP 주소, 마지막 부팅/종료 시간 표시. 클릭 시 상세 이력 조회 |
| 일별 요약 | 선택한 날짜의 각 PC별 첫 부팅 시간과 마지막 종료 시간 표시. 날짜 네비게이션 지원 |
| 일별 사용 현황 | 7/14/30일 기간별 부팅-종료 시간 그리드 형태로 시각화 |
| 전체 이벤트 타임라인 | 모든 PC의 최근 이벤트를 시간순으로 표시. 1/3/7/14일 필터링 |
| 컴퓨터 관리 | 표시 이름 변경, 개별/전체 삭제, 상세 이력(요약/상세) 조회 |

#### 3.3.2 인증 흐름

1. 최초 접속 시 `GET /api/auth/check`로 상태 확인
2. 비밀번호 미설정이면 초기 비밀번호 설정 화면 표시
3. 비밀번호 설정 후 또는 기존 비밀번호가 있으면 로그인 화면 표시
4. 로그인 성공 시 세션 쿠키 설정 및 CSRF 토큰 수신
5. 이후 API 요청에 세션 쿠키 자동 포함, PUT/DELETE 요청에 CSRF 토큰 포함

---

## 4. API 엔드포인트 목록

### 4.1 Agent 전용 엔드포인트 (API Key 인증)

| 메서드 | 경로 | 설명 | Rate Limit | 파라미터 |
|--------|------|------|------------|----------|
| POST | `/api/events` | 부팅/종료 이벤트 생성 | 60/분 | Body: `computer_name`, `event_type` ("boot"/"shutdown"), `timestamp` (선택) |
| POST | `/api/heartbeat` | 하트비트 전송 | 120/분 | Query: `computer_name`, `ip_address` (선택) |
| POST | `/api/computers/register` | PC 등록 (설치 시) | 10/분 | Query: `computer_name`, `ip_address` (선택) |
| GET | `/api/events/last` | 마지막 이벤트 조회 | 60/분 | Query: `computer_name`, `event_type` |

### 4.2 대시보드 엔드포인트 (세션 인증)

| 메서드 | 경로 | 설명 | 파라미터 |
|--------|------|------|----------|
| GET | `/api/events` | 이벤트 목록 조회 | Query: `computer_name`, `event_type`, `start_date`, `end_date`, `limit` (기본 100) |
| GET | `/api/computers` | 컴퓨터 목록 조회 | - |
| GET | `/api/stats` | 일별 통계 조회 | Query: `computer_name`, `days` (기본 7) |
| GET | `/api/computers/{computer_name}/history` | 특정 PC 이벤트 이력 | Query: `days` (기본 30) |
| PUT | `/api/computers/{hostname}` | 표시 이름 변경 | Body: `display_name`, CSRF 필수 |
| DELETE | `/api/computers/{hostname}` | PC 및 관련 이벤트 삭제 | CSRF 필수 |
| DELETE | `/api/computers` | 모든 PC 및 이벤트 삭제 | CSRF 필수 |
| GET | `/api/timeline/shutdown` | 종료 이벤트 타임라인 | Query: `days` (기본 7) |
| GET | `/api/daily-summary` | 전체 일별 요약 | Query: `days` (기본 7) |
| GET | `/api/computers/{computer_name}/daily-summary` | 특정 PC 일별 요약 | Query: `days` (기본 30) |
| GET | `/api/timeline/all` | 전체 이벤트 타임라인 | Query: `days` (기본 7), `limit` (기본 100) |

### 4.3 인증 엔드포인트

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| GET | `/api/auth/check` | 인증 상태 확인 | - |
| POST | `/api/auth/set-password` | 최초 비밀번호 설정 | 5/분 |
| POST | `/api/auth/login` | 로그인 | 5/분 |
| POST | `/api/auth/logout` | 로그아웃 | - |

### 4.4 관리자 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/admin/rotate-api-key` | API 키 순환 | 세션 + CSRF |

### 4.5 공개 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/health` | 서버 상태 확인 (`{"status": "ok", "service": "computeroff"}`) |
| GET | `/` | 웹 대시보드 (index.html) |

---

## 5. 데이터베이스 구조

SQLite 데이터베이스(`computeroff.db`)를 사용하며, 서버 최초 실행 시 자동 생성된다.

### 5.1 테이블 목록

#### events (부팅/종료 이벤트)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER (PK, AUTO) | 이벤트 고유 ID |
| computer_name | TEXT (NOT NULL) | 컴퓨터 호스트명 |
| event_type | TEXT (NOT NULL) | 이벤트 타입 (`boot`, `shutdown`, `install`) |
| timestamp | DATETIME (NOT NULL) | 이벤트 발생 시간 (KST) |
| created_at | DATETIME | 레코드 생성 시간 |

- 인덱스: `idx_computer_timestamp` (computer_name, timestamp)

#### heartbeats (실시간 온라인 상태)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| computer_name | TEXT (PK) | 컴퓨터 호스트명 |
| last_seen | DATETIME (NOT NULL) | 마지막 하트비트 시간 (KST) |
| ip_address | TEXT | IP 주소 |

#### computers (PC 메타데이터)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| hostname | TEXT (PK) | 컴퓨터 호스트명 |
| display_name | TEXT | 관리자가 설정한 표시 이름 |
| created_at | DATETIME | 등록 시간 |
| updated_at | DATETIME | 수정 시간 |

#### sessions (로그인 세션)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| session_id | TEXT (PK) | 세션 ID (64자 hex) |
| token_hash | TEXT | 세션 토큰 SHA-256 해시 |
| csrf_token | TEXT | CSRF 토큰 (64자 hex) |
| created_at | DATETIME | 생성 시간 |
| expires_at | DATETIME (NOT NULL) | 만료 시간 (24시간) |
| last_activity | DATETIME | 마지막 활동 시간 (슬라이딩 만료) |

#### settings (시스템 설정)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| key | TEXT (PK) | 설정 키 |
| value | TEXT (NOT NULL) | 설정 값 |
| updated_at | DATETIME | 수정 시간 |

주요 설정 키:
- `api_key`: Agent 인증용 API 키
- `api_key_shown`: API 키 최초 표시 여부 (true/false)
- `admin_password`: 관리자 비밀번호 해시 (bcrypt 또는 SHA-256)

### 5.2 DB 설정

- WAL 모드 (`PRAGMA journal_mode=WAL`): 동시 읽기/쓰기 성능 향상
- 타임아웃 30초 (`PRAGMA busy_timeout=30000`): 동시 접근 시 대기
- 시간대: 모든 시간은 KST(UTC+9) 기준 (`datetime('now', '+9 hours')`)

---

## 6. 설치 및 실행 방법

### 6.1 서버 설치

#### 로컬 실행

```bash
# 1. 서버 디렉토리로 이동
cd server

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 서버 실행 (기본 포트: 8000)
python main.py

# 포트 변경 시
PORT=9000 python main.py
```

서버 실행 후 콘솔에 API 키가 표시된다. 이 키는 한 번만 표시되므로 반드시 기록해 두어야 한다.

```
============================================================
  ComputerOff 서버 최초 실행
============================================================
  API Key: Rk60sPWdkZSFNLLEH71n2iOO1BzEKPUqMVIgl2dIIms
  (이 키는 다시 표시되지 않습니다. 안전하게 보관하세요)
============================================================
```

#### 클라우드 VM 배포 (Oracle Cloud / Ubuntu)

```bash
# 1. deploy.sh로 코드 업로드
cd deploy
./deploy.sh <VM_IP> <VM_USER> <SSH_KEY_PATH>
# 예시: ./deploy.sh 123.45.67.89 opc ~/.ssh/id_rsa

# 2. VM에 SSH 접속 후 서비스 등록
ssh opc@123.45.67.89
cd /opt/computeroff/deploy
sudo ./install-service.sh
```

#### Railway 배포

프로젝트에 `Procfile`과 `railway.json`이 포함되어 있어 Railway에 바로 배포할 수 있다.

```bash
# Railway CLI로 배포
railway deploy
```

### 6.2 Agent 설치

#### 방법 A: 빌드된 exe 사용 (권장)

1. `agent/build.bat`에서 `SERVER_URL`과 `API_KEY`를 서버 정보로 수정한다.
2. `agent/build.bat`를 실행하여 exe를 빌드한다.
3. `dist/` 폴더에 생성된 exe 파일을 대상 PC에 복사한다.
   - `agent_windows_x64.exe`: 64비트 Windows 10/11
   - `agent_windows_x86.exe`: 32비트 Windows 7/8/10/11
   - `agent_windows_win7_x64.exe`: Windows 7 64비트 전용 (Python 3.8 기반)
4. 대상 PC에서 **관리자 권한으로** exe를 실행한다.
5. 자동 설치가 진행되며, 진행 상황이 콘솔에 표시된다.

#### 방법 B: Python으로 직접 설치

```bash
cd agent
pip install -r requirements.txt

# config.json 작성
echo {"server_url": "http://서버IP:8000", "api_key": "API키"} > config.json

# 관리자 권한 CMD에서 실행
python installer.py
```

#### Agent 제거

```cmd
# exe를 사용한 제거
agent_windows_x64.exe --uninstall

# 수동 제거 (관리자 CMD)
schtasks /Delete /TN "ComputerOff-Boot" /F
schtasks /Delete /TN "ComputerOff-Monitor" /F
schtasks /Delete /TN "ComputerOff-Shutdown" /F
schtasks /Delete /TN "ComputerOff-Heartbeat" /F
```

### 6.3 빌드 요구사항

Agent exe 빌드에 필요한 Python 버전:

| 빌드 대상 | 필요 Python | 설명 |
|-----------|------------|------|
| 64비트 (Windows 10/11) | Python 3.x (최신) | 기본 빌드 |
| 32비트 | Python 3.8 32비트 | `py -3.8-32` |
| Windows 7 64비트 | Python 3.8 64비트 | `py -3.8` (Python 3.9+는 Windows 7 미지원) |

### 6.4 서버 의존성

```
fastapi==0.104.1       # 웹 프레임워크
uvicorn==0.24.0        # ASGI 서버
python-dateutil==2.8.2 # 날짜/시간 유틸리티
bcrypt==4.1.2          # 비밀번호 해싱 (선택, 미설치 시 SHA-256 폴백)
slowapi==0.1.9         # API Rate Limiting
```

### 6.5 Agent 의존성

```
requests>=2.31.0       # HTTP 클라이언트
pyinstaller>=6.10.0    # exe 빌드 도구 (빌드 시에만 필요)
```

---

## 7. 설정 방법

### 7.1 서버 설정

서버는 별도 설정 파일 없이 환경 변수와 DB settings 테이블로 관리된다.

| 항목 | 설정 방법 | 기본값 |
|------|-----------|--------|
| 포트 | 환경 변수 `PORT` | 8000 |
| API 키 | 자동 생성 (DB), 대시보드에서 순환 가능 | 자동 |
| 관리자 비밀번호 | 대시보드 최초 접속 시 설정 | 미설정 |
| 온라인 판단 기준 | `database.py`의 `ONLINE_THRESHOLD_SECONDS` | 180초 |
| bcrypt 라운드 | `database.py`의 `BCRYPT_ROUNDS` | 12 |
| 비밀번호 최소 길이 | `database.py`의 `MIN_PASSWORD_LENGTH` | 8 |

### 7.2 Agent 설정

Agent의 모든 설정은 `config.json`에 저장된다.

| 항목 | 키 | 필수 | 설명 |
|------|-----|------|------|
| 서버 URL | `server_url` | 필수 | FastAPI 서버 주소 (예: `http://123.45.67.89:8000`) |
| API 키 | `api_key` | 필수 | 서버에서 발급된 API 키 |

### 7.3 빌드 설정

`agent/build.bat`에서 다음 변수를 수정한다.

```batch
set SERVER_URL=http://서버IP:8000
set API_KEY=서버에서_발급된_API_키
```

이 설정은 빌드 시 `config.json`으로 생성되어 exe에 번들된다. 대상 PC에서 exe를 실행하면 번들된 `config.json`을 읽어 자동 설치가 진행된다.

### 7.4 방화벽 설정

| 구간 | 포트 | 프로토콜 | 설명 |
|------|------|----------|------|
| 서버 | 8000 (또는 커스텀) | TCP | Agent -> 서버 통신 |
| Agent | - | - | 아웃바운드 HTTP만 필요 |

---

## 8. 다른 프로그램과의 연동 가능성

ComputerOff는 REST API 기반이므로 다른 프로그램과 유연하게 연동할 수 있다.

### 8.1 이벤트 전송 API 연동

다른 프로그램에서 PC 이벤트를 직접 전송할 수 있다.

```bash
# 부팅 이벤트 전송
curl -X POST http://서버IP:8000/api/events \
  -H "Content-Type: application/json" \
  -H "X-API-Key: API키" \
  -d '{"computer_name": "PC-01", "event_type": "boot", "timestamp": "2026-02-19T09:00:00"}'

# 하트비트 전송
curl -X POST "http://서버IP:8000/api/heartbeat?computer_name=PC-01&ip_address=192.168.1.10" \
  -H "X-API-Key: API키"

# 서버 상태 확인 (인증 불필요)
curl http://서버IP:8000/api/health
```

### 8.2 데이터 조회 API 연동

대시보드 API를 통해 PC 현황 데이터를 조회하여 다른 시스템에 활용할 수 있다. 세션 인증이 필요하다.

```python
import requests

# 로그인하여 세션 쿠키 획득
session = requests.Session()
session.post("http://서버IP:8000/api/auth/login", json={"password": "비밀번호"})

# 컴퓨터 목록 및 온라인 상태 조회
computers = session.get("http://서버IP:8000/api/computers").json()
for pc in computers['computers']:
    print(f"{pc['computer_name']}: {pc['status']} (IP: {pc.get('ip_address')})")

# 일별 요약 조회
summary = session.get("http://서버IP:8000/api/daily-summary?days=7").json()
```

### 8.3 연동 시나리오

| 시나리오 | 연동 방식 | 설명 |
|----------|-----------|------|
| 근태 관리 시스템 | `/api/daily-summary` 조회 | PC 첫 부팅 = 출근, 마지막 종료 = 퇴근으로 활용 |
| 자산 관리 시스템 | `/api/computers` 조회 | 등록된 PC 목록, 온라인/오프라인 상태, IP 주소 활용 |
| 알림 시스템 | `/api/computers` 주기적 조회 | 특정 PC 오프라인 전환 시 알림 (Slack, 이메일 등) |
| 전력 관리 | `/api/daily-summary` 조회 | PC 사용 시간 분석으로 전력 사용량 추정 |
| 보안 모니터링 | `/api/timeline/all` 조회 | 비정상 시간대 부팅/종료 감지 |
| 통합 대시보드 | 여러 API 조합 | 기존 관리 시스템에 PC 상태 위젯 추가 |

### 8.4 연동 시 주의사항

- **API Key 보안**: Agent 전용 API 키는 서버 콘솔에서 최초 1회만 표시된다. 분실 시 대시보드에서 키 순환 필요.
- **Rate Limit**: 이벤트 전송은 분당 60건, 하트비트는 분당 120건으로 제한된다.
- **타임스탬프**: 모든 시간은 KST(UTC+9) 기준이다. 타임스탬프 미지정 시 서버 시간이 사용된다.
- **타임스탬프 검증**: 미래 시간 1시간, 과거 30일 이내만 허용된다.
- **컴퓨터 이름 규칙**: 영문, 숫자, `_`, `-`, `.`만 허용되며 최대 64자이다 (정규식: `^[a-zA-Z0-9_\-\.]{1,64}$`).
- **헬스 체크**: `/api/health` 엔드포인트는 인증 없이 접근 가능하므로 서버 상태 모니터링에 활용할 수 있다.
