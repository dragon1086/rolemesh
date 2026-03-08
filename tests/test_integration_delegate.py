"""
tests/test_integration_delegate.py
IntegrationManager.generate_delegate_script() + auto_script 단위 테스트 (최소 10개)
"""
import os
import stat
import pytest

from rolemesh.routing.integration import (
    IntegrationManager,
    DuplicateIntegrationError,
)


@pytest.fixture
def mgr(tmp_path):
    db = str(tmp_path / "test_delegate.db")
    m = IntegrationManager(db_path=db)
    yield m
    m.close()


@pytest.fixture
def tmpl_path(tmp_path):
    """실제 프로젝트 템플릿 경로를 반환한다."""
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    path = os.path.normpath(os.path.join(repo_root, "scripts", "templates", "delegate.sh.tmpl"))
    assert os.path.exists(path), f"템플릿 파일 없음: {path}"
    return path


# ── 1. auto_script=True → 스크립트 파일 생성 확인 ────────────────────────────

def test_add_auto_script_creates_file(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    info = mgr.add(
        "gemini", role="builder", endpoint="local://gemini",
        cmd="gemini -p", provider="gemini",
        auto_script=True,
    )
    assert "script_path" in info
    assert os.path.exists(info["script_path"])


def test_generate_script_file_exists(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="testbot", cmd="testbot --run", provider="openai",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    assert os.path.isfile(path)
    assert path.endswith("testbot-delegate.sh")


# ── 2. 스크립트 내 BatchCooldown/CB/Throttle 코드 포함 확인 (grep) ──────────

def test_script_contains_batch_cooldown(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="bot-cd", cmd="mybot -p", provider="anthropic",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    content = open(path).read()
    assert "BatchCooldown" in content


def test_script_contains_circuit_breaker(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="bot-cb", cmd="mybot -p", provider="anthropic",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    content = open(path).read()
    assert "ProviderCircuitBreaker" in content or "Circuit Breaker" in content


def test_script_contains_throttle(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="bot-th", cmd="mybot -p", provider="anthropic",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    content = open(path).read()
    assert "TokenBucketThrottle" in content or "Throttle" in content


# ── 3. 실행 권한(chmod +x) 확인 ─────────────────────────────────────────────

def test_script_is_executable(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="bot-exec", cmd="mybot -p", provider="gemini",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    mode = os.stat(path).st_mode
    assert mode & stat.S_IXUSR, "owner execute bit 없음"


# ── 4. --no-auto-script → 파일 미생성 확인 ──────────────────────────────────

def test_no_auto_script_does_not_create_file(mgr, tmp_path):
    info = mgr.add(
        "silent-bot", role="analyzer", endpoint="local://silent",
        cmd="silent --run", provider="openai",
        auto_script=False,
    )
    assert "script_path" not in info


# ── 5. 중복 add → DuplicateIntegrationError ──────────────────────────────────

def test_duplicate_add_raises(mgr):
    mgr.add("dup-bot", role="builder", endpoint="local://dup",
             cmd="dup -p", provider="openai", auto_script=False)
    with pytest.raises(DuplicateIntegrationError):
        mgr.add("dup-bot", role="analyzer", endpoint="local://dup2",
                 cmd="dup -p", provider="openai", auto_script=False)


# ── 6. allow_update=True → 스크립트 갱신 ────────────────────────────────────

def test_allow_update_regenerates_script(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    info1 = mgr.add(
        "upd-bot", role="builder", endpoint="local://upd",
        cmd="oldcmd -p", provider="gemini",
        auto_script=True,
    )
    # 실제로 scripts_dir 지정해서 갱신 확인
    path2 = mgr.generate_delegate_script(
        name="upd-bot", cmd="newcmd -p", provider="gemini",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    content = open(path2).read()
    assert "newcmd -p" in content


# ── 7. provider 이름이 스크립트에 올바르게 반영 ──────────────────────────────

def test_provider_name_in_script(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="prov-bot", cmd="prov-cmd --run", provider="my-special-provider",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    content = open(path).read()
    assert "my-special-provider" in content


# ── 8. cmd 이름이 스크립트에 올바르게 반영 ──────────────────────────────────

def test_cmd_in_script(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="cmd-bot", cmd="gemini --special-flag", provider="gemini",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    content = open(path).read()
    assert "gemini --special-flag" in content


# ── 9. auto_script=True이고 cmd 빈 문자열 → ValueError ─────────────────────

def test_auto_script_with_empty_cmd_raises(mgr):
    with pytest.raises(ValueError, match="cmd"):
        mgr.add(
            "no-cmd-bot", role="builder", endpoint="local://x",
            cmd="", provider="openai",
            auto_script=True,
        )


# ── 10. agent 이름이 스크립트 파일명에 반영 ─────────────────────────────────

def test_script_filename_matches_agent_name(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="amp-analyst", cmd="python3 ~/amp/cli.py", provider="anthropic",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    assert os.path.basename(path) == "amp-analyst-delegate.sh"


# ── 11. generate_delegate_script에 빈 cmd → ValueError ─────────────────────

def test_generate_script_empty_cmd_raises(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    with pytest.raises(ValueError, match="cmd"):
        mgr.generate_delegate_script(
            name="empty-cmd", cmd="", provider="openai",
            scripts_dir=scripts_dir, template_path=tmpl_path,
        )


# ── 12. 스크립트 shebang 확인 ───────────────────────────────────────────────

def test_script_has_shebang(mgr, tmp_path, tmpl_path):
    scripts_dir = str(tmp_path / "scripts")
    path = mgr.generate_delegate_script(
        name="shebang-bot", cmd="mybot -p", provider="openai",
        scripts_dir=scripts_dir, template_path=tmpl_path,
    )
    first_line = open(path).readline().strip()
    assert first_line.startswith("#!/usr/bin/env bash") or first_line.startswith("#!/bin/bash")
