import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 한국 시간대 (UTC+9)
KST = timezone(timedelta(hours=9))
from typing import Optional

from fastapi import FastAPI, HTTPException, Response, Request, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import database


# ==================== Rate Limiter 설정 ====================
limiter = Limiter(key_func=get_remote_address)


app = FastAPI(title="ComputerOff", description="컴퓨터 온오프 시간 수집 시스템")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ==================== 보안 미들웨어 ====================

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """보안 헤더 추가 미들웨어"""
    response = await call_next(request)

    # 보안 헤더 추가
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # CSP (Content Security Policy)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "frame-ancestors 'self'"
    )

    return response


# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# ==================== 입력 검증 상수 ====================
COMPUTER_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]{1,64}$')
DISPLAY_NAME_MAX_LENGTH = 100
EVENT_TYPES = ('boot', 'shutdown')


# ==================== 입력 검증 Pydantic 모델 ====================

class EventCreate(BaseModel):
    computer_name: str
    event_type: str
    timestamp: Optional[datetime] = None

    @field_validator('computer_name')
    @classmethod
    def validate_computer_name(cls, v):
        if not COMPUTER_NAME_PATTERN.match(v):
            raise ValueError('computer_name은 영문, 숫자, _, -, .만 허용 (최대 64자)')
        return v

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, v):
        if v not in EVENT_TYPES:
            raise ValueError("event_type은 'boot' 또는 'shutdown'이어야 합니다")
        return v

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        if v is not None:
            # 한국 시간 기준으로 검증 (서버가 UTC여도 KST 기준)
            now_kst = datetime.now(KST).replace(tzinfo=None)
            # 미래 시간 검증 (1시간 이내 허용)
            if v > now_kst + timedelta(hours=1):
                raise ValueError('timestamp가 미래 시간입니다')
            # 너무 오래된 시간 검증 (30일 이내)
            if v < now_kst - timedelta(days=30):
                raise ValueError('timestamp가 30일 이상 과거입니다')
        return v


class EventResponse(BaseModel):
    id: int
    computer_name: str
    event_type: str
    timestamp: str
    created_at: str


class ComputerUpdate(BaseModel):
    display_name: str

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('display_name은 비어있을 수 없습니다')
        if len(v) > DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(f'display_name은 최대 {DISPLAY_NAME_MAX_LENGTH}자입니다')
        return v


class LoginRequest(BaseModel):
    password: str


class PasswordRequest(BaseModel):
    password: str

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < database.MIN_PASSWORD_LENGTH:
            raise ValueError(f'비밀번호는 최소 {database.MIN_PASSWORD_LENGTH}자 이상이어야 합니다')

        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)

        if not (has_upper and has_lower and has_digit):
            raise ValueError('비밀번호는 대문자, 소문자, 숫자를 각각 1개 이상 포함해야 합니다')

        return v


# ==================== 의존성 함수 ====================

def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """API 키 검증 (Agent 엔드포인트용)"""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API 키가 필요합니다")
    if not database.validate_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="유효하지 않은 API 키입니다")
    return x_api_key


def verify_session(request: Request):
    """세션 검증 (Dashboard 엔드포인트용)"""
    session = request.cookies.get("session")
    if not session or not database.validate_session(session):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return session


def verify_csrf(request: Request, x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token")):
    """CSRF 토큰 검증 (PUT/DELETE 요청용)"""
    session = request.cookies.get("session")
    if not session:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if not x_csrf_token:
        raise HTTPException(status_code=403, detail="CSRF 토큰이 필요합니다")
    if not database.validate_csrf_token(session, x_csrf_token):
        raise HTTPException(status_code=403, detail="유효하지 않은 CSRF 토큰입니다")
    return x_csrf_token


# ==================== 애플리케이션 이벤트 ====================

@app.on_event("startup")
def startup():
    database.init_db()
    # 최초 실행 시 API 키 표시
    api_key = database.get_api_key_if_first_time()
    if api_key:
        print("\n" + "=" * 60)
        print("  ComputerOff 서버 최초 실행")
        print("=" * 60)
        print(f"  API Key: {api_key}")
        print("  (이 키는 다시 표시되지 않습니다. 안전하게 보관하세요)")
        print("=" * 60 + "\n")


# ==================== Agent 엔드포인트 (API 키 인증) ====================

@app.post("/api/events", response_model=dict)
@limiter.limit("60/minute")
def create_event(request: Request, event: EventCreate, _: str = Depends(verify_api_key)):
    """이벤트 생성 (Agent용, API 키 필수)"""
    timestamp = event.timestamp or datetime.now()
    event_id = database.insert_event(
        computer_name=event.computer_name,
        event_type=event.event_type,
        timestamp=timestamp
    )

    return {"id": event_id, "status": "ok"}


@app.post("/api/heartbeat")
@limiter.limit("120/minute")
def heartbeat(
    request: Request,
    computer_name: str,
    ip_address: Optional[str] = None,
    _: str = Depends(verify_api_key)
):
    """하트비트 수신 (Agent용, API 키 필수)"""
    # computer_name 검증
    if not COMPUTER_NAME_PATTERN.match(computer_name):
        raise HTTPException(status_code=422, detail="잘못된 computer_name 형식")

    database.update_heartbeat(computer_name, ip_address)
    return {"status": "ok"}


@app.post("/api/computers/register")
@limiter.limit("10/minute")
def register_computer(
    request: Request,
    computer_name: str,
    ip_address: Optional[str] = None,
    _: str = Depends(verify_api_key)
):
    """PC 등록 (Agent용, API 키 필수)"""
    # computer_name 검증
    if not COMPUTER_NAME_PATTERN.match(computer_name):
        raise HTTPException(status_code=422, detail="잘못된 computer_name 형식")

    database.register_computer(computer_name, ip_address)
    return {"status": "ok"}


@app.get("/api/events/last")
@limiter.limit("60/minute")
def get_last_event(
    request: Request,
    computer_name: str,
    event_type: str,
    _: str = Depends(verify_api_key)
):
    """특정 컴퓨터의 마지막 이벤트 조회 (Agent용, API 키 필수)"""
    # 입력 검증
    if not COMPUTER_NAME_PATTERN.match(computer_name):
        raise HTTPException(status_code=422, detail="잘못된 computer_name 형식")
    if event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="event_type은 'boot' 또는 'shutdown'이어야 합니다")

    event = database.get_last_event(computer_name, event_type)
    if event:
        return {"event": event, "found": True}
    return {"event": None, "found": False}


# ==================== 공개 엔드포인트 (인증 불필요) ====================

@app.get("/api/health")
def health_check():
    """헬스 체크 (인증 불필요)"""
    return {"status": "ok", "service": "computeroff"}


# ==================== Dashboard 엔드포인트 (세션 인증) ====================

@app.get("/api/events")
def get_events(
    request: Request,
    computer_name: Optional[str] = None,
    event_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    _: str = Depends(verify_session)
):
    """이벤트 목록 조회 (Dashboard용, 세션 필수)"""
    events = database.get_events(
        computer_name=computer_name,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    return {"events": events, "count": len(events)}


@app.get("/api/computers")
def get_computers(request: Request, _: str = Depends(verify_session)):
    """컴퓨터 목록 조회 (Dashboard용, 세션 필수)"""
    # 먼저 오프라인 전환된 컴퓨터들의 종료 이벤트 복구
    recovered = database.check_and_recover_offline_shutdowns()
    if recovered:
        print(f"[Recovery] 종료 이벤트 {len(recovered)}개 복구됨: {[r['computer_name'] for r in recovered]}")

    computers = database.get_computers()
    return {"computers": computers, "count": len(computers)}


@app.get("/api/stats")
def get_stats(
    request: Request,
    computer_name: Optional[str] = None,
    days: int = 7,
    _: str = Depends(verify_session)
):
    """통계 조회 (Dashboard용, 세션 필수)"""
    stats = database.get_daily_stats(computer_name=computer_name, days=days)
    return {"stats": stats, "days": days}


@app.get("/api/computers/{computer_name}/history")
def get_computer_history(
    request: Request,
    computer_name: str,
    days: int = 30,
    _: str = Depends(verify_session)
):
    """특정 컴퓨터의 이벤트 이력 조회 (Dashboard용, 세션 필수)"""
    history = database.get_computer_history(computer_name, days)
    return {"computer_name": computer_name, "history": history, "days": days}


@app.put("/api/computers/{hostname}")
def update_computer(
    request: Request,
    hostname: str,
    data: ComputerUpdate,
    _session: str = Depends(verify_session),
    _csrf: str = Depends(verify_csrf)
):
    """컴퓨터 표시 이름 변경 (CSRF 보호)"""
    database.set_computer_display_name(hostname, data.display_name)
    return {"status": "ok", "hostname": hostname, "display_name": data.display_name}


@app.delete("/api/computers/{hostname}")
def delete_computer(
    request: Request,
    hostname: str,
    _session: str = Depends(verify_session),
    _csrf: str = Depends(verify_csrf)
):
    """컴퓨터 및 관련 이벤트 삭제 (CSRF 보호)"""
    deleted_events = database.delete_computer(hostname)
    return {"status": "ok", "hostname": hostname, "deleted_events": deleted_events}


@app.delete("/api/computers")
def delete_all_computers(
    request: Request,
    _session: str = Depends(verify_session),
    _csrf: str = Depends(verify_csrf)
):
    """모든 컴퓨터 및 관련 이벤트 삭제 (CSRF 보호)"""
    result = database.delete_all_computers()
    return {"status": "ok", **result}


# ==================== 인증 API ====================

@app.get("/api/auth/check")
def check_auth(request: Request):
    """인증 상태 확인"""
    password_set = database.is_password_set()

    if not password_set:
        return {"authenticated": False, "password_set": False}

    session = request.cookies.get("session")
    authenticated = database.validate_session(session) if session else False

    # CSRF 토큰도 함께 반환 (인증된 경우)
    csrf_token = None
    if authenticated and session:
        csrf_token = database.get_session_csrf_token(session)

    return {
        "authenticated": authenticated,
        "password_set": True,
        "csrf_token": csrf_token
    }


@app.post("/api/auth/set-password")
@limiter.limit("5/minute")
def set_password(request: Request, data: PasswordRequest, response: Response):
    """최초 비밀번호 설정"""
    if database.is_password_set():
        raise HTTPException(status_code=400, detail="비밀번호가 이미 설정되어 있습니다")

    hashed = database.hash_password(data.password)
    database.set_setting('admin_password', hashed)

    # 자동 로그인
    session_id, csrf_token = database.create_session()
    response.set_cookie(
        key="session",
        value=session_id,
        httponly=True,
        max_age=86400,  # 24시간
        samesite="strict",
        secure=False  # HTTPS 적용 시 True로 변경
    )

    return {"status": "ok", "csrf_token": csrf_token}


@app.post("/api/auth/login")
@limiter.limit("5/minute")
def login(request: Request, data: LoginRequest, response: Response):
    """로그인"""
    if not database.is_password_set():
        raise HTTPException(status_code=400, detail="비밀번호가 설정되지 않았습니다")

    if not database.verify_password(data.password):
        raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다")

    session_id, csrf_token = database.create_session()
    response.set_cookie(
        key="session",
        value=session_id,
        httponly=True,
        max_age=86400,
        samesite="strict",
        secure=False  # HTTPS 적용 시 True로 변경
    )

    return {"status": "ok", "csrf_token": csrf_token}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    """로그아웃"""
    session = request.cookies.get("session")
    if session:
        database.delete_session(session)
    response.delete_cookie("session")
    return {"status": "ok"}


# ==================== 관리자 API ====================

@app.post("/api/admin/rotate-api-key")
def rotate_api_key(
    request: Request,
    _session: str = Depends(verify_session),
    _csrf: str = Depends(verify_csrf)
):
    """API 키 순환 (Dashboard용, 세션 + CSRF 필수)"""
    new_key = database.rotate_api_key()
    return {"status": "ok", "api_key": new_key}


# ==================== 타임라인 API (세션 인증) ====================

@app.get("/api/timeline/shutdown")
def get_shutdown_timeline(request: Request, days: int = 7, _: str = Depends(verify_session)):
    """날짜별 종료 이벤트 타임라인"""
    return database.get_shutdown_timeline(days)


@app.get("/api/daily-summary")
def get_daily_summary_api(request: Request, days: int = 7, _: str = Depends(verify_session)):
    """하루 단위 시작/종료 요약"""
    summary = database.get_daily_summary(days)
    return {"summary": summary, "days": days}


@app.get("/api/computers/{computer_name}/daily-summary")
def get_computer_daily_summary_api(
    request: Request,
    computer_name: str,
    days: int = 30,
    _: str = Depends(verify_session)
):
    """특정 컴퓨터의 하루 단위 시작/종료 요약"""
    summary = database.get_computer_daily_summary(computer_name, days)
    return {"computer_name": computer_name, "summary": summary, "days": days}


@app.get("/api/timeline/all")
def get_all_events_timeline_api(
    request: Request,
    days: int = 7,
    limit: int = 100,
    _: str = Depends(verify_session)
):
    """전체 컴퓨터 이벤트 타임라인"""
    events = database.get_all_events_timeline(days, limit)
    return {"events": events, "days": days, "count": len(events)}


# ==================== 정적 파일 및 루트 ====================

static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
def dashboard():
    return FileResponse(static_path / "index.html")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
