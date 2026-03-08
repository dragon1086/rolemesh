#!/bin/bash
# RoleMesh 상태 대시보드
set -euo pipefail

DB="${HOME}/ai-comms/registry.db"

if [[ ! -f "$DB" ]]; then
  echo "[status] DB 없음: $DB"
  exit 1
fi

echo "=== RoleMesh Queue Status ($(date '+%Y-%m-%d %H:%M:%S')) ==="
echo ""

echo "--- Task Queue ---"
sqlite3 -column -header "$DB" \
  "SELECT status, COUNT(*) AS count FROM task_queue GROUP BY status ORDER BY status;"

echo ""
echo "--- Dead Letter Queue ---"
DLQ=$(sqlite3 "$DB" "SELECT COUNT(*) FROM dead_letter;")
echo "dlq_count: $DLQ"

echo ""
echo "--- Recent DLQ Entries (최근 5개) ---"
sqlite3 -column -header "$DB" \
  "SELECT task_id, title, retry_count, substr(error,1,60) AS error, datetime(dlq_at,'unixepoch','localtime') AS dlq_at FROM dead_letter ORDER BY dlq_at DESC LIMIT 5;" 2>/dev/null || true

echo ""
echo "--- Running Workers ---"
ps aux | grep -E "rolemesh\.(queue_worker|message_worker|autoevo_worker)" | grep -v grep \
  | awk '{print $2, $11, $12}' \
  || echo "(실행 중인 워커 없음)"
