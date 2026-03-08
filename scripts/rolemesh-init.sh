#!/bin/bash
# rolemesh-init.sh — RoleMesh Installer Wizard 래퍼
# 사용: bash ~/rolemesh/scripts/rolemesh-init.sh

set -euo pipefail

PYTHON=/opt/homebrew/bin/python3
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="$PROJECT/src:$PYTHONPATH"
else
  export PYTHONPATH="$PROJECT/src"
fi

cd "$PROJECT"

exec "$PYTHON" -m rolemesh.cli.installer "$@"
