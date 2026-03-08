#!/bin/bash
# RoleMesh 워커 전체 시작 스크립트 (launchd 진입점)
set -euo pipefail

PYTHON=/opt/homebrew/bin/python3
PROJECT=/Users/rocky/rolemesh

export PYTHONPATH="$PROJECT/src"

cd "$PROJECT"

echo "[rolemesh] 워커 시작: $(date)" >&2

"$PYTHON" -m rolemesh.queue_worker &
"$PYTHON" -m rolemesh.message_worker &
"$PYTHON" -m rolemesh.autoevo_worker &

wait
