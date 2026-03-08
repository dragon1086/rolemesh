"""tests/test_circuit_breaker.py — ProviderCircuitBreaker + ProviderRouter tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from rolemesh.adapters.circuit_breaker import CBState, ProviderCircuitBreaker
from rolemesh.adapters.provider_router import FALLBACK_PROVIDER, ProviderRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_cb_files(tmp_path, monkeypatch):
    """Redirect CB state files to tmp_path so tests don't share state."""
    monkeypatch.setattr("rolemesh.adapters.circuit_breaker._STATE_DIR", tmp_path)
    yield
    # cleanup is automatic with tmp_path


@pytest.fixture
def cb():
    return ProviderCircuitBreaker(failure_threshold=3, cooldown_sec=60)


@pytest.fixture
def router():
    return ProviderRouter(
        providers=["anthropic", "openai", "gemini"],
        failure_threshold=3,
        cooldown_sec=60,
    )


# ---------------------------------------------------------------------------
# 1. CLOSED → OPEN: 연속 실패 3회
# ---------------------------------------------------------------------------

def test_closed_to_open_after_threshold(cb):
    """3 consecutive failures transition CLOSED → OPEN."""
    assert cb.get_state("anthropic") == CBState.CLOSED
    cb.record_failure("anthropic")
    cb.record_failure("anthropic")
    assert cb.get_state("anthropic") == CBState.CLOSED  # still closed at 2
    cb.record_failure("anthropic")
    assert cb.get_state("anthropic") == CBState.OPEN


# ---------------------------------------------------------------------------
# 2. OPEN 중 is_available() False
# ---------------------------------------------------------------------------

def test_open_is_not_available(cb):
    """OPEN state → is_available returns False."""
    for _ in range(3):
        cb.record_failure("openai")
    assert cb.get_state("openai") == CBState.OPEN
    assert cb.is_available("openai") is False


# ---------------------------------------------------------------------------
# 3. cooldown 후 HALF_OPEN 전환
# ---------------------------------------------------------------------------

def test_open_transitions_to_half_open_after_cooldown(cb):
    """After cooldown elapses, OPEN → HALF_OPEN."""
    for _ in range(3):
        cb.record_failure("gemini")
    assert cb.get_state("gemini") == CBState.OPEN

    # Simulate cooldown elapsed by patching time.time
    future = time.time() + 61
    with patch("rolemesh.adapters.circuit_breaker.time.time", return_value=future):
        state = cb.get_state("gemini")
    assert state == CBState.HALF_OPEN


# ---------------------------------------------------------------------------
# 4. HALF_OPEN + 성공 → CLOSED
# ---------------------------------------------------------------------------

def test_half_open_success_to_closed(cb):
    """Successful call during HALF_OPEN transitions to CLOSED."""
    for _ in range(3):
        cb.record_failure("anthropic")

    future = time.time() + 61
    with patch("rolemesh.adapters.circuit_breaker.time.time", return_value=future):
        assert cb.is_available("anthropic") is True  # HALF_OPEN
        cb.record_success("anthropic")

    assert cb.get_state("anthropic") == CBState.CLOSED


# ---------------------------------------------------------------------------
# 5. HALF_OPEN + 실패 → OPEN
# ---------------------------------------------------------------------------

def test_half_open_failure_back_to_open(cb):
    """Failed call during HALF_OPEN transitions back to OPEN."""
    for _ in range(3):
        cb.record_failure("openai")

    future = time.time() + 61
    with patch("rolemesh.adapters.circuit_breaker.time.time", return_value=future):
        assert cb.is_available("openai") is True  # HALF_OPEN
        cb.record_failure("openai")
        state = cb.get_state("openai")
    assert state == CBState.OPEN


# ---------------------------------------------------------------------------
# 6. 모든 provider OPEN → fallback 반환
# ---------------------------------------------------------------------------

def test_all_providers_open_returns_fallback(router):
    """When all providers are OPEN, route() returns local_rule."""
    for p in ["anthropic", "openai", "gemini"]:
        for _ in range(3):
            router.record_failure(p)
    assert router.route() == FALLBACK_PROVIDER


# ---------------------------------------------------------------------------
# 7. 첫 번째 CLOSED provider 선택
# ---------------------------------------------------------------------------

def test_route_selects_first_available(router):
    """route() picks first available provider in order."""
    # Open anthropic
    for _ in range(3):
        router.record_failure("anthropic")
    # openai should be chosen
    assert router.route() == "openai"


# ---------------------------------------------------------------------------
# 8. record_success resets to CLOSED
# ---------------------------------------------------------------------------

def test_record_success_resets_to_closed(cb):
    """record_success always resets provider to CLOSED regardless of prior state."""
    cb.record_failure("anthropic")
    cb.record_failure("anthropic")
    cb.record_success("anthropic")
    assert cb.get_state("anthropic") == CBState.CLOSED
    # Subsequent failures start fresh counter
    cb.record_failure("anthropic")
    cb.record_failure("anthropic")
    assert cb.get_state("anthropic") == CBState.CLOSED  # only 2, not open yet


# ---------------------------------------------------------------------------
# 9. cooldown_remaining > 0 while OPEN
# ---------------------------------------------------------------------------

def test_cooldown_remaining_while_open(cb):
    """cooldown_remaining returns positive seconds when circuit is OPEN."""
    for _ in range(3):
        cb.record_failure("gemini")
    remaining = cb.cooldown_remaining("gemini")
    assert 0 < remaining <= 60


# ---------------------------------------------------------------------------
# 10. cooldown_remaining == 0 when CLOSED
# ---------------------------------------------------------------------------

def test_cooldown_remaining_zero_when_closed(cb):
    """cooldown_remaining returns 0 for CLOSED provider."""
    assert cb.cooldown_remaining("anthropic") == 0


# ---------------------------------------------------------------------------
# 11. get_status() 전체 provider 상태 반환
# ---------------------------------------------------------------------------

def test_get_status_returns_all_providers(router):
    """get_status() includes all providers with correct keys."""
    status = router.get_status()
    for p in ["anthropic", "openai", "gemini"]:
        assert p in status
        assert "state" in status[p]
        assert "cooldown_remaining" in status[p]
        assert "available" in status[p]
        assert status[p]["state"] == CBState.CLOSED.value
        assert status[p]["available"] is True


def test_provider_router_copies_provider_list():
    providers = ["anthropic", "openai"]
    router = ProviderRouter(providers=providers)

    providers.append("gemini")

    assert router.providers == ["anthropic", "openai"]


@pytest.mark.parametrize("providers", [[""], ["anthropic", "  "], [FALLBACK_PROVIDER]])
def test_provider_router_rejects_invalid_provider_names(providers):
    with pytest.raises(ValueError):
        ProviderRouter(providers=providers)


def test_provider_router_rejects_invalid_thresholds():
    with pytest.raises(ValueError, match="failure_threshold"):
        ProviderRouter(failure_threshold=0)
    with pytest.raises(ValueError, match="cooldown_sec"):
        ProviderRouter(cooldown_sec=-1)


# ---------------------------------------------------------------------------
# 12. is_available True for CLOSED, False for OPEN
# ---------------------------------------------------------------------------

def test_is_available_false_for_open_true_for_closed(cb):
    """is_available correctly reflects CLOSED(True) vs OPEN(False)."""
    assert cb.is_available("anthropic") is True
    for _ in range(3):
        cb.record_failure("anthropic")
    assert cb.is_available("anthropic") is False


# ---------------------------------------------------------------------------
# 13. 실패가 threshold 미만이면 CLOSED 유지
# ---------------------------------------------------------------------------

def test_below_threshold_stays_closed(cb):
    """Fewer failures than threshold keeps state CLOSED."""
    cb.record_failure("openai")
    cb.record_failure("openai")
    assert cb.get_state("openai") == CBState.CLOSED
    assert cb.is_available("openai") is True


# ---------------------------------------------------------------------------
# 14. reset() forces back to CLOSED
# ---------------------------------------------------------------------------

def test_reset_forces_closed(cb):
    """reset() forcefully transitions any state back to CLOSED."""
    for _ in range(3):
        cb.record_failure("gemini")
    assert cb.get_state("gemini") == CBState.OPEN
    cb.reset("gemini")
    assert cb.get_state("gemini") == CBState.CLOSED
    assert cb.is_available("gemini") is True


def test_corrupted_state_file_recovers_to_closed(tmp_path):
    state_file = tmp_path / "rolemesh-cb-anthropic.json"
    state_file.write_text("{not-json", encoding="utf-8")
    cb = ProviderCircuitBreaker(failure_threshold=3, cooldown_sec=45)

    assert cb.get_state("anthropic") == CBState.CLOSED
    recovered = state_file.read_text(encoding="utf-8")
    assert '"state": "CLOSED"' in recovered
    assert '"cooldown_sec": 45' in recovered
