"""provider_router.py — Route tasks to available providers via circuit breakers."""

from __future__ import annotations

import time
from typing import Any, Optional

from .circuit_breaker import CBState, ProviderCircuitBreaker

DEFAULT_PROVIDERS = ["anthropic", "openai", "gemini"]
FALLBACK_PROVIDER = "local_rule"


class ProviderRouter:
    """Route tasks to available providers using per-provider circuit breakers.

    Args:
        providers:         Ordered list of provider names to try.
        failure_threshold: Consecutive failures before OPEN (default 3).
        cooldown_sec:      Seconds to stay OPEN before HALF_OPEN (default 60).
    """

    def __init__(
        self,
        providers: Optional[list[str]] = None,
        failure_threshold: int = 3,
        cooldown_sec: int = 60,
    ) -> None:
        self.providers: list[str] = providers if providers is not None else list(DEFAULT_PROVIDERS)
        self.cb = ProviderCircuitBreaker(
            failure_threshold=failure_threshold,
            cooldown_sec=cooldown_sec,
        )

    def route(self, task: Any = None) -> str:  # noqa: ARG002
        """Return the first available provider name, or FALLBACK_PROVIDER.

        Iterates providers in order; returns the first whose circuit is
        CLOSED or HALF_OPEN. Falls back to 'local_rule' if all are OPEN.
        """
        for provider in self.providers:
            if self.cb.is_available(provider):
                return provider
        return FALLBACK_PROVIDER

    def record_success(self, provider: str) -> None:
        """Delegate success signal to the circuit breaker."""
        self.cb.record_success(provider)

    def record_failure(self, provider: str) -> None:
        """Delegate failure signal to the circuit breaker."""
        self.cb.record_failure(provider)

    def get_status(self) -> dict[str, dict]:
        """Return status dict for all providers.

        Returns:
            {
                "anthropic": {
                    "state": "CLOSED",
                    "cooldown_remaining": 0,
                    "available": True,
                },
                ...
            }
        """
        status: dict[str, dict] = {}
        for provider in self.providers:
            state = self.cb.get_state(provider)
            remaining = self.cb.cooldown_remaining(provider)
            status[provider] = {
                "state": state.value,
                "cooldown_remaining": remaining,
                "available": state in (CBState.CLOSED, CBState.HALF_OPEN),
            }
        return status
