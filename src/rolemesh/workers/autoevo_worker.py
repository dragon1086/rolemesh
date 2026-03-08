"""
rolemesh_autoevo_worker.py
- RoleMesh 자율진화 루프 유지 워커
- rolemesh-autoevo 소스의 pending/running 태스크가 비면 다음 라운드 자동 enqueue
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
import time

from ..core.registry_client import RegistryClient

# RoleMesh Throttle guard (graceful degradation if unavailable)
try:
    from ..adapters.throttle import TokenBucketThrottle as _Throttle
    _autoevo_throttle = _Throttle()
    _AUTOEVO_THROTTLE = True
except Exception:
    _AUTOEVO_THROTTLE = False

PID_FILE = "/tmp/rolemesh-autoevo-worker.pid"
TOPIC = "요즘 오픈클로나 별에 별 AI가 나와서 뭘써야할지 모르겠어서 많이 받아놨어. 진짜 쓸모있게 쓰는 법 어디 없나?"
SOURCE = "rolemesh-autoevo"
STATE_FILE = "/tmp/rolemesh-autoevo.state.json"
EMPTY_STREAK_LIMIT = 3
PAUSE_SECONDS = 6 * 3600  # 6h
RESUME_TRIGGER_FILE = "/tmp/rolemesh-autoevo.resume"




def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"empty_streak": 0, "paused_until": 0, "last_reason": ""}


def _save_state(st: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception:
        pass


def _pause(st: dict, reason: str, seconds: int = PAUSE_SECONDS) -> dict:
    now = int(time.time())
    st["paused_at"] = now
    st["paused_until"] = now + seconds
    st["last_reason"] = reason
    _save_state(st)
    return st


def _is_paused(st: dict) -> tuple[bool, int, str]:
    now = int(time.time())
    until = int(st.get("paused_until", 0) or 0)
    if until > now:
        return True, until - now, st.get("last_reason", "")
    return False, 0, ""


def _has_convergence_risk(conn: sqlite3.Connection) -> tuple[bool, str]:
    rows = conn.execute(
        """
        SELECT COALESCE(result_summary,''), COALESCE(error,'')
        FROM task_queue
        WHERE source = ? AND status IN ('done','failed')
        ORDER BY created_at DESC
        LIMIT 24
        """,
        (SOURCE,),
    ).fetchall()
    if len(rows) < 12:
        return False, ""

    def is_noop(txt: str) -> bool:
        pats = ["변경 불필요", "이미 구현 완료", "완전 구현", "스펙 부재", "구현 거부", "no-change", "already implemented"]
        return any(p in txt for p in pats)

    hits = 0
    for summary, err in rows:
        txt = f"{summary} {err}"
        if is_noop(txt):
            hits += 1

    ratio = hits / max(len(rows), 1)
    if ratio >= 0.65:
        return True, f"convergence-risk(noop_ratio={ratio:.2f})"
    return False, ""



def _should_resume(conn: sqlite3.Connection, st: dict) -> tuple[bool, str]:
    # 1) 운영자 수동 재개 트리거
    if os.path.exists(RESUME_TRIGGER_FILE):
        try:
            os.remove(RESUME_TRIGGER_FILE)
        except Exception:
            pass
        return True, "manual-resume-trigger"

    # 2) 외부에서 수동 enqueue 된 활성 태스크가 있으면 즉시 재개
    if _has_active(conn):
        return True, "external-active-tasks"

    # 3) 최근 결과가 의미 있는 진전(비-noop) 중심으로 바뀌면 재개
    rows = conn.execute(
        """
        SELECT COALESCE(result_summary,''), COALESCE(error,'')
        FROM task_queue
        WHERE source = ? AND status IN ('done','failed')
        ORDER BY created_at DESC
        LIMIT 12
        """,
        (SOURCE,),
    ).fetchall()
    if len(rows) >= 6:
        pats = ["변경 불필요", "이미 구현 완료", "완전 구현", "스펙 부재", "구현 거부", "no-change", "already implemented"]
        def is_noop(txt: str) -> bool:
            return any(p in txt for p in pats)
        non_noop = 0
        for summary, err in rows[:6]:
            txt = f"{summary} {err}"
            if not is_noop(txt):
                non_noop += 1
        if non_noop >= 3:
            return True, f"recent-progress(non_noop={non_noop}/6)"

    return False, ""

def _next_round(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT title FROM task_queue
        WHERE source = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (SOURCE,),
    ).fetchone()
    if not row or not row[0]:
        return 1
    title = row[0]
    # title 예: [R3] RoleMesh JTBD 분석
    if title.startswith("[R"):
        try:
            return int(title.split("]", 1)[0][2:]) + 1
        except Exception:
            pass
    return 1


def _has_active(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM task_queue
        WHERE source = ? AND status IN ('pending', 'running')
        """,
        (SOURCE,),
    ).fetchone()
    return (row[0] if row else 0) > 0




def _should_skip_task(conn: sqlite3.Connection, task_title: str) -> tuple[bool, str]:
    """반복 중복/거부 패턴 태스크 enqueue 억제."""
    rows = conn.execute(
        """
        SELECT status, COALESCE(result_summary,''), COALESCE(error,'')
        FROM task_queue
        WHERE source = ? AND title LIKE ?
        ORDER BY created_at DESC
        LIMIT 12
        """,
        (SOURCE, f"%] {task_title}"),
    ).fetchall()
    if not rows:
        return False, ""

    # Builder 계열 스펙 부재 거부 반복 차단
    if task_title == "RoleMesh Builder 실행안":
        refusals = 0
        for st, summary, err in rows:
            txt = f"{summary} {err}"
            if "스펙 부재" in txt or "구현 거부" in txt:
                refusals += 1
        if refusals >= 3:
            return True, "spec-missing-repeat"

    # 이미 구현/변경 불필요 반복 차단
    noop_hits = 0
    for st, summary, err in rows:
        txt = f"{summary} {err}"
        if "변경 불필요" in txt or "이미 구현 완료" in txt or "완전 구현" in txt:
            noop_hits += 1
    if noop_hits >= 4:
        return True, "already-implemented-repeat"

    return False, ""

def enqueue_round(client: RegistryClient, conn: sqlite3.Connection, round_no: int) -> list[str]:
    phase_defs = [
        # Analyst (amp)
        ("RoleMesh JTBD 분석", "사용자 도구 피로도/혼란 원인 재평가 + 개선 가설 3개 도출", "analysis", 10),
        ("RoleMesh 추천엔진 규칙 설계", "역할 추천 규칙 업데이트 + 라우팅 기준 개선안", "analysis", 9),

        # Builder (cokac) — 코딩형 태스크 강제 포함
        ("RoleMesh Builder 실행안", "코드 구현 관점에서 설치마법사/라우팅 로직 프로토타입 제안 (함수/파일/테스트 항목 포함)", "coding", 9),

        # PM (roki)
        ("RoleMesh 설치마법사 UX 개선", "질문 흐름/실패 복구 문구/라이트 모드 개선", "coordination", 8),
        ("RoleMesh 확장 통합 가이드", "신규 AI 통합 시 역할 자동 추천 가이드 개선", "analysis", 8),
        ("RoleMesh 라운드 브리프", "결정사항/구현안/다음액션 3줄로 통합 요약", "coordination", 8),
    ]
    ids = []
    for title, desc, kind, prio in phase_defs:
        skip, reason = _should_skip_task(conn, title)
        if skip:
            print(f"[rolemesh-autoevo] skip enqueue: {title} ({reason})")
            continue
        # Throttle check before enqueue
        if _AUTOEVO_THROTTLE:
            _wait = _autoevo_throttle.acquire("anthropic")
            if _wait is not True:
                print(f"[rolemesh-autoevo] throttle wait {_wait:.1f}s before enqueue: {title}")
                time.sleep(float(_wait))
                _wait2 = _autoevo_throttle.acquire("anthropic")
                if _wait2 is not True:
                    print(f"[rolemesh-autoevo] throttle retry failed, skip enqueue: {title}")
                    continue
        task_id = client.enqueue(
            title=f"[R{round_no}] {title}",
            description=(
                f"주제: {TOPIC}\n"
                f"라운드: R{round_no}\n"
                f"요청: {desc}\n"
                f"완료 시 result_summary에 핵심 3줄 요약 작성"
            ),
            kind=kind,
            priority=prio,
            source=SOURCE,
        )
        ids.append(task_id)
    return ids


def run_loop(poll_sec: int = 60) -> None:
    client = RegistryClient()
    conn = client._conn_ctx()
    st = _load_state()
    print(f"[rolemesh-autoevo] started poll={poll_sec}s pid={os.getpid()}")

    while True:
        try:
            paused, remain, reason = _is_paused(st)
            if paused:
                resume, why = _should_resume(conn, st)
                if resume:
                    st["paused_until"] = 0
                    st["empty_streak"] = 0
                    st["last_reason"] = f"resumed:{why}"
                    _save_state(st)
                    print(f"[rolemesh-autoevo] resumed reason={why}")
                else:
                    print(f"[rolemesh-autoevo] paused {remain}s reason={reason}")
                    time.sleep(min(poll_sec, max(30, remain)))
                    st = _load_state()
                    continue

            risky, risk_reason = _has_convergence_risk(conn)
            if risky:
                st = _pause(st, risk_reason)
                print(f"[rolemesh-autoevo] pause triggered: {risk_reason}")
                time.sleep(poll_sec)
                continue

            if not _has_active(conn):
                r = _next_round(conn)
                ids = enqueue_round(client, conn, r)
                print(f"[rolemesh-autoevo] enqueued round R{r} ({len(ids)} tasks)")

                if len(ids) == 0:
                    st["empty_streak"] = int(st.get("empty_streak", 0)) + 1
                    if st["empty_streak"] >= EMPTY_STREAK_LIMIT:
                        st = _pause(st, f"empty-enqueue-streak={st['empty_streak']}")
                        st["empty_streak"] = 0
                else:
                    st["empty_streak"] = 0
                _save_state(st)

            time.sleep(poll_sec)
        except Exception as e:
            print(f"[rolemesh-autoevo] error: {e}", file=sys.stderr)
            time.sleep(poll_sec)


def daemonize() -> None:
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    def _cleanup(sig, frame):
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--poll", type=int, default=60)
    p.add_argument("--daemon", action="store_true")
    args = p.parse_args()
    if args.daemon:
        daemonize()
    run_loop(args.poll)


if __name__ == "__main__":
    main()
