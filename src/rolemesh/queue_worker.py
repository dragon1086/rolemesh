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
DONE_EVENT_COOLDOWN_SEC = 120
DONE_EVENT_STATE = '/tmp/rolemesh-done-event.last'

# 완료 알림 티어링: 사용자/수동 트리거만 즉시 알림, 자동 루프는 무음(라운드 요약에 위임)
NOISY_SOURCES = {"rolemesh-autoevo", "rolemesh-build", "paper-autoevo"}


def _should_notify_done(task: dict) -> bool:
    source = (task.get("source") or "manual").strip()
    priority = int(task.get("priority") or 0)
    # high priority는 즉시 알림 허용
    if priority >= 9:
        return True
    # 자동 루프 source는 done 이벤트 무음
    if source in NOISY_SOURCES:
        return False
    # 그 외(수동/외부 요청)는 알림
    return True




def _allow_done_event() -> bool:
    now = int(time.time())
    try:
        if os.path.exists(DONE_EVENT_STATE):
            last = int(open(DONE_EVENT_STATE).read().strip() or '0')
            if now - last < DONE_EVENT_COOLDOWN_SEC:
                return False
    except Exception:
        pass
    try:
        with open(DONE_EVENT_STATE, 'w') as f:
            f.write(str(now))
    except Exception:
        pass
    return True


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
        # 완료 알림 티어링 적용
        if _should_notify_done(task) and _allow_done_event():
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
    # 시작 로그는 stderr로 (사용자 채널 차단, 디버그용 유지)
    print(f"[worker] 시작 (PID={os.getpid()}, poll={POLL_INTERVAL}s)", file=sys.stderr)

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
