"""tests/test_codex_delegate.py — codex-delegate.sh basic contract tests."""

from __future__ import annotations

import os
import stat
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "codex-delegate.sh"


def _content() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_codex_delegate_file_exists():
    assert SCRIPT_PATH.exists(), f"파일 없음: {SCRIPT_PATH}"


def test_codex_delegate_is_executable():
    mode = os.stat(SCRIPT_PATH).st_mode
    assert mode & stat.S_IXUSR, "owner execute bit 없음"


def test_codex_delegate_contains_openai_codex_provider():
    assert 'PROVIDER="openai-codex"' in _content()


def test_codex_delegate_contains_codex_exec_command():
    content = _content()
    assert "codex exec -s danger-full-access --model gpt-5.4 -C" in content


def test_codex_delegate_records_batch_complete():
    assert "BatchCooldown().record_complete()" in _content()


def test_codex_delegate_usage_mentions_C_option():
    assert "사용법: $0 -C /path/to/project 'prompt'" in _content()
