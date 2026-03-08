"""
tests/test_intentgate_regression.py
IntentGate 오탐/미탐 회귀 테스트 — 최소 10개 케이스
오탐/미탐 케이스는 주석으로 명시
"""
import pytest
from unittest.mock import MagicMock
from rolemesh.routing.symphony_fusion import SymphonyMACRS, WorkItem


@pytest.fixture
def sf():
    return SymphonyMACRS(registry=MagicMock())


def item(kind, description, title="Test"):
    return WorkItem(id="t1", title=title, description=description, kind=kind)


# ── [정탐] coding + 스펙 부재 → clarify ──────────────────────

def test_01_coding_no_spec_clarify(sf):
    """[정탐] coding 요청에 파일/IO/테스트 정보 없음 → clarify"""
    r = sf._intent_gate(item("coding", "뭔가 만들어줘"))
    assert r["action"] == "clarify"
    assert len(r["missing_required"]) > 0


def test_02_coding_missing_all_three_fields(sf):
    """[정탐] target-files, io-spec, acceptance-tests 모두 누락 → 3개 missing"""
    r = sf._intent_gate(item("coding", "사용자 등록 기능 구현해줘"))
    assert "target-files-or-modules" in r["missing_required"]
    assert "io-spec" in r["missing_required"]
    assert "acceptance-tests" in r["missing_required"]


def test_03_coding_empty_description_clarify(sf):
    """[정탐] 빈 coding 요청 → clarify (모든 필드 누락)"""
    r = sf._intent_gate(item("coding", ""))
    assert r["action"] == "clarify"
    assert len(r["missing_required"]) == 3


def test_04_coding_only_file_missing_io_and_test(sf):
    """[정탐] 파일명만 있고 IO/테스트 없음 → clarify (partial spec)"""
    r = sf._intent_gate(item("coding", "src/rolemesh/init_db.py에 마이그레이션 추가"))
    assert r["action"] == "clarify"
    assert "io-spec" in r["missing_required"]
    assert "acceptance-tests" in r["missing_required"]
    assert "target-files-or-modules" not in r["missing_required"]


def test_05_coding_file_and_io_no_test_clarify(sf):
    """[정탐] 파일+IO 있지만 테스트 없음 → clarify"""
    r = sf._intent_gate(item("coding", "src/rolemesh/init_db.py. 입력: db_path str, 출력: Connection"))
    assert r["action"] == "clarify"
    assert "acceptance-tests" in r["missing_required"]
    assert "target-files-or-modules" not in r["missing_required"]
    assert "io-spec" not in r["missing_required"]


# ── [정탐] coding + 스펙 충분 → proceed ─────────────────────

def test_06_coding_full_spec_proceed(sf):
    """[정탐] 파일 + IO + 테스트 모두 있으면 proceed"""
    desc = (
        "src/rolemesh/amp_caller.py 파일에 retry 함수 추가. "
        "입력: query str, 출력: dict. "
        "테스트: pytest tests/test_amp.py"
    )
    r = sf._intent_gate(item("coding", desc))
    assert r["action"] == "proceed"
    assert r["missing_required"] == []


def test_07_coding_module_keyword_satisfies_target(sf):
    """[정탐] 'module' 키워드로 target-files 충족 후 전체 스펙 있으면 proceed"""
    desc = "registry_client module 수정. 입력: agent_id str, 출력: bool. 테스트: acceptance test 포함"
    r = sf._intent_gate(item("coding", desc))
    assert "target-files-or-modules" not in r["missing_required"]


# ── [정탐] analysis → proceed (스펙 없어도 OK) ───────────────

def test_08_analysis_no_spec_proceed(sf):
    """[정탐] analysis 요청은 spec 없어도 proceed"""
    r = sf._intent_gate(item("analysis", "현재 시장 동향 분석해줘"))
    assert r["action"] == "proceed"
    assert r["missing_required"] == []


def test_09_analysis_brief_description_proceed(sf):
    """[정탐] analysis + 짧은 설명도 proceed"""
    r = sf._intent_gate(item("analysis", "전략 분석"))
    assert r["action"] == "proceed"


# ── [정탐] 빈 요청 → clarify ─────────────────────────────────

def test_10_empty_request_coding_clarify(sf):
    """[정탐] 공백만 있는 coding 요청 → clarify"""
    r = sf._intent_gate(item("coding", "   "))
    assert r["action"] == "clarify"


# ── [정탐] 모호한 coding 요청 → clarify ─────────────────────

def test_11_ambiguous_alase_with_full_spec_still_clarify(sf):
    """[정탐] '알아서' 포함 → ambiguous=True, clarify
    스펙이 충분해도 모호성 신호가 있으면 clarify 반환"""
    desc = (
        "src/rolemesh/amp_caller.py 파일. "
        "입력: str, 출력: dict. 테스트: pytest. "
        "알아서 잘 해줘"
    )
    r = sf._intent_gate(item("coding", desc))
    assert r["action"] == "clarify"
    assert r["ambiguous"] is True


def test_12_ambiguous_jeokdanghi_clarify(sf):
    """[정탐] '적당히' 포함 analysis → clarify (ambiguity 신호는 kind 무관하게 적용)"""
    r = sf._intent_gate(item("analysis", "적당히 분석해줘"))
    assert r["action"] == "clarify"
    assert r["ambiguous"] is True


# ── [정탐] coordination → proceed (spec 검사 없음) ────────────

def test_13_coordination_proceed(sf):
    """[정탐] coordination 타입은 spec 검사 없이 proceed"""
    r = sf._intent_gate(item("coordination", "결과 통합 및 보고"))
    assert r["action"] == "proceed"
    assert r["missing_required"] == []


# ── [오탐 주의] 경계 케이스 ──────────────────────────────────

def test_14_false_positive_api_word_satisfies_io_spec(sf):
    """[오탐 주의] 'api' 단어 하나만으로 io-spec 충족 처리됨
    실제로 IO 설명이 없어도 'api' 문자열 포함이면 io-spec을 충족으로 간주.
    현재 로직 허용 범위: 의도적 설계이나 스펙 부재 오탐 가능성 있음."""
    desc = "src/rolemesh/amp_caller.py 파일. api 관련 작업. 테스트: pytest"
    r = sf._intent_gate(item("coding", desc))
    # 'api'가 io-spec 키워드로 인정 → io-spec 충족
    assert "io-spec" not in r["missing_required"]
    # [오탐 위험] 실제 IO 명세 없이 단어만 존재하는 케이스


def test_15_false_negative_test_dotpy_satisfies_target_files(sf):
    """[미탐 주의] 테스트 경로의 '.py'가 target-files 충족으로 인정됨
    구현 타겟 파일이 아닌 테스트 파일의 .py 확장자로 target-files-or-modules 충족.
    현재 로직 허용 범위: 단순 문자열 검색이므로 미탐 발생 가능."""
    desc = "버그 수정. 입력: id int, 출력: bool. 테스트: pytest tests/test_registry.py"
    r = sf._intent_gate(item("coding", desc))
    # '.py'가 target-files 키워드로 인정 → target 충족 → proceed
    assert "target-files-or-modules" not in r["missing_required"]
    # [미탐 위험] 구현 대상 파일 미지정 상태에서 proceed 반환
    assert r["action"] == "proceed"
