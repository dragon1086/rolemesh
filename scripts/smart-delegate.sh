#!/usr/bin/env bash
# smart-delegate.sh — smart-delegate provider fallback wrapper
#
# 사용법:
#   scripts/smart-delegate.sh -C /path/to/project 'prompt'

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Python 경로 자동 탐색 (venv 우선)
if [[ -f "$REPO_ROOT/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [[ -f "$REPO_ROOT/venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/venv/bin/python3"
else
    PYTHON="python3"
fi

if [[ $# -ne 3 || "${1:-}" != "-C" ]]; then
    echo "사용법: $0 -C /path/to/project 'prompt'" >&2
    echo "  예시: $0 -C ~/rolemesh '테스트 고쳐줘'" >&2
    exit 1
fi

WORKDIR="${2:-}"
PROMPT="${3:-}"

if [[ ! -d "$WORKDIR" ]]; then
    echo "[smart-delegate] ❌ 작업 디렉터리 없음: $WORKDIR" >&2
    exit 1
fi

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "[smart-delegate] 📋 위임 시작: $TIMESTAMP" >&2
echo "[smart-delegate] workdir: $WORKDIR" >&2

ATTEMPT=1
MAX_ATTEMPTS=3
ATTEMPTED=""
LAST_PROVIDER=""
LAST_EXIT=1

while [[ $ATTEMPT -le $MAX_ATTEMPTS ]]; do
    PROVIDER=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.adapters.smart_router import SmartRouter

attempted = [p for p in '$ATTEMPTED'.split(',') if p]
providers = [p for p in SmartRouter().providers if p not in attempted]
router = SmartRouter(providers=providers)
print(router.get_available_provider() or '')
")

    if [[ -z "$PROVIDER" ]]; then
        break
    fi

    DELEGATE_SCRIPT=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.adapters.smart_router import SmartRouter
print(SmartRouter().get_delegate_script_path('$PROVIDER'))
")

    echo "[smart-delegate] attempt ${ATTEMPT}/${MAX_ATTEMPTS}: provider=$PROVIDER" >&2
    LAST_PROVIDER="$PROVIDER"
    DELEGATE_EXIT=0

    case "$PROVIDER" in
        anthropic)
            "$DELEGATE_SCRIPT" -p "$PROMPT" || DELEGATE_EXIT=$?
            ;;
        openai-codex)
            "$DELEGATE_SCRIPT" -C "$WORKDIR" "$PROMPT" || DELEGATE_EXIT=$?
            ;;
        gemini)
            "$DELEGATE_SCRIPT" -p "$PROMPT" || DELEGATE_EXIT=$?
            ;;
        *)
            echo "[smart-delegate] ❌ 알 수 없는 provider: $PROVIDER" >&2
            exit 1
            ;;
    esac

    if [[ $DELEGATE_EXIT -eq 0 ]]; then
        "$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.adapters.smart_router import SmartRouter
SmartRouter().record_success('$PROVIDER')
" 2>/dev/null || true
        exit 0
    fi

    "$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.adapters.smart_router import SmartRouter
SmartRouter().record_failure('$PROVIDER')
" 2>/dev/null || true

    echo "[smart-delegate] ⚠️  provider 실패: $PROVIDER (exit=$DELEGATE_EXIT)" >&2
    LAST_EXIT=$DELEGATE_EXIT
    if [[ -z "$ATTEMPTED" ]]; then
        ATTEMPTED="$PROVIDER"
    else
        ATTEMPTED="$ATTEMPTED,$PROVIDER"
    fi
    ATTEMPT=$((ATTEMPT + 1))
done

echo "[smart-delegate] ❌ 모든 fallback 시도 실패" >&2
if [[ -n "$LAST_PROVIDER" ]]; then
    echo "[smart-delegate] 마지막 provider: $LAST_PROVIDER (exit=$LAST_EXIT)" >&2
fi
exit 1
