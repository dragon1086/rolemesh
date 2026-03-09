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
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time

from ..core.registry_client import RegistryClient
from ..routing.symphony_fusion import SymphonyMACRS, WorkItem
from ..adapters.provider_router import ProviderRouter
from ..adapters.throttle import TokenBucketThrottle


PID_FILE = "/tmp/macrs_worker.pid"
logger = logging.getLogger(__name__)
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


def _is_timeout_error(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, subprocess.TimeoutExpired))


def _format_task_error(exc: BaseException) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        cmd = exc.cmd if isinstance(exc.cmd, str) else " ".join(map(str, exc.cmd or ()))
        return f"timeout: cmd={cmd} after {exc.timeout}s"
    if isinstance(exc, TimeoutError):
        msg = str(exc).strip()
        return f"timeout: {msg}" if msg else "timeout"
    return str(exc)


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
    from ..adapters.provider_router import FALLBACK_PROVIDER

    for attempt in range(THROTTLE_MAX_RETRIES):
        provider = _router.route()
        if provider == FALLBACK_PROVIDER:
            # All circuits OPEN — no point throttle-retrying
            logger.warning("worker all providers open, rescheduling task_id=%s", task_id)
            return None

        result = _throttle.acquire(provider)
        if result is True:
            return provider

        wait_sec = float(result)
        logger.info(
            "worker throttle wait %.1fs attempt=%s/%s provider=%s task_id=%s",
            wait_sec,
            attempt + 1,
            THROTTLE_MAX_RETRIES,
            provider,
            task_id,
        )
        time.sleep(wait_sec)

    # Throttle exhausted after retries
    logger.warning("worker throttle exhausted, rescheduling task_id=%s", task_id)
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
        logger.warning("worker provider unavailable, rescheduled task_id=%s", task_id)
        return

    logger.info("worker executing task_id=%s title=%s provider=%s", task_id, task["title"], provider)

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
            logger.warning("worker verification failed delegated-only task_id=%s", task_id)
            return

        if report and not _is_verified_report(report):
            vmsg = "verification_failed: invalid DONE_REPORT_V1 payload"
            client.complete_task(task_id, error=vmsg, status="verification_failed")
            try:
                _send_openclaw_event(f"Hold: [{task['title']}] invalid DONE_REPORT_V1")
            except Exception:
                pass
            logger.warning("worker verification failed invalid report task_id=%s", task_id)
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
            logger.warning(
                "worker completed with announce failure task_id=%s error=%s",
                task_id,
                announce_error,
            )
        else:
            client.complete_task(task_id, summary=summary[:500])
            logger.info("worker completed task_id=%s", task_id)
    except subprocess.TimeoutExpired as e:
        _router.record_failure(provider)
        error_msg = _format_task_error(e)[:300]
        retry_count = int(task.get("retry_count") or 0)
        max_retries = 3

        if retry_count < max_retries:
            delay = 30 * (2 ** retry_count)  # 30s → 60s → 120s
            client.retry_task(task_id, retry_count + 1, delay)
            logger.warning(
                "worker timeout retry scheduled task_id=%s attempt=%s/%s delay=%ss error=%s",
                task_id,
                retry_count + 1,
                max_retries,
                delay,
                error_msg,
            )
        else:
            client.move_to_dlq(task_id, error_msg)
            try:
                _send_openclaw_event(
                    f"DLQ: [{task['title']}] timeout 소진 — {error_msg[:150]}"
                )
            except Exception:
                pass
            logger.error(
                "worker moved to dlq after timeout task_id=%s error=%s",
                task_id,
                error_msg,
            )
    except Exception as e:
        _router.record_failure(provider)
        timed_out = _is_timeout_error(e)
        error_msg = _format_task_error(e)[:300]
        retry_count = int(task.get("retry_count") or 0)
        max_retries = 3

        if retry_count < max_retries:
            delay = 30 * (2 ** retry_count)  # 30s → 60s → 120s
            client.retry_task(task_id, retry_count + 1, delay)
            logger.warning(
                "worker retry scheduled task_id=%s timed_out=%s attempt=%s/%s delay=%ss error=%s",
                task_id,
                timed_out,
                retry_count + 1,
                max_retries,
                delay,
                error_msg,
            )
        else:
            client.move_to_dlq(task_id, error_msg)
            try:
                _send_openclaw_event(
                    f"DLQ: [{task['title']}] {'timeout' if timed_out else 'retry'} 소진 — {error_msg[:150]}"
                )
            except Exception:
                pass
            logger.error(
                "worker moved to dlq after retries task_id=%s timed_out=%s error=%s",
                task_id,
                timed_out,
                error_msg,
            )


DEFAULT_DB_PATH = os.path.expanduser("~/ai-comms/registry.db")
STALE_RECOVER_INTERVAL = 300  # recover_stale 주기(초): 5분마다 실행


def recover_stale(stale_threshold_seconds: int = 1800, db_path: str = DEFAULT_DB_PATH) -> int:
    """running 상태이고 started_at이 stale_threshold_seconds 초 초과한 태스크를 pending으로 복귀.

    반환값: 복구된 건수
    """
    cutoff = int(time.time()) - stale_threshold_seconds
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "UPDATE task_queue SET status='pending', started_at=NULL "
                "WHERE status='running' AND started_at < ?",
                (cutoff,),
            )
            conn.commit()
            recovered = cur.rowcount
        finally:
            conn.close()
    except Exception as e:
        logger.exception("worker recover_stale failed: %s", e)
        return 0

    if recovered:
        logger.info(
            "worker recovered stale tasks count=%s stale_threshold_seconds=%s",
            recovered,
            stale_threshold_seconds,
        )
    return recovered


def run_loop() -> None:
    client = RegistryClient()
    orchestrator = SymphonyMACRS(registry=client)
    logger.info("worker started pid=%s poll=%ss", os.getpid(), POLL_INTERVAL)

    last_stale_check = 0.0
    while True:
        # stale 복구: STALE_RECOVER_INTERVAL마다 실행
        now = time.time()
        if now - last_stale_check >= STALE_RECOVER_INTERVAL:
            recover_stale()
            last_stale_check = now

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
