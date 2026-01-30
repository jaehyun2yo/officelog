import sqlite3
import hashlib
import secrets
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

    # 설정 테이블 (비밀번호 등)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 컴퓨터 테이블 (표시 이름 매핑)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS computers (
            hostname TEXT PRIMARY KEY,
            display_name TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 세션 테이블 (로그인 세션)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL
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

    # 이벤트 기반 정보 + 하트비트 정보 + 표시 이름 조인
    cursor.execute("""
        SELECT
            e.computer_name,
            MAX(CASE WHEN e.event_type = 'boot' THEN e.timestamp END) as last_boot,
            MAX(CASE WHEN e.event_type = 'shutdown' THEN e.timestamp END) as last_shutdown,
            COUNT(*) as total_events,
            h.last_seen,
            h.ip_address,
            c.display_name
        FROM events e
        LEFT JOIN heartbeats h ON e.computer_name = h.computer_name
        LEFT JOIN computers c ON e.computer_name = c.hostname
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
                SELECT (julianday('now', '+9 hours') - julianday(?)) * 86400 as seconds_ago
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
        VALUES (?, datetime('now', '+9 hours'), ?)
    """, (computer_name, ip_address))

    conn.commit()
    conn.close()


def register_computer(computer_name: str, ip_address: Optional[str] = None):
    """PC 등록 - 설치 시 호출 (즉시 관리자 페이지에 표시)

    이미 등록된 PC 재설치 시 install 이벤트 중복 삽입 방지
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 기존 PC 확인 (중복 등록 방지)
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM events WHERE computer_name = ?
    """, (computer_name,))
    existing_count = cursor.fetchone()['cnt']

    # computers 테이블에 등록
    cursor.execute("""
        INSERT OR IGNORE INTO computers (hostname, created_at, updated_at)
        VALUES (?, datetime('now', '+9 hours'), datetime('now', '+9 hours'))
    """, (computer_name,))

    # heartbeats 테이블에 초기 등록 (IP 포함)
    cursor.execute("""
        INSERT OR REPLACE INTO heartbeats (computer_name, last_seen, ip_address)
        VALUES (?, datetime('now', '+9 hours'), ?)
    """, (computer_name, ip_address))

    # 초기 install 이벤트 삽입 (PC 목록 표시용)
    # 단, 이미 등록된 PC는 중복 삽입 안 함
    if existing_count == 0:
        cursor.execute("""
            INSERT INTO events (computer_name, event_type, timestamp)
            VALUES (?, 'install', datetime('now', '+9 hours'))
        """, (computer_name,))

    conn.commit()
    conn.close()


def get_computer_history(computer_name: str, days: int = 30) -> list[dict]:
    """특정 컴퓨터의 boot/shutdown 이벤트 이력 조회"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM events
        WHERE computer_name = ?
        AND event_type IN ('boot', 'shutdown')
        AND timestamp >= datetime('now', '+9 hours', ?)
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
        WHERE timestamp >= DATE('now', '+9 hours', ?)
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


# ==================== 설정 관련 함수 ====================

def get_setting(key: str) -> Optional[str]:
    """설정값 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None


def set_setting(key: str, value: str):
    """설정값 저장"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now', '+9 hours'))
    """, (key, value))
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    """비밀번호 SHA-256 해시"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str) -> bool:
    """비밀번호 검증"""
    stored_hash = get_setting('admin_password')
    if not stored_hash:
        return False
    return hash_password(password) == stored_hash


def is_password_set() -> bool:
    """비밀번호 설정 여부 확인"""
    return get_setting('admin_password') is not None


# ==================== 세션 관련 함수 ====================

def create_session() -> str:
    """새 세션 생성 (24시간 유효)"""
    session_id = secrets.token_hex(32)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (session_id, expires_at)
        VALUES (?, datetime('now', '+9 hours', '+24 hours'))
    """, (session_id,))
    conn.commit()
    conn.close()
    return session_id


def validate_session(session_id: str) -> bool:
    """세션 유효성 확인"""
    if not session_id:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM sessions
        WHERE session_id = ? AND expires_at > datetime('now', '+9 hours')
    """, (session_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def delete_session(session_id: str):
    """세션 삭제"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def cleanup_expired_sessions():
    """만료된 세션 정리"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE expires_at <= datetime('now', '+9 hours')")
    conn.commit()
    conn.close()


# ==================== 컴퓨터 이름 관련 함수 ====================

def get_computer_display_name(hostname: str) -> Optional[str]:
    """표시 이름 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT display_name FROM computers WHERE hostname = ?", (hostname,))
    row = cursor.fetchone()
    conn.close()
    return row['display_name'] if row else None


def set_computer_display_name(hostname: str, display_name: str):
    """표시 이름 설정"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO computers (hostname, display_name, updated_at)
        VALUES (?, ?, datetime('now', '+9 hours'))
    """, (hostname, display_name))
    conn.commit()
    conn.close()


def delete_computer(hostname: str) -> int:
    """컴퓨터 및 관련 데이터 삭제"""
    conn = get_connection()
    cursor = conn.cursor()

    # 이벤트 삭제
    cursor.execute("DELETE FROM events WHERE computer_name = ?", (hostname,))
    deleted_events = cursor.rowcount

    # 하트비트 삭제
    cursor.execute("DELETE FROM heartbeats WHERE computer_name = ?", (hostname,))

    # 컴퓨터 정보 삭제
    cursor.execute("DELETE FROM computers WHERE hostname = ?", (hostname,))

    conn.commit()
    conn.close()
    return deleted_events


def get_all_display_names() -> dict:
    """모든 표시 이름 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT hostname, display_name FROM computers WHERE display_name IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return {row['hostname']: row['display_name'] for row in rows}


# ==================== 타임라인 관련 함수 ====================

def get_shutdown_timeline(days: int = 7) -> dict:
    """날짜별 종료 이벤트 조회"""
    conn = get_connection()
    cursor = conn.cursor()

    # 날짜 목록 조회
    cursor.execute("""
        SELECT DISTINCT DATE(timestamp) as date
        FROM events
        WHERE timestamp >= DATE('now', '+9 hours', ?)
        ORDER BY date DESC
    """, (f'-{days} days',))
    dates = [row['date'] for row in cursor.fetchall()]

    # 컴퓨터 목록 조회
    cursor.execute("""
        SELECT DISTINCT computer_name
        FROM events
        WHERE timestamp >= DATE('now', '+9 hours', ?)
        ORDER BY computer_name
    """, (f'-{days} days',))
    computers = [row['computer_name'] for row in cursor.fetchall()]

    # 종료 이벤트 조회 (날짜별 마지막 종료 시간)
    cursor.execute("""
        SELECT
            DATE(timestamp) as date,
            computer_name,
            MAX(TIME(timestamp)) as shutdown_time,
            COUNT(*) as event_count
        FROM events
        WHERE event_type = 'shutdown'
        AND timestamp >= DATE('now', ?)
        GROUP BY DATE(timestamp), computer_name
    """, (f'-{days} days',))

    # 타임라인 데이터 구성
    timeline = {date: {} for date in dates}
    for row in cursor.fetchall():
        timeline[row['date']][row['computer_name']] = {
            'time': row['shutdown_time'],
            'event_count': row['event_count']
        }

    conn.close()

    # 표시 이름 매핑
    display_names = get_all_display_names()

    return {
        'dates': dates,
        'computers': computers,
        'display_names': display_names,
        'timeline': timeline
    }


def get_daily_summary(days: int = 7) -> list[dict]:
    """하루 단위 시작/종료 요약 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            DATE(timestamp) as date,
            computer_name,
            MIN(CASE WHEN event_type = 'boot' THEN TIME(timestamp) END) as first_boot,
            MAX(CASE WHEN event_type = 'shutdown' THEN TIME(timestamp) END) as last_shutdown
        FROM events
        WHERE timestamp >= DATE('now', '+9 hours', ?)
        AND event_type IN ('boot', 'shutdown')
        GROUP BY DATE(timestamp), computer_name
        ORDER BY date DESC, computer_name
    """, (f'-{days} days',))
    rows = cursor.fetchall()
    conn.close()
    display_names = get_all_display_names()
    result = []
    for row in rows:
        data = dict(row)
        data['display_name'] = display_names.get(data['computer_name'])
        result.append(data)
    return result
