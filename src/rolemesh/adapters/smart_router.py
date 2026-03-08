"""smart_router.py — Provider selection with CB and throttle-aware fallback."""

from __future__ import annotations

from pathlib import Path

from .circuit_breaker import CBState, ProviderCircuitBreaker
from .throttle import TokenBucketThrottle, _load_state

DEFAULT_PROVIDERS = ["anthropic", "openai-codex", "gemini"]
_DELEGATE_SCRIPTS = {
    "anthropic": "scripts/cokac-delegate.sh",
    "openai-codex": "scripts/codex-delegate.sh",
    "gemini": "scripts/gemini-delegate.sh",
}


class SmartRouter:
    """Pick the first provider whose circuit is available and throttle is not exhausted."""

    def __init__(
        self,
        providers: list[str] | None = None,
        failure_threshold: int = 3,
        cooldown_sec: int = 60,
        throttle: TokenBucketThrottle | None = None,
        cb: ProviderCircuitBreaker | None = None,
    ) -> None:
        self.providers = list(providers) if providers is not None else list(DEFAULT_PROVIDERS)
        self.throttle = throttle if throttle is not None else TokenBucketThrottle()
        self.cb = cb if cb is not None else ProviderCircuitBreaker(
            failure_threshold=failure_threshold,
            cooldown_sec=cooldown_sec,
        )

    def _throttle_available(self, provider: str) -> bool:
        capacity = self.throttle._capacity(provider)
        state = _load_state(provider, capacity)
        state = self.throttle._refill(state, capacity)
        return float(state["tokens"]) >= 1.0

    def get_available_provider(self, task_type: str = "code") -> str | None:  # noqa: ARG002
        """Return the first provider that is not OPEN and has throttle capacity."""
        for provider in self.providers:
            if self.cb.get_state(provider) == CBState.OPEN:
                continue
            if not self._throttle_available(provider):
                continue
            return provider
        return None

    def get_delegate_script(self, provider: str) -> str:
        """Return the delegate script path for a provider."""
        if provider not in _DELEGATE_SCRIPTS:
            raise ValueError(f"unknown provider: {provider}")
        return _DELEGATE_SCRIPTS[provider]

    def get_delegate_script_path(self, provider: str) -> Path:
        """Return the absolute delegate script path for a provider."""
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / self.get_delegate_script(provider)

    def record_failure(self, provider: str) -> None:
        self.cb.record_failure(provider)

    def record_success(self, provider: str) -> None:
        self.cb.record_success(provider)
