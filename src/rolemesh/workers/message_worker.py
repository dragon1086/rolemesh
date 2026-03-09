"""
message_worker.py — MACRS SQLite messages 소비 워커

역할:
- messages.pending 을 claim(processing) 후 실제 처리자에게 전달
- 처리 완료 시 done, 실패 시 failed로 ack

실행:
  python message_worker.py --agent cokac --daemon
  python message_worker.py --agent amp
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time

from ..core.registry_client import RegistryClient, Message
from ..adapters.amp_caller import ask_amp

PID_FILE_TMPL = "/tmp/macrs_message_worker_{agent}.pid"
POLL_INTERVAL = 5
logger = logging.getLogger(__name__)


def _recover_stale_messages(client: RegistryClient, agent: str, stale_sec: int) -> int:
    """processing 상태가 오래된 메시지를 pending으로 복구한다."""
    now = int(time.time())
    conn = client._conn_ctx()
    with conn:
        cur = conn.execute(
            """
            UPDATE messages
            SET status='pending'
            WHERE to_agent=? AND status='processing'
              AND processed_at IS NOT NULL
              AND processed_at < ?
            """,
            (agent, now - stale_sec),
        )
    return cur.rowcount


def _process_claimed_messages(client: RegistryClient, agent: str, msgs: list[Message]) -> None:
    for m in msgs:
        try:
            ok, detail = _handle(m, client, agent)
            client.ack_message(m.id, status="done" if ok else "failed")
            logger.info("message %s -> %s (%s)", m.id, "done" if ok else "failed", detail)
        except Exception as e:
            client.ack_message(m.id, status="failed")
            logger.exception("message %s -> failed (%s)", m.id, e)


def _to_cokac(msg: Message) -> tuple[bool, str]:
    script = os.path.expanduser("~/.claude/scripts/claude-comms/send-message.sh")
    if not os.path.exists(script):
        return False, "send-message.sh not found"

    content = msg.content if isinstance(msg.content, dict) else {"raw": str(msg.content)}
    body = content.get("task") or content.get("description") or json.dumps(content, ensure_ascii=False)
    text = (
        f"[MACRS message bus]\n"
        f"id: {msg.id}\n"
        f"from: {msg.from_agent}\n"
        f"to: {msg.to_agent}\n\n"
        f"{body}"
    )
    cp = subprocess.run(
        ["bash", script, "openclaw-bot", "cokac-bot", "normal", text, "none"],
        capture_output=True,
        text=True,
    )
    ok = cp.returncode == 0
    detail = (cp.stdout or "")[-300:] + (cp.stderr or "")[-300:]
    return ok, detail.strip()


def _to_amp(msg: Message, client: RegistryClient) -> tuple[bool, str]:
    content = msg.content if isinstance(msg.content, dict) else {"raw": str(msg.content)}
    task = content.get("task") or content.get("query") or content.get("description")
    if not task:
        return False, "missing task/query/description"

    out = ask_amp(task, force_tool=content.get("force_tool"), timeout=90)
    # 응답을 발신자에게 회신으로 남김 (버스 순환)
    reply_payload = {
        "reply_to": msg.id,
        "from": "amp",
        "answer": out.get("answer", ""),
        "tool_used": out.get("tool_used"),
        "cser": out.get("cser"),
        "fallback": out.get("fallback", False),
    }
    client.send_message(from_agent="amp", to_agent=msg.from_agent, content=reply_payload)
    return True, f"tool={out.get('tool_used')} cser={out.get('cser')}"


def _to_roki(msg: Message) -> tuple[bool, str]:
    # roki 전용 메시지는 로그 처리 (필요 시 openclaw event로 확장 가능)
    return True, "accepted-by-roki"


def _handle(msg: Message, client: RegistryClient, agent: str) -> tuple[bool, str]:
    if agent == "cokac":
        return _to_cokac(msg)
    if agent == "amp":
        return _to_amp(msg, client)
    if agent == "roki":
        return _to_roki(msg)
    return False, f"unsupported agent: {agent}"


def run_loop(agent: str, poll: int = POLL_INTERVAL, stale_sec: int = 300) -> None:
    client = RegistryClient()
    logger.info("message worker start agent=%s poll=%ss stale=%ss pid=%s", agent, poll, stale_sec, os.getpid())

    while True:
        try:
            recovered = _recover_stale_messages(client, agent, stale_sec)
            if recovered:
                logger.info("recovered %s stale messages for %s", recovered, agent)

            msgs = client.claim_pending(to_agent=agent, limit=20)
            if not msgs:
                time.sleep(poll)
                continue

            _process_claimed_messages(client, agent, msgs)
        except Exception as e:
            logger.exception("message worker loop error for %s: %s", agent, e)
            time.sleep(poll)


def daemonize(pid_file: str) -> None:
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)

    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    def _cleanup(sig, frame):
        try:
            os.remove(pid_file)
        except FileNotFoundError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)


def main() -> None:
    p = argparse.ArgumentParser(description="MACRS messages 소비 워커")
    p.add_argument("--agent", required=True, choices=["cokac", "amp", "roki"], help="소비 대상 to_agent")
    p.add_argument("--poll", type=int, default=POLL_INTERVAL, help="poll interval seconds")
    p.add_argument("--stale-sec", type=int, default=300, help="processing 복구 임계(초)")
    p.add_argument("--daemon", action="store_true", help="daemon mode")
    args = p.parse_args()

    pid_file = PID_FILE_TMPL.format(agent=args.agent)
    if args.daemon:
        daemonize(pid_file)

    run_loop(agent=args.agent, poll=args.poll, stale_sec=args.stale_sec)


if __name__ == "__main__":
    main()
