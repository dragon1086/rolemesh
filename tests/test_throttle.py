"""tests/test_throttle.py — TokenBucketThrottle + queue_worker integration tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rolemesh.adapters.throttle import TokenBucketThrottle, _STATE_DIR, _STATE_PREFIX


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_throttle_files(tmp_path, monkeypatch):
    """Redirect throttle state files to tmp_path so tests don't share state."""
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)
    yield


@pytest.fixture
def throttle():
    return TokenBucketThrottle(rpm_overrides={"anthropic": 20, "openai": 30, "gemini": 60})


# ---------------------------------------------------------------------------
# 1. Fresh bucket → acquire() returns True
# ---------------------------------------------------------------------------

def test_fresh_bucket_returns_true(throttle):
    """A fresh bucket has full tokens; first acquire must succeed immediately."""
    result = throttle.acquire("anthropic")
    assert result is True


# ---------------------------------------------------------------------------
# 2. After drain, acquire() returns wait_sec > 0
# ---------------------------------------------------------------------------

def test_drained_bucket_returns_wait_sec(throttle):
    """After draining all tokens, acquire returns a positive float."""
    throttle.drain("anthropic")
    result = throttle.acquire("anthropic")
    assert isinstance(result, float)
    assert result > 0


# ---------------------------------------------------------------------------
# 3. wait_sec is reasonable (< 60s for capacity≥1)
# ---------------------------------------------------------------------------

def test_wait_sec_is_less_than_60(throttle):
    """wait_sec should be at most 60 seconds (one full refill period)."""
    throttle.drain("anthropic")
    result = throttle.acquire("anthropic")
    assert isinstance(result, float)
    assert result < 60.0


# ---------------------------------------------------------------------------
# 4. After reset, acquire() returns True again
# ---------------------------------------------------------------------------

def test_reset_restores_full_bucket(throttle):
    """reset() refills bucket to full; next acquire succeeds immediately."""
    throttle.drain("anthropic")
    throttle.reset("anthropic")
    result = throttle.acquire("anthropic")
    assert result is True


# ---------------------------------------------------------------------------
# 5. Providers are independent — draining one doesn't affect another
# ---------------------------------------------------------------------------

def test_providers_are_independent(throttle):
    """Draining anthropic must not affect openai or gemini."""
    throttle.drain("anthropic")
    assert throttle.acquire("openai") is True
    assert throttle.acquire("gemini") is True


# ---------------------------------------------------------------------------
# 6. Higher RPM providers have more initial tokens
# ---------------------------------------------------------------------------

def test_higher_rpm_provider_has_more_tokens(throttle):
    """gemini (60 rpm) can serve more requests before exhaustion than anthropic (20 rpm)."""
    anthropic_count = 0
    gemini_count = 0

    while throttle.acquire("anthropic") is True:
        anthropic_count += 1
        if anthropic_count > 100:
            break

    while throttle.acquire("gemini") is True:
        gemini_count += 1
        if gemini_count > 200:
            break

    assert gemini_count > anthropic_count


# ---------------------------------------------------------------------------
# 7. Token refill over time: simulate elapsed time
# ---------------------------------------------------------------------------

def test_tokens_refill_over_simulated_time(throttle):
    """Simulating elapsed time causes token refill so acquire succeeds again."""
    throttle.drain("anthropic")

    # Before time passes: should be waiting
    result_before = throttle.acquire("anthropic")
    assert isinstance(result_before, float)
    assert result_before > 0

    # Simulate 3 seconds elapsed (anthropic=20rpm → rate=1/3 tok/s → ~1 token in 3s)
    with patch("rolemesh.adapters.throttle.time.time", return_value=time.time() + 3.1):
        result_after = throttle.acquire("anthropic")
    assert result_after is True


# ---------------------------------------------------------------------------
# 8. rpm_overrides are respected
# ---------------------------------------------------------------------------

def test_rpm_overrides_applied():
    """Custom RPM override is respected over defaults."""
    t = TokenBucketThrottle(rpm_overrides={"custom_provider": 1})
    # Drain completely
    t.drain("custom_provider")
    result = t.acquire("custom_provider")
    assert isinstance(result, float)
    # wait should be ~60s (1 rpm → 60s per token)
    assert result > 30.0


# ---------------------------------------------------------------------------
# 9. State persists across instances (same files)
# ---------------------------------------------------------------------------

def test_state_persists_across_instances(tmp_path, monkeypatch):
    """Bucket state written by one instance is read by another."""
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)

    t1 = TokenBucketThrottle(rpm_overrides={"anthropic": 20})
    t1.drain("anthropic")

    # New instance — should see drained state
    t2 = TokenBucketThrottle(rpm_overrides={"anthropic": 20})
    result = t2.acquire("anthropic")
    assert isinstance(result, float)
    assert result > 0


# ---------------------------------------------------------------------------
# 10. queue_worker: _select_provider_with_throttle returns provider when available
# ---------------------------------------------------------------------------

def test_select_provider_returns_provider_when_available(tmp_path, monkeypatch):
    """_select_provider_with_throttle returns a provider name on fresh state."""
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)
    monkeypatch.setattr("rolemesh.adapters.circuit_breaker._STATE_DIR", tmp_path)

    from rolemesh.workers.queue_worker import _select_provider_with_throttle, _router, _throttle
    # Reset router state to make providers available
    for p in ["anthropic", "openai", "gemini"]:
        _router.cb.reset(p)
        _throttle.reset(p)

    client = MagicMock()
    result = _select_provider_with_throttle("task-001", client)
    assert result in ("anthropic", "openai", "gemini")


# ---------------------------------------------------------------------------
# 11. queue_worker: all providers OPEN → retry_task with 60s
# ---------------------------------------------------------------------------

def test_select_provider_returns_none_when_all_open(tmp_path, monkeypatch):
    """When all providers are OPEN, _select_provider_with_throttle returns None."""
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)
    monkeypatch.setattr("rolemesh.adapters.circuit_breaker._STATE_DIR", tmp_path)

    from rolemesh.workers.queue_worker import _select_provider_with_throttle, _router
    for p in ["anthropic", "openai", "gemini"]:
        for _ in range(3):
            _router.record_failure(p)

    client = MagicMock()
    result = _select_provider_with_throttle("task-002", client)
    assert result is None


# ---------------------------------------------------------------------------
# 12. queue_worker._run_task: no available provider → retry_task(id, +1, 60)
# ---------------------------------------------------------------------------

def test_run_task_reschedules_when_no_provider(tmp_path, monkeypatch):
    """_run_task reschedules with retry_after=60 when no provider is available."""
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)
    monkeypatch.setattr("rolemesh.adapters.circuit_breaker._STATE_DIR", tmp_path)

    from rolemesh.workers import queue_worker
    from rolemesh.workers.queue_worker import _router

    # Open all circuits
    for p in ["anthropic", "openai", "gemini"]:
        for _ in range(3):
            _router.record_failure(p)

    task = {
        "id": "task-reschedule",
        "title": "Test Reschedule",
        "description": "do something",
        "kind": "auto",
        "source": "manual",
        "priority": 5,
        "retry_count": 0,
    }
    orchestrator = MagicMock()
    client = MagicMock()

    queue_worker._run_task(task, orchestrator, client)

    client.retry_task.assert_called_once_with("task-reschedule", 1, 60)
    orchestrator.run_goal.assert_not_called()


# ---------------------------------------------------------------------------
# 13. Throttle wait_sec proportional to RPM
# ---------------------------------------------------------------------------

def test_wait_sec_proportional_to_rpm(throttle):
    """Lower RPM → longer wait_sec when bucket is drained."""
    throttle.drain("anthropic")   # 20 rpm → ~3s/token
    throttle.drain("gemini")      # 60 rpm → ~1s/token

    wait_anthropic = throttle.acquire("anthropic")
    wait_gemini = throttle.acquire("gemini")

    assert isinstance(wait_anthropic, float)
    assert isinstance(wait_gemini, float)
    # anthropic (slower) should have a longer wait than gemini (faster)
    assert wait_anthropic > wait_gemini
