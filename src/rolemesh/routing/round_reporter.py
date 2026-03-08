"""
rolemesh_round_reporter.py
- rolemesh-autoevo 라운드 완료 시 1회 요약 알림 전송
- openclaw system event 사용
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time

from ..core.quality_tracker import QualityTracker

DB = os.path.expanduser("~/ai-comms/registry.db")
PID_FILE = "/tmp/rolemesh-round-reporter.pid"
SOURCE = "rolemesh-autoevo"
STATE_FILE = "/tmp/rolemesh-round-reporter.last"


def _send_event(text: str) -> None:
    try:
        subprocess.run(
            ["openclaw", "system", "event", "--text", text, "--mode", "now"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


def _extract_round(title: str) -> int | None:
    m = re.match(r"^\[R(\d+)\]", title or "")
    return int(m.group(1)) if m else None


def _latest_fully_done_round(conn: sqlite3.Connection) -> tuple[int | None, dict]:
    rows = conn.execute(
        """
        SELECT title, status, result_summary
        FROM task_queue
        WHERE source = ?
        ORDER BY created_at DESC
        """,
        (SOURCE,),
    ).fetchall()

    by_round: dict[int, list[tuple[str, str]]] = {}
    for title, status, summary in rows:
        r = _extract_round(title)
        if r is None:
            continue
        by_round.setdefault(r, []).append((status, summary or ""))

    if not by_round:
        return None, {}

    for r in sorted(by_round.keys(), reverse=True):
        items = by_round[r]
        if len(items) >= 4 and all(s == "done" for s, _ in items[:4]):
            summaries = [sm for _, sm in items[:4] if sm.strip()]
            return r, {"count": len(items[:4]), "summaries": summaries}

    return None, {}


def _extract_done_report_v1(summary: str) -> dict | None:
    text = summary or ""
    marker = "DONE_REPORT_V1:"
    if marker not in text:
        return None
    raw = text.split(marker, 1)[1].strip().splitlines()[0].strip()
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _record_quality_scores(
    quality_tracker: QualityTracker,
    round_no: int,
    summaries: list[str],
) -> None:
    for index, summary in enumerate(summaries, start=1):
        report = _extract_done_report_v1(summary)
        if not report:
            continue

        score = report.get("score")
        if score is None:
            continue

        batch_id = str(
            report.get("batch_id")
            or report.get("task_id")
            or report.get("id")
            or f"R{round_no}-{index}"
        )
        provider = str(report.get("provider") or report.get("assignee") or "unknown")
        timestamp = report.get("timestamp") or report.get("ts")

        try:
            quality_tracker.record(
                batch_id=batch_id,
                score=float(score),
                provider=provider,
                timestamp=None if timestamp is None else float(timestamp),
            )
        except Exception:
            continue


def run_loop(poll: int = 20):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    quality_tracker = QualityTracker(DB)

    last_reported = 0
    if os.path.exists(STATE_FILE):
        try:
            last_reported = int(open(STATE_FILE).read().strip() or "0")
        except Exception:
            last_reported = 0

    while True:
        try:
            r, info = _latest_fully_done_round(conn)
            if r and r > last_reported:
                _record_quality_scores(quality_tracker, r, info.get("summaries", []))
                lines = []
                for s in info.get("summaries", [])[:3]:
                    s = " ".join(s.split())
                    lines.append(f"- {s[:120]}")
                text = f"RoleMesh R{r} 완료 ✅\n" + ("\n".join(lines) if lines else "요약 수집 완료")
                _send_event(text)
                last_reported = r
                with open(STATE_FILE, "w") as f:
                    f.write(str(r))
            time.sleep(poll)
        except Exception as e:
            print(f"[round-reporter] {e}", file=sys.stderr)
            time.sleep(poll)


def daemonize():
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--poll", type=int, default=20)
    p.add_argument("--daemon", action="store_true")
    args = p.parse_args()
    if args.daemon:
        daemonize()
    run_loop(args.poll)


if __name__ == "__main__":
    main()
