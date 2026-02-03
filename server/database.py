import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# bcrypt 임포트 (없으면 SHA-256 폴백)
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    print("[WARNING] bcrypt 미설치 - SHA-256 폴백 사용 (pip install bcrypt)")


DB_PATH = Path(__file__).parent / "computeroff.db"

# 비밀번호 정책 상수
MIN_PASSWORD_LENGTH = 8
BCRYPT_ROUNDS = 12

# 레거시 SHA-256 마이그레이션 기간 (90일)
LEGACY_MIGRATION_DAYS = 90


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

    # 설정 테이블 (비밀번호, API 키 등)
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

    # 세션 테이블 (로그인 세션) - token_hash, csrf_token, last_activity 컬럼 추가
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            token_hash TEXT,
            csrf_token TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 기존 sessions 테이블에 새 컬럼 추가 (마이그레이션)
    try:
        cursor.execute("ALTER TABLE sessions ADD COLUMN token_hash TEXT")
    except sqlite3.OperationalError:
        pass  # 이미 존재

    try:
        cursor.execute("ALTER TABLE sessions ADD COLUMN csrf_token TEXT")
    except sqlite3.OperationalError:
        pass  # 이미 존재

    try:
        cursor.execute("ALTER TABLE sessions ADD COLUMN last_activity DATETIME DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass  # 이미 존재

    # API 키 초기 생성 (없으면)
    cursor.execute("SELECT value FROM settings WHERE key = 'api_key'")
    if not cursor.fetchone():
        api_key = secrets.token_urlsafe(32)
        cursor.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES ('api_key', ?, datetime('now', '+9 hours'))
        """, (api_key,))
        # API 키 표시 플래그 설정 (최초 1회만 표시)
        cursor.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES ('api_key_shown', 'false', datetime('now', '+9 hours'))
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

        # 하트비트 기반 온라인 상태 (120초 이내 하트비트 있으면 온라인)
        if last_seen:
            cursor.execute("""
                SELECT (julianday('now', '+9 hours') - julianday(?)) * 86400 as seconds_ago
            """, (last_seen,))
            result_check = cursor.fetchone()
            seconds_ago = result_check['seconds_ago'] if result_check else 9999

            data['status'] = 'online' if seconds_ago < 120 else 'offline'
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


# ==================== 비밀번호 해싱 함수 (bcrypt 우선, SHA-256 폴백) ====================

def hash_password(password: str) -> str:
    """비밀번호 bcrypt 해시 (bcrypt 없으면 SHA-256 폴백)"""
    if HAS_BCRYPT:
        # bcrypt 해시 생성 (12 rounds)
        salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    else:
        # SHA-256 폴백 (bcrypt 미설치 시)
        return hashlib.sha256(password.encode()).hexdigest()


def _is_bcrypt_hash(stored_hash: str) -> bool:
    """bcrypt 해시인지 확인 ($2b$ 접두사)"""
    return stored_hash.startswith('$2b$') or stored_hash.startswith('$2a$')


def _is_sha256_hash(stored_hash: str) -> bool:
    """SHA-256 해시인지 확인 (64자 hex)"""
    return len(stored_hash) == 64 and all(c in '0123456789abcdef' for c in stored_hash)


def _hash_sha256(password: str) -> str:
    """SHA-256 해시 (레거시 검증용)"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str) -> bool:
    """비밀번호 검증 (bcrypt 우선, 레거시 SHA-256 자동 마이그레이션)"""
    stored_hash = get_setting('admin_password')
    if not stored_hash:
        return False

    # bcrypt 해시인 경우
    if HAS_BCRYPT and _is_bcrypt_hash(stored_hash):
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))

    # SHA-256 레거시 해시인 경우
    if _is_sha256_hash(stored_hash):
        if _hash_sha256(password) == stored_hash:
            # 레거시 비밀번호 검증 성공 -> bcrypt로 자동 마이그레이션
            if HAS_BCRYPT:
                new_hash = hash_password(password)
                set_setting('admin_password', new_hash)
                print("[INFO] 비밀번호가 bcrypt로 자동 마이그레이션됨")
            return True
        return False

    # bcrypt가 없고 bcrypt 해시가 저장된 경우
    if not HAS_BCRYPT and _is_bcrypt_hash(stored_hash):
        print("[ERROR] bcrypt 해시가 저장되어 있지만 bcrypt 미설치")
        return False

    return False


def is_password_set() -> bool:
    """비밀번호 설정 여부 확인"""
    return get_setting('admin_password') is not None


def validate_password_policy(password: str) -> tuple[bool, str]:
    """비밀번호 정책 검증

    Returns:
        (통과 여부, 오류 메시지)
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다"

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)

    if not (has_upper and has_lower and has_digit):
        return False, "비밀번호는 대문자, 소문자, 숫자를 각각 1개 이상 포함해야 합니다"

    return True, ""


# ==================== API 키 관련 함수 ====================

def get_api_key() -> Optional[str]:
    """API 키 조회"""
    return get_setting('api_key')


def validate_api_key(api_key: str) -> bool:
    """API 키 검증"""
    stored_key = get_api_key()
    if not stored_key:
        return False
    return secrets.compare_digest(api_key, stored_key)


def rotate_api_key() -> str:
    """API 키 순환 (새 키 생성)"""
    new_key = secrets.token_urlsafe(32)
    set_setting('api_key', new_key)
    set_setting('api_key_shown', 'false')  # 새 키도 한 번만 표시
    return new_key


def get_api_key_if_first_time() -> Optional[str]:
    """최초 1회만 API 키 반환 (보안)"""
    shown = get_setting('api_key_shown')
    if shown == 'false':
        set_setting('api_key_shown', 'true')
        return get_api_key()
    return None


# ==================== 세션 관련 함수 ====================

def _hash_session_token(session_id: str) -> str:
    """세션 토큰 SHA-256 해시"""
    return hashlib.sha256(session_id.encode()).hexdigest()


def create_session() -> tuple[str, str]:
    """새 세션 생성 (24시간 유효)

    Returns:
        (session_id, csrf_token)
    """
    session_id = secrets.token_hex(32)
    token_hash = _hash_session_token(session_id)
    csrf_token = secrets.token_hex(32)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (session_id, token_hash, csrf_token, expires_at, last_activity)
        VALUES (?, ?, ?, datetime('now', '+9 hours', '+24 hours'), datetime('now', '+9 hours'))
    """, (session_id, token_hash, csrf_token))
    conn.commit()
    conn.close()

    return session_id, csrf_token


def validate_session(session_id: str) -> bool:
    """세션 유효성 확인 (슬라이딩 만료 적용)"""
    if not session_id:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    # 해시 기반 검증 (보안 강화)
    token_hash = _hash_session_token(session_id)

    # Dual verification: 해시 또는 평문 (마이그레이션 기간)
    cursor.execute("""
        SELECT 1 FROM sessions
        WHERE (token_hash = ? OR session_id = ?)
        AND expires_at > datetime('now', '+9 hours')
    """, (token_hash, session_id))
    row = cursor.fetchone()

    if row:
        # 슬라이딩 만료: 활동 시 만료 시간 갱신
        cursor.execute("""
            UPDATE sessions
            SET last_activity = datetime('now', '+9 hours'),
                expires_at = datetime('now', '+9 hours', '+24 hours')
            WHERE token_hash = ? OR session_id = ?
        """, (token_hash, session_id))
        conn.commit()

    conn.close()
    return row is not None


def get_session_csrf_token(session_id: str) -> Optional[str]:
    """세션의 CSRF 토큰 조회"""
    if not session_id:
        return None

    conn = get_connection()
    cursor = conn.cursor()

    token_hash = _hash_session_token(session_id)

    cursor.execute("""
        SELECT csrf_token FROM sessions
        WHERE (token_hash = ? OR session_id = ?)
        AND expires_at > datetime('now', '+9 hours')
    """, (token_hash, session_id))
    row = cursor.fetchone()
    conn.close()

    return row['csrf_token'] if row else None


def validate_csrf_token(session_id: str, csrf_token: str) -> bool:
    """CSRF 토큰 검증"""
    stored_token = get_session_csrf_token(session_id)
    if not stored_token or not csrf_token:
        return False
    return secrets.compare_digest(stored_token, csrf_token)


def delete_session(session_id: str):
    """세션 삭제"""
    conn = get_connection()
    cursor = conn.cursor()

    token_hash = _hash_session_token(session_id)

    cursor.execute("""
        DELETE FROM sessions WHERE token_hash = ? OR session_id = ?
    """, (token_hash, session_id))
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


def delete_all_computers() -> dict:
    """모든 컴퓨터 및 관련 데이터 삭제"""
    conn = get_connection()
    cursor = conn.cursor()

    # 삭제 전 개수 조회
    cursor.execute("SELECT COUNT(*) as cnt FROM events")
    deleted_events = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(DISTINCT computer_name) as cnt FROM events")
    deleted_computers = cursor.fetchone()['cnt']

    # 모든 이벤트 삭제
    cursor.execute("DELETE FROM events")

    # 모든 하트비트 삭제
    cursor.execute("DELETE FROM heartbeats")

    # 모든 컴퓨터 정보 삭제
    cursor.execute("DELETE FROM computers")

    conn.commit()
    conn.close()

    return {
        "deleted_computers": deleted_computers,
        "deleted_events": deleted_events
    }


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
        AND timestamp >= DATE('now', '+9 hours', ?)
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
    # ISO 형식 타임스탬프 처리를 위해 strftime 사용
    cursor.execute("""
        SELECT
            strftime('%Y-%m-%d', timestamp) as date,
            computer_name,
            MIN(CASE WHEN event_type = 'boot' THEN strftime('%H:%M:%S', timestamp) END) as first_boot,
            MAX(CASE WHEN event_type = 'shutdown' THEN strftime('%H:%M:%S', timestamp) END) as last_shutdown
        FROM events
        WHERE timestamp >= strftime('%Y-%m-%d', datetime('now', '+9 hours', ?))
        AND event_type IN ('boot', 'shutdown')
        GROUP BY strftime('%Y-%m-%d', timestamp), computer_name
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


def get_computer_daily_summary(computer_name: str, days: int = 30) -> list[dict]:
    """특정 컴퓨터의 하루 단위 시작/종료 요약 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    # ISO 형식 타임스탬프 처리를 위해 strftime 사용
    cursor.execute("""
        SELECT
            strftime('%Y-%m-%d', timestamp) as date,
            MIN(CASE WHEN event_type = 'boot' THEN strftime('%H:%M:%S', timestamp) END) as first_boot,
            MAX(CASE WHEN event_type = 'shutdown' THEN strftime('%H:%M:%S', timestamp) END) as last_shutdown,
            SUM(CASE WHEN event_type = 'boot' THEN 1 ELSE 0 END) as boot_count,
            SUM(CASE WHEN event_type = 'shutdown' THEN 1 ELSE 0 END) as shutdown_count
        FROM events
        WHERE computer_name = ?
        AND timestamp >= strftime('%Y-%m-%d', datetime('now', '+9 hours', ?))
        AND event_type IN ('boot', 'shutdown')
        GROUP BY strftime('%Y-%m-%d', timestamp)
        ORDER BY date DESC
    """, (computer_name, f'-{days} days'))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_events_timeline(days: int = 7, limit: int = 100) -> list[dict]:
    """전체 컴퓨터의 이벤트를 시간순으로 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            e.id,
            e.computer_name,
            e.event_type,
            e.timestamp,
            c.display_name
        FROM events e
        LEFT JOIN computers c ON e.computer_name = c.hostname
        WHERE e.timestamp >= DATE('now', '+9 hours', ?)
        AND e.event_type IN ('boot', 'shutdown')
        ORDER BY e.timestamp DESC
        LIMIT ?
    """, (f'-{days} days', limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_event(computer_name: str, event_type: str) -> Optional[dict]:
    """특정 컴퓨터의 마지막 이벤트 조회

    Args:
        computer_name: 컴퓨터 이름 (hostname)
        event_type: 이벤트 타입 ('boot' 또는 'shutdown')

    Returns:
        마지막 이벤트 정보 (id, computer_name, event_type, timestamp) 또는 None
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, computer_name, event_type, timestamp
        FROM events
        WHERE computer_name = ? AND event_type = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (computer_name, event_type))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ==================== 종료 이벤트 복구 함수 ====================

def get_computers_needing_shutdown_recovery() -> list[dict]:
    """종료 이벤트 복구가 필요한 컴퓨터 목록 조회

    조건:
    1. 하트비트가 60초 이상 지남 (오프라인)
    2. 마지막 boot 이후 shutdown 이벤트가 없음
    3. last_seen이 last_boot 이후여야 함 (안전장치)

    Returns:
        복구 대상 컴퓨터 목록 [{computer_name, last_boot, last_seen}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            h.computer_name,
            h.last_seen,
            MAX(CASE WHEN e.event_type = 'boot' THEN e.timestamp END) as last_boot,
            MAX(CASE WHEN e.event_type = 'shutdown' THEN e.timestamp END) as last_shutdown
        FROM heartbeats h
        JOIN events e ON h.computer_name = e.computer_name
        GROUP BY h.computer_name, h.last_seen
        HAVING
            -- 조건 1: 오프라인 (60초 이상 하트비트 없음)
            (julianday('now', '+9 hours') - julianday(h.last_seen)) * 86400 >= 60
            -- 조건 2: last_boot이 존재
            AND last_boot IS NOT NULL
            -- 조건 3: shutdown이 없거나 last_boot > last_shutdown
            AND (last_shutdown IS NULL OR datetime(last_boot) > datetime(last_shutdown))
            -- 조건 4: last_seen >= last_boot (하트비트가 부팅 이후에 발생)
            -- datetime() 함수로 정규화하여 ISO 8601(T 구분)과 SQLite(공백 구분) 형식 비교 문제 해결
            AND datetime(h.last_seen) >= datetime(last_boot)
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def check_and_recover_offline_shutdowns() -> list[dict]:
    """오프라인 전환된 컴퓨터들의 종료 이벤트 자동 복구

    메인 로직:
    1. get_computers_needing_shutdown_recovery() 호출
    2. 각 컴퓨터에 대해 shutdown 이벤트 생성 (last_seen 시간 사용)
    3. 복구 결과 반환

    Returns:
        복구된 이벤트 목록 [{computer_name, shutdown_time}, ...]
    """
    computers = get_computers_needing_shutdown_recovery()

    if not computers:
        return []

    recovered = []
    conn = get_connection()
    cursor = conn.cursor()

    for comp in computers:
        computer_name = comp['computer_name']
        last_seen = comp['last_seen']

        # shutdown 이벤트 삽입
        cursor.execute("""
            INSERT INTO events (computer_name, event_type, timestamp)
            VALUES (?, 'shutdown', ?)
        """, (computer_name, last_seen))

        recovered.append({
            'computer_name': computer_name,
            'shutdown_time': last_seen
        })

    conn.commit()
    conn.close()

    return recovered
