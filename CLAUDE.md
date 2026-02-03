# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 언어 규칙

모든 응답은 한글로 작성합니다.


- 프로그램은 32 비트 64비트 모두 지원가능하게 해야한다.

## 작업 완료 규칙

- 작업이 완료되면 업데이트 내용을 정리하여 문서로 작성해야 합니다.

---

## 도메인 정보

### 프로젝트 개요

**ComputerOff**는 Windows PC의 부팅/종료 이벤트를 수집하고 웹 대시보드로 관리하는 시스템입니다.

```
Windows PC (Agent) → HTTP POST → FastAPI Server → SQLite DB → Web Dashboard
```

---

### Agent (`/agent`)

Windows 클라이언트로 부팅/종료 이벤트를 서버로 전송합니다.

| 파일 | 설명 |
|------|------|
| `agent.py` | 이벤트 전송 스크립트 (boot/shutdown) |
| `installer.py` | 설치 및 Windows 작업 스케줄러 등록 |
| `config.json` | 서버 URL 및 API 키 설정 |
| `build.bat` | PyInstaller 빌드 스크립트 |

**주요 기능:**
- 부팅/종료 이벤트 HTTP POST 전송
- 재시도 로직 (3회, 2초 간격)
- Windows 작업 스케줄러 연동
- Windows 7/8/10/11 지원

**개발 규칙:**
- 하트비트 전송 시 CMD 창이 표시되지 않도록 백그라운드에서 실행해야 함
- pythonw.exe 사용 또는 CREATE_NO_WINDOW 플래그 적용 필수

---

### 관리자 페이지 (`/server/static/index.html`)

웹 기반 대시보드로 모든 PC의 상태를 모니터링합니다.

**주요 기능:**

| 기능 | 설명 |
|------|------|
| 컴퓨터 목록 | 등록된 PC 목록 및 온라인/오프라인 상태 표시 |
| 일별 요약 | 특정 날짜의 첫 부팅/마지막 종료 시간 표시 |
| 일별 사용 타임라인 | 7/14/30일 기간별 부팅/종료 시간 그리드 |
| 사용량 그래프 | Chart.js 기반 시각화 |
| 전체 이벤트 타임라인 | 모든 PC의 최근 이벤트 필터링 (1/3/7/14일) |
| 컴퓨터 관리 | 표시 이름 변경, 삭제, 상세 이력 조회 |

**인증:**
- 비밀번호 기반 로그인
- 세션 관리 (24시간 만료)
- CSRF 토큰 보호

---

### 서버 API (`/server/main.py`)

**Agent 전용 엔드포인트 (API Key 필요):**
- `POST /api/events` - 이벤트 전송
- `POST /api/heartbeat` - 온라인 상태 전송
- `POST /api/computers/register` - PC 등록

**대시보드 엔드포인트 (세션 필요):**
- `GET /api/computers` - PC 목록 조회
- `GET /api/events` - 이벤트 조회 (필터링)
- `GET /api/daily-summary` - 일별 요약
- `GET /api/timeline/all` - 전체 타임라인

---

### 데이터베이스 (`/server/database.py`)

| 테이블 | 설명 |
|--------|------|
| `events` | 부팅/종료 이벤트 (computer_name, event_type, timestamp) |
| `heartbeats` | 실시간 온라인 상태 (last_seen, ip_address) |
| `computers` | PC 메타데이터 (표시 이름 등) |
| `sessions` | 사용자 세션 관리 |
| `settings` | 설정 (API 키, 비밀번호) |

**주요 로직:**
- 오프라인 종료 이벤트 자동 복구
- 온라인 상태 판단 (하트비트 120초 이내)
- bcrypt 비밀번호 해싱