"""tests/test_role_mapper.py — RoleMapper 단위 테스트 (최소 10개)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from rolemesh.routing.role_mapper import RoleMapper, RoleSuggestion


# ── 헬퍼 ─────────────────────────────────────────────────────────────────


def _make_suggestion(role: str, agent: str, confidence: float, reason: str = "test") -> RoleSuggestion:
    return RoleSuggestion(role=role, agent=agent, confidence=confidence, reason=reason)


# ── detect_stack 테스트 ───────────────────────────────────────────────────


class TestDetectStack:
    def test_empty_when_no_tools(self):
        mapper = RoleMapper()
        with patch("shutil.which", return_value=None), \
             patch("os.path.exists", return_value=False):
            stack = mapper.detect_stack()
        assert stack == []

    def test_claude_detected(self):
        mapper = RoleMapper()
        def which_side(name):
            return "/usr/local/bin/claude" if name == "claude" else None
        with patch("shutil.which", side_effect=which_side), \
             patch("os.path.exists", return_value=False):
            stack = mapper.detect_stack()
        assert "claude" in stack

    def test_openclaw_detected(self):
        mapper = RoleMapper()
        def which_side(name):
            return "/usr/local/bin/openclaw" if name == "openclaw" else None
        with patch("shutil.which", side_effect=which_side), \
             patch("os.path.exists", return_value=False):
            stack = mapper.detect_stack()
        assert "openclaw" in stack

    def test_amp_detected_via_binary(self):
        mapper = RoleMapper()
        def which_side(name):
            return "/usr/local/bin/amp" if name == "amp" else None
        with patch("shutil.which", side_effect=which_side), \
             patch("os.path.exists", return_value=False):
            stack = mapper.detect_stack()
        assert "amp" in stack

    def test_python3_with_amp_dir_detected(self):
        mapper = RoleMapper()
        def which_side(name):
            return "/usr/bin/python3" if name == "python3" else None
        with patch("shutil.which", side_effect=which_side), \
             patch("os.path.exists", return_value=True):
            stack = mapper.detect_stack()
        assert "python3" in stack

    def test_node_detected(self):
        mapper = RoleMapper()
        def which_side(name):
            return "/usr/local/bin/node" if name == "node" else None
        with patch("shutil.which", side_effect=which_side), \
             patch("os.path.exists", return_value=False):
            stack = mapper.detect_stack()
        assert "node" in stack

    def test_npm_detected(self):
        mapper = RoleMapper()
        def which_side(name):
            return "/usr/local/bin/npm" if name == "npm" else None
        with patch("shutil.which", side_effect=which_side), \
             patch("os.path.exists", return_value=False):
            stack = mapper.detect_stack()
        assert "npm" in stack

    def test_multiple_tools_detected(self):
        mapper = RoleMapper()
        available = {"claude", "openclaw", "node"}
        def which_side(name):
            return f"/bin/{name}" if name in available else None
        with patch("shutil.which", side_effect=which_side), \
             patch("os.path.exists", return_value=False):
            stack = mapper.detect_stack()
        assert "claude" in stack
        assert "openclaw" in stack
        assert "node" in stack


# ── suggest_roles 테스트 ─────────────────────────────────────────────────


class TestSuggestRoles:
    def test_empty_stack_returns_fallback_builder(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles([])
        assert len(result) == 1
        assert result[0]["role"] == "builder"
        assert result[0]["agent"] == "codex-builder"

    def test_claude_suggests_builder(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["claude"])
        roles = [s["role"] for s in result]
        assert "builder" in roles

    def test_openclaw_suggests_pm(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["openclaw"])
        roles = [s["role"] for s in result]
        assert "pm" in roles

    def test_amp_suggests_analyst(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["amp"])
        roles = [s["role"] for s in result]
        assert "analyst" in roles

    def test_node_suggests_frontend_builder(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["node"])
        roles = [s["role"] for s in result]
        assert "frontend-builder" in roles

    def test_npm_suggests_frontend_builder(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["npm"])
        roles = [s["role"] for s in result]
        assert "frontend-builder" in roles

    def test_full_stack_suggests_all_roles(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["claude", "openclaw", "amp", "node"])
        roles = {s["role"] for s in result}
        assert "pm" in roles
        assert "builder" in roles
        assert "analyst" in roles
        assert "frontend-builder" in roles

    def test_suggestion_has_required_keys(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["claude"])
        assert len(result) > 0
        for s in result:
            assert "role" in s
            assert "agent" in s
            assert "confidence" in s
            assert "reason" in s

    def test_confidence_is_between_0_and_1(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["claude", "openclaw", "amp", "node", "npm"])
        for s in result:
            assert 0.0 <= s["confidence"] <= 1.0, f"신뢰도 범위 초과: {s}"

    def test_unknown_tool_ignored(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles(["unknowntool123", "nonexistent"])
        assert len(result) == 1
        assert result[0]["agent"] == "codex-builder"

    def test_normalizes_case_duplicates_and_paths(self):
        mapper = RoleMapper()
        result = mapper.suggest_roles([" /usr/local/bin/CLAUDE ", "claude", "NodeJS"])
        roles = {s["role"] for s in result}
        assert "builder" in roles
        assert "frontend-builder" in roles


# ── resolve_conflicts 테스트 ─────────────────────────────────────────────


class TestResolveConflicts:
    def test_deduplicates_same_role(self):
        mapper = RoleMapper()
        suggestions = [
            _make_suggestion("pm", "openclaw-pm", 0.95),
            _make_suggestion("pm", "local-pm", 0.60),
        ]
        result = mapper.resolve_conflicts(suggestions)
        pm_entries = [s for s in result if s["role"] == "pm"]
        assert len(pm_entries) == 1

    def test_keeps_higher_confidence(self):
        mapper = RoleMapper()
        suggestions = [
            _make_suggestion("pm", "openclaw-pm", 0.95),
            _make_suggestion("pm", "local-pm", 0.60),
        ]
        result = mapper.resolve_conflicts(suggestions)
        pm = next(s for s in result if s["role"] == "pm")
        assert pm["agent"] == "openclaw-pm"
        assert pm["confidence"] == 0.95

    def test_pm_priority_over_builder(self):
        mapper = RoleMapper()
        suggestions = [
            _make_suggestion("builder", "claude-builder", 0.95),
            _make_suggestion("pm", "openclaw-pm", 0.90),
        ]
        result = mapper.resolve_conflicts(suggestions)
        assert result[0]["role"] == "pm"

    def test_empty_returns_empty(self):
        mapper = RoleMapper()
        assert mapper.resolve_conflicts([]) == []

    def test_single_suggestion_unchanged(self):
        mapper = RoleMapper()
        suggestions = [_make_suggestion("builder", "claude-builder", 0.95)]
        result = mapper.resolve_conflicts(suggestions)
        assert len(result) == 1
        assert result[0]["agent"] == "claude-builder"

    def test_role_order_pm_builder_analyst_frontend(self):
        mapper = RoleMapper()
        suggestions = [
            _make_suggestion("frontend-builder", "node-frontend", 0.80),
            _make_suggestion("analyst", "amp-analyst", 0.85),
            _make_suggestion("builder", "claude-builder", 0.95),
            _make_suggestion("pm", "openclaw-pm", 0.95),
        ]
        result = mapper.resolve_conflicts(suggestions)
        roles = [s["role"] for s in result]
        assert roles.index("pm") < roles.index("builder")
        assert roles.index("builder") < roles.index("analyst")
        assert roles.index("analyst") < roles.index("frontend-builder")
