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
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any

from .registry_client import RegistryClient
from .amp_caller import ask_amp
try:
    from .contracts import build_contract  # package import
except Exception:
    from contracts import build_contract  # script/local import fallback

PM_QUALITY_LOG = os.path.expanduser("~/ai-comms/pm_packet_quality.jsonl")
CONTRACT_ARTIFACT_DIR = os.path.expanduser("~/ai-comms/contracts")
PARALLEL_CAP = 3



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

    def _distill_core_request(self, text: str) -> str:
        """장문/군더더기 입력에서 핵심 요청만 압축."""
        raw = (text or "").strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        cleaned: list[str] = []
        for ln in lines:
            if re.match(r"^(참고|배경|맥락|context)[:：]", ln, re.IGNORECASE):
                continue
            cleaned.append(ln)
        joined = " ".join(cleaned) if cleaned else raw
        joined = re.sub(r"\s+", " ", joined).strip()
        return joined[:700]

    def _infer_focus_points(self, text: str) -> list[str]:
        """도메인 특화에 과몰입하지 않고 범용 품질 축으로 포커스 생성."""
        t = (text or "").lower()
        points: list[str] = []

        has_security = any(k in t for k in ["로그인", "인증", "auth", "oauth", "권한", "security", "보안", "개인정보", "암호"])
        has_data = any(k in t for k in ["db", "database", "schema", "데이터", "저장", "마이그레이션", "cache", "인덱스"])
        has_perf = any(k in t for k in ["성능", "latency", "throughput", "최적화", "scale", "대용량", "부하"])
        has_external = any(k in t for k in ["api", "외부", "webhook", "integration", "연동", "결제", "payment", "billing"])
        has_ui = any(k in t for k in ["ui", "ux", "화면", "폼", "dashboard", "cli", "버튼", "텔레그램"])

        if has_security:
            points.append("보안 기본값(입력검증/권한검사/민감정보 보호)과 실패 정책을 먼저 확정")
        if has_data:
            points.append("데이터 모델/상태전이/무결성 제약을 먼저 명세")
        if has_perf:
            points.append("성능 목표(SLO)와 측정 지표(p95/처리량)를 수용 기준에 포함")
        if has_external:
            points.append("외부 의존성 실패 시 재시도/백오프/멱등성(idempotency) 정책 명시")
        if has_ui:
            points.append("사용자 시나리오(성공/실패/빈상태) 기반으로 UX/출력 형식 검증")

        # 공통 기본 축
        points += [
            "핵심 요구를 기능 3~5개로 축소",
            "입출력·에러 케이스를 계약(Contract) 형태로 명세",
            "테스트 가능한 acceptance 기준을 선확정",
        ]

        # 중복 제거 + 상한
        dedup = []
        seen = set()
        for p in points:
            if p not in seen:
                dedup.append(p)
                seen.add(p)
        return dedup[:6]


    def _intent_gate(self, item: WorkItem) -> dict[str, Any]:
        """요청 의도를 정제하고 모호성/필수정보 누락을 탐지."""
        core = self._distill_core_request(item.description)
        ambiguity_signals = ["알아서", "적당히", "대충", "좋게", "실행 가능한 구현 태스크 분해"]
        ambiguous = any(sig in core for sig in ambiguity_signals)

        required_missing: list[str] = []
        if item.kind == "coding":
            low = core.lower()
            if not any(k in low for k in ["파일", "module", "모듈", ".py", "src/", "경로"]):
                required_missing.append("target-files-or-modules")
            if not any(k in low for k in ["입력", "출력", "io", "api", "함수 시그니처", "schema"]):
                required_missing.append("io-spec")
            if not any(k in low for k in ["테스트", "acceptance", "수용 기준", "완료 기준"]):
                required_missing.append("acceptance-tests")

        return {
            "core_request": core,
            "ambiguous": ambiguous,
            "missing_required": required_missing,
            "action": "clarify" if ambiguous or required_missing else "proceed",
        }

    def _write_contract_artifacts(self, contract: dict[str, Any], packet: dict[str, Any]) -> dict[str, str]:
        os.makedirs(CONTRACT_ARTIFACT_DIR, exist_ok=True)
        cid = contract["contract_id"]
        base = os.path.join(CONTRACT_ARTIFACT_DIR, cid)
        os.makedirs(base, exist_ok=True)

        manifest_path = os.path.join(base, "feature_manifest.json")
        progress_path = os.path.join(base, "handoff_progress.md")

        manifest = {
            "contract_id": cid,
            "session_id": contract.get("session_id"),
            "goal": contract.get("goal"),
            "features": [
                {"id": f"F{i+1:02d}", "description": fp, "passes": False}
                for i, fp in enumerate(packet.get("focus_points", [])[:5])
            ],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        with open(progress_path, "w", encoding="utf-8") as f:
            f.write(
                f"# Contract Handoff\n\n"
                f"- contract_id: {cid}\n"
                f"- session_id: {contract.get('session_id')}\n"
                f"- owner: {contract.get('owner')}\n"
                f"- timeout_sec: {contract.get('timeout_sec')}\n\n"
                f"## Next Steps\n"
                f"1. feature_manifest.json에서 passes=false 항목 1개씩 처리\n"
                f"2. 완료 시 proof(파일/테스트/커밋) 1회 보고\n"
            )

        return {"manifest_path": manifest_path, "progress_path": progress_path}

    def _build_contract(self, item: WorkItem) -> dict[str, Any]:
        packet = self._build_pm_packet(item)
        owner = "Builder" if item.kind == "coding" else ("Analyst" if item.kind == "analysis" else "PM")
        c = build_contract(
            title=item.title,
            goal=packet["core_request"],
            acceptance=packet["acceptance"],
            deliverables=packet["deliverables"],
            owner=owner,
            timeout_sec=2400 if item.kind == "coding" else 1200,
        )
        return c.to_dict()

    def _build_pm_packet(self, item: WorkItem) -> dict[str, Any]:
        gate = self._intent_gate(item)
        core = gate["core_request"]
        focus = self._infer_focus_points(core)
        return {
            "core_request": core,
            "intent_gate": gate,
            "deliverables": [
                "변경 파일 목록",
                "핵심 구현 요약(최대 5줄)",
                "테스트 결과(실행 명령+pass/fail)",
                "커밋 해시",
            ],
            "acceptance": [
                "요구 기능이 재현 가능한 형태로 동작",
                "실패/경계 케이스 최소 1개 이상 테스트 포함",
                "문서/README 영향 시 링크 또는 섹션 업데이트",
            ],
            "focus_points": focus,
            "execution_harness": {
                "agent": "claude-code",
                "guidance": [
                    "작업 전 구현 범위를 3~5개 체크리스트로 명시",
                    "[MANDATORY] 코딩 작업은 Superpowers 워크플로우(브레인스토밍→설계확정→작업계획→TDD→코드리뷰)를 기본 절차로 적용",
                    "Superpowers 단계 산출물(설계 요약/작업계획/테스트근거)을 완료보고에 포함",
                    "불명확 스펙은 임의 구현 대신 질문 또는 defer",
                    "완료 보고는 중복 없이 1회(요약+proof)로 전송",
                ],
            },
        }


    def _score_pm_packet(self, packet: dict[str, Any]) -> dict[str, Any]:
        core = (packet.get("core_request") or "").strip()
        acceptance = packet.get("acceptance") or []
        deliverables = packet.get("deliverables") or []
        focus = packet.get("focus_points") or []
        guidance = ((packet.get("execution_harness") or {}).get("guidance") or [])

        score = 0
        score += min(len(core) / 280.0, 1.0) * 30  # 핵심요청 밀도
        score += min(len(acceptance), 4) / 4 * 25
        score += min(len(deliverables), 4) / 4 * 20
        score += min(len(focus), 6) / 6 * 15
        score += min(len(guidance), 4) / 4 * 10

        return {
            "score": round(score, 1),
            "core_len": len(core),
            "acceptance_count": len(acceptance),
            "deliverables_count": len(deliverables),
            "focus_count": len(focus),
            "guidance_count": len(guidance),
        }

    def _log_pm_packet_quality(self, item: WorkItem, packet: dict[str, Any], assignee: str) -> None:
        metrics = self._score_pm_packet(packet)
        row = {
            "ts": int(time.time()),
            "work_id": item.id,
            "title": item.title,
            "kind": item.kind,
            "assignee": assignee,
            **metrics,
        }
        try:
            os.makedirs(os.path.dirname(PM_QUALITY_LOG), exist_ok=True)
            with open(PM_QUALITY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

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

        packet = self._build_pm_packet(item)
        gate = packet.get("intent_gate", {})
        if gate.get("action") == "clarify":
            return "failed", {"reason": "intent-gate-blocked", "missing": gate.get("missing_required", []), "ambiguous": gate.get("ambiguous")}

        contract = self._build_contract(item)
        artifacts = self._write_contract_artifacts(contract, packet)
        self._log_pm_packet_quality(item, packet, "cokac")
        msg = (
            f"[RoleMesh PM Routing Packet]\n"
            f"id: {item.id}\n"
            f"title: {item.title}\n"
            f"priority: {item.priority}\n"
            f"contract_id: {contract['contract_id']}\n"
            f"session_id: {contract['session_id']}\n"
            f"manifest: {artifacts['manifest_path']}\n"
            f"handoff: {artifacts['progress_path']}\n\n"
            f"핵심 요청(core_request):\n{packet['core_request']}\n\n"
            f"우선 검토 포인트:\n- " + "\n- ".join(packet["focus_points"]) + "\n\n"
            f"수용 기준(acceptance):\n- " + "\n- ".join(packet["acceptance"]) + "\n\n"
            f"산출물(deliverables):\n- " + "\n- ".join(packet["deliverables"]) + "\n\n"
            f"계약(Contract): owner={contract['owner']}, timeout={contract['timeout_sec']}s\n\n"
            f"실행 하네스 가이드:\n- " + "\n- ".join(packet["execution_harness"]["guidance"]) + "\n\n"
            f"원문 요청(raw):\n{item.description}\n\n"
            f"요청: 구현 완료 후 proof(변경파일/테스트결과/커밋) 포함, 중복 보고 없이 1회 회신"
        )

        if os.path.exists(script):
            cp = subprocess.run(
                ["bash", script, "openclaw-bot", "cokac-bot", "normal", msg, "required"],
                capture_output=True,
                text=True,
            )
            ok = cp.returncode == 0
            return (
                "delegated" if ok else "failed",
                {"script": script, "returncode": cp.returncode, "stdout": cp.stdout[-400:], "stderr": cp.stderr[-400:], "contract": contract, "artifacts": artifacts},
            )

        # fallback: registry message bus
        msg_id = self.registry.send_message(
            from_agent="roki",
            to_agent="cokac",
            content={
                "work_item": asdict(item),
                "pm_packet": self._build_pm_packet(item),
                "contract": self._build_contract(item),
                "request": "implement_and_reply_with_proof",
                "artifacts": artifacts,
            },
        )
        return "delegated", {"channel": "registry_messages", "message_id": msg_id}

    def execute(self, item: WorkItem) -> WorkResult:
        start = time.time()
        assignee = self.route(item)

        if assignee == "amp":
            try:
                # practical mode: 속도 우선(90s), 실패 시 quick_answer fallback
                out = ask_amp(item.description, force_tool="analyze", timeout=150)
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
                    out = ask_amp(item.description, force_tool="quick_answer", timeout=80)
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
        items = self.decompose(goal)[:PARALLEL_CAP]
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


# Naming clarity alias (non-breaking):
RoleMeshOrchestrator = SymphonyMACRS
