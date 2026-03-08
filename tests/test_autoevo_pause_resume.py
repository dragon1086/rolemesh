"""
tests/test_autoevo_pause_resume.py
autoevo_worker.py pause/resume 회귀 테스트
- convergence brake 조건 충족 시 pause 상태파일 생성 확인
- resume 트리거 파일 생성 시 재개 확인
- empty enqueue streak 카운터 증가 확인
"""
import json
import os
import sqlite3
import time
from unittest.mock import MagicMock

import pytest

import rolemesh.workers.autoevo_worker as aw


@pytest.fixture(autouse=True)
def tmp_state_file(tmp_path, monkeypatch):
    sf = str(tmp_path / "autoevo.state.json")
    monkeypatch.setattr(aw, "STATE_FILE", sf)
    return sf


@pytest.fixture(autouse=True)
def tmp_resume_trigger(tmp_path, monkeypatch):
    rf = str(tmp_path / "autoevo.resume")
    monkeypatch.setattr(aw, "RESUME_TRIGGER_FILE", rf)
    return rf


@pytest.fixture
def tmp_db():
    """임시 in-memory SQLite DB (task_queue 테이블 포함)"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE task_queue (
            id             TEXT PRIMARY KEY,
            title          TEXT,
            description    TEXT,
            kind           TEXT,
            status         TEXT DEFAULT 'pending',
            priority       INTEGER DEFAULT 5,
            source         TEXT DEFAULT 'manual',
            result_summary TEXT,
            error          TEXT,
            created_at     REAL,
            started_at     REAL,
            done_at        REAL,
            retry_count    INTEGER DEFAULT 0,
            run_after      REAL DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def _insert_task(conn, i, status="done", summary="", source="rolemesh-autoevo"):
    conn.execute(
        "INSERT INTO task_queue (id, title, status, source, result_summary, created_at) "
        "VALUES (?, 'T', ?, ?, ?, ?)",
        (str(i), status, source, summary, time.time() - i),
    )
    conn.commit()


# ── pause / _is_paused ────────────────────────────────────────

def test_pause_creates_state_file(tmp_state_file):
    """_pause 호출 시 STATE_FILE에 paused_until > now 저장"""
    st = {"empty_streak": 0}
    aw._pause(st, "test-reason", seconds=3600)

    assert os.path.exists(tmp_state_file)
    with open(tmp_state_file) as f:
        data = json.load(f)
    assert data["paused_until"] > int(time.time())
    assert data["last_reason"] == "test-reason"


def test_pause_sets_paused_at(tmp_state_file):
    """_pause 호출 시 paused_at 타임스탬프 기록"""
    st = {"empty_streak": 0}
    before = int(time.time())
    result = aw._pause(st, "convergence-risk", seconds=100)
    assert "paused_at" in result
    assert result["paused_at"] >= before


def test_is_paused_true_during_pause(tmp_state_file):
    """pause 직후 _is_paused → True, remain > 0"""
    st = {"empty_streak": 0}
    st = aw._pause(st, "convergence-risk", seconds=3600)
    paused, remain, reason = aw._is_paused(st)
    assert paused is True
    assert remain > 0
    assert reason == "convergence-risk"


def test_is_paused_false_after_expiry(tmp_state_file):
    """paused_until이 과거 → _is_paused → False"""
    st = {"paused_until": int(time.time()) - 1, "last_reason": "old"}
    paused, remain, _ = aw._is_paused(st)
    assert paused is False
    assert remain == 0


def test_is_paused_initial_state(tmp_state_file):
    """초기 state (paused_until=0) → _is_paused → False"""
    st = {"empty_streak": 0, "paused_until": 0}
    paused, _, _ = aw._is_paused(st)
    assert paused is False


# ── convergence brake ─────────────────────────────────────────

def test_convergence_risk_above_threshold(tmp_db):
    """noop 비율 >= 0.65 (20개 중 15개 noop) → 위험 감지"""
    for i in range(20):
        summary = "변경 불필요" if i < 15 else "새로운 기능 추가 완료"
        _insert_task(tmp_db, i, summary=summary)

    risky, reason = aw._has_convergence_risk(tmp_db)
    assert risky is True
    assert "convergence-risk" in reason
    assert "noop_ratio" in reason


def test_convergence_risk_below_threshold(tmp_db):
    """noop 비율 < 0.65 → 위험 없음"""
    for i in range(12):
        summary = "변경 불필요" if i < 6 else "새로운 기능 추가 완료"
        _insert_task(tmp_db, i, summary=summary)

    risky, _ = aw._has_convergence_risk(tmp_db)
    assert risky is False


def test_convergence_risk_insufficient_rows(tmp_db):
    """12개 미만 행 → 위험 없음 (샘플 부족)"""
    for i in range(10):
        _insert_task(tmp_db, i, summary="변경 불필요")

    risky, _ = aw._has_convergence_risk(tmp_db)
    assert risky is False


def test_convergence_risk_already_implemented_pattern(tmp_db):
    """'이미 구현 완료' 패턴도 noop으로 집계"""
    for i in range(20):
        summary = "이미 구현 완료" if i < 14 else "기능 추가"
        _insert_task(tmp_db, i, summary=summary)

    risky, reason = aw._has_convergence_risk(tmp_db)
    assert risky is True


# ── resume trigger ─────────────────────────────────────────────

def test_resume_trigger_file_causes_resume(tmp_db, tmp_resume_trigger):
    """RESUME_TRIGGER_FILE 존재 시 즉시 재개 + 파일 삭제"""
    with open(tmp_resume_trigger, "w") as f:
        f.write("")

    st = {"paused_until": int(time.time()) + 3600}
    should, why = aw._should_resume(tmp_db, st)

    assert should is True
    assert "manual-resume-trigger" in why
    assert not os.path.exists(tmp_resume_trigger)


def test_resume_trigger_file_deleted_after_resume(tmp_db, tmp_resume_trigger):
    """resume 후 trigger 파일이 삭제되어 중복 재개 없음"""
    with open(tmp_resume_trigger, "w") as f:
        f.write("")

    st = {"paused_until": int(time.time()) + 3600}
    aw._should_resume(tmp_db, st)

    # 두 번째 호출 시 trigger 없으므로 active tasks 없으면 재개 안 함
    should, _ = aw._should_resume(tmp_db, st)
    assert should is False


def test_resume_no_trigger_no_active_stays_paused(tmp_db):
    """trigger 파일 없고 active 태스크 없으면 재개 안 함"""
    st = {"paused_until": int(time.time()) + 3600}
    should, _ = aw._should_resume(tmp_db, st)
    assert should is False


def test_resume_on_external_active_tasks(tmp_db):
    """pending 태스크가 외부에서 추가되면 즉시 재개"""
    tmp_db.execute(
        "INSERT INTO task_queue (id, title, status, source, created_at) "
        "VALUES ('ext1', 'External Task', 'pending', 'rolemesh-autoevo', ?)",
        (time.time(),),
    )
    tmp_db.commit()

    st = {"paused_until": int(time.time()) + 3600}
    should, why = aw._should_resume(tmp_db, st)
    assert should is True
    assert "external-active-tasks" in why


# ── empty_streak 카운터 ────────────────────────────────────────

def test_empty_streak_initial_zero(tmp_state_file):
    """_load_state → empty_streak 초기값 0"""
    st = aw._load_state()
    assert st["empty_streak"] == 0


def test_empty_streak_increments_and_persists(tmp_state_file):
    """empty_streak 증가 후 _save_state/_load_state 왕복 검증"""
    st = aw._load_state()
    st["empty_streak"] = int(st.get("empty_streak", 0)) + 1
    aw._save_state(st)

    loaded = aw._load_state()
    assert loaded["empty_streak"] == 1


def test_empty_streak_triggers_pause_at_limit(tmp_state_file):
    """empty_streak >= EMPTY_STREAK_LIMIT → pause 발동"""
    st = {"empty_streak": aw.EMPTY_STREAK_LIMIT - 1, "paused_until": 0}
    st["empty_streak"] += 1

    if st["empty_streak"] >= aw.EMPTY_STREAK_LIMIT:
        st = aw._pause(st, f"empty-enqueue-streak={st['empty_streak']}")

    paused, _, reason = aw._is_paused(st)
    assert paused is True
    assert "empty-enqueue-streak" in reason


def test_empty_streak_below_limit_no_pause(tmp_state_file):
    """empty_streak < EMPTY_STREAK_LIMIT → pause 발동 안 함"""
    st = {"empty_streak": aw.EMPTY_STREAK_LIMIT - 2, "paused_until": 0}
    st["empty_streak"] += 1

    # 아직 limit 미달
    assert st["empty_streak"] < aw.EMPTY_STREAK_LIMIT
    paused, _, _ = aw._is_paused(st)
    assert paused is False


def test_enqueue_round_continues_after_single_enqueue_failure(monkeypatch):
    client = MagicMock()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []

    calls = {"n": 0}

    def _enqueue(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first enqueue failed")
        return f"task-{calls['n']}"

    client.enqueue.side_effect = _enqueue
    monkeypatch.setattr(aw, "_AUTOEVO_THROTTLE", False)

    ids = aw.enqueue_round(client, conn, round_no=5)

    assert len(ids) > 0
    assert client.enqueue.call_count == 6
