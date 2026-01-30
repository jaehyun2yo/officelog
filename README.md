# ComputerOff - 컴퓨터 온오프 시간 수집 시스템

여러 대의 Windows 컴퓨터의 부팅/종료 시간을 수집하여 웹 대시보드에서 확인하는 시스템입니다.

## 시스템 요구사항

- **Agent (클라이언트)**: Windows 7, 8, 10, 11
- **Server**: Python 3.8+

## 아키텍처

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Windows PC 1  │     │   Windows PC 2  │     │   Windows PC N  │
│   (Agent)       │     │   (Agent)       │     │   (Agent)       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │         HTTP POST     │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │      서버 (Server)      │
                    │  - REST API            │
                    │  - 웹 대시보드          │
                    │  - SQLite DB           │
                    └────────────────────────┘
```

## 빠른 시작

### 1. 서버 실행

```bash
cd server
pip install -r requirements.txt
python main.py
```

서버가 `http://0.0.0.0:8000`에서 실행됩니다.
대시보드: `http://서버IP:8000`

### 2. Agent 설치 (각 PC에)

**방법 A: 빌드된 exe 사용 (권장)**

1. `agent/build.bat` 실행하여 exe 빌드
2. `dist/computeroff-agent.exe`를 대상 PC에 복사
3. **관리자 권한으로** exe 실행
4. 서버 주소 입력 후 "설치" 클릭

**방법 B: Python으로 직접 실행**

```bash
cd agent
pip install -r requirements.txt
python installer.py
```

### 3. 동작 확인

- PC 재부팅 → 대시보드에서 "부팅" 이벤트 확인
- PC 종료 → 대시보드에서 "종료" 이벤트 확인

## API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/events` | POST | 이벤트 수신 |
| `/api/events` | GET | 이벤트 조회 |
| `/api/computers` | GET | 컴퓨터 목록 |
| `/api/stats` | GET | 통계 조회 |
| `/` | GET | 대시보드 |

### 이벤트 전송 예시

```bash
curl -X POST http://서버IP:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{"computer_name": "PC-01", "event_type": "boot"}'
```

## 프로젝트 구조

```
computeroff/
├── server/
│   ├── main.py           # FastAPI 서버
│   ├── database.py       # SQLite 연결/모델
│   ├── static/
│   │   ├── index.html    # 대시보드 UI
│   │   ├── style.css
│   │   └── script.js
│   └── requirements.txt
├── agent/
│   ├── agent.py          # 이벤트 전송 스크립트
│   ├── installer.py      # Task Scheduler 등록 + 설정 UI
│   ├── build.bat         # PyInstaller로 exe 빌드
│   └── requirements.txt
├── dist/                 # 빌드 결과물
│   └── computeroff-agent.exe
└── README.md
```

## Agent 제거

1. **관리자 권한으로** `computeroff-agent.exe` 실행
2. "제거" 버튼 클릭

또는 명령줄에서:

```cmd
schtasks /Delete /TN "ComputerOff-Boot" /F
schtasks /Delete /TN "ComputerOff-Shutdown" /F
```

## 문제 해결

### Agent가 이벤트를 보내지 않음

1. `agent.log` 파일 확인
2. 서버 주소가 올바른지 확인
3. 방화벽에서 8000 포트 허용

### 종료 이벤트가 감지되지 않음

Windows 7에서는 종료 이벤트 감지에 제한이 있을 수 있습니다.
강제 종료(전원 버튼)의 경우 이벤트가 전송되지 않습니다.

### Task Scheduler 작업 확인

```cmd
schtasks /Query /TN "ComputerOff-Boot"
schtasks /Query /TN "ComputerOff-Shutdown"
```
