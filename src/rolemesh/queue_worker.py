"""
queue_worker.py — MACRS 태스크 큐 워커

태스크 큐를 30초마다 폴링하여 pending 태스크를 Symphony×MACRS로 실행.

실행:
    python queue_worker.py           # 포그라운드
    python queue_worker.py --daemon  # 데몬 (PID: /tmp/macrs_worker.pid)
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

from registry_client import RegistryClient
from symphony_fusion import SymphonyMACRS, WorkItem


PID_FILE = "/tmp/macrs_worker.pid"
POLL_INTERVAL = 30  # seconds


def _send_openclaw_event(text: str) -> None:
    try:
        subprocess.run(
            ["openclaw", "system", "event", "--text", text, "--mode", "now"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass  # openclaw 미설치 환경 무시


def _run_task(task: dict, orchestrator: SymphonyMACRS, client: RegistryClient) -> None:
    task_id = task["id"]
    goal = task.get("description") or task["title"]
    kind = task.get("kind")
    source = task.get("source") or "manual"
    print(f"[worker] 실행: {task_id} ({task['title']})")

    try:
        if kind and kind != "auto":
            item = WorkItem(
                id=task_id,
                title=task["title"],
                description=goal,
                kind=kind,
            )
            result = orchestrator.execute(item)
            summary = result.summary
        else:
            out = orchestrator.run_goal(goal)
            summaries = [r["summary"] for r in out.get("results", [])]
            summary = " | ".join(summaries)

        client.complete_task(task_id, summary=summary[:500])
        # 대화 블로킹 방지: 자율진화(rolemesh-autoevo) 완료 이벤트는 기본적으로 무음
        if source != "rolemesh-autoevo":
            _send_openclaw_event(f"Done: [{task['title']}] {summary[:200]}")
        print(f"[worker] 완료: {task_id}")
    except Exception as e:
        error_msg = str(e)[:300]
        client.complete_task(task_id, error=error_msg)
        # 실패는 source와 무관하게 알림 유지
        _send_openclaw_event(f"Failed: [{task['title']}] {error_msg}")
        print(f"[worker] 실패: {task_id} — {error_msg}", file=sys.stderr)


def run_loop() -> None:
    client = RegistryClient()
    orchestrator = SymphonyMACRS(registry=client)
    print(f"[worker] 시작 (PID={os.getpid()}, poll={POLL_INTERVAL}s)")

    while True:
        task = client.dequeue_next()
        if task:
            _run_task(task, orchestrator, client)
        else:
            time.sleep(POLL_INTERVAL)


def daemonize() -> None:
    """간단한 더블-포크 데몬화"""
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)

    # PID 파일 기록
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
    p = argparse.ArgumentParser(description="MACRS 태스크 큐 워커")
    p.add_argument("--daemon", action="store_true", help="데몬 모드로 실행")
    args = p.parse_args()

    if args.daemon:
        daemonize()

    run_loop()


if __name__ == "__main__":
    main()
