from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class Contract:
    contract_id: str
    session_id: str
    title: str
    goal: str
    scope: list[str]
    out_of_scope: list[str]
    acceptance: list[str]
    deliverables: list[str]
    timeout_sec: int
    owner: str
    created_at: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_contract(
    *,
    title: str,
    goal: str,
    acceptance: list[str],
    deliverables: list[str],
    owner: str,
    timeout_sec: int = 1800,
) -> Contract:
    cid = str(uuid.uuid4())
    sid = f"ctr-{cid[:8]}"
    return Contract(
        contract_id=cid,
        session_id=sid,
        title=title,
        goal=goal,
        scope=[
            "핵심 요구를 기능 단위로 구현",
            "실패/경계 케이스를 테스트로 검증",
            "결과를 proof 형식으로 보고",
        ],
        out_of_scope=[
            "요청되지 않은 대규모 리팩토링",
            "프로덕션 파괴적 변경",
            "근거 없는 추정 구현",
        ],
        acceptance=acceptance,
        deliverables=deliverables,
        timeout_sec=timeout_sec,
        owner=owner,
        created_at=int(time.time()),
    )
