"""
tests/test_symphony_fusion.py
IntentGate(_intent_gate) 동작 단위 테스트
"""
import pytest
from unittest.mock import MagicMock
from symphony_fusion import SymphonyMACRS, WorkItem


@pytest.fixture
def sf():
    registry = MagicMock()
    return SymphonyMACRS(registry=registry)


def item(kind, description):
    return WorkItem(id="t1", title="Test", description=description, kind=kind)


# ── coding + 스펙 부재 → clarify ─────────────────────────────

def test_coding_no_spec_returns_clarify(sf):
    """coding 요청이지만 파일명/IO/테스트 없음 → clarify"""
    result = sf._intent_gate(item("coding", "뭔가 만들어줘"))
    assert result["action"] == "clarify"
    assert len(result["missing_required"]) > 0


def test_coding_missing_target_files(sf):
    """파일/모듈 정보 없으면 target-files-or-modules 누락"""
    desc = "입력: query, 출력: dict. 테스트: pytest tests/"
    result = sf._intent_gate(item("coding", desc))
    assert "target-files-or-modules" in result["missing_required"]


def test_coding_missing_io_spec(sf):
    """IO 스펙 없으면 io-spec 누락"""
    desc = "src/rolemesh/amp_caller.py에 함수 추가. 테스트: pytest"
    result = sf._intent_gate(item("coding", desc))
    assert "io-spec" in result["missing_required"]


def test_coding_missing_acceptance_tests(sf):
    """수용 기준 없으면 acceptance-tests 누락"""
    desc = "src/rolemesh/amp_caller.py 파일. 입력: str, 출력: dict"
    result = sf._intent_gate(item("coding", desc))
    assert "acceptance-tests" in result["missing_required"]


# ── analysis 정상 요청 → proceed ─────────────────────────────

def test_analysis_request_returns_proceed(sf):
    """analysis 요청은 missing_required 검사 없이 proceed"""
    result = sf._intent_gate(item("analysis", "이 전략을 분석해줘"))
    assert result["action"] == "proceed"
    assert result["missing_required"] == []


def test_analysis_core_request_extracted(sf):
    result = sf._intent_gate(item("analysis", "시장 상황을 분석하고 보고해줘"))
    assert result["core_request"] != ""
    assert result["ambiguous"] is False


# ── 모호한 표현 → clarify ─────────────────────────────────────

def test_ambiguous_signal_returns_clarify(sf):
    """'알아서' 포함 → ambiguous=True, action=clarify"""
    result = sf._intent_gate(item("analysis", "알아서 해줘"))
    assert result["action"] == "clarify"
    assert result["ambiguous"] is True


def test_ambiguous_word_degteogi(sf):
    result = sf._intent_gate(item("coding", "적당히 만들어줘"))
    assert result["action"] == "clarify"
    assert result["ambiguous"] is True


# ── coding + 충분한 스펙 → proceed ──────────────────────────

def test_coding_with_full_spec_returns_proceed(sf):
    """파일명 + IO + 테스트 모두 있으면 proceed"""
    desc = (
        "src/rolemesh/amp_caller.py 파일에 함수를 추가해줘. "
        "입력: query str, 출력: dict. "
        "테스트: pytest tests/test_amp.py"
    )
    result = sf._intent_gate(item("coding", desc))
    assert result["action"] == "proceed"
    assert result["missing_required"] == []
