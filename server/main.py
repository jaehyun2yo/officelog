from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database


app = FastAPI(title="ComputerOff", description="컴퓨터 온오프 시간 수집 시스템")


class EventCreate(BaseModel):
    computer_name: str
    event_type: str  # 'boot' or 'shutdown'
    timestamp: Optional[datetime] = None


class EventResponse(BaseModel):
    id: int
    computer_name: str
    event_type: str
    timestamp: str
    created_at: str


class ComputerUpdate(BaseModel):
    display_name: str


class LoginRequest(BaseModel):
    password: str


class PasswordRequest(BaseModel):
    password: str


@app.on_event("startup")
def startup():
    database.init_db()


@app.post("/api/events", response_model=dict)
def create_event(event: EventCreate):
    if event.event_type not in ('boot', 'shutdown'):
        raise HTTPException(status_code=400, detail="event_type must be 'boot' or 'shutdown'")

    timestamp = event.timestamp or datetime.now()
    event_id = database.insert_event(
        computer_name=event.computer_name,
        event_type=event.event_type,
        timestamp=timestamp
    )

    return {"id": event_id, "status": "ok"}


@app.get("/api/events")
def get_events(
    computer_name: Optional[str] = None,
    event_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100
):
    events = database.get_events(
        computer_name=computer_name,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    return {"events": events, "count": len(events)}


@app.get("/api/events/last")
def get_last_event(computer_name: str, event_type: str):
    """특정 컴퓨터의 마지막 이벤트 조회

    에이전트가 부팅 시 미전송 종료 이벤트 복구에 사용
    """
    if event_type not in ('boot', 'shutdown'):
        raise HTTPException(status_code=400, detail="event_type must be 'boot' or 'shutdown'")

    event = database.get_last_event(computer_name, event_type)
    if event:
        return {"event": event, "found": True}
    return {"event": None, "found": False}


@app.get("/api/computers")
def get_computers():
    # 먼저 오프라인 전환된 컴퓨터들의 종료 이벤트 복구
    recovered = database.check_and_recover_offline_shutdowns()
    if recovered:
        print(f"[Recovery] 종료 이벤트 {len(recovered)}개 복구됨: {[r['computer_name'] for r in recovered]}")

    computers = database.get_computers()
    return {"computers": computers, "count": len(computers)}


@app.get("/api/stats")
def get_stats(computer_name: Optional[str] = None, days: int = 7):
    stats = database.get_daily_stats(computer_name=computer_name, days=days)
    return {"stats": stats, "days": days}


@app.post("/api/heartbeat")
def heartbeat(computer_name: str, ip_address: Optional[str] = None):
    """하트비트 수신 (실시간 온라인 상태 갱신)"""
    database.update_heartbeat(computer_name, ip_address)
    return {"status": "ok"}


@app.post("/api/computers/register")
def register_computer(computer_name: str, ip_address: Optional[str] = None):
    """PC 등록 (설치 시 호출 - 즉시 관리자 페이지에 표시)"""
    database.register_computer(computer_name, ip_address)
    return {"status": "ok"}


@app.get("/api/computers/{computer_name}/history")
def get_computer_history(computer_name: str, days: int = 30):
    """특정 컴퓨터의 이벤트 이력 조회"""
    history = database.get_computer_history(computer_name, days)
    return {"computer_name": computer_name, "history": history, "days": days}


@app.put("/api/computers/{hostname}")
def update_computer(hostname: str, data: ComputerUpdate):
    """컴퓨터 표시 이름 변경"""
    database.set_computer_display_name(hostname, data.display_name)
    return {"status": "ok", "hostname": hostname, "display_name": data.display_name}


@app.delete("/api/computers/{hostname}")
def delete_computer(hostname: str):
    """컴퓨터 및 관련 이벤트 삭제"""
    deleted_events = database.delete_computer(hostname)
    return {"status": "ok", "hostname": hostname, "deleted_events": deleted_events}


# ==================== 인증 API ====================

@app.get("/api/auth/check")
def check_auth(request: Request):
    """인증 상태 확인"""
    password_set = database.is_password_set()

    if not password_set:
        return {"authenticated": False, "password_set": False}

    session = request.cookies.get("session")
    authenticated = database.validate_session(session) if session else False
    return {"authenticated": authenticated, "password_set": True}


@app.post("/api/auth/set-password")
def set_password(data: PasswordRequest, response: Response):
    """최초 비밀번호 설정"""
    if database.is_password_set():
        raise HTTPException(status_code=400, detail="비밀번호가 이미 설정되어 있습니다")

    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 4자 이상이어야 합니다")

    hashed = database.hash_password(data.password)
    database.set_setting('admin_password', hashed)

    # 자동 로그인
    session_id = database.create_session()
    response.set_cookie(
        key="session",
        value=session_id,
        httponly=True,
        max_age=86400,  # 24시간
        samesite="lax"
    )

    return {"status": "ok"}


@app.post("/api/auth/login")
def login(data: LoginRequest, response: Response):
    """로그인"""
    if not database.is_password_set():
        raise HTTPException(status_code=400, detail="비밀번호가 설정되지 않았습니다")

    if not database.verify_password(data.password):
        raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다")

    session_id = database.create_session()
    response.set_cookie(
        key="session",
        value=session_id,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )

    return {"status": "ok"}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    """로그아웃"""
    session = request.cookies.get("session")
    if session:
        database.delete_session(session)
    response.delete_cookie("session")
    return {"status": "ok"}


# ==================== 타임라인 API ====================

@app.get("/api/timeline/shutdown")
def get_shutdown_timeline(days: int = 7):
    """날짜별 종료 이벤트 타임라인"""
    return database.get_shutdown_timeline(days)


@app.get("/api/daily-summary")
def get_daily_summary_api(days: int = 7):
    """하루 단위 시작/종료 요약"""
    summary = database.get_daily_summary(days)
    return {"summary": summary, "days": days}


@app.get("/api/computers/{computer_name}/daily-summary")
def get_computer_daily_summary_api(computer_name: str, days: int = 30):
    """특정 컴퓨터의 하루 단위 시작/종료 요약"""
    summary = database.get_computer_daily_summary(computer_name, days)
    return {"computer_name": computer_name, "summary": summary, "days": days}


@app.get("/api/timeline/all")
def get_all_events_timeline_api(days: int = 7, limit: int = 100):
    """전체 컴퓨터 이벤트 타임라인"""
    events = database.get_all_events_timeline(days, limit)
    return {"events": events, "days": days, "count": len(events)}


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
