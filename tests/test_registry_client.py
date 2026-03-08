"""
tests/test_registry_client.py
queue_counts / move_to_dlq / retry_task 단위 테스트
"""
import time
import pytest
from registry_client import RegistryClient


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "test.db")
    c = RegistryClient(db_path=db)
    yield c
    c.close()


# ── queue_counts ──────────────────────────────────────────────

def test_queue_counts_empty_db(client):
    counts = client.queue_counts()
    assert isinstance(counts, dict)
    assert counts["dlq"] == 0


def test_queue_counts_pending(client):
    client.enqueue("task-A", "desc A")
    counts = client.queue_counts()
    assert counts.get("pending", 0) == 1
    assert counts["dlq"] == 0


def test_queue_counts_multiple_statuses(client):
    client.enqueue("task-1", "desc 1")
    client.enqueue("task-2", "desc 2")
    task = client.dequeue_next()
    assert task is not None
    client.complete_task(task["id"], summary="ok")

    counts = client.queue_counts()
    assert counts.get("pending", 0) == 1
    assert counts.get("done", 0) == 1
    assert counts["dlq"] == 0


# ── move_to_dlq ───────────────────────────────────────────────

def test_move_to_dlq_increments_dlq_count(client):
    task_id = client.enqueue("dlq-task", "desc")
    client.move_to_dlq(task_id, reason="test error")
    counts = client.queue_counts()
    assert counts["dlq"] == 1


def test_move_to_dlq_sets_dead_letter_status(client):
    task_id = client.enqueue("dlq-task2", "desc")
    client.move_to_dlq(task_id, reason="exhausted")
    counts = client.queue_counts()
    assert counts.get("dead_letter", 0) == 1


def test_move_to_dlq_nonexistent_task_no_error(client):
    # 존재하지 않는 task_id: 예외 없이 조용히 처리
    client.move_to_dlq("nonexistent-id", reason="test")
    assert client.queue_counts()["dlq"] == 0


def test_move_to_dlq_preserves_reason(client):
    task_id = client.enqueue("reason-task", "desc")
    reason = "retry limit reached"
    client.move_to_dlq(task_id, reason=reason)
    conn = client._conn_ctx()
    row = conn.execute(
        "SELECT error FROM dead_letter WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert row is not None
    assert reason in row["error"]


# ── retry_task ────────────────────────────────────────────────

def test_retry_task_sets_pending(client):
    task_id = client.enqueue("retry-task", "desc")
    client.dequeue_next()  # running 상태로 전환
    client.retry_task(task_id, retry_count=1, delay_sec=30)
    conn = client._conn_ctx()
    row = conn.execute(
        "SELECT status, retry_count FROM task_queue WHERE id = ?", (task_id,)
    ).fetchone()
    assert row["status"] == "pending"
    assert row["retry_count"] == 1


def test_retry_task_backoff_delay(client):
    task_id = client.enqueue("backoff-task", "desc")
    before = time.time()
    delay = 60
    client.retry_task(task_id, retry_count=2, delay_sec=delay)
    conn = client._conn_ctx()
    row = conn.execute(
        "SELECT run_after FROM task_queue WHERE id = ?", (task_id,)
    ).fetchone()
    assert row["run_after"] >= before + delay - 1


def test_retry_task_run_after_not_dequeued_immediately(client):
    task_id = client.enqueue("delayed-task", "desc")
    client.retry_task(task_id, retry_count=1, delay_sec=9999)
    # run_after가 미래이므로 dequeue_next에서 나오지 않아야 함
    result = client.dequeue_next()
    assert result is None or result["id"] != task_id
