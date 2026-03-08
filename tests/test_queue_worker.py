"""
tests/test_queue_worker.py
retry 카운터 증가 / retry 소진 시 DLQ 이동 단위 테스트
"""
import pytest
from unittest.mock import MagicMock, patch
from queue_worker import _run_task


def make_task(retry_count=0, source="manual", priority=5, kind="auto"):
    return {
        "id": "test-task-id",
        "title": "Test Task",
        "description": "do something",
        "kind": kind,
        "source": source,
        "priority": priority,
        "retry_count": retry_count,
    }


@pytest.fixture
def client():
    return MagicMock()


@pytest.fixture
def orchestrator():
    return MagicMock()


# ── retry 카운터 증가 ─────────────────────────────────────────

def test_first_failure_retries_with_count_1(client, orchestrator):
    """최초 실패: retry_count=0 → retry_task(id, 1, 30s)"""
    orchestrator.run_goal.side_effect = RuntimeError("first failure")
    task = make_task(retry_count=0)

    with patch("queue_worker._send_openclaw_event"):
        _run_task(task, orchestrator, client)

    client.retry_task.assert_called_once_with("test-task-id", 1, 30)
    client.move_to_dlq.assert_not_called()


def test_second_failure_retries_with_count_2(client, orchestrator):
    """2번째 실패: retry_count=1 → retry_task(id, 2, 60s) — exponential backoff"""
    orchestrator.run_goal.side_effect = RuntimeError("second failure")
    task = make_task(retry_count=1)

    with patch("queue_worker._send_openclaw_event"):
        _run_task(task, orchestrator, client)

    client.retry_task.assert_called_once_with("test-task-id", 2, 60)
    client.move_to_dlq.assert_not_called()


def test_third_failure_retries_with_count_3(client, orchestrator):
    """3번째 실패: retry_count=2 → retry_task(id, 3, 120s)"""
    orchestrator.run_goal.side_effect = RuntimeError("third failure")
    task = make_task(retry_count=2)

    with patch("queue_worker._send_openclaw_event"):
        _run_task(task, orchestrator, client)

    client.retry_task.assert_called_once_with("test-task-id", 3, 120)
    client.move_to_dlq.assert_not_called()


# ── retry 소진 시 DLQ 이동 ────────────────────────────────────

def test_retry_exhausted_moves_to_dlq(client, orchestrator):
    """retry_count=3 (=max_retries): move_to_dlq 호출, retry_task 호출 안 함"""
    orchestrator.run_goal.side_effect = RuntimeError("fatal")
    task = make_task(retry_count=3)

    with patch("queue_worker._send_openclaw_event"):
        _run_task(task, orchestrator, client)

    client.move_to_dlq.assert_called_once()
    assert client.move_to_dlq.call_args[0][0] == "test-task-id"
    client.retry_task.assert_not_called()


def test_retry_exhausted_includes_error_message(client, orchestrator):
    """DLQ 이동 시 에러 메시지 포함"""
    orchestrator.run_goal.side_effect = RuntimeError("specific error message")
    task = make_task(retry_count=3)

    with patch("queue_worker._send_openclaw_event"):
        _run_task(task, orchestrator, client)

    reason_arg = client.move_to_dlq.call_args[0][1]
    assert "specific error message" in reason_arg


# ── 성공 시 retry/DLQ 없음 ───────────────────────────────────

def test_success_no_retry_no_dlq(client, orchestrator):
    """성공 시 retry_task, move_to_dlq 호출 안 함"""
    orchestrator.run_goal.return_value = {"results": [{"summary": "done ok"}]}
    task = make_task(retry_count=0)

    with patch("queue_worker._send_openclaw_event"), \
         patch("queue_worker._allow_done_event", return_value=False):
        _run_task(task, orchestrator, client)

    client.retry_task.assert_not_called()
    client.move_to_dlq.assert_not_called()
    client.complete_task.assert_called_once()
