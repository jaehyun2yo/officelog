import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).parent / "computeroff.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            computer_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_computer_timestamp
        ON events(computer_name, timestamp)
    """)

    # 하트비트 테이블 (실시간 온라인 상태 확인용)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS heartbeats (
            computer_name TEXT PRIMARY KEY,
            last_seen DATETIME NOT NULL,
            ip_address TEXT
        )
    """)

    conn.commit()
    conn.close()


def insert_event(computer_name: str, event_type: str, timestamp: datetime) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO events (computer_name, event_type, timestamp) VALUES (?, ?, ?)",
        (computer_name, event_type, timestamp.isoformat())
    )

    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return event_id


def get_events(
    computer_name: Optional[str] = None,
    event_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100
) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM events WHERE 1=1"
    params = []

    if computer_name:
        query += " AND computer_name = ?"
        params.append(computer_name)

    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)

    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date.isoformat())

    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date.isoformat())

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_computers() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    # 이벤트 기반 정보 + 하트비트 정보 조인
    cursor.execute("""
        SELECT
            e.computer_name,
            MAX(CASE WHEN e.event_type = 'boot' THEN e.timestamp END) as last_boot,
            MAX(CASE WHEN e.event_type = 'shutdown' THEN e.timestamp END) as last_shutdown,
            COUNT(*) as total_events,
            h.last_seen,
            h.ip_address
        FROM events e
        LEFT JOIN heartbeats h ON e.computer_name = h.computer_name
        GROUP BY e.computer_name
        ORDER BY MAX(e.timestamp) DESC
    """)

    rows = cursor.fetchall()

    result = []
    for row in rows:
        data = dict(row)
        last_seen = data.get('last_seen')

        # 하트비트 기반 온라인 상태 (60초 이내 하트비트 있으면 온라인)
        if last_seen:
            cursor.execute("""
                SELECT (julianday('now') - julianday(?)) * 86400 as seconds_ago
            """, (last_seen,))
            result_check = cursor.fetchone()
            seconds_ago = result_check['seconds_ago'] if result_check else 9999

            data['status'] = 'online' if seconds_ago < 60 else 'offline'
            data['seconds_ago'] = int(seconds_ago)
        else:
            # 하트비트 없으면 이벤트 기반으로 판단
            last_boot = data.get('last_boot')
            last_shutdown = data.get('last_shutdown')

            if last_boot and last_shutdown:
                data['status'] = 'online' if last_boot > last_shutdown else 'offline'
            elif last_boot:
                data['status'] = 'online'
            else:
                data['status'] = 'offline'

        result.append(data)

    conn.close()
    return result


def update_heartbeat(computer_name: str, ip_address: Optional[str] = None):
    """하트비트 업데이트 (온라인 상태 갱신)"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO heartbeats (computer_name, last_seen, ip_address)
        VALUES (?, datetime('now'), ?)
    """, (computer_name, ip_address))

    conn.commit()
    conn.close()


def get_computer_history(computer_name: str, days: int = 30) -> list[dict]:
    """특정 컴퓨터의 이벤트 이력 조회"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM events
        WHERE computer_name = ?
        AND timestamp >= datetime('now', ?)
        ORDER BY timestamp DESC
    """, (computer_name, f'-{days} days'))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_daily_stats(computer_name: Optional[str] = None, days: int = 7) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            DATE(timestamp) as date,
            computer_name,
            SUM(CASE WHEN event_type = 'boot' THEN 1 ELSE 0 END) as boot_count,
            SUM(CASE WHEN event_type = 'shutdown' THEN 1 ELSE 0 END) as shutdown_count
        FROM events
        WHERE timestamp >= DATE('now', ?)
    """
    params = [f'-{days} days']

    if computer_name:
        query += " AND computer_name = ?"
        params.append(computer_name)

    query += " GROUP BY DATE(timestamp), computer_name ORDER BY date DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
