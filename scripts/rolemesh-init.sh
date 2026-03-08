#!/bin/bash
# rolemesh-init.sh — RoleMesh Installer Wizard 래퍼
# 사용: bash ~/rolemesh/scripts/rolemesh-init.sh

set -euo pipefail

PYTHON=/opt/homebrew/bin/python3
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"

export PYTHONPATH="$PROJECT/src"

cd "$PROJECT"

exec "$PYTHON" -m rolemesh.installer "$@"
