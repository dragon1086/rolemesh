#!/bin/bash
# RoleMesh 상태 대시보드
set -euo pipefail

DB="${HOME}/ai-comms/registry.db"
REQUIRED_CMDS=(sqlite3 python3 ps awk grep date)
MISSING_CMDS=()

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

have_table() {
  local table="$1"
  sqlite3 "$DB" "SELECT 1 FROM sqlite_master WHERE type='table' AND name='${table}' LIMIT 1;" 2>/dev/null | grep -q '^1$'
}

for cmd in "${REQUIRED_CMDS[@]}"; do
  if ! have_cmd "$cmd"; then
    MISSING_CMDS+=("$cmd")
  fi
done

if [[ ! -f "$DB" ]]; then
  echo "[status] DB 없음: $DB"
  exit 1
fi

echo "=== RoleMesh Queue Status ($(date '+%Y-%m-%d %H:%M:%S')) ==="
echo ""

if [[ ${#MISSING_CMDS[@]} -gt 0 ]]; then
  echo "[status] 일부 명령 누락: ${MISSING_CMDS[*]}"
  echo "[status] 가능한 섹션만 표시합니다."
  echo ""
fi

echo "--- Task Queue ---"
if have_cmd sqlite3 && have_table task_queue; then
  sqlite3 -column -header "$DB" \
    "SELECT status, COUNT(*) AS count FROM task_queue GROUP BY status ORDER BY status;"
else
  echo "(task_queue 조회 불가: sqlite3 또는 테이블 없음)"
fi

echo ""
echo "--- Dead Letter Queue ---"
if have_cmd sqlite3 && have_table dead_letter; then
  DLQ=$(sqlite3 "$DB" "SELECT COUNT(*) FROM dead_letter;")
  echo "dlq_count: $DLQ"
else
  echo "dlq_count: N/A (dead_letter 테이블 없음)"
fi

echo ""
echo "--- Recent DLQ Entries (최근 5개) ---"
if have_cmd sqlite3 && have_table dead_letter; then
  sqlite3 -column -header "$DB" \
    "SELECT task_id, title, retry_count, substr(error,1,60) AS error, datetime(dlq_at,'unixepoch','localtime') AS dlq_at FROM dead_letter ORDER BY dlq_at DESC LIMIT 5;" 2>/dev/null || true
else
  echo "(표시할 dead_letter 항목 없음)"
fi

echo ""
echo "--- Running Workers ---"
if have_cmd ps && have_cmd grep && have_cmd awk; then
  ps aux | grep -E "rolemesh(\.workers)?\.(queue_worker|message_worker|autoevo_worker)" | grep -v grep \
    | awk '{print $2, $11, $12}' \
    || echo "(실행 중인 워커 없음)"
else
  echo "(워커 프로세스 조회 불가: ps/grep/awk 필요)"
fi

for module in rolemesh.workers.queue_worker rolemesh.workers.message_worker rolemesh.workers.autoevo_worker; do
  if have_cmd python3; then
    PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}" \
      python3 -c "import importlib; importlib.import_module('${module}')" >/dev/null 2>&1 \
      || echo "  module import failed: ${module}"
  else
    echo "  module import skipped: python3 없음"
    break
  fi
done

echo ""
echo "--- Batch Cooldown Status ---"
if have_cmd python3; then
  PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}" python3 -c "
import json, time, sys
STATE_FILE = '/tmp/rolemesh-batch-cooldown.json'
COOLDOWN_SEC = 120.0
try:
    import yaml
    cfg_path = __import__('pathlib').Path.home() / 'rolemesh' / 'config' / 'throttle.yaml'
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.open()) or {}
        if 'batch_cooldown_sec' in cfg:
            COOLDOWN_SEC = float(cfg['batch_cooldown_sec'])
except Exception:
    pass
try:
    d = json.load(open(STATE_FILE))
    last = float(d.get('last_complete_at', 0))
    remaining = COOLDOWN_SEC - (time.time() - last)
    if remaining > 0:
        print(f'  배치 쿨다운: {remaining:.0f}s 남음')
    else:
        print('  배치 쿨다운: READY')
except FileNotFoundError:
    print('  배치 쿨다운: READY (기록 없음)')
except Exception as e:
    print(f'  배치 쿨다운: ERROR ({e})')
" 2>&1
else
  echo "  배치 쿨다운: 확인 불가 (python3 없음)"
fi

echo ""
echo "--- Provider Circuit Breaker Status ---"
for provider in anthropic openai gemini; do
  STATE_FILE="/tmp/rolemesh-cb-${provider}.json"
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "  ${provider}: CLOSED (no state file)"
    continue
  fi
  if ! have_cmd python3; then
    echo "  ${provider}: 확인 불가 (python3 없음)"
    continue
  fi
  STATE=$(PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}" python3 -c "
import json, time, sys
try:
    d = json.load(open('${STATE_FILE}'))
    state = d.get('state', 'CLOSED')
    opened_at = int(d.get('opened_at', 0))
    cooldown = int(d.get('cooldown_sec', 60))
    now = int(time.time())
    if state == 'OPEN':
        elapsed = now - opened_at
        if elapsed >= cooldown:
            state = 'HALF_OPEN'
            remaining = 0
        else:
            remaining = cooldown - elapsed
        print(f'{state} (cooldown: {remaining}s 남음)' if remaining > 0 else f'{state}')
    else:
        print(state)
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1)
  echo "  ${provider}: ${STATE}"
done
