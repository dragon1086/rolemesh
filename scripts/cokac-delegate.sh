#!/usr/bin/env bash
# cokac-delegate.sh — 록이(PM)가 cokac에 위임할 때 사용하는 표준 실행기
#
# 사용법:
#   scripts/cokac-delegate.sh -p "작업 내용"
#   scripts/cokac-delegate.sh --model claude-opus-4-5 -p "복잡한 작업"
#   scripts/cokac-delegate.sh --dangerously-skip-permissions -p "자동 승인 필요한 작업"
#
# 주의: 직접 `claude -p` 호출 금지. 이 스크립트를 통해서만 위임할 것.
# Throttle/CB/BatchCooldown이 자동 적용되어 Anthropic rate limit 방지.

set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
    SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$SCRIPT_DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DELEGATE="$SCRIPT_DIR/claude-delegate.sh"

# Python 경로 자동 탐색 (venv 우선)
if [[ -f "$REPO_ROOT/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [[ -f "$REPO_ROOT/venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/venv/bin/python3"
else
    PYTHON="python3"
fi

if [[ ! -f "$DELEGATE" ]]; then
    echo "[cokac-delegate] ❌ claude-delegate.sh 없음: $DELEGATE" >&2
    exit 1
fi

if [[ $# -eq 0 ]]; then
    echo "사용법: $0 [claude 옵션...] -p <prompt>" >&2
    echo "  예시: $0 -p '버그 수정해줘'" >&2
    echo "  예시: $0 --model claude-opus-4-5 -p '복잡한 리팩토링'" >&2
    echo "" >&2
    echo "이 스크립트는 록이(PM)가 cokac에 위임할 때 사용하는 표준 실행기입니다." >&2
    echo "직접 'claude -p' 호출은 금지되어 있습니다. (Delegation-Protocol.md 참조)" >&2
    exit 1
fi

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "[cokac-delegate] 📋 위임 시작: $TIMESTAMP" >&2
echo "[cokac-delegate] 인수: $*" >&2

# ── 1. Batch Cooldown 체크 ────────────────────────────────────────────────────
COOLDOWN_RESULT=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
try:
    from rolemesh.adapters.batch_cooldown import BatchCooldown
    bc = BatchCooldown()
    remaining = bc.acquire()
    if remaining > 0.0:
        print(f'WAIT:{remaining:.1f}')
    else:
        print('OK:0')
except Exception as e:
    print(f'ERR:{e}')
")

CD_STATUS="${COOLDOWN_RESULT%%:*}"
CD_DETAIL="${COOLDOWN_RESULT#*:}"

if [[ "$CD_STATUS" == "WAIT" ]]; then
    WAIT_INT=$(printf "%.0f" "$CD_DETAIL")
    echo "[cokac-delegate] ⏳ 배치 쿨다운: ${CD_DETAIL}s 대기 중..." >&2
    sleep "$WAIT_INT"
fi

if [[ "$CD_STATUS" == "ERR" ]]; then
    echo "[cokac-delegate] ⚠️  BatchCooldown 체크 실패 (${CD_DETAIL}) — 체크 없이 진행" >&2
fi

# ── 2. claude-delegate.sh로 위임 (CB/Throttle 체크 포함) ─────────────────────
DELEGATE_EXIT=0
"$DELEGATE" "$@" || DELEGATE_EXIT=$?

# ── 3. 배치 완료 시간 기록 ────────────────────────────────────────────────────
"$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
try:
    from rolemesh.adapters.batch_cooldown import BatchCooldown
    BatchCooldown().record_complete()
except Exception:
    pass
" 2>/dev/null || true

exit "$DELEGATE_EXIT"
