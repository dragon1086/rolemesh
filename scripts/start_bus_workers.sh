#!/bin/bash
# start_bus_workers.sh — MACRS 메시지/태스크 워커 일괄 시작

set -e
cd "$(dirname "$0")"

nohup python3 queue_worker.py --daemon >/tmp/macrs-worker.log 2>&1 &
nohup python3 message_worker.py --agent cokac --daemon >/tmp/macrs-msg-cokac.log 2>&1 &
nohup python3 message_worker.py --agent amp --daemon >/tmp/macrs-msg-amp.log 2>&1 &

echo "started: queue_worker + message_worker(cokac, amp)"
for f in /tmp/macrs_worker.pid /tmp/macrs_message_worker_cokac.pid /tmp/macrs_message_worker_amp.pid; do
  if [[ -f "$f" ]]; then
    echo "$(basename "$f"): $(cat "$f")"
  fi
done
