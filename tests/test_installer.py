"""
tests/test_installer.py — RoleMeshInstaller 단위 테스트
"""
import os
import sys
import importlib
from unittest import mock

import pytest

# PYTHONPATH에 src가 포함되어 있다고 가정 (conftest.py 또는 pytest.ini)
from rolemesh.cli.installer import RoleMeshInstaller, Environment, RoleConfig


# ── fixtures ──────────────────────────────────────────────────

@pytest.fixture
def installer(tmp_path):
    db = str(tmp_path / "rolemesh.db")
    return RoleMeshInstaller(db_path=db)


# ── detect_environment ────────────────────────────────────────

class TestDetectEnvironment:
    def test_returns_environment_object(self, installer):
        env = installer.detect_environment()
        assert isinstance(env, Environment)

    def test_python_version_set(self, installer):
        env = installer.detect_environment()
        assert env.python_version is not None
        parts = env.python_version.split(".")
        assert len(parts) == 3
        assert int(parts[0]) >= 3

    def test_claude_detected_when_present(self, installer):
        with mock.patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}" if x == "claude" else None):
            env = installer.detect_environment()
        assert env.has_claude is True
        assert env.claude_path == "/usr/bin/claude"

    def test_claude_not_detected_when_absent(self, installer):
        with mock.patch("shutil.which", return_value=None):
            env = installer.detect_environment()
        assert env.has_claude is False
        assert env.claude_path is None

    def test_openclaw_detected(self, installer):
        with mock.patch("shutil.which", side_effect=lambda x: f"/usr/local/bin/{x}" if x == "openclaw" else None):
            env = installer.detect_environment()
        assert env.has_openclaw is True
        assert env.openclaw_path == "/usr/local/bin/openclaw"

    def test_amp_detected(self, installer):
        with mock.patch("shutil.which", side_effect=lambda x: f"/usr/local/bin/{x}" if x == "amp" else None):
            env = installer.detect_environment()
        assert env.has_amp is True

    def test_env_vars_read(self, installer):
        with mock.patch.dict(os.environ, {
            "ANTHROPIC_MODEL": "claude-opus-4-6",
            "CLAUDE_CODE_OAUTH_TOKEN": "tok-abc",
        }):
            env = installer.detect_environment()
        assert env.anthropic_model == "claude-opus-4-6"
        assert env.has_oauth_token is True

    def test_missing_env_vars(self, installer):
        stripped = {k: v for k, v in os.environ.items()
                    if k not in ("ANTHROPIC_MODEL", "CLAUDE_CODE_OAUTH_TOKEN")}
        with mock.patch.dict(os.environ, stripped, clear=True):
            env = installer.detect_environment()
        assert env.anthropic_model is None
        assert env.has_oauth_token is False


# ── recommend_roles ───────────────────────────────────────────

class TestRecommendRoles:
    def _env(self, **kwargs) -> Environment:
        e = Environment()
        for k, v in kwargs.items():
            setattr(e, k, v)
        return e

    def test_all_tools_gives_three_roles(self, installer):
        env = self._env(has_claude=True, has_openclaw=True, has_amp=True,
                        claude_path="/usr/bin/claude",
                        openclaw_path="/usr/bin/openclaw",
                        amp_path="/usr/bin/amp")
        roles = installer.recommend_roles(env)
        role_names = [r.role for r in roles]
        assert "PM" in role_names
        assert "Builder" in role_names
        assert "Analyst" in role_names

    def test_only_claude_gives_builder(self, installer):
        env = self._env(has_claude=True, claude_path="/usr/bin/claude")
        roles = installer.recommend_roles(env)
        assert any(r.role == "Builder" for r in roles)
        assert not any(r.role == "Analyst" for r in roles)

    def test_only_openclaw_gives_pm(self, installer):
        env = self._env(has_openclaw=True, openclaw_path="/usr/bin/openclaw")
        roles = installer.recommend_roles(env)
        assert any(r.role == "PM" for r in roles)
        assert not any(r.role == "Builder" for r in roles)

    def test_no_tools_gives_light_mode(self, installer):
        env = self._env()  # nothing detected
        roles = installer.recommend_roles(env)
        assert len(roles) >= 1
        assert roles[0].role == "PM"

    def test_pm_role_has_capabilities(self, installer):
        env = self._env(has_openclaw=True, openclaw_path="/usr/bin/openclaw")
        roles = installer.recommend_roles(env)
        pm = next(r for r in roles if r.role == "PM")
        assert len(pm.capabilities) > 0
        assert pm.capabilities[0]["name"] == "project_management"

    def test_builder_tool_is_claude(self, installer):
        env = self._env(has_claude=True, claude_path="/usr/bin/claude")
        roles = installer.recommend_roles(env)
        builder = next(r for r in roles if r.role == "Builder")
        assert builder.tool == "claude"

    def test_analyst_tool_is_amp(self, installer):
        env = self._env(has_amp=True, amp_path="/usr/bin/amp")
        roles = installer.recommend_roles(env)
        analyst = next(r for r in roles if r.role == "Analyst")
        assert analyst.tool == "amp"


# ── init_database ─────────────────────────────────────────────

class TestInitDatabase:
    def test_creates_db_file(self, installer):
        installer.init_database()
        assert os.path.exists(installer.db_path)

    def test_db_has_agents_table(self, installer):
        import sqlite3
        installer.init_database()
        conn = sqlite3.connect(installer.db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "agents" in tables
        assert "capabilities" in tables
        assert "task_queue" in tables

    def test_idempotent(self, installer):
        """두 번 호출해도 오류 없음."""
        installer.init_database()
        installer.init_database()
        assert os.path.exists(installer.db_path)


# ── register_roles ────────────────────────────────────────────

class TestRegisterRoles:
    def test_registers_agents(self, installer):
        from rolemesh.core.registry_client import RegistryClient
        installer.init_database()
        roles = [
            RoleConfig(
                role="Builder",
                agent_id="test-builder",
                display_name="Test Builder",
                description="테스트용",
                tool="claude",
                capabilities=[{
                    "name": "code_write",
                    "description": "코드 작성",
                    "keywords": ["코드"],
                    "cost_level": "high",
                }],
            )
        ]
        installer.register_roles(roles)

        client = RegistryClient(db_path=installer.db_path)
        agents = client.list_agents(active_only=False)
        client.close()
        assert any(a["agent_id"] == "test-builder" for a in agents)

    def test_registers_capabilities(self, installer):
        import sqlite3
        installer.init_database()
        roles = [
            RoleConfig(
                role="PM",
                agent_id="test-pm",
                display_name="Test PM",
                description="테스트 PM",
                tool=None,
                capabilities=[{
                    "name": "project_management",
                    "description": "관리",
                    "keywords": ["관리"],
                    "cost_level": "medium",
                }],
            )
        ]
        installer.register_roles(roles)

        conn = sqlite3.connect(installer.db_path)
        caps = conn.execute(
            "SELECT name FROM capabilities WHERE agent_id = 'test-pm'"
        ).fetchall()
        conn.close()
        assert any(c[0] == "project_management" for c in caps)
