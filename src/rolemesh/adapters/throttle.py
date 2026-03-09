"""throttle.py — Token-bucket rate throttle per provider.

acquire(provider) → True if immediately available, else float wait_sec.
State is persisted to /tmp/rolemesh-throttle-<provider>.json.
Config: ~/rolemesh/config/throttle.yaml (optional).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Union

try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_STATE_DIR = Path("/tmp")
_STATE_PREFIX = "rolemesh-throttle-"
_CONFIG_PATH = Path.home() / "rolemesh" / "config" / "throttle.yaml"

logger = logging.getLogger(__name__)

DEFAULT_RPM: dict[str, int] = {
    "anthropic": 20,
    "openai": 30,
    "gemini": 60,
}


def _load_config() -> dict[str, int]:
    """Load per-provider RPM from throttle.yaml, falling back to defaults."""
    if _YAML_AVAILABLE and _CONFIG_PATH.exists():
        try:
            with _CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            merged = dict(DEFAULT_RPM)
            merged.update({k: int(v) for k, v in data.items()})
            return merged
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("Failed to load throttle config from %s: %s", _CONFIG_PATH, exc)
    return dict(DEFAULT_RPM)


def _state_file(provider: str) -> Path:
    return _STATE_DIR / f"{_STATE_PREFIX}{provider}.json"


def _load_state(provider: str, capacity: int) -> dict:
    try:
        with _state_file(provider).open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Validate expected keys exist
        if "tokens" in data and "last_refill" in data:
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.debug("Failed to load throttle state for provider=%s: %s", provider, exc)
    return {"tokens": float(capacity), "last_refill": time.time()}


def _save_state(provider: str, data: dict) -> None:
    try:
        path = _state_file(provider)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.debug("Failed to save throttle state for provider=%s: %s", provider, exc)


class TokenBucketThrottle:
    """Per-provider token-bucket rate throttle.

    Args:
        rpm_overrides: Optional dict to override per-provider RPM.
    """

    def __init__(self, rpm_overrides: dict[str, int] | None = None) -> None:
        self._rpm = _load_config()
        if rpm_overrides:
            self._rpm.update(rpm_overrides)

    def _capacity(self, provider: str) -> int:
        return self._rpm.get(provider, DEFAULT_RPM.get("anthropic", 20))

    def _refill(self, state: dict, capacity: int) -> dict:
        """Refill tokens based on elapsed time (token rate = capacity/60 per second)."""
        now = time.time()
        elapsed = now - state["last_refill"]
        rate = capacity / 60.0  # tokens per second
        state["tokens"] = min(float(capacity), state["tokens"] + elapsed * rate)
        state["last_refill"] = now
        return state

    def wait_time(self, provider: str) -> float:
        """Return seconds until a token is available without consuming one."""
        capacity = self._capacity(provider)
        state = _load_state(provider, capacity)
        state = self._refill(state, capacity)
        _save_state(provider, state)
        if state["tokens"] >= 1.0:
            return 0.0
        rate = capacity / 60.0
        return max(0.0, (1.0 - state["tokens"]) / rate)

    def acquire(self, provider: str) -> Union[bool, float]:
        """Attempt to consume one token for provider.

        Returns:
            True  — token consumed, request can proceed immediately.
            float — seconds to wait before retrying (token unavailable).
        """
        capacity = self._capacity(provider)
        state = _load_state(provider, capacity)
        state = self._refill(state, capacity)

        if state["tokens"] >= 1.0:
            state["tokens"] -= 1.0
            _save_state(provider, state)
            return True

        # Compute wait until 1 token is available
        rate = capacity / 60.0
        wait_sec = (1.0 - state["tokens"]) / rate
        _save_state(provider, state)
        return wait_sec

    def reset(self, provider: str) -> None:
        """Reset token bucket to full capacity (for testing / manual recovery)."""
        capacity = self._capacity(provider)
        _save_state(provider, {"tokens": float(capacity), "last_refill": time.time()})

    def drain(self, provider: str) -> None:
        """Drain all tokens (for testing)."""
        capacity = self._capacity(provider)
        state = _load_state(provider, capacity)
        state["tokens"] = 0.0
        state["last_refill"] = time.time()
        _save_state(provider, state)
