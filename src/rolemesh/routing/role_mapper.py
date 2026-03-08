"""
role_mapper.py — 시스템 도구 탐지 기반 역할 자동 매핑.

사용 예:
    from rolemesh.role_mapper import RoleMapper
    mapper = RoleMapper()
    stack = mapper.detect_stack()
    suggestions = mapper.suggest_roles(stack)
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable, Mapping
from typing import TypedDict


class RoleSuggestion(TypedDict):
    role: str
    agent: str
    confidence: float
    reason: str


# 역할별 우선순위 (낮을수록 높은 우선순위)
_ROLE_PRIORITY: dict[str, int] = {
    "pm": 0,
    "builder": 1,
    "analyst": 2,
    "frontend-builder": 3,
}

_FALLBACK_SUGGESTIONS: list[RoleSuggestion] = [
    RoleSuggestion(
        role="builder",
        agent="codex-builder",
        confidence=0.30,
        reason="명시적 도구 매칭 없음 — 범용 Codex Builder를 기본 후보로 제안",
    ),
]

# 도구 → 역할 매핑 테이블
_TOOL_ROLE_MAP: list[dict] = [
    {
        "tool": "openclaw",
        "role": "pm",
        "agent": "openclaw-pm",
        "confidence": 0.95,
        "reason": "openclaw 감지 — PM 전담 에이전트 (우선 배정)",
    },
    {
        "tool": "claude",
        "role": "builder",
        "agent": "claude-builder",
        "confidence": 0.95,
        "reason": "claude 감지 — 코드 구현 전담 Builder (우선 배정)",
    },
    {
        "tool": "amp",
        "role": "analyst",
        "agent": "amp-analyst",
        "confidence": 0.85,
        "reason": "amp 감지 — 데이터 분석·전략 검토 Analyst",
    },
    {
        "tool": "python3",
        "role": "analyst",
        "agent": "python-analyst",
        "confidence": 0.70,
        "reason": "python3 + ~/amp 디렉터리 감지 — 스크립트 기반 Analyst",
    },
    {
        "tool": "node",
        "role": "frontend-builder",
        "agent": "node-frontend",
        "confidence": 0.80,
        "reason": "node 감지 — 프론트엔드 Builder",
    },
    {
        "tool": "npm",
        "role": "frontend-builder",
        "agent": "npm-frontend",
        "confidence": 0.75,
        "reason": "npm 감지 — 프론트엔드 패키지 Builder",
    },
]


class RoleMapper:
    """시스템 도구 탐지 → 역할 자동 매핑."""

    def _normalize_stack(self, stack: list[str] | str | None) -> list[str]:
        """입력 스택을 소문자/별칭 기준으로 정규화하고 중복 제거."""
        if not stack:
            return []

        if isinstance(stack, str):
            raw_stack: Iterable[object] = stack.split(",")
        else:
            raw_stack = stack

        aliases = {
            "python": "python3",
            "python.exe": "python3",
            "nodejs": "node",
        }
        normalized: list[str] = []
        seen: set[str] = set()

        for raw in raw_stack:
            if raw is None:
                continue
            tool = str(raw).strip().lower()
            if not tool:
                continue
            tool = os.path.basename(tool)
            tool = re.split(r"\s+", tool, maxsplit=1)[0]
            tool = aliases.get(tool, tool)
            if tool in seen:
                continue
            seen.add(tool)
            normalized.append(tool)

        return normalized

    def _sanitize_suggestion(self, suggestion: Mapping[str, object]) -> RoleSuggestion | None:
        """외부 입력 suggestion을 안전한 RoleSuggestion 포맷으로 정규화."""
        role = str(suggestion.get("role", "")).strip()
        agent = str(suggestion.get("agent", "")).strip()
        reason = str(suggestion.get("reason", "")).strip()

        if not role or not agent or not reason:
            return None

        try:
            confidence = float(suggestion.get("confidence", 0.0))
        except (TypeError, ValueError):
            return None

        confidence = max(0.0, min(1.0, confidence))
        return RoleSuggestion(
            role=role,
            agent=agent,
            confidence=confidence,
            reason=reason,
        )

    # ── 탐지 ──────────────────────────────────────────────────────

    def detect_stack(self) -> list[str]:
        """시스템에서 사용 가능한 도구 목록 반환.

        Returns:
            감지된 도구 이름 목록. 예: ["claude", "openclaw", "python3"]
        """
        tools: list[str] = []

        if shutil.which("claude"):
            tools.append("claude")

        if shutil.which("openclaw"):
            tools.append("openclaw")

        # amp 바이너리 직접 감지
        if shutil.which("amp"):
            tools.append("amp")
        # python3 + ~/amp 경로 존재 → analyst 후보
        elif shutil.which("python3") and os.path.exists(os.path.expanduser("~/amp")):
            tools.append("python3")

        if shutil.which("node"):
            tools.append("node")

        if shutil.which("npm"):
            tools.append("npm")

        return tools

    # ── 추천 ──────────────────────────────────────────────────────

    def suggest_roles(self, stack: list[str] | str | None) -> list[RoleSuggestion]:
        """스택 기반 역할 추천 목록 반환.

        Args:
            stack: 도구 이름 목록. 예: ["claude", "openclaw"]

        Returns:
            [{role, agent, confidence, reason}] 목록 (confidence 내림차순).
        """
        normalized_stack = self._normalize_stack(stack)
        if not normalized_stack:
            return list(_FALLBACK_SUGGESTIONS)

        stack_set = set(normalized_stack)
        candidates: list[RoleSuggestion] = []

        for entry in _TOOL_ROLE_MAP:
            if entry["tool"] in stack_set:
                candidates.append(
                    RoleSuggestion(
                        role=entry["role"],
                        agent=entry["agent"],
                        confidence=entry["confidence"],
                        reason=entry["reason"],
                    )
                )

        resolved = self.resolve_conflicts(candidates)
        if resolved:
            return resolved
        return list(_FALLBACK_SUGGESTIONS)

    def suggest(self, stack: list[str] | str | None = None) -> list[RoleSuggestion]:
        """하위 호환용 별칭."""
        return self.suggest_roles(stack)

    # ── 충돌 해소 ─────────────────────────────────────────────────

    def resolve_conflicts(self, suggestions: list[RoleSuggestion]) -> list[RoleSuggestion]:
        """역할 중복 시 우선순위 적용.

        규칙:
        - PM: openclaw 우선 (confidence 높은 쪽)
        - Builder: claude 우선 (confidence 높은 쪽)
        - 동일 역할 내 confidence 가장 높은 항목만 유지.

        Args:
            suggestions: 충돌 가능성 있는 추천 목록.

        Returns:
            역할별 대표 추천 목록 (_ROLE_PRIORITY 순 정렬).
        """
        # 역할별로 confidence 최고 항목 선택
        role_best: dict[str, RoleSuggestion] = {}
        for s in suggestions:
            if not isinstance(s, Mapping):
                continue
            normalized = self._sanitize_suggestion(s)
            if normalized is None:
                continue

            role = normalized["role"]
            if role not in role_best or normalized["confidence"] > role_best[role]["confidence"]:
                role_best[role] = normalized

        # 우선순위 → confidence 내림차순 정렬
        return sorted(
            role_best.values(),
            key=lambda x: (_ROLE_PRIORITY.get(x["role"], 99), -x["confidence"]),
        )
