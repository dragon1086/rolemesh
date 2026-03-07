"""
rolemesh_autoevo_worker.py
- RoleMesh 자율진화 루프 유지 워커
- rolemesh-autoevo 소스의 pending/running 태스크가 비면 다음 라운드 자동 enqueue
"""

from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import sys
import time

from registry_client import RegistryClient

PID_FILE = "/tmp/rolemesh-autoevo-worker.pid"
TOPIC = "요즘 오픈클로나 별에 별 AI가 나와서 뭘써야할지 모르겠어서 많이 받아놨어. 진짜 쓸모있게 쓰는 법 어디 없나?"
SOURCE = "rolemesh-autoevo"


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


def enqueue_round(client: RegistryClient, round_no: int) -> list[str]:
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
    print(f"[rolemesh-autoevo] started poll={poll_sec}s pid={os.getpid()}")

    while True:
        try:
            if not _has_active(conn):
                r = _next_round(conn)
                ids = enqueue_round(client, r)
                print(f"[rolemesh-autoevo] enqueued round R{r} ({len(ids)} tasks)")
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
