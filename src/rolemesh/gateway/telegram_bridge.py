"""telegram_bridge.py — Rule-based Telegram message routing for RoleMesh."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from rolemesh.adapters.circuit_breaker import CBState
from rolemesh.adapters.smart_router import SmartRouter


class MessageClass(str, Enum):
    """High-level message buckets used by the Telegram bridge."""

    CODING = "coding"
    ANALYSIS = "analysis"
    MEMORY = "memory"
    COORDINATION = "coordination"


@dataclass(frozen=True)
class RouteResult:
    """Final routing decision returned by TelegramBridge.route()."""

    message_class: MessageClass
    provider: str
    delegate_script: str | None
    reason: str

    def to_dict(self) -> dict[str, str | None]:
        """Serialize the route result with enum values normalized to strings."""
        payload = asdict(self)
        payload["message_class"] = self.message_class.value
        return payload


class TelegramBridge:
    """Classify Telegram messages and decide whether RoleMesh should delegate them."""

    _CODING_KEYWORDS = (
        "코드",
        "버그",
        "픽스",
        "fix",
        "refactor",
        "리팩토링",
        "테스트",
        "test",
        "구현",
        "개발",
        "함수",
        "class ",
        "api",
        "스크립트",
    )
    _ANALYSIS_KEYWORDS = (
        "분석",
        "전략",
        "매수",
        "매도",
        "투자",
        "리스크",
        "시장",
        "지표",
        "시나리오",
        "판단",
    )
    _MEMORY_KEYWORDS = (
        "기억해",
        "저장해",
        "기록해",
        "메모해",
        "remember",
        "save this",
        "note this",
    )
    _SCRIPT_BY_PROVIDER = {
        "anthropic": "scripts/cokac-delegate.sh",
        "openai-codex": "scripts/codex-delegate.sh",
        "gemini": "scripts/gemini-delegate.sh",
    }

    def __init__(self, router: SmartRouter | None = None) -> None:
        self.router = router or SmartRouter()

    def classify(self, message: str) -> MessageClass:
        """Classify a Telegram message into one of the bridge buckets."""
        text = (message or "").strip().casefold()
        if not text:
            return MessageClass.COORDINATION
        if self._contains_any(text, self._MEMORY_KEYWORDS):
            return MessageClass.MEMORY
        if self._contains_any(text, self._CODING_KEYWORDS):
            return MessageClass.CODING
        if self._contains_any(text, self._ANALYSIS_KEYWORDS):
            return MessageClass.ANALYSIS
        return MessageClass.COORDINATION

    def should_delegate(self, message_class: MessageClass) -> bool:
        """Return True when the message should be delegated to a worker/provider."""
        return message_class in {MessageClass.CODING, MessageClass.ANALYSIS}

    def route(self, message: str) -> RouteResult:
        """Return the final routing decision for a Telegram message."""
        message_class = self.classify(message)
        if message_class is MessageClass.CODING:
            provider = self.router.get_available_provider("code") or "self"
            delegate_script = self._SCRIPT_BY_PROVIDER.get(provider)
            if delegate_script is None:
                return RouteResult(
                    message_class=message_class,
                    provider="self",
                    delegate_script=None,
                    reason="coding request detected but no remote provider is currently available",
                )
            return RouteResult(
                message_class=message_class,
                provider=provider,
                delegate_script=delegate_script,
                reason=f"coding keywords detected; delegate via {provider}",
            )

        if message_class is MessageClass.ANALYSIS:
            provider = self._select_analysis_provider()
            delegate_script = "scripts/amp-analyst-delegate.sh" if provider != "self" else None
            reason = (
                f"analysis keywords detected; delegate via {provider} analyst path"
                if provider != "self"
                else "analysis request detected but no remote provider is currently available"
            )
            return RouteResult(
                message_class=message_class,
                provider=provider,
                delegate_script=delegate_script,
                reason=reason,
            )

        if message_class is MessageClass.MEMORY:
            return RouteResult(
                message_class=message_class,
                provider="self",
                delegate_script=None,
                reason="memory command detected; keep the request in local coordination flow",
            )

        return RouteResult(
            message_class=message_class,
            provider="self",
            delegate_script=None,
            reason="general conversation detected; no delegation required",
        )

    def _select_analysis_provider(self) -> str:
        if "anthropic" not in self.router.providers:
            return "self"
        if self.router.cb.get_state("anthropic") == CBState.OPEN:
            return "self"
        if not self.router._throttle_available("anthropic"):
            return "self"
        return "anthropic"

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)
