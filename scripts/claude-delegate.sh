#!/usr/bin/env bash
# claude-delegate.sh — claude 실행 전 Throttle/Circuit Breaker 체크 래퍼
#
# 사용법:
#   scripts/claude-delegate.sh [claude 옵션...] -- <prompt>
#   scripts/claude-delegate.sh -p "작업 내용"
#   scripts/claude-delegate.sh --version
#
# CB OPEN이면 exit 1. Throttle wait 필요하면 sleep 후 실행.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROVIDER="anthropic"

# Python 경로 자동 탐색 (venv 우선)
if [[ -f "$REPO_ROOT/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [[ -f "$REPO_ROOT/venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/venv/bin/python3"
else
    PYTHON="python3"
fi

# --version 플래그: CB/Throttle 체크 없이 claude --version 실행
if [[ "${1:-}" == "--version" ]]; then
    exec claude --version
fi

# ── 1. Circuit Breaker 체크 ─────────────────────────────────────────────────
CB_RESULT=$("$PYTHON" - <<'PYEOF'
import sys
sys.path.insert(0, '$REPO_ROOT/src')
try:
    from rolemesh.circuit_breaker import ProviderCircuitBreaker, CBState
    cb = ProviderCircuitBreaker()
    state = cb.get_state("$PROVIDER")
    remaining = cb.cooldown_remaining("$PROVIDER")
    if state == CBState.OPEN:
        print(f"OPEN:{remaining}")
    else:
        print(f"OK:{state.value}")
except Exception as e:
    print(f"ERR:{e}")
PYEOF
)

# 변수 치환 문제 방지를 위해 heredoc 방식 재작성
CB_RESULT=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
try:
    from rolemesh.circuit_breaker import ProviderCircuitBreaker, CBState
    cb = ProviderCircuitBreaker()
    state = cb.get_state('$PROVIDER')
    remaining = cb.cooldown_remaining('$PROVIDER')
    if state == CBState.OPEN:
        print(f'OPEN:{remaining}')
    else:
        print(f'OK:{state.value}')
except Exception as e:
    print(f'ERR:{e}')
")

CB_STATUS="${CB_RESULT%%:*}"
CB_DETAIL="${CB_RESULT#*:}"

if [[ "$CB_STATUS" == "OPEN" ]]; then
    echo "[claude-delegate] ❌ Circuit Breaker OPEN — anthropic 차단 중 (${CB_DETAIL}s 남음)" >&2
    echo "[claude-delegate] 재시도: ${CB_DETAIL}초 후 다시 시도하거나, CB 상태를 확인하세요." >&2
    exit 1
fi

if [[ "$CB_STATUS" == "ERR" ]]; then
    echo "[claude-delegate] ⚠️  CB 체크 실패 (${CB_DETAIL}) — 체크 없이 진행" >&2
fi

# ── 2. Throttle 체크 ──────────────────────────────────────────────────────────
THROTTLE_RESULT=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
try:
    from rolemesh.throttle import TokenBucketThrottle
    t = TokenBucketThrottle()
    result = t.acquire('$PROVIDER')
    if result is True:
        print('OK:0')
    else:
        print(f'WAIT:{result:.1f}')
except Exception as e:
    print(f'ERR:{e}')
")

TH_STATUS="${THROTTLE_RESULT%%:*}"
TH_DETAIL="${THROTTLE_RESULT#*:}"

if [[ "$TH_STATUS" == "WAIT" ]]; then
    WAIT_INT=$(printf "%.0f" "$TH_DETAIL")
    echo "[claude-delegate] ⏳ Throttle: ${TH_DETAIL}s 대기 중..." >&2
    sleep "$WAIT_INT"
fi

if [[ "$TH_STATUS" == "ERR" ]]; then
    echo "[claude-delegate] ⚠️  Throttle 체크 실패 (${TH_DETAIL}) — 체크 없이 진행" >&2
fi

# ── 3. claude 실행 ────────────────────────────────────────────────────────────
echo "[claude-delegate] ✅ CB=${CB_DETAIL}, Throttle=${TH_STATUS} — claude 실행" >&2
exec claude "$@"
