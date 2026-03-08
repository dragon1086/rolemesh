"""
tests/test_aicomms_integration.py

ai-comms 경로(symphony_fusion, autoevo_worker) CB/Throttle 연동 통합 테스트.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from rolemesh.routing.symphony_fusion import SymphonyMACRS, WorkItem, _SF_GUARD
from rolemesh.workers.autoevo_worker import enqueue_round, _AUTOEVO_THROTTLE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_state_files(tmp_path, monkeypatch):
    """Redirect CB and throttle state files to tmp_path."""
    monkeypatch.setattr("rolemesh.adapters.circuit_breaker._STATE_DIR", tmp_path)
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)
    yield


@pytest.fixture
def sf():
    registry = MagicMock()
    return SymphonyMACRS(registry=registry)


def _analysis_item(desc="시장 분석 요청"):
    return WorkItem(id="t1", title="Test", description=desc, kind="analysis")


# ---------------------------------------------------------------------------
# 1. CB OPEN 시 symphony_fusion → local_rule fallback 반환
# ---------------------------------------------------------------------------

def test_symphony_cb_open_returns_local_rule_fallback(sf, tmp_path, monkeypatch):
    """CB OPEN 상태에서 execute() → status=fallback, proof.fallback=local_rule"""
    import rolemesh.routing.symphony_fusion as sf_mod

    # Force CB to report unavailable
    mock_cb = MagicMock()
    mock_cb.is_available.return_value = False
    monkeypatch.setattr(sf_mod, "_sf_cb", mock_cb)
    monkeypatch.setattr(sf_mod, "_SF_GUARD", True)

    result = sf.execute(_analysis_item())

    assert result.status == "fallback"
    assert result.proof.get("fallback") == "local_rule"
    assert result.proof.get("reason") == "circuit_breaker_open"
    mock_cb.is_available.assert_called_once_with("amp")


# ---------------------------------------------------------------------------
# 2. CB CLOSED, throttle ok → ask_amp 호출됨
# ---------------------------------------------------------------------------

def test_symphony_cb_closed_throttle_ok_calls_ask_amp(sf, monkeypatch):
    """CB CLOSED + throttle ok → ask_amp 정상 호출"""
    import rolemesh.routing.symphony_fusion as sf_mod

    mock_cb = MagicMock()
    mock_cb.is_available.return_value = True
    mock_throttle = MagicMock()
    mock_throttle.acquire.return_value = True  # immediately available

    monkeypatch.setattr(sf_mod, "_sf_cb", mock_cb)
    monkeypatch.setattr(sf_mod, "_sf_throttle", mock_throttle)
    monkeypatch.setattr(sf_mod, "_SF_GUARD", True)

    mock_ask = MagicMock(return_value={"answer": "테스트 답변", "cser": 0.5, "persona_domain": None, "conflicts": []})
    monkeypatch.setattr(sf_mod, "ask_amp", mock_ask)

    result = sf.execute(_analysis_item())

    assert result.status == "done"
    mock_ask.assert_called_once()


# ---------------------------------------------------------------------------
# 3. throttle wait_sec 반환 → sleep + 재시도 후 실패 → fallback
# ---------------------------------------------------------------------------

def test_symphony_throttle_exceeded_returns_fallback(sf, monkeypatch):
    """throttle.acquire가 두 번 모두 wait_sec 반환 → throttle_exceeded fallback"""
    import rolemesh.routing.symphony_fusion as sf_mod

    mock_cb = MagicMock()
    mock_cb.is_available.return_value = True
    mock_throttle = MagicMock()
    mock_throttle.acquire.return_value = 1.5  # always returns wait_sec

    monkeypatch.setattr(sf_mod, "_sf_cb", mock_cb)
    monkeypatch.setattr(sf_mod, "_sf_throttle", mock_throttle)
    monkeypatch.setattr(sf_mod, "_SF_GUARD", True)

    slept = []
    monkeypatch.setattr(sf_mod.time, "sleep", lambda s: slept.append(s))

    result = sf.execute(_analysis_item())

    assert result.status == "fallback"
    assert result.proof.get("fallback") == "local_rule"
    assert result.proof.get("reason") == "throttle_exceeded"
    assert len(slept) == 1
    assert slept[0] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# 4. throttle wait → sleep → 재시도 성공 → ask_amp 호출
# ---------------------------------------------------------------------------

def test_symphony_throttle_wait_then_success(sf, monkeypatch):
    """throttle 첫 번째 acquire가 wait_sec, 재시도 True → ask_amp 호출됨"""
    import rolemesh.routing.symphony_fusion as sf_mod

    mock_cb = MagicMock()
    mock_cb.is_available.return_value = True
    mock_throttle = MagicMock()
    mock_throttle.acquire.side_effect = [0.5, True]  # wait then ok

    monkeypatch.setattr(sf_mod, "_sf_cb", mock_cb)
    monkeypatch.setattr(sf_mod, "_sf_throttle", mock_throttle)
    monkeypatch.setattr(sf_mod, "_SF_GUARD", True)

    slept = []
    monkeypatch.setattr(sf_mod.time, "sleep", lambda s: slept.append(s))

    mock_ask = MagicMock(return_value={"answer": "ok", "cser": None, "persona_domain": None, "conflicts": []})
    monkeypatch.setattr(sf_mod, "ask_amp", mock_ask)

    result = sf.execute(_analysis_item())

    assert result.status == "done"
    assert len(slept) == 1
    mock_ask.assert_called_once()


# ---------------------------------------------------------------------------
# 5. _SF_GUARD=False → guard 비활성, ask_amp 바로 호출 (graceful degradation)
# ---------------------------------------------------------------------------

def test_symphony_guard_disabled_calls_ask_amp_directly(sf, monkeypatch):
    """_SF_GUARD=False 시 CB/Throttle 체크 없이 ask_amp 바로 호출"""
    import rolemesh.routing.symphony_fusion as sf_mod

    monkeypatch.setattr(sf_mod, "_SF_GUARD", False)

    mock_ask = MagicMock(return_value={"answer": "no guard", "cser": None, "persona_domain": None, "conflicts": []})
    monkeypatch.setattr(sf_mod, "ask_amp", mock_ask)

    result = sf.execute(_analysis_item())

    assert result.status == "done"
    mock_ask.assert_called_once()


# ---------------------------------------------------------------------------
# 6. autoevo enqueue_round: throttle ok → client.enqueue 호출됨
# ---------------------------------------------------------------------------

def test_autoevo_throttle_ok_enqueues_tasks(tmp_path, monkeypatch):
    """throttle ok → 모든 phase_defs 태스크가 enqueue됨"""
    import rolemesh.workers.autoevo_worker as aw_mod

    mock_throttle = MagicMock()
    mock_throttle.acquire.return_value = True
    monkeypatch.setattr(aw_mod, "_autoevo_throttle", mock_throttle)
    monkeypatch.setattr(aw_mod, "_AUTOEVO_THROTTLE", True)

    mock_client = MagicMock()
    mock_client.enqueue.return_value = "task-id-1"

    mock_conn = MagicMock()
    # _should_skip_task → returns (False, "") for all tasks
    mock_conn.execute.return_value.fetchall.return_value = []

    ids = enqueue_round(mock_client, mock_conn, round_no=1)

    assert mock_client.enqueue.call_count > 0
    assert len(ids) == mock_client.enqueue.call_count


# ---------------------------------------------------------------------------
# 7. autoevo enqueue_round: throttle wait → sleep + 재시도 성공
# ---------------------------------------------------------------------------

def test_autoevo_throttle_wait_sleep_retry_success(tmp_path, monkeypatch):
    """throttle 첫 acquire wait_sec → sleep 후 재시도 True → enqueue 호출"""
    import rolemesh.workers.autoevo_worker as aw_mod

    # First call returns wait, second returns True (for each task, repeat)
    call_count = {"n": 0}
    def _acquire(provider):
        call_count["n"] += 1
        return 0.01 if call_count["n"] % 2 == 1 else True

    mock_throttle = MagicMock()
    mock_throttle.acquire.side_effect = _acquire
    monkeypatch.setattr(aw_mod, "_autoevo_throttle", mock_throttle)
    monkeypatch.setattr(aw_mod, "_AUTOEVO_THROTTLE", True)

    slept = []
    monkeypatch.setattr(aw_mod.time, "sleep", lambda s: slept.append(s))

    mock_client = MagicMock()
    mock_client.enqueue.return_value = "tid"

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []

    ids = enqueue_round(mock_client, mock_conn, round_no=2)

    assert mock_client.enqueue.call_count > 0
    assert len(slept) > 0  # sleep was called at least once


# ---------------------------------------------------------------------------
# 8. autoevo enqueue_round: throttle 재시도 실패 → 해당 태스크 skip
# ---------------------------------------------------------------------------

def test_autoevo_throttle_retry_fail_skips_task(tmp_path, monkeypatch):
    """throttle 두 번 모두 wait_sec → enqueue 호출 안 됨 (skip)"""
    import rolemesh.workers.autoevo_worker as aw_mod

    mock_throttle = MagicMock()
    mock_throttle.acquire.return_value = 99.0  # always wait

    monkeypatch.setattr(aw_mod, "_autoevo_throttle", mock_throttle)
    monkeypatch.setattr(aw_mod, "_AUTOEVO_THROTTLE", True)
    monkeypatch.setattr(aw_mod.time, "sleep", lambda s: None)

    mock_client = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []

    ids = enqueue_round(mock_client, mock_conn, round_no=3)

    assert mock_client.enqueue.call_count == 0
    assert ids == []
