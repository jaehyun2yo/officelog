# Agent API Key 지원 업데이트

## 업데이트 일자
2026-02-02

## 변경 내용 요약

### 1. API 키 지원 추가
- 모든 HTTP 요청에 `X-API-Key` 헤더 추가
- config.json에서 `api_key` 읽기

### 2. GUI 제거, 자동 설치로 변경
- tkinter GUI 완전 제거
- 실행 시 자동으로 설치 진행
- 기존 설치 감지 시 자동 삭제 후 재설치

### 3. 빌드 시 API 키 포함
- build.bat에서 서버 URL과 API 키 입력
- exe 파일에 config.json 포함 (PyInstaller --add-data)

### 4. 결과물 이름 통일
- `agent_windows_x64.exe` (64비트, Windows 10/11)
- `agent_windows_x86.exe` (32비트, Windows 7/8/10/11)

---

## 빌드 방법

### 1. 서버에서 API 키 확인
서버 최초 실행 시 콘솔에 API 키가 출력됩니다.
또는 서버의 SQLite 데이터베이스에서 확인:
```sql
SELECT value FROM settings WHERE key = 'api_key';
```

### 2. Agent 빌드
```bash
cd agent
build.bat
```

빌드 시 입력:
- 서버 URL (예: `http://34.64.116.152:8000`)
- API 키 (서버에서 확인한 키)

### 3. 결과물
```
dist/
├── agent_windows_x64.exe  (64비트)
└── agent_windows_x86.exe  (32비트)
```

---

## 설치 방법

### 각 클라이언트 PC에서:

1. exe 파일을 PC에 복사
2. **관리자 권한으로 실행** (우클릭 → 관리자 권한으로 실행)
3. 자동으로 설치 진행
   - 기존 설치 감지 시 자동 제거
   - Task Scheduler 작업 등록
   - 서버에 PC 등록

### 설치 확인
```
==================================================
  ComputerOff Agent 자동 설치
==================================================

서버 주소: http://34.64.116.152:8000
API 키: 설정됨

[설치] Agent 설치 중...
  ✓ 설정 저장: 완료
  ✓ 서버 등록: 완료
  ✓ 부팅 작업 등록: 완료
  ✓ 종료 모니터 등록: 완료
  ✓ 종료 작업 등록 (폴백): 완료
  ✓ 실시간 상태 확인 등록: 완료

==================================================
  설치 완료!
  컴퓨터를 다시 시작하면 자동으로 모니터링이 시작됩니다.
==================================================
```

---

## 제거 방법

```bash
agent_windows_x64.exe --uninstall
```

---

## 수정된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `agent/agent.py` | API 키 헤더 추가 |
| `agent/installer.py` | GUI 제거, 자동 설치, API 키 지원 |
| `agent/build.bat` | API 키 입력, 결과물 이름 변경 |

---

## 검증 방법

1. 관리자 페이지에서 컴퓨터가 "온라인" 상태인지 확인
2. 설치 폴더의 `agent.log`에서 401 에러가 없는지 확인
3. 수동 테스트:
   ```
   agent_windows_x64.exe --run heartbeat
   ```
