"""
Symphony × MACRS Fusion Orchestrator

목표:
- MACRS(능력 레지스트리 + 라우팅) 위에 Symphony 스타일 'work-unit 실행' 계층 추가
- 각 작업을 isolated run으로 분해/배정하고, 증빙을 수집
- 현재 환경(록이/amp/cokac)에서 즉시 실행 가능한 최소 구현

핵심 원칙:
1) PM(록이)는 work를 분해/배정한다.
2) analysis는 amp로, coding은 cokac으로, memory/coordination은 roki가 처리한다.
3) 실행 결과는 proof(요약/근거/duration)를 남긴다.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any

from registry_client import RegistryClient
from amp_caller import ask_amp


@dataclass
class WorkItem:
    id: str
    title: str
    description: str
    kind: str  # analysis | coding | coordination | mixed
    priority: str = "normal"


@dataclass
class WorkResult:
    work_id: str
    assignee: str
    status: str
    summary: str
    proof: dict[str, Any]
    duration_ms: int


class SymphonyMACRS:
    def __init__(self, registry: RegistryClient | None = None):
        self.registry = registry or RegistryClient()

    def classify(self, text: str) -> str:
        t = text.lower()
        # analysis 키워드는 coding보다 우선순위 높음
        analysis_kw = ["분석", "검토", "판단", "비교", "전략", "리스크", "전망", "의사결정",
                       "should", "vs", "어떻게", "어떤", "어느쪽", "해야할", "차세대", "방향"]
        # coding은 구체적 구현/파일 작업만 해당
        coding_kw = ["코드", "구현", "버그", "리팩토", "테스트", "fix", "build", "deploy",
                     "refactor", "함수", "파일 수정", "클래스", "컴포넌트", "프로젝트 파일"]

        has_analysis = any(k in t for k in analysis_kw)
        has_coding = any(k in t for k in coding_kw)

        # analysis 신호가 있으면 coding과 함께여도 analysis 또는 mixed (analysis 먼저)
        if has_analysis and has_coding:
            return "mixed"  # 둘 다: 분석 먼저, 그 결과로 coding spec 확정
        if has_coding:
            return "coding"
        if has_analysis:
            return "analysis"
        return "coordination"

    def decompose(self, goal: str) -> list[WorkItem]:
        kind = self.classify(goal)
        wid = lambda p: f"{p}-{uuid.uuid4().hex[:8]}"

        if kind == "mixed":
            return [
                WorkItem(wid("analysis"), "요구사항/리스크 분석", goal, "analysis", "high"),
                WorkItem(wid("coding"), "구현", goal, "coding", "high"),
                WorkItem(wid("coord"), "통합/검증", "analysis + coding 결과 통합 검증", "coordination", "normal"),
            ]
        return [WorkItem(wid(kind), "작업 실행", goal, kind, "normal")]

    def route(self, item: WorkItem) -> str:
        # 고정 정책 + registry lookup 하이브리드
        if item.kind == "analysis":
            return "amp"
        if item.kind == "coding":
            return "cokac"
        return "roki"

    def _delegate_to_cokac(self, item: WorkItem) -> tuple[str, dict[str, Any]]:
        """cokac-bot에게 위임 (Obsidian comms 스크립트 사용)."""
        script = os.path.expanduser("~/.claude/scripts/claude-comms/send-message.sh")

        # 중복 방지: RoleMesh Builder 요청이 이미 inbox에 있으면 추가 발송 생략
        try:
            inbox_dir = os.path.expanduser("~/obsidian-vault/.claude-comms/cokac-bot/inbox")
            if "RoleMesh Builder 실행안" in item.title and os.path.isdir(inbox_dir):
                pending = [p for p in os.listdir(inbox_dir) if p.endswith('.md')]
                if pending:
                    return "delegated", {
                        "dedup": True,
                        "reason": "pending cokac inbox exists",
                        "pending_count": len(pending),
                    }
        except Exception:
            pass

        msg = (
            f"[Symphony-MACRS WorkItem]\n"
            f"id: {item.id}\n"
            f"title: {item.title}\n"
            f"priority: {item.priority}\n"
            f"description:\n{item.description}\n\n"
            f"요청: 구현 완료 후 proof(변경파일/테스트결과/커밋) 포함 회신"
        )

        if os.path.exists(script):
            cp = subprocess.run(
                ["bash", script, "openclaw-bot", "cokac-bot", "normal", msg],
                capture_output=True,
                text=True,
            )
            ok = cp.returncode == 0
            return (
                "delegated" if ok else "failed",
                {"script": script, "returncode": cp.returncode, "stdout": cp.stdout[-400:], "stderr": cp.stderr[-400:]},
            )

        # fallback: registry message bus
        msg_id = self.registry.send_message(
            from_agent="roki",
            to_agent="cokac",
            content={"work_item": asdict(item), "request": "implement_and_reply_with_proof"},
        )
        return "delegated", {"channel": "registry_messages", "message_id": msg_id}

    def execute(self, item: WorkItem) -> WorkResult:
        start = time.time()
        assignee = self.route(item)

        if assignee == "amp":
            try:
                # practical mode: 속도 우선(90s), 실패 시 quick_answer fallback
                out = ask_amp(item.description, force_tool="analyze", timeout=90)
                summary = out.get("answer", "")[:700]
                proof = {
                    "tool": "analyze",
                    "cser": out.get("cser"),
                    "persona_domain": out.get("persona_domain"),
                    "conflicts_count": len(out.get("conflicts", []) if isinstance(out.get("conflicts"), list) else []),
                }
                status = "done"
            except Exception as e:
                try:
                    out = ask_amp(item.description, force_tool="quick_answer", timeout=40)
                    summary = out.get("answer", "")[:700]
                    proof = {"tool": "quick_answer_fallback", "fallback_reason": str(e)}
                    status = "done"
                except Exception as e2:
                    summary = f"amp 호출 실패: {e2}"
                    proof = {"error": str(e2), "initial_error": str(e)}
                    status = "failed"

        elif assignee == "cokac":
            status, proof = self._delegate_to_cokac(item)
            summary = "cokac-bot에 구현 위임 완료" if status == "delegated" else "cokac 위임 실패"

        else:
            # coordination/ops는 roki가 처리
            summary = "조정 작업: 하위 결과를 수집/검증 후 사용자에 보고"
            proof = {"note": "manual_orchestrator_step"}
            status = "done"

        dur = int((time.time() - start) * 1000)
        return WorkResult(
            work_id=item.id,
            assignee=assignee,
            status=status,
            summary=summary,
            proof=proof,
            duration_ms=dur,
        )

    def run_goal(self, goal: str) -> dict[str, Any]:
        items = self.decompose(goal)
        results = [self.execute(i) for i in items]

        return {
            "goal": goal,
            "items": [asdict(i) for i in items],
            "results": [asdict(r) for r in results],
            "created_at": int(time.time()),
        }


def main():
    import argparse

    p = argparse.ArgumentParser(description="Symphony×MACRS orchestrator")
    p.add_argument("goal", help="작업 목표 텍스트")
    p.add_argument("--json", action="store_true", help="JSON 출력")
    args = p.parse_args()

    orch = SymphonyMACRS()
    out = orch.run_goal(args.goal)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"🎼 Goal: {out['goal']}")
        for r in out["results"]:
            print(f"- [{r['status']}] {r['assignee']} :: {r['summary']} ({r['duration_ms']}ms)")


if __name__ == "__main__":
    main()
