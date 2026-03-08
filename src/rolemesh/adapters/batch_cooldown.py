"""batch_cooldown.py — Enforces a mandatory cool-down between batch delegations.

After each batch completes, the completion time is recorded to
/tmp/rolemesh-batch-cooldown.json. Subsequent batches must wait until
the cooldown period elapses.

acquire()          → 0.0 if ready, float seconds remaining if cooling.
record_complete()  → stamp current time as most-recent batch completion.
get_status()       → {state: "cooling"|"ready", remaining_sec: float}

Config: ~/rolemesh/config/throttle.yaml → batch_cooldown_sec (default: 120)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TypedDict

try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_STATE_FILE = Path("/tmp/rolemesh-batch-cooldown.json")
_CONFIG_PATH = Path.home() / "rolemesh" / "config" / "throttle.yaml"
DEFAULT_COOLDOWN_SEC: float = 120.0


def _load_cooldown_sec() -> float:
    """Load batch_cooldown_sec from throttle.yaml, falling back to default."""
    if _YAML_AVAILABLE and _CONFIG_PATH.exists():
        try:
            with _CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if "batch_cooldown_sec" in data:
                return float(data["batch_cooldown_sec"])
        except Exception:
            pass
    return DEFAULT_COOLDOWN_SEC


class StatusDict(TypedDict):
    state: str          # "cooling" | "ready"
    remaining_sec: float


class BatchCooldown:
    """Enforces a mandatory cool-down between batch delegations.

    Args:
        cooldown_sec: Override cooldown duration in seconds. If None, loaded
                      from config/throttle.yaml → batch_cooldown_sec.
        state_file:   Override state file path (used in tests).
    """

    def __init__(
        self,
        cooldown_sec: float | None = None,
        state_file: Path | None = None,
    ) -> None:
        self._cooldown_sec = cooldown_sec if cooldown_sec is not None else _load_cooldown_sec()
        self._state_file = state_file if state_file is not None else _STATE_FILE

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_last_complete(self) -> float | None:
        try:
            with self._state_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("last_complete_at")
            return float(ts) if ts is not None else None
        except Exception:
            return None

    def _save_last_complete(self, ts: float) -> None:
        try:
            with self._state_file.open("w", encoding="utf-8") as f:
                json.dump({"last_complete_at": ts}, f, ensure_ascii=False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self) -> float:
        """Check whether a new batch may start.

        Returns:
            0.0        — ready to proceed (no prior batch or cooldown elapsed).
            float > 0  — seconds remaining before the next batch may start.
        """
        last = self._load_last_complete()
        if last is None:
            return 0.0
        elapsed = time.time() - last
        remaining = self._cooldown_sec - elapsed
        return max(0.0, remaining)

    def record_complete(self) -> None:
        """Record the current time as the most recent batch completion."""
        self._save_last_complete(time.time())

    def get_status(self) -> StatusDict:
        """Return current cooldown status dict.

        Returns:
            {"state": "cooling"|"ready", "remaining_sec": float}
        """
        remaining = self.acquire()
        return {
            "state": "cooling" if remaining > 0.0 else "ready",
            "remaining_sec": remaining,
        }
