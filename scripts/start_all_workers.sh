#!/bin/bash
# RoleMesh 워커 전체 시작 스크립트 (launchd 진입점)
set -euo pipefail

PYTHON=/opt/homebrew/bin/python3
PROJECT=/Users/rocky/rolemesh

export PYTHONPATH="$PROJECT/src"
export ROLEMESH_PROJECT_ROOT="$PROJECT"
export ROLEMESH_DB_PATH="${HOME}/ai-comms/registry.db"

cd "$PROJECT"

echo "[rolemesh] 워커 시작: $(date)" >&2

"$PYTHON" -m rolemesh.workers.queue_worker &
"$PYTHON" -m rolemesh.workers.message_worker --agent amp &
"$PYTHON" -m rolemesh.workers.autoevo_worker &

wait
