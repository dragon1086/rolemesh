from __future__ import annotations

import pytest

from rolemesh.core.contracts import Contract, build_contract


def test_build_contract_trims_and_filters_text_fields():
    contract = build_contract(
        title="  배치 처리 개선  ",
        goal="  실패 재시도 추가 ",
        acceptance=[" 성공 ", " ", "\t", "로그 기록"],
        deliverables=[" 코드 변경 ", "", "테스트 결과 "],
        owner="  Builder ",
    )

    assert contract.title == "배치 처리 개선"
    assert contract.goal == "실패 재시도 추가"
    assert contract.owner == "Builder"
    assert contract.acceptance == ["성공", "로그 기록"]
    assert contract.deliverables == ["코드 변경", "테스트 결과"]


def test_build_contract_rejects_empty_acceptance():
    with pytest.raises(ValueError, match="acceptance"):
        build_contract(
            title="제목",
            goal="목표",
            acceptance=[" ", ""],
            deliverables=["문서"],
            owner="PM",
        )


def test_contract_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="timeout_sec"):
        Contract(
            contract_id="cid",
            session_id="sid",
            title="title",
            goal="goal",
            scope=["scope"],
            out_of_scope=["out"],
            acceptance=["accept"],
            deliverables=["deliverable"],
            timeout_sec=0,
            owner="owner",
            created_at=0,
        )
