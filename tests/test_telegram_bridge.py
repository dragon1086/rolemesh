from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

from rolemesh.gateway.telegram_bridge import MessageClass, RouteResult, TelegramBridge


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "telegram-route.sh"


def test_coding_keywords_classify_as_coding_for_code_fix_request():
    bridge = TelegramBridge()
    assert bridge.classify("코드 수정해줘") is MessageClass.CODING


def test_coding_keywords_classify_as_coding_for_bug_fix_request():
    bridge = TelegramBridge()
    assert bridge.classify("버그 픽스 부탁해") is MessageClass.CODING


def test_analysis_keywords_classify_as_analysis_for_buy_timing():
    bridge = TelegramBridge()
    assert bridge.classify("지금 매수 타이밍이야?") is MessageClass.ANALYSIS


def test_analysis_keywords_classify_as_analysis_for_strategy_review():
    bridge = TelegramBridge()
    assert bridge.classify("전략 분석해줘") is MessageClass.ANALYSIS


def test_memory_keywords_classify_as_memory_for_remember_command():
    bridge = TelegramBridge()
    assert bridge.classify("이거 기억해") is MessageClass.MEMORY


def test_memory_keywords_classify_as_memory_for_save_command():
    bridge = TelegramBridge()
    assert bridge.classify("이 메모 저장해") is MessageClass.MEMORY


def test_general_conversation_classifies_as_coordination_for_greeting():
    bridge = TelegramBridge()
    assert bridge.classify("안녕") is MessageClass.COORDINATION


def test_general_conversation_classifies_as_coordination_for_small_talk():
    bridge = TelegramBridge()
    assert bridge.classify("뭐해") is MessageClass.COORDINATION


def test_should_delegate_returns_true_for_coding():
    bridge = TelegramBridge()
    assert bridge.should_delegate(MessageClass.CODING) is True


def test_should_delegate_returns_false_for_coordination():
    bridge = TelegramBridge()
    assert bridge.should_delegate(MessageClass.COORDINATION) is False


def test_route_returns_route_result_structure():
    bridge = TelegramBridge()
    result = bridge.route("코드 수정해줘")
    assert isinstance(result, RouteResult)
    assert isinstance(result.message_class, MessageClass)
    assert isinstance(result.provider, str)
    assert isinstance(result.reason, str)


def test_route_for_coding_includes_delegate_script():
    bridge = TelegramBridge()
    result = bridge.route("버그 픽스")
    assert result.message_class is MessageClass.CODING
    assert result.delegate_script in {
        "scripts/cokac-delegate.sh",
        "scripts/codex-delegate.sh",
        "scripts/gemini-delegate.sh",
    }


def test_route_for_coordination_keeps_self_provider():
    bridge = TelegramBridge()
    result = bridge.route("안녕")
    assert result.provider == "self"
    assert result.delegate_script is None


def test_telegram_route_script_exists():
    assert SCRIPT_PATH.exists(), f"파일 없음: {SCRIPT_PATH}"


def test_telegram_route_script_is_executable():
    mode = os.stat(SCRIPT_PATH).st_mode
    assert mode & stat.S_IXUSR, "owner execute bit 없음"


def test_telegram_route_script_outputs_json():
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "코드 수정해줘"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == {"class", "provider", "delegate_script", "reason"}
    assert payload["class"] == "coding"
