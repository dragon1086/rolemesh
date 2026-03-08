"""
queue_worker.py — MACRS 태스크 큐 워커

태스크 큐를 30초마다 폴링하여 pending 태스크를 Symphony×MACRS로 실행.

실행:
    python queue_worker.py           # 포그라운드
    python queue_worker.py --daemon  # 데몬 (PID: /tmp/macrs_worker.pid)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time

from .registry_client import RegistryClient
from .symphony_fusion import SymphonyMACRS, WorkItem
from .provider_router import ProviderRouter
from .throttle import TokenBucketThrottle


PID_FILE = "/tmp/macrs_worker.pid"
POLL_INTERVAL = 30  # seconds
THROTTLE_MAX_RETRIES = 3  # max waits before rescheduling task
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








def _extract_done_report_v1(summary: str) -> dict | None:
    t=(summary or '')
    marker='DONE_REPORT_V1:'
    if marker not in t:
        return None
    raw=t.split(marker,1)[1].strip().splitlines()[0].strip()
    try:
        obj=json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _is_verified_report(report: dict | None) -> bool:
    if not report:
        return False
    if report.get('status') not in ('implemented','verified'):
        return False
    if not report.get('changed_files') or not report.get('diff_summary') or not report.get('tests') or not report.get('artifacts'):
        return False
    for t in report.get('tests',[]):
        try:
            if int(t.get('exit_code',1))!=0:
                return False
        except Exception:
            return False
    return True

def _is_delegated_only_result(summary: str) -> bool:
    t = (summary or "").strip().lower()
    if not t:
        return False
    delegated_markers = [
        "구현 위임 완료", "위임 완료", "delegated", "assigned to",
        "cokac-bot에 구현 위임 완료",
        "조정 작업: 하위 결과를 수집/검증 후 사용자에 보고",
    ]
    return any(m.lower() in t for m in delegated_markers)


def _verification_failed_msg(summary: str) -> str:
    return "verification_failed: delegated-only result (no proof). raw=" + (summary or "")[:180]
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
    """openclaw 이벤트 전송. 실패 시 예외를 발생시킨다."""
    subprocess.run(
        ["openclaw", "system", "event", "--text", text, "--mode", "now"],
        capture_output=True,
        timeout=10,
        check=True,
    )


_router = ProviderRouter()
_throttle = TokenBucketThrottle()


def _select_provider_with_throttle(task_id: str, client: RegistryClient) -> str | None:
    """Pick an available provider respecting CB + throttle.

    Returns provider name, or None if all providers are exhausted
    (caller should reschedule the task).
    """
    from .provider_router import FALLBACK_PROVIDER

    for attempt in range(THROTTLE_MAX_RETRIES):
        provider = _router.route()
        if provider == FALLBACK_PROVIDER:
            # All circuits OPEN — no point throttle-retrying
            print(
                f"[worker] 모든 provider OPEN → 재스케줄: {task_id}",
                file=sys.stderr,
            )
            return None

        result = _throttle.acquire(provider)
        if result is True:
            return provider

        wait_sec = float(result)
        print(
            f"[worker] throttle wait {wait_sec:.1f}s (attempt {attempt + 1}/{THROTTLE_MAX_RETRIES})"
            f" provider={provider} task={task_id}",
            file=sys.stderr,
        )
        time.sleep(wait_sec)

    # Throttle exhausted after retries
    print(
        f"[worker] throttle 소진 → 재스케줄: {task_id}",
        file=sys.stderr,
    )
    return None


def _run_task(task: dict, orchestrator: SymphonyMACRS, client: RegistryClient) -> None:
    task_id = task["id"]
    goal = task.get("description") or task["title"]
    kind = task.get("kind")
    source = task.get("source") or "manual"

    # ── Provider 선택 (CB + Throttle) ──────────────────────────────
    provider = _select_provider_with_throttle(task_id, client)
    if provider is None:
        client.retry_task(task_id, int(task.get("retry_count") or 0) + 1, 60)
        print(f"[worker] 재스케줄(provider 없음): {task_id}", file=sys.stderr)
        return

    print(f"[worker] 실행: {task_id} ({task['title']}) via {provider}")

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

        _router.record_success(provider)
        report = _extract_done_report_v1(summary)

        if _is_delegated_only_result(summary):
            vmsg = _verification_failed_msg(summary)
            client.complete_task(task_id, error=vmsg, status="verification_failed")
            try:
                _send_openclaw_event(f"Hold: [{task['title']}] delegated-only result blocked")
            except Exception:
                pass
            print(f"[worker] 보류(검증실패): {task_id}", file=sys.stderr)
            return

        if report and not _is_verified_report(report):
            vmsg = "verification_failed: invalid DONE_REPORT_V1 payload"
            client.complete_task(task_id, error=vmsg, status="verification_failed")
            try:
                _send_openclaw_event(f"Hold: [{task['title']}] invalid DONE_REPORT_V1")
            except Exception:
                pass
            print(f"[worker] 보류(리포트검증실패): {task_id}", file=sys.stderr)
            return

        # 본체 성공 — announce 시도
        announce_error = None
        if _should_notify_done(task) and _allow_done_event():
            try:
                _send_openclaw_event(f"Done: [{task['title']}] {summary[:200]}")
            except Exception as ae:
                announce_error = str(ae)[:300]

        if announce_error:
            client.complete_task(
                task_id,
                summary=summary[:500],
                error=f"announce_failed: {announce_error}",
                status="completed_with_announce_error",
            )
            print(f"[worker] 완료(announce 실패): {task_id} — {announce_error}", file=sys.stderr)
        else:
            client.complete_task(task_id, summary=summary[:500])
            print(f"[worker] 완료: {task_id}")
    except Exception as e:
        _router.record_failure(provider)
        error_msg = str(e)[:300]
        retry_count = int(task.get("retry_count") or 0)
        max_retries = 3

        if retry_count < max_retries:
            delay = 30 * (2 ** retry_count)  # 30s → 60s → 120s
            client.retry_task(task_id, retry_count + 1, delay)
            print(
                f"[worker] 재시도 예약: {task_id} "
                f"(시도 {retry_count + 1}/{max_retries}, {delay}s 후) — {error_msg}",
                file=sys.stderr,
            )
        else:
            client.move_to_dlq(task_id, error_msg)
            try:
                _send_openclaw_event(
                    f"DLQ: [{task['title']}] retry 소진 — {error_msg[:150]}"
                )
            except Exception:
                pass
            print(f"[worker] DLQ(retry 소진): {task_id} — {error_msg}", file=sys.stderr)


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
