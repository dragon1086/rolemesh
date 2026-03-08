from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
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

    def __post_init__(self) -> None:
        self.contract_id = _require_text("contract_id", self.contract_id)
        self.session_id = _require_text("session_id", self.session_id)
        self.title = _require_text("title", self.title)
        self.goal = _require_text("goal", self.goal)
        self.owner = _require_text("owner", self.owner)
        self.scope = _normalize_text_list("scope", self.scope, min_items=1)
        self.out_of_scope = _normalize_text_list("out_of_scope", self.out_of_scope, min_items=1)
        self.acceptance = _normalize_text_list("acceptance", self.acceptance, min_items=1)
        self.deliverables = _normalize_text_list("deliverables", self.deliverables, min_items=1)

        if not isinstance(self.timeout_sec, int) or self.timeout_sec <= 0:
            raise ValueError("timeout_sec must be a positive integer")
        if not isinstance(self.created_at, int) or self.created_at < 0:
            raise ValueError("created_at must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_text(name: str, value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{name} must be a non-empty string")
    return text


def _normalize_text_list(name: str, values: list[str], *, min_items: int = 0) -> list[str]:
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if len(normalized) < min_items:
        raise ValueError(f"{name} must contain at least {min_items} item(s)")
    return normalized


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
        title=_require_text("title", title),
        goal=_require_text("goal", goal),
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
        acceptance=_normalize_text_list("acceptance", acceptance, min_items=1),
        deliverables=_normalize_text_list("deliverables", deliverables, min_items=1),
        timeout_sec=timeout_sec,
        owner=_require_text("owner", owner),
        created_at=int(time.time()),
    )
