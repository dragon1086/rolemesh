"""
tests/test_e2e_smoke.py
E2E Smoke 테스트 — 실제 임시 SQLite DB 기반

세 시나리오:
  a) analysis 요청: IntentGate → proceed → task enqueue → done 전환
  b) coding + 스펙 충분: proceed → enqueue
  c) coding + 스펙 부재: clarify → enqueue 차단
"""
import pytest
from unittest.mock import MagicMock, patch

from rolemesh.core.registry_client import RegistryClient
from rolemesh.routing.symphony_fusion import SymphonyMACRS, WorkItem


@pytest.fixture
def tmp_client(tmp_path):
    """임시 DB를 사용하는 RegistryClient"""
    db_path = str(tmp_path / "test_registry.db")
    client = RegistryClient(db_path=db_path)
    yield client
    client.close()


@pytest.fixture
def sf(tmp_client):
    """임시 DB 기반 SymphonyMACRS"""
    return SymphonyMACRS(registry=tmp_client)


# ── 시나리오 a) analysis → proceed → enqueue → done ──────────

def test_e2e_a_analysis_proceed_enqueue_done(sf, tmp_client):
    """
    analysis 요청 전체 흐름:
    1. IntentGate → action=proceed (spec 검사 없음)
    2. task_queue enqueue → pending
    3. dequeue_next → running
    4. complete_task → done
    """
    desc = "RoleMesh 추천 엔진 현황 분석"
    work_item = WorkItem(id="e2e-a1", title="분석 태스크", description=desc, kind="analysis")

    # 1. IntentGate → proceed
    gate = sf._intent_gate(work_item)
    assert gate["action"] == "proceed", f"analysis should proceed, got: {gate}"
    assert gate["missing_required"] == []
    assert gate["ambiguous"] is False

    # 2. Enqueue → pending
    task_id = tmp_client.enqueue(
        title=work_item.title,
        description=desc,
        kind=work_item.kind,
        source="e2e-test",
    )
    counts = tmp_client.queue_counts()
    assert counts.get("pending", 0) >= 1

    # 3. Dequeue → running (dequeue_next은 UPDATE 전 row 반환이므로 DB 재조회로 확인)
    task = tmp_client.dequeue_next()
    assert task is not None
    assert task["id"] == task_id
    running_tasks = tmp_client.list_tasks(status="running")
    assert any(t["id"] == task_id for t in running_tasks)

    # 4. Complete → done
    tmp_client.complete_task(task_id, summary="분석 완료: 3가지 개선 가설 도출")
    done_tasks = tmp_client.list_tasks(status="done")
    assert any(t["id"] == task_id for t in done_tasks)

    # done 상태에서 dequeue_next는 None 반환
    assert tmp_client.dequeue_next() is None


def test_e2e_a_analysis_execute_returns_done(sf):
    """
    analysis 요청을 execute()로 직접 실행 시 status=done 반환
    (ask_amp mock)
    """
    work_item = WorkItem(
        id="e2e-a2",
        title="시장 분석",
        description="RoleMesh 사용자 pain point 분석",
        kind="analysis",
    )

    mock_amp_result = {"answer": "분석 결과: 주요 pain point 3가지", "cser": 0.9}
    with patch("rolemesh.routing.symphony_fusion.ask_amp", return_value=mock_amp_result):
        result = sf.execute(work_item)

    assert result.status == "done"
    assert result.assignee == "amp"
    assert "분석 결과" in result.summary


# ── 시나리오 b) coding + 스펙 충분 → proceed → enqueue ────────

def test_e2e_b_coding_full_spec_proceed_enqueue(sf, tmp_client):
    """
    coding + 스펙 충분:
    1. IntentGate → action=proceed
    2. enqueue 허용 → pending
    3. dequeue_next → running (task 확인)
    """
    desc = (
        "src/rolemesh/amp_caller.py 파일에 retry 함수 추가. "
        "입력: query str, max_retry int, 출력: dict. "
        "테스트: pytest tests/test_amp.py"
    )
    work_item = WorkItem(id="e2e-b1", title="코딩 태스크", description=desc, kind="coding")

    # 1. IntentGate → proceed
    gate = sf._intent_gate(work_item)
    assert gate["action"] == "proceed", f"full-spec coding should proceed, got missing: {gate['missing_required']}"
    assert gate["missing_required"] == []

    # 2. Enqueue
    task_id = tmp_client.enqueue(
        title=work_item.title,
        description=desc,
        kind=work_item.kind,
        source="e2e-test",
    )

    counts = tmp_client.queue_counts()
    assert counts.get("pending", 0) >= 1

    # 3. Dequeue → running
    task = tmp_client.dequeue_next()
    assert task is not None
    assert task["id"] == task_id


def test_e2e_b_coding_full_spec_delegate_not_blocked(sf):
    """
    coding + 스펙 충분: _delegate_to_cokac에서 intent-gate 차단 없음
    (send-message.sh 없고 registry fallback도 mocked)
    """
    desc = (
        "src/rolemesh/amp_caller.py 파일에 timeout 함수 추가. "
        "입력: seconds int, 출력: bool. "
        "테스트: pytest tests/"
    )
    work_item = WorkItem(id="e2e-b2", title="코딩-풀스펙", description=desc, kind="coding")

    with patch("rolemesh.routing.symphony_fusion.os.path.exists", return_value=False), \
         patch("rolemesh.routing.symphony_fusion.os.makedirs"), \
         patch("builtins.open", side_effect=OSError("mock")):
        # _write_contract_artifacts가 실패해도 gate 검사는 이미 통과
        packet = sf._build_pm_packet(work_item)
        gate = packet["intent_gate"]

    assert gate["action"] == "proceed"
    assert gate["missing_required"] == []


# ── 시나리오 c) coding + 스펙 부재 → clarify → enqueue 차단 ──

def test_e2e_c_coding_no_spec_clarify_blocks_delegation(sf, tmp_client):
    """
    coding + 스펙 부재:
    1. IntentGate → action=clarify
    2. _delegate_to_cokac → ("failed", {"reason": "intent-gate-blocked"})
    3. task_queue에 태스크 추가 없음 확인
    """
    work_item = WorkItem(
        id="e2e-c1",
        title="모호한 코딩 요청",
        description="뭔가 코딩해줘",
        kind="coding",
    )

    # 1. IntentGate → clarify
    gate = sf._intent_gate(work_item)
    assert gate["action"] == "clarify"
    assert len(gate["missing_required"]) > 0

    # 2. _delegate_to_cokac → failed (gate가 내부에서 차단)
    status, proof = sf._delegate_to_cokac(work_item)
    assert status == "failed"
    assert proof.get("reason") == "intent-gate-blocked"
    assert len(proof.get("missing", [])) > 0

    # 3. Queue 비어 있음 (clarify path에서 enqueue 없음)
    counts = tmp_client.queue_counts()
    assert counts.get("pending", 0) == 0


def test_e2e_c_coding_no_spec_execute_returns_failed(sf):
    """
    coding + 스펙 부재: execute() 호출 시 status=failed 반환
    """
    work_item = WorkItem(
        id="e2e-c2",
        title="모호 요청",
        description="뭔가 만들어줘",
        kind="coding",
    )

    result = sf.execute(work_item)
    assert result.status == "failed"
    assert result.assignee == "cokac"


def test_e2e_c_clarify_does_not_enqueue_on_run_goal(sf, tmp_client):
    """
    run_goal()에서 coding + 스펙 부재 처리 시 WorkResult status=failed 반환
    (task_queue는 run_goal에서 직접 사용하지 않음; intent-gate 차단 확인)
    """
    result = sf.run_goal("버그 수정해줘")
    # classify("버그 수정해줘") → "coding"
    # coding 아이템의 결과가 failed이어야 함
    failed = [r for r in result["results"] if r["status"] == "failed"]
    assert len(failed) >= 1
    assert any("cokac" == r["assignee"] for r in failed)
