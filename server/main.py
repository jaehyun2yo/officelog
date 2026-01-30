from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
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


@app.get("/api/computers")
def get_computers():
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


@app.get("/api/computers/{computer_name}/history")
def get_computer_history(computer_name: str, days: int = 30):
    """특정 컴퓨터의 이벤트 이력 조회"""
    history = database.get_computer_history(computer_name, days)
    return {"computer_name": computer_name, "history": history, "days": days}


static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
def dashboard():
    return FileResponse(static_path / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
