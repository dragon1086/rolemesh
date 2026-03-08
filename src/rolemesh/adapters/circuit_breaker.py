"""circuit_breaker.py — Provider Circuit Breaker for RoleMesh.

상태: CLOSED(정상) / OPEN(차단) / HALF_OPEN(시험중)
영속화: /tmp/rolemesh-cb-<provider>.json
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from typing import Optional


class CBState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


_STATE_DIR = Path("/tmp")
_STATE_PREFIX = "rolemesh-cb-"


def _state_file(provider: str) -> Path:
    return _STATE_DIR / f"{_STATE_PREFIX}{provider}.json"


def _default_state(cooldown_sec: int = 60) -> dict:
    return {
        "state": CBState.CLOSED.value,
        "failures": 0,
        "opened_at": 0,
        "cooldown_sec": cooldown_sec,
    }


def _load(provider: str) -> tuple[dict, bool]:
    try:
        with _state_file(provider).open("r", encoding="utf-8") as f:
            return json.load(f), False
    except Exception:
        return _default_state(), True


def _save(provider: str, data: dict) -> None:
    try:
        with _state_file(provider).open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


class ProviderCircuitBreaker:
    """Per-provider circuit breaker with file-based state persistence.

    Args:
        failure_threshold: consecutive failures before OPEN (default 3)
        cooldown_sec: seconds to stay OPEN before HALF_OPEN (default 60)
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_sec: int = 60,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, provider: str) -> dict:
        data, recovered = _load(provider)
        normalized = _default_state(self.cooldown_sec)
        if not recovered:
            try:
                normalized["state"] = CBState(str(data.get("state", CBState.CLOSED.value))).value
                normalized["failures"] = max(0, int(data.get("failures", 0)))
                normalized["opened_at"] = max(0, int(data.get("opened_at", 0)))
                normalized["cooldown_sec"] = max(0, int(data.get("cooldown_sec", self.cooldown_sec)))
            except (TypeError, ValueError):
                recovered = True
        data = normalized
        if recovered:
            self._put(provider, data)
        return data

    def _put(self, provider: str, data: dict) -> None:
        _save(provider, data)

    def _maybe_transition(self, provider: str, data: dict) -> dict:
        """OPEN → HALF_OPEN if cooldown elapsed."""
        if data["state"] == CBState.OPEN:
            elapsed = int(time.time()) - int(data.get("opened_at", 0))
            cooldown = int(data.get("cooldown_sec", self.cooldown_sec))
            if elapsed >= cooldown:
                data["state"] = CBState.HALF_OPEN
                self._put(provider, data)
        return data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self, provider: str) -> bool:
        """Return True if provider can accept a request right now."""
        data = self._get(provider)
        data = self._maybe_transition(provider, data)
        state = data["state"]
        return state in (CBState.CLOSED, CBState.HALF_OPEN)

    def record_success(self, provider: str) -> None:
        """Record a successful call → always transition to CLOSED."""
        data = self._get(provider)
        data["state"] = CBState.CLOSED
        data["failures"] = 0
        data["opened_at"] = 0
        self._put(provider, data)

    def record_failure(self, provider: str) -> None:
        """Record a failed call.

        CLOSED: increment failures; if >= threshold → OPEN
        HALF_OPEN: → OPEN (reset cooldown)
        OPEN: no-op (already open)
        """
        data = self._get(provider)
        data = self._maybe_transition(provider, data)
        state = data["state"]

        if state == CBState.OPEN:
            return

        data["failures"] = int(data.get("failures", 0)) + 1

        if state == CBState.HALF_OPEN or data["failures"] >= self.failure_threshold:
            data["state"] = CBState.OPEN
            data["opened_at"] = int(time.time())
            data["cooldown_sec"] = self.cooldown_sec

        self._put(provider, data)

    def get_state(self, provider: str) -> CBState:
        """Current state (with OPEN→HALF_OPEN transition applied)."""
        data = self._get(provider)
        data = self._maybe_transition(provider, data)
        return CBState(data["state"])

    def cooldown_remaining(self, provider: str) -> int:
        """Seconds remaining in OPEN cooldown (0 if not OPEN)."""
        data = self._get(provider)
        if data["state"] != CBState.OPEN:
            return 0
        elapsed = int(time.time()) - int(data.get("opened_at", 0))
        cooldown = int(data.get("cooldown_sec", self.cooldown_sec))
        remaining = cooldown - elapsed
        return max(0, remaining)

    def reset(self, provider: str) -> None:
        """Force-reset to CLOSED (for testing / manual recovery)."""
        self._put(provider, {
            "state": CBState.CLOSED,
            "failures": 0,
            "opened_at": 0,
            "cooldown_sec": self.cooldown_sec,
        })
