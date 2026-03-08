"""
registry_client.py — MACRS 공유 라이브러리
Multi-Agent Capability Registry System

모든 AI 에이전트가 이 모듈을 import해서 registry.db와 통신한다.
의존성: Python 표준 라이브러리 (sqlite3, json, uuid, time) + httpx (LLM 라우팅)

사용 예시:
    from registry_client import RegistryClient
    c = RegistryClient()
    c.register_agent("amp", "amp 분석봇", endpoint="http://localhost:3010")
    c.register_capability("amp", "emergent_analysis", keywords=["분석","검토"])
    results = c.lookup("이 전략 분석해줘")
    # results[0].routing_explanation → 선택 이유
    # results[0].routing_id → 피드백 참조용 ID
    c.routing_feedback(results[0].routing_id, was_correct=True)
"""

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .init_db import get_shared_connection, release_shared_connection

DEFAULT_DB_PATH = os.path.expanduser("~/ai-comms/registry.db")
ROUTING_LOG_PATH = os.path.expanduser("~/ai-comms/routing_log.jsonl")
DEFAULT_DLQ_MAX_ITEMS = 500
logger = logging.getLogger(__name__)


def _get_openai_api_key() -> str | None:
    """~/.zshrc 또는 환경변수에서 OPENAI_API_KEY 읽기"""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    zshrc_path = os.path.expanduser("~/.zshrc")
    try:
        with open(zshrc_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export OPENAI_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        return key
    except Exception:
        pass
    return None




def _hydrate_retry_description(description: str) -> str:
    """재시도 태스크에서 원본 payload를 잃지 않도록 msg-id 기준으로 설명 보강."""
    desc = (description or "").strip()
    m = re.search(r"(msg-\d{8}-\d{6})", desc)
    if not m:
        return desc
    msg_id = m.group(1)

    candidates = [
        f"/Users/rocky/obsidian-vault/.claude-comms/openclaw-bot/inbox/{msg_id}.md",
        f"/Users/rocky/obsidian-vault/.claude-comms/cokac-bot/inbox/{msg_id}.md",
    ]

    # session log fallback: msg-...-YYYYMMDDHHMM.log
    log_dir = "/Users/rocky/obsidian-vault/.claude-comms/shared/session-logs"
    try:
        if os.path.isdir(log_dir):
            for name in sorted(os.listdir(log_dir), reverse=True):
                if name.startswith(msg_id + "-") and name.endswith('.log'):
                    candidates.append(os.path.join(log_dir, name))
                    break
    except Exception:
        pass

    for c in candidates:
        try:
            if os.path.exists(c):
                txt = Path(c).read_text(encoding='utf-8', errors='ignore')
                txt = txt.strip()
                if txt:
                    snippet = txt[:1600]
                    return desc + "\n\n[auto-hydrated payload source: " + c + "]\n" + snippet
        except Exception:
            continue
    return desc

def _normalize_task_title(title: str) -> str:
    t = (title or "").strip().lower()
    # [RB12], [R3] 같은 라운드 prefix 제거
    t = re.sub(r"^\[(rb|r)\d+\]\s*", "", t)
    t = re.sub(r"\s+", " ", t)
    return t



@dataclass
class AgentMatch:
    """lookup() 결과: 매칭된 에이전트 + 능력 + 점수"""
    agent_id: str
    capability: str
    description: str
    endpoint: str | None
    score: float          # 0.0~1.0 (LLM 또는 키워드 매칭 + 실적 가중)
    cost_level: str
    routing_explanation: str = ""   # 라우팅 선택 이유 (투명성)
    routing_id: str = ""            # 피드백 참조용 ID


@dataclass
class Message:
    """메시지 큐 항목"""
    id: str
    from_agent: str
    to_agent: str
    content: dict
    status: str
    created_at: int


class RegistryClient:
    """
    MACRS 레지스트리 클라이언트.
    - 에이전트 등록/조회
    - 능력 선언
    - 태스크 라우팅 (LLM 의미 기반, 폴백: 키워드 매칭)
    - 라우팅 로깅 (~/ai-comms/routing_log.jsonl)
    - 피드백 루프 (routing_feedback, weekly_stats)
    - 메시지 버스 (Obsidian 파일 IPC 대체)
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._conn = get_shared_connection(db_path)
        self._openai_api_key = _get_openai_api_key()
        self._dlq_max_items = DEFAULT_DLQ_MAX_ITEMS

    def _conn_ctx(self) -> sqlite3.Connection:
        """연결이 살아있는지 확인 후 반환"""
        try:
            if self._conn is None:
                raise sqlite3.ProgrammingError("connection is closed")
            self._conn.execute("SELECT 1")
        except sqlite3.Error:
            logger.debug("Reopening shared registry DB connection for %s", self.db_path)
            self._conn = get_shared_connection(self.db_path)
        return self._conn

    # ── 에이전트 관리 ────────────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        display_name: str,
        description: str = "",
        endpoint: str = "",
    ) -> None:
        """에이전트 등록 (이미 있으면 업데이트)"""
        conn = self._conn_ctx()
        conn.execute("""
            INSERT INTO agents (agent_id, display_name, description, endpoint, last_heartbeat, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            ON CONFLICT(agent_id) DO UPDATE SET
                display_name   = excluded.display_name,
                description    = excluded.description,
                endpoint       = excluded.endpoint,
                last_heartbeat = excluded.last_heartbeat,
                status         = 'active'
        """, (agent_id, display_name, description, endpoint, int(time.time())))
        conn.commit()
        logger.info("registry agent registered: %s", agent_id)

    def heartbeat(self, agent_id: str) -> None:
        """에이전트 생존 신호 (1분마다 호출 권장)"""
        conn = self._conn_ctx()
        conn.execute(
            "UPDATE agents SET last_heartbeat = ?, status = 'active' WHERE agent_id = ?",
            (int(time.time()), agent_id)
        )
        conn.commit()

    def mark_offline(self, agent_id: str) -> None:
        """에이전트 오프라인 표시"""
        conn = self._conn_ctx()
        conn.execute(
            "UPDATE agents SET status = 'offline' WHERE agent_id = ?",
            (agent_id,)
        )
        conn.commit()

    def list_agents(self, active_only: bool = True) -> list[dict]:
        """등록된 에이전트 목록 반환"""
        conn = self._conn_ctx()
        if active_only:
            rows = conn.execute(
                "SELECT * FROM agents WHERE status = 'active'"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM agents").fetchall()
        return [dict(r) for r in rows]

    # ── 능력 선언 ────────────────────────────────────────────────

    def register_capability(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        keywords: list[str] | None = None,
        cost_level: str = "medium",
        avg_latency_ms: int = 0,
    ) -> None:
        """에이전트의 능력 등록 (이미 있으면 업데이트)"""
        keywords_json = json.dumps(keywords or [], ensure_ascii=False)
        conn = self._conn_ctx()
        conn.execute(
            "DELETE FROM capabilities WHERE agent_id = ? AND name = ?",
            (agent_id, name)
        )
        conn.execute("""
            INSERT INTO capabilities (agent_id, name, description, keywords, cost_level, avg_latency_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (agent_id, name, description, keywords_json, cost_level, avg_latency_ms))
        conn.commit()
        logger.info("registry capability registered: %s -> %s", agent_id, name)

    # ── LLM 라우팅 (내부) ────────────────────────────────────────

    def _llm_route(
        self, task_text: str, caps: list[dict]
    ) -> tuple[str | None, str | None, str]:
        """GPT-4o-mini로 태스크 라우팅.

        Returns:
            (agent_id, capability, explanation)
            agent_id가 None이면 매칭 없음 또는 LLM 오류.
        """
        if not self._openai_api_key:
            return None, None, "OPENAI_API_KEY 없음 — 키워드 폴백 사용"

        try:
            import httpx
        except ImportError:
            return None, None, "httpx 미설치 — 키워드 폴백 사용"

        caps_lines = []
        valid_choices = []
        for c in caps:
            kw = json.loads(c.get("keywords") or "[]")
            caps_lines.append(
                f'- {c["agent_id"]}.{c["name"]}: {c.get("description", "")} '
                f'(키워드: {", ".join(kw)})'
            )
            valid_choices.append(f'{c["agent_id"]}.{c["name"]}')

        caps_text = "\n".join(caps_lines)
        valid_str = ", ".join(valid_choices)

        user_prompt = (
            f"다음 AI 에이전트 능력 목록에서 태스크에 가장 적합한 에이전트를 선택하세요.\n\n"
            f"능력 목록:\n{caps_text}\n\n"
            f"태스크: {task_text}\n\n"
            f"JSON으로만 응답하세요:\n"
            f'{{"agent_id": "agent_id 또는 none", "capability": "capability 또는 none", '
            f'"confidence": 0.0~1.0 사이 숫자, "explanation": "선택 이유 1-2문장"}}\n\n'
            f'적합한 능력이 없으면 agent_id를 "none"으로 반환하세요. '
            f"유효한 선택: {valid_str}"
        )

        payload = {
            "model": "gpt-5.4",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "당신은 AI 에이전트 라우팅 전문가입니다. "
                        "태스크를 분석하고 가장 적합한 에이전트를 JSON으로 선택합니다."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._openai_api_key}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            result = json.loads(content)

            agent_id = result.get("agent_id", "none")
            capability = result.get("capability", "none")
            confidence = float(result.get("confidence", 0.0))
            explanation = result.get("explanation", "")

            if agent_id == "none" or confidence < 0.3:
                return None, None, explanation or "LLM: 적합한 에이전트 없음"

            # 유효성 검사
            if f"{agent_id}.{capability}" not in valid_choices:
                return None, None, f"LLM 유효하지 않은 선택: {agent_id}.{capability}"

            return agent_id, capability, explanation

        except Exception as e:
            return None, None, f"LLM 오류: {e}"

    def _log_routing(
        self,
        routing_id: str,
        task_text: str,
        chosen_agent: str,
        chosen_capability: str,
        explanation: str,
        score: float,
        routing_method: str,
    ) -> None:
        """라우팅 결정을 routing_log.jsonl 및 DB에 기록"""
        entry = {
            "routing_id": routing_id,
            "timestamp": int(time.time()),
            "task_text": task_text,
            "chosen_agent": chosen_agent,
            "chosen_capability": chosen_capability,
            "explanation": explanation,
            "score": score,
            "routing_method": routing_method,
        }

        # JSONL 파일 기록
        try:
            with open(ROUTING_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("routing_log file write failed")

        # DB 기록
        try:
            conn = self._conn_ctx()
            conn.execute("""
                INSERT INTO routing_log
                    (id, timestamp, task_text, chosen_agent, chosen_capability,
                     explanation, score, routing_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                routing_id, entry["timestamp"], task_text, chosen_agent,
                chosen_capability, explanation, score, routing_method,
            ))
            conn.commit()
        except Exception:
            logger.exception("routing_log DB write failed")

    # ── 태스크 라우팅 ────────────────────────────────────────────

    def lookup(self, task_text: str, top_k: int = 3) -> list[AgentMatch]:
        """
        태스크 텍스트에 맞는 에이전트+능력 반환 (LLM 의미 기반, 폴백: 키워드 매칭).

        LLM 라우팅 (OPENAI_API_KEY 필요):
          - GPT-4o-mini로 태스크 의미 분석 후 최적 에이전트 선택
          - API 키 없거나 호출 실패 시 키워드 매칭 폴백

        키워드 폴백 점수:
          - 키워드 매칭: 매칭 수 / 전체 키워드 수 × 0.7
          - 실적 가중치: 성공률 × 0.3
          - 오프라인 에이전트 제외

        반환값에 routing_explanation (선택 이유), routing_id (피드백 참조) 포함.
        """
        conn = self._conn_ctx()
        task_lower = task_text.lower()
        routing_id = str(uuid.uuid4())

        # 활성 에이전트의 모든 능력
        rows = conn.execute("""
            SELECT c.*, a.endpoint, a.status
            FROM capabilities c
            JOIN agents a ON c.agent_id = a.agent_id
            WHERE a.status = 'active'
        """).fetchall()

        if not rows:
            return []

        caps = [dict(r) for r in rows]
        matches: list[AgentMatch] = []
        routing_method = "keyword_fallback"

        # ── 1. LLM 라우팅 시도 ──
        llm_agent_id, llm_capability, llm_explanation = self._llm_route(task_text, caps)

        if llm_agent_id and llm_capability:
            routing_method = "llm"

            # LLM이 선택한 캐퍼빌리티 찾기
            for cap in caps:
                if cap["agent_id"] == llm_agent_id and cap["name"] == llm_capability:
                    perf_row = conn.execute("""
                        SELECT AVG(success) as success_rate
                        FROM performance
                        WHERE agent_id = ? AND capability = ?
                        ORDER BY created_at DESC LIMIT 50
                    """, (llm_agent_id, llm_capability)).fetchone()
                    success_rate = perf_row["success_rate"] if perf_row["success_rate"] else 0.8
                    score = round(0.7 + success_rate * 0.3, 3)  # LLM 기본 점수 0.7

                    matches.append(AgentMatch(
                        agent_id=llm_agent_id,
                        capability=llm_capability,
                        description=cap.get("description") or "",
                        endpoint=cap.get("endpoint"),
                        score=score,
                        cost_level=cap.get("cost_level", "medium"),
                        routing_explanation=llm_explanation,
                        routing_id=routing_id,
                    ))
                    break

            # 나머지 슬롯은 키워드 매칭으로 채우기 (LLM 선택 제외)
            for cap in caps:
                if len(matches) >= top_k:
                    break
                if cap["agent_id"] == llm_agent_id and cap["name"] == llm_capability:
                    continue
                keywords = json.loads(cap.get("keywords") or "[]")
                if not keywords:
                    continue
                matched = sum(1 for kw in keywords if kw.lower() in task_lower)
                if matched == 0:
                    continue
                perf_row = conn.execute("""
                    SELECT AVG(success) as success_rate
                    FROM performance
                    WHERE agent_id = ? AND capability = ?
                    ORDER BY created_at DESC LIMIT 50
                """, (cap["agent_id"], cap["name"])).fetchone()
                success_rate = perf_row["success_rate"] if perf_row["success_rate"] else 0.8
                score = round((matched / len(keywords)) * 0.7 + success_rate * 0.3, 3)
                matches.append(AgentMatch(
                    agent_id=cap["agent_id"],
                    capability=cap["name"],
                    description=cap.get("description") or "",
                    endpoint=cap.get("endpoint"),
                    score=score,
                    cost_level=cap.get("cost_level", "medium"),
                    routing_explanation=f"키워드 매칭 (보조): {matched}/{len(keywords)}개 일치",
                    routing_id=routing_id,
                ))

            matches.sort(key=lambda x: x.score, reverse=True)

            # 로깅
            top = matches[0] if matches else None
            self._log_routing(
                routing_id, task_text,
                top.agent_id if top else "none",
                top.capability if top else "none",
                top.routing_explanation if top else llm_explanation,
                top.score if top else 0.0,
                routing_method,
            )
            return matches[:top_k]

        # ── 2. 키워드 폴백 ──
        for cap in caps:
            keywords = json.loads(cap.get("keywords") or "[]")
            if not keywords:
                continue
            matched = sum(1 for kw in keywords if kw.lower() in task_lower)
            if matched == 0:
                continue
            perf_row = conn.execute("""
                SELECT AVG(success) as success_rate
                FROM performance
                WHERE agent_id = ? AND capability = ?
                ORDER BY created_at DESC LIMIT 50
            """, (cap["agent_id"], cap["name"])).fetchone()
            success_rate = perf_row["success_rate"] if perf_row["success_rate"] else 0.8
            score = round((matched / len(keywords)) * 0.7 + success_rate * 0.3, 3)

            # 폴백 이유 구성
            reason_suffix = f"{matched}/{len(keywords)}개 키워드 일치"
            if llm_explanation and "OPENAI_API_KEY" not in llm_explanation:
                explanation = f"LLM 폴백 ({llm_explanation}) | {reason_suffix}"
            else:
                explanation = f"키워드 매칭: {reason_suffix}"

            matches.append(AgentMatch(
                agent_id=cap["agent_id"],
                capability=cap["name"],
                description=cap.get("description") or "",
                endpoint=cap.get("endpoint"),
                score=score,
                cost_level=cap.get("cost_level", "medium"),
                routing_explanation=explanation,
                routing_id=routing_id,
            ))

        matches.sort(key=lambda x: x.score, reverse=True)
        result = matches[:top_k]

        # 로깅
        if result:
            self._log_routing(
                routing_id, task_text,
                result[0].agent_id, result[0].capability,
                result[0].routing_explanation, result[0].score, routing_method,
            )
        else:
            self._log_routing(routing_id, task_text, "none", "none", "매칭 없음", 0.0, routing_method)

        return result

    def get_stats(self, agent_id: str, capability: str) -> dict:
        """특정 에이전트+능력의 실적 통계"""
        conn = self._conn_ctx()
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                AVG(success) as success_rate,
                AVG(duration_ms) as avg_duration_ms
            FROM performance
            WHERE agent_id = ? AND capability = ?
        """, (agent_id, capability)).fetchone()
        if not row:
            return {"total": 0, "success_rate": 0.0, "avg_duration_ms": 0}
        return {
            "total": row["total"],
            "success_rate": round(row["success_rate"] or 0.0, 3),
            "avg_duration_ms": round(row["avg_duration_ms"] or 0.0, 1),
        }

    # ── 실적 기록 ────────────────────────────────────────────────

    def record_outcome(
        self,
        agent_id: str,
        capability: str,
        success: bool,
        duration_ms: int = 0,
        task_hash: str = "",
    ) -> None:
        """태스크 결과 기록 (라우팅 품질 향상에 사용)"""
        conn = self._conn_ctx()
        conn.execute("""
            INSERT INTO performance (agent_id, capability, task_hash, success, duration_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (agent_id, capability, task_hash, 1 if success else 0, duration_ms))
        conn.commit()

    # ── 피드백 루프 ──────────────────────────────────────────────

    def routing_feedback(
        self,
        routing_id: str,
        was_correct: bool,
        actual_agent: str = "",
    ) -> None:
        """라우팅 결정에 대한 피드백 기록.

        Args:
            routing_id:  lookup() 결과의 AgentMatch.routing_id
            was_correct: 라우팅이 올바랐는지 (True/False)
            actual_agent: 실제 사용된 에이전트 (틀렸을 때 기록)
        """
        conn = self._conn_ctx()
        feedback_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO routing_feedback (id, routing_id, was_correct, actual_agent, feedback_at)
            VALUES (?, ?, ?, ?, ?)
        """, (feedback_id, routing_id, 1 if was_correct else 0, actual_agent, int(time.time())))
        conn.commit()

    def weekly_stats(self) -> dict:
        """주간 라우팅 정확도 및 에이전트별 성공률 반환.

        Returns:
            {
                "period": "7d",
                "routing_accuracy": float,          # 라우팅 정확도 (0.0~1.0)
                "total_feedback": int,              # 피드백 수
                "agent_success_rates": [...],       # 에이전트별 성공률
                "routing_methods": {...},           # LLM vs 키워드 사용 비율
            }
        """
        one_week_ago = int(time.time()) - 7 * 24 * 3600
        conn = self._conn_ctx()

        # 라우팅 정확도 (피드백 기반)
        acc_row = conn.execute("""
            SELECT COUNT(*) as total, AVG(was_correct) as accuracy
            FROM routing_feedback
            WHERE feedback_at >= ?
        """, (one_week_ago,)).fetchone()

        # 에이전트별 성공률
        agent_rows = conn.execute("""
            SELECT agent_id, COUNT(*) as total, AVG(success) as success_rate
            FROM performance
            WHERE created_at >= ?
            GROUP BY agent_id
        """, (one_week_ago,)).fetchall()

        # 라우팅 방법별 통계
        method_rows = conn.execute("""
            SELECT routing_method, COUNT(*) as cnt
            FROM routing_log
            WHERE timestamp >= ?
            GROUP BY routing_method
        """, (one_week_ago,)).fetchall()

        return {
            "period": "7d",
            "routing_accuracy": round(acc_row["accuracy"] or 0.0, 3),
            "total_feedback": acc_row["total"],
            "agent_success_rates": [
                {
                    "agent_id": r["agent_id"],
                    "total": r["total"],
                    "success_rate": round(r["success_rate"] or 0.0, 3),
                }
                for r in agent_rows
            ],
            "routing_methods": {r["routing_method"]: r["cnt"] for r in method_rows},
        }

    # ── 메시지 버스 (Obsidian 파일 IPC 대체) ─────────────────────

    def send_message(
        self,
        from_agent: str,
        to_agent: str,
        content: dict,
    ) -> str:
        """메시지 발송. 메시지 ID(UUID) 반환."""
        msg_id = str(uuid.uuid4())
        conn = self._conn_ctx()
        conn.execute("""
            INSERT INTO messages (id, from_agent, to_agent, content, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (msg_id, from_agent, to_agent, json.dumps(content, ensure_ascii=False)))
        conn.commit()
        return msg_id

    def send_message_auto(self, from_agent: str, task_text: str, content: dict | None = None) -> tuple[str, str]:
        """라우팅 lookup 기반 자동 수신자 선택 + 메시지 발송.

        Returns:
            (msg_id, chosen_agent)
        """
        matches = self.lookup(task_text, top_k=1)
        if not matches:
            raise ValueError(f"적합한 수신자를 찾지 못함: {task_text}")
        chosen = matches[0].agent_id
        payload = dict(content or {})
        payload.setdefault("task", task_text)
        payload.setdefault("routed_by", "lookup")
        payload.setdefault("capability", matches[0].capability)
        msg_id = self.send_message(from_agent=from_agent, to_agent=chosen, content=payload)
        return msg_id, chosen

    def get_pending(self, to_agent: str) -> list[Message]:
        """수신 대기 중인 메시지 목록 반환"""
        conn = self._conn_ctx()
        rows = conn.execute("""
            SELECT * FROM messages
            WHERE to_agent = ? AND status = 'pending'
            ORDER BY created_at ASC
        """, (to_agent,)).fetchall()
        return [
            Message(
                id=r["id"],
                from_agent=r["from_agent"],
                to_agent=r["to_agent"],
                content=json.loads(r["content"]),
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def claim_pending(self, to_agent: str, limit: int = 10) -> list[Message]:
        """pending 메시지를 원자적으로 processing으로 점유(claim) 후 반환."""
        conn = self._conn_ctx()
        claimed_rows = []
        with conn:
            rows = conn.execute("""
                SELECT * FROM messages
                WHERE to_agent = ? AND status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
            """, (to_agent, limit)).fetchall()

            for r in rows:
                updated = conn.execute("""
                    UPDATE messages
                    SET status = 'processing', processed_at = ?
                    WHERE id = ? AND status = 'pending'
                """, (int(time.time()), r["id"])).rowcount
                if updated:
                    claimed_rows.append(r)

        return [
            Message(
                id=r["id"],
                from_agent=r["from_agent"],
                to_agent=r["to_agent"],
                content=json.loads(r["content"]),
                status="processing",
                created_at=r["created_at"],
            )
            for r in claimed_rows
        ]

    def ack_message(self, msg_id: str, status: str = "done") -> None:
        """메시지 처리 완료/실패 표시 (status: done|failed|processing 등)."""
        conn = self._conn_ctx()
        conn.execute("""
            UPDATE messages
            SET status = ?, processed_at = ?
            WHERE id = ?
        """, (status, int(time.time()), msg_id))
        conn.commit()

    def close(self) -> None:
        """DB 연결 종료"""
        release_shared_connection(self._conn, self.db_path)
        self._conn = None

    # ── 태스크 큐 ────────────────────────────────────────────────

    def enqueue(
        self,
        title: str,
        description: str = "",
        kind: str | None = None,
        priority: int = 5,
        source: str = "manual",
    ) -> str:
        """태스크 큐에 추가. task_id(UUID) 반환.

        중복/추상 요청 방지:
        - 동일 의미 제목(normalized) + pending/running 이면 기존 task_id 반환
        - rolemesh Builder Prototype 추상 요청은 차단
        """
        conn = self._conn_ctx()
        norm_title = _normalize_task_title(title)
        desc = _hydrate_retry_description((description or "").strip())

        # 1) admission gate: 반복되는 추상 coding 요청 차단
        if source in ("rolemesh-build", "rolemesh-autoevo") and kind == "coding":
            if "builder prototype tasks" in norm_title:
                generic_markers = [
                    "실행 가능한 구현 태스크 분해",
                    "구현 태스크 분해",
                    "실행 가능한",
                ]
                is_generic = (len(desc) < 40) or any(m in desc for m in generic_markers)
                if is_generic:
                    raise ValueError("enqueue blocked: coding task spec too generic. required: (1) target files/modules (2) feature list (3) input/output spec (4) acceptance tests")

        # 2) semantic dedupe: 같은 의미 제목의 활성 태스크 재생성 방지
        rows = conn.execute(
            """
            SELECT id, title FROM task_queue
            WHERE source = ? AND status IN ('pending','running')
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (source,),
        ).fetchall()
        for r in rows:
            if _normalize_task_title(r["title"]) == norm_title:
                logger.info("queue deduped: reuse %s - %s", r["id"], title)
                return r["id"]

        task_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO task_queue (id, title, description, kind, status, priority, source, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """, (task_id, title, desc, kind, priority, source, time.time()))
        conn.commit()
        logger.info("queue enqueued: %s - %s", task_id, title)
        return task_id

    def dequeue_next(self) -> dict | None:
        """pending 중 우선순위 최고 태스크를 running으로 원자적 변경 후 반환. 없으면 None.

        run_after가 설정된 태스크는 해당 시각 이후에만 dequeue.
        """
        conn = self._conn_ctx()
        now = time.time()
        with conn:
            row = conn.execute("""
                SELECT * FROM task_queue
                WHERE status = 'pending'
                  AND (run_after IS NULL OR run_after <= ?)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            """, (now,)).fetchone()
            if row is None:
                return None
            conn.execute("""
                UPDATE task_queue
                SET status = 'running', started_at = ?
                WHERE id = ? AND status = 'pending'
            """, (time.time(), row["id"]))
        return dict(row)

    def retry_task(self, task_id: str, retry_count: int, delay_sec: int) -> None:
        """태스크를 exponential backoff 후 재시도 대기열로 복귀."""
        run_after = time.time() + delay_sec
        conn = self._conn_ctx()
        dlq_row = conn.execute(
            "SELECT * FROM dead_letter WHERE task_id = ? ORDER BY dlq_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        description = None
        if dlq_row is not None:
            description = dlq_row["description"]
        conn.execute("""
            UPDATE task_queue
            SET status = 'pending', retry_count = ?, run_after = ?,
                error = NULL, started_at = NULL, done_at = NULL,
                description = COALESCE(?, description)
            WHERE id = ?
        """, (retry_count, run_after, description, task_id))
        if dlq_row is not None:
            conn.execute("DELETE FROM dead_letter WHERE task_id = ?", (task_id,))
        conn.commit()
        logger.info("queue retry #%s in %ss: %s", retry_count, delay_sec, task_id)

    def move_to_dlq(self, task_id: str, reason: str = "") -> None:
        """retry 소진 태스크를 dead_letter 테이블로 이동."""
        conn = self._conn_ctx()
        row = conn.execute(
            "SELECT * FROM task_queue WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return
        r = dict(row)
        dlq_id = str(uuid.uuid4())
        conn.execute("""
            INSERT OR REPLACE INTO dead_letter
                (id, task_id, title, description, kind, source, priority,
                 retry_count, error, created_at, dlq_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dlq_id, task_id, r["title"], r.get("description", ""),
            r.get("kind"), r.get("source", "manual"), r.get("priority", 5),
            r.get("retry_count", 0), reason[:300], r.get("created_at"), time.time(),
        ))
        conn.execute(
            "UPDATE task_queue SET status = 'dead_letter', error = ?, done_at = ? WHERE id = ?",
            (reason[:300], time.time(), task_id),
        )
        if self._dlq_max_items > 0:
            conn.execute(
                """
                DELETE FROM dead_letter
                WHERE id IN (
                    SELECT id FROM dead_letter
                    ORDER BY dlq_at DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (self._dlq_max_items,),
            )
        conn.commit()
        logger.info("queue DLQ: %s", task_id)

    def queue_counts(self) -> dict:
        """태스크 상태별 카운트 + DLQ 카운트 반환."""
        conn = self._conn_ctx()
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM task_queue GROUP BY status"
        ).fetchall()
        counts = {r["status"]: r["cnt"] for r in rows}
        dlq_row = conn.execute("SELECT COUNT(*) as cnt FROM dead_letter").fetchone()
        counts["dlq"] = dlq_row["cnt"] if dlq_row else 0
        return counts

    def complete_task(
        self,
        task_id: str,
        summary: str = "",
        error: str | None = None,
        status: str | None = None,
    ) -> None:
        """태스크 완료(done), 실패(failed), 또는 커스텀 상태 처리."""
        if status is None:
            status = "failed" if error else "done"
        conn = self._conn_ctx()
        conn.execute("""
            UPDATE task_queue
            SET status = ?, result_summary = ?, error = ?, done_at = ?
            WHERE id = ?
        """, (status, summary, error, time.time(), task_id))
        conn.commit()
        logger.info("queue %s: %s", status, task_id)

    def list_tasks(self, status: str | None = None, limit: int = 20) -> list[dict]:
        """태스크 목록 반환. status 미지정 시 전체."""
        conn = self._conn_ctx()
        if status:
            rows = conn.execute("""
                SELECT * FROM task_queue WHERE status = ?
                ORDER BY priority DESC, created_at ASC LIMIT ?
            """, (status, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM task_queue
                ORDER BY priority DESC, created_at ASC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
