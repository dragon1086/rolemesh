"""tests/test_batch_cooldown.py — BatchCooldown unit tests."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from rolemesh.adapters.batch_cooldown import BatchCooldown, DEFAULT_COOLDOWN_SEC


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def state_file(tmp_path) -> Path:
    return tmp_path / "rolemesh-batch-cooldown.json"


@pytest.fixture
def bc(state_file) -> BatchCooldown:
    return BatchCooldown(cooldown_sec=120.0, state_file=state_file)


# ---------------------------------------------------------------------------
# 1. Fresh state (no file) → acquire() returns 0.0
# ---------------------------------------------------------------------------

def test_fresh_state_acquire_returns_zero(bc):
    """When no state file exists, acquire() must return 0.0 (ready)."""
    result = bc.acquire()
    assert result == 0.0


# ---------------------------------------------------------------------------
# 2. Immediately after record_complete() → acquire() returns positive wait
# ---------------------------------------------------------------------------

def test_acquire_immediately_after_record_returns_positive(bc):
    """Right after record_complete(), remaining cooldown must be > 0."""
    bc.record_complete()
    result = bc.acquire()
    assert isinstance(result, float)
    assert result > 0.0


# ---------------------------------------------------------------------------
# 3. acquire() after cooldown elapsed → returns 0.0
# ---------------------------------------------------------------------------

def test_acquire_after_cooldown_elapsed_returns_zero(state_file):
    """After the cooldown window passes, acquire() returns 0.0."""
    bc = BatchCooldown(cooldown_sec=10.0, state_file=state_file)
    bc.record_complete()

    # Simulate 11 seconds later
    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=time.time() + 11.0):
        result = bc.acquire()
    assert result == 0.0


# ---------------------------------------------------------------------------
# 4. record_complete() persists a timestamp to the state file
# ---------------------------------------------------------------------------

def test_record_complete_saves_timestamp(state_file):
    """record_complete() must write last_complete_at to the state file."""
    bc = BatchCooldown(cooldown_sec=120.0, state_file=state_file)
    before = time.time()
    bc.record_complete()
    after = time.time()

    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert "last_complete_at" in data
    assert before <= data["last_complete_at"] <= after


# ---------------------------------------------------------------------------
# 5. Custom cooldown_sec is respected
# ---------------------------------------------------------------------------

def test_custom_cooldown_sec_respected(state_file):
    """A custom short cooldown elapses quickly, a long one does not."""
    bc_short = BatchCooldown(cooldown_sec=5.0, state_file=state_file)
    bc_short.record_complete()

    # 6s in the future → should be ready
    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=time.time() + 6.0):
        assert bc_short.acquire() == 0.0

    # Still 4s remaining without time travel
    result = bc_short.acquire()
    assert result > 0.0
    assert result <= 5.0


# ---------------------------------------------------------------------------
# 6. get_status() returns "cooling" when cooldown is active
# ---------------------------------------------------------------------------

def test_get_status_returns_cooling(bc):
    """After record_complete(), get_status() must return state='cooling'."""
    bc.record_complete()
    status = bc.get_status()
    assert status["state"] == "cooling"
    assert status["remaining_sec"] > 0.0


# ---------------------------------------------------------------------------
# 7. get_status() returns "ready" when cooldown has elapsed
# ---------------------------------------------------------------------------

def test_get_status_returns_ready(state_file):
    """After cooldown passes, get_status() must return state='ready'."""
    bc = BatchCooldown(cooldown_sec=5.0, state_file=state_file)
    bc.record_complete()

    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=time.time() + 6.0):
        status = bc.get_status()
    assert status["state"] == "ready"
    assert status["remaining_sec"] == 0.0


# ---------------------------------------------------------------------------
# 8. Default cooldown is 120 seconds
# ---------------------------------------------------------------------------

def test_default_cooldown_is_120s(state_file):
    """Default cooldown must be exactly 120 seconds."""
    bc = BatchCooldown(state_file=state_file)
    assert bc._cooldown_sec == DEFAULT_COOLDOWN_SEC
    assert DEFAULT_COOLDOWN_SEC == 120.0

    bc.record_complete()
    # 119s later — still cooling
    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=time.time() + 119.0):
        result = bc.acquire()
    assert result > 0.0

    # 121s later — ready
    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=time.time() + 121.0):
        result = bc.acquire()
    assert result == 0.0


# ---------------------------------------------------------------------------
# 9. config batch_cooldown_sec is loaded from throttle.yaml
# ---------------------------------------------------------------------------

def test_config_batch_cooldown_sec_respected(tmp_path, monkeypatch):
    """batch_cooldown_sec in throttle.yaml is read and applied."""
    cfg = tmp_path / "throttle.yaml"
    cfg.write_text("batch_cooldown_sec: 60\nanthropic: 15\n")

    monkeypatch.setattr("rolemesh.adapters.batch_cooldown._CONFIG_PATH", cfg)
    monkeypatch.setattr("rolemesh.adapters.batch_cooldown._YAML_AVAILABLE", True)

    state_file = tmp_path / "cooldown.json"
    bc = BatchCooldown(state_file=state_file)
    assert bc._cooldown_sec == 60.0

    bc.record_complete()
    # 61s later → ready (60s cooldown)
    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=time.time() + 61.0):
        assert bc.acquire() == 0.0
    # 59s later → still cooling
    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=time.time() + 59.0):
        assert bc.acquire() > 0.0


# ---------------------------------------------------------------------------
# 10. Remaining time decreases as time advances
# ---------------------------------------------------------------------------

def test_remaining_decreases_over_time(state_file):
    """acquire() remaining_sec decreases as simulated time advances."""
    bc = BatchCooldown(cooldown_sec=120.0, state_file=state_file)
    now = time.time()
    bc.record_complete()

    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=now + 30.0):
        r30 = bc.acquire()
    with patch("rolemesh.adapters.batch_cooldown.time.time", return_value=now + 60.0):
        r60 = bc.acquire()

    assert r30 > r60 > 0.0
