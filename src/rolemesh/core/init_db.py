import os
import logging
import sqlite3
import threading
from dataclasses import dataclass

"""
init_db.py — MACRS SQLite 스키마 초기화
Multi-Agent Capability Registry System

실행: python ~/ai-comms/init_db.py
"""

# 기본 DB 경로
DEFAULT_DB_PATH = os.path.expanduser("~/ai-comms/registry.db")
logger = logging.getLogger(__name__)
_POOL_LOCK = threading.RLock()


@dataclass
class _SharedConnection:
    conn: sqlite3.Connection
    refcount: int = 0


_SHARED_CONNECTIONS: dict[tuple[int, str], _SharedConnection] = {}


def _normalize_db_path(db_path: str) -> str:
    return os.path.abspath(os.path.expanduser(db_path))


def _open_connection(db_path: str) -> sqlite3.Connection:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    _create_tables(conn)
    _migrate_tables(conn)
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """DB 연결 후 스키마 초기화. 테이블이 이미 있으면 스킵."""
    return _open_connection(_normalize_db_path(db_path))


def get_shared_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """현재 스레드에서 재사용할 공유 SQLite 연결을 반환한다."""
    normalized_path = _normalize_db_path(db_path)
    key = (threading.get_ident(), normalized_path)

    with _POOL_LOCK:
        entry = _SHARED_CONNECTIONS.get(key)
        if entry is not None:
            try:
                entry.conn.execute("SELECT 1")
            except sqlite3.Error:
                try:
                    entry.conn.close()
                except sqlite3.Error:
                    pass
                entry = None
                _SHARED_CONNECTIONS.pop(key, None)
            else:
                entry.refcount += 1
                return entry.conn

        conn = _open_connection(normalized_path)
        _SHARED_CONNECTIONS[key] = _SharedConnection(conn=conn, refcount=1)
        return conn


def release_shared_connection(conn: sqlite3.Connection | None, db_path: str = DEFAULT_DB_PATH) -> None:
    """공유 연결 참조를 해제하고 마지막 사용자면 연결을 닫는다."""
    if conn is None:
        return

    normalized_path = _normalize_db_path(db_path)
    key = (threading.get_ident(), normalized_path)

    with _POOL_LOCK:
        entry = _SHARED_CONNECTIONS.get(key)
        if entry is None or entry.conn is not conn:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            return

        entry.refcount -= 1
        if entry.refcount > 0:
            return

        _SHARED_CONNECTIONS.pop(key, None)
        try:
            entry.conn.close()
        except sqlite3.Error:
            pass


def _migrate_tables(conn: sqlite3.Connection) -> None:
    """기존 DB에 누락 컬럼 추가 (무중단 마이그레이션)."""
    migrations = [
        ("task_queue", "retry_count", "INTEGER DEFAULT 0"),
        ("task_queue", "run_after",   "REAL DEFAULT 0"),
    ]
    for table, column, col_def in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            conn.commit()
        except Exception:
            pass  # 이미 존재하면 무시


def _create_tables(conn: sqlite3.Connection) -> None:
    """4개 핵심 테이블 생성"""
    cursor = conn.cursor()

    # agents: 등록된 AI 에이전트 목록
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id     TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            description  TEXT,
            endpoint     TEXT,              -- MCP URL 또는 IPC 경로
            last_heartbeat INTEGER,         -- unix timestamp
            status       TEXT DEFAULT 'active'  -- active / offline
        )
    """)

    # capabilities: 각 에이전트의 능력 선언
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS capabilities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    TEXT NOT NULL,
            name        TEXT NOT NULL,       -- 'emergent_analysis', 'code_write' 등
            description TEXT,
            keywords    TEXT,               -- JSON 배열 ["분석", "검토", ...]
            cost_level  TEXT DEFAULT 'medium',  -- low / medium / high
            avg_latency_ms INTEGER,
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        )
    """)

    # performance: 실적 기록 (시간이 지날수록 라우팅 정확도 향상)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    TEXT NOT NULL,
            capability  TEXT NOT NULL,
            task_hash   TEXT,
            success     INTEGER,            -- 1 = 성공, 0 = 실패
            duration_ms INTEGER,
            created_at  INTEGER DEFAULT (strftime('%s','now'))
        )
    """)

    # messages: 에이전트 간 메시지 큐 (Obsidian 파일 IPC 대체)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id           TEXT PRIMARY KEY,  -- UUID
            from_agent   TEXT NOT NULL,
            to_agent     TEXT NOT NULL,
            content      TEXT NOT NULL,     -- JSON 직렬화
            status       TEXT DEFAULT 'pending',  -- pending / processing / done / failed
            created_at   INTEGER DEFAULT (strftime('%s','now')),
            processed_at INTEGER
        )
    """)

    # task_queue: Symphony×MACRS 태스크 큐
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id             TEXT PRIMARY KEY,
            title          TEXT NOT NULL,
            description    TEXT DEFAULT '',
            kind           TEXT,
            status         TEXT DEFAULT 'pending',
            priority       INTEGER DEFAULT 5,
            source         TEXT DEFAULT 'manual',
            result_summary TEXT,
            created_at     REAL,
            started_at     REAL,
            done_at        REAL,
            error          TEXT,
            retry_count    INTEGER DEFAULT 0,
            run_after      REAL DEFAULT 0
        )
    """)

    # dead_letter: retry 소진 태스크 보관소
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dead_letter (
            id          TEXT PRIMARY KEY,
            task_id     TEXT NOT NULL,
            title       TEXT NOT NULL,
            description TEXT DEFAULT '',
            kind        TEXT,
            source      TEXT DEFAULT 'manual',
            priority    INTEGER DEFAULT 5,
            retry_count INTEGER DEFAULT 0,
            error       TEXT,
            created_at  REAL,
            dlq_at      REAL
        )
    """)

    # routing_log: 라우팅 결정 기록 (투명성)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routing_log (
            id                TEXT PRIMARY KEY,
            timestamp         INTEGER NOT NULL,
            task_text         TEXT NOT NULL,
            chosen_agent      TEXT NOT NULL,
            chosen_capability TEXT NOT NULL,
            explanation       TEXT,
            score             REAL,
            routing_method    TEXT DEFAULT 'keyword_fallback'
        )
    """)

    # routing_feedback: 라우팅 피드백 (피드백 루프)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routing_feedback (
            id          TEXT PRIMARY KEY,
            routing_id  TEXT NOT NULL,
            was_correct INTEGER NOT NULL,
            actual_agent TEXT DEFAULT '',
            feedback_at INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quality_scores (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            score    REAL NOT NULL,
            provider TEXT NOT NULL,
            ts       REAL NOT NULL
        )
    """)

    conn.commit()
    logger.debug("SQLite schema initialized for %s", conn)


if __name__ == "__main__":
    db_path = DEFAULT_DB_PATH
    logging.basicConfig(level=logging.INFO)
    logger.info("DB 초기화: %s", db_path)
    conn = init_db(db_path)
    conn.close()
    logger.info("완료")
