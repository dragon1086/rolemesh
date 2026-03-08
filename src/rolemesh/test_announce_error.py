"""
test_announce_error.py — completed_with_announce_error 상태 분리 시뮬레이션 테스트

3가지 시나리오:
1. 본체 성공 + announce 성공 → status=done
2. 본체 성공 + announce 실패 → status=completed_with_announce_error
3. 본체 실패 → status=failed
"""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

# queue_worker 모듈의 의존성을 mock
import sys
sys.modules["registry_client"] = MagicMock()
sys.modules["symphony_fusion"] = MagicMock()

import queue_worker
from queue_worker import _run_task


class TestAnnounceErrorSeparation(unittest.TestCase):
    def _make_task(self, task_id="t1", title="Test Task"):
        return {
            "id": task_id,
            "title": title,
            "description": "test goal",
            "source": "manual",
        }

    def _make_orchestrator(self, results=None):
        orch = MagicMock()
        orch.run_goal.return_value = {
            "results": results or [{"summary": "ok"}]
        }
        return orch

    @patch.object(queue_worker, "_allow_done_event", return_value=True)
    @patch.object(queue_worker, "_should_notify_done", return_value=True)
    @patch.object(queue_worker, "_send_openclaw_event")
    def test_success_with_announce_ok(self, mock_send, mock_notify, mock_allow):
        """본체 성공 + announce 성공 → done"""
        client = MagicMock()
        orch = self._make_orchestrator()
        task = self._make_task()

        _run_task(task, orch, client)

        mock_send.assert_called_once()
        client.complete_task.assert_called_once_with("t1", summary="ok")

    @patch.object(queue_worker, "_allow_done_event", return_value=True)
    @patch.object(queue_worker, "_should_notify_done", return_value=True)
    @patch.object(queue_worker, "_send_openclaw_event", side_effect=subprocess.CalledProcessError(1, "openclaw"))
    def test_success_with_announce_fail(self, mock_send, mock_notify, mock_allow):
        """본체 성공 + announce 실패 → completed_with_announce_error"""
        client = MagicMock()
        orch = self._make_orchestrator()
        task = self._make_task()

        _run_task(task, orch, client)

        client.complete_task.assert_called_once()
        call_kwargs = client.complete_task.call_args
        self.assertEqual(call_kwargs.kwargs.get("status") or call_kwargs[1].get("status"),
                         "completed_with_announce_error")
        # summary는 여전히 포함되어야 함
        _, kwargs = call_kwargs
        self.assertIn("ok", kwargs.get("summary", ""))

    @patch.object(queue_worker, "_allow_done_event", return_value=True)
    @patch.object(queue_worker, "_should_notify_done", return_value=True)
    @patch.object(queue_worker, "_send_openclaw_event")
    def test_body_failure(self, mock_send, mock_notify, mock_allow):
        """본체 실패 → failed (기존 동작 유지)"""
        client = MagicMock()
        orch = MagicMock()
        orch.run_goal.side_effect = RuntimeError("boom")
        task = self._make_task()

        _run_task(task, orch, client)

        client.complete_task.assert_called_once()
        call_kwargs = client.complete_task.call_args
        self.assertIn("boom", str(call_kwargs))

    @patch.object(queue_worker, "_allow_done_event", return_value=True)
    @patch.object(queue_worker, "_should_notify_done", return_value=False)
    @patch.object(queue_worker, "_send_openclaw_event")
    def test_success_no_announce_needed(self, mock_send, mock_notify, mock_allow):
        """본체 성공 + announce 불필요(noisy source) → done, announce 미호출"""
        client = MagicMock()
        orch = self._make_orchestrator()
        task = self._make_task()

        _run_task(task, orch, client)

        mock_send.assert_not_called()
        client.complete_task.assert_called_once_with("t1", summary="ok")

    @patch.object(queue_worker, "_allow_done_event", return_value=True)
    @patch.object(queue_worker, "_should_notify_done", return_value=True)
    @patch.object(queue_worker, "_send_openclaw_event")
    def test_body_fail_announce_also_fails(self, mock_send, mock_notify, mock_allow):
        """본체 실패 + announce도 실패 → failed (announce 실패 무시)"""
        client = MagicMock()
        orch = MagicMock()
        orch.run_goal.side_effect = RuntimeError("body error")
        mock_send.side_effect = subprocess.CalledProcessError(1, "openclaw")
        task = self._make_task()

        _run_task(task, orch, client)

        client.complete_task.assert_called_once()
        call_kwargs = client.complete_task.call_args
        # status should not contain announce error — it's a body failure
        self.assertNotIn("completed_with_announce_error", str(call_kwargs))
        self.assertIn("body error", str(call_kwargs))


if __name__ == "__main__":
    unittest.main()
