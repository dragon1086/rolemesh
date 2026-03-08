"""
init_db.py — MACRS SQLite 스키마 초기화
Multi-Agent Capability Registry System

실행: python ~/ai-comms/init_db.py
"""

import sqlite3
import os

# 기본 DB 경로
DEFAULT_DB_PATH = os.path.expanduser("~/ai-comms/registry.db")


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """DB 연결 후 스키마 초기화. 테이블이 이미 있으면 스킵."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    _migrate_tables(conn)
    return conn


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

    conn.commit()
    print(f"[init_db] 스키마 초기화 완료: {conn}")


if __name__ == "__main__":
    db_path = DEFAULT_DB_PATH
    print(f"[init_db] DB 초기화: {db_path}")
    conn = init_db(db_path)
    conn.close()
    print("[init_db] 완료")
