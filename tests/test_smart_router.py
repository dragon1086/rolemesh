"""tests/test_smart_router.py — SmartRouter and smart-delegate.sh contract tests."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from rolemesh.adapters.circuit_breaker import ProviderCircuitBreaker
from rolemesh.adapters.smart_router import SmartRouter
from rolemesh.adapters.throttle import TokenBucketThrottle


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "smart-delegate.sh"


@pytest.fixture
def isolate_state(tmp_path, monkeypatch):
    monkeypatch.setattr("rolemesh.adapters.circuit_breaker._STATE_DIR", tmp_path)
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)
    return tmp_path


def _content() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_smart_router_instantiation(isolate_state):
    router = SmartRouter()
    assert router.providers == ["anthropic", "openai-codex", "gemini"]


def test_open_circuit_provider_is_skipped(isolate_state):
    router = SmartRouter()
    for _ in range(router.cb.failure_threshold):
        router.record_failure("anthropic")
    assert router.get_available_provider() == "openai-codex"


def test_throttle_exhausted_provider_is_skipped(isolate_state):
    throttle = TokenBucketThrottle(rpm_overrides={"anthropic": 1, "openai-codex": 2, "gemini": 3})
    throttle.drain("anthropic")
    router = SmartRouter(throttle=throttle)
    assert router.get_available_provider() == "openai-codex"


def test_all_providers_open_returns_none(isolate_state):
    router = SmartRouter()
    for provider in router.providers:
        for _ in range(router.cb.failure_threshold):
            router.record_failure(provider)
    assert router.get_available_provider() is None


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("anthropic", "scripts/cokac-delegate.sh"),
        ("openai-codex", "scripts/codex-delegate.sh"),
        ("gemini", "scripts/gemini-delegate.sh"),
    ],
)
def test_get_delegate_script_mapping(isolate_state, provider, expected):
    assert SmartRouter().get_delegate_script(provider) == expected


def test_smart_delegate_file_exists_and_is_executable():
    assert SCRIPT_PATH.exists(), f"파일 없음: {SCRIPT_PATH}"
    mode = os.stat(SCRIPT_PATH).st_mode
    assert mode & stat.S_IXUSR, "owner execute bit 없음"


def test_smart_delegate_contains_name():
    assert "smart-delegate" in _content()


def test_record_failure_and_success_delegate_to_cb(isolate_state):
    cb = ProviderCircuitBreaker(failure_threshold=1, cooldown_sec=60)
    router = SmartRouter(cb=cb)
    router.record_failure("anthropic")
    assert router.cb.get_state("anthropic").value == "OPEN"
    router.record_success("anthropic")
    assert router.cb.get_state("anthropic").value == "CLOSED"
