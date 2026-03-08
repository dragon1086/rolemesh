from __future__ import annotations

from rolemesh.routing.role_mapper import RoleMapper


def test_suggest_accepts_comma_separated_string():
    mapper = RoleMapper()

    result = mapper.suggest("claude, NodeJS")

    roles = {item["role"] for item in result}
    assert roles == {"builder", "frontend-builder"}


def test_resolve_conflicts_skips_invalid_entries_and_clamps_confidence():
    mapper = RoleMapper()

    result = mapper.resolve_conflicts(
        [
            {"role": "builder", "agent": "claude-builder", "confidence": 1.4, "reason": "ok"},
            {"role": "", "agent": "invalid", "confidence": 0.5, "reason": "bad"},
            {"role": "pm", "agent": "openclaw-pm", "confidence": "bad", "reason": "bad"},
        ]
    )

    assert result == [
        {
            "role": "builder",
            "agent": "claude-builder",
            "confidence": 1.0,
            "reason": "ok",
        }
    ]
