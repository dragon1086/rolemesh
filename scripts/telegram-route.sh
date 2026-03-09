#!/usr/bin/env bash
# telegram-route.sh — Telegram 메시지를 RoleMesh 라우팅 결정으로 변환
#
# 사용법:
#   scripts/telegram-route.sh '메시지 텍스트'

set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
    SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$SCRIPT_DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ $# -ne 1 ]]; then
    echo "사용법: $0 '메시지 텍스트'" >&2
    exit 1
fi

if [[ -f "$REPO_ROOT/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [[ -f "$REPO_ROOT/venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/venv/bin/python3"
else
    PYTHON="python3"
fi

"$PYTHON" -c '
import json
import sys

from rolemesh.gateway.telegram_bridge import TelegramBridge

result = TelegramBridge().route(sys.argv[1]).to_dict()
payload = {
    "class": result["message_class"],
    "provider": result["provider"],
    "delegate_script": result["delegate_script"],
    "reason": result["reason"],
}
print(json.dumps(payload, ensure_ascii=False))
' "$1"
