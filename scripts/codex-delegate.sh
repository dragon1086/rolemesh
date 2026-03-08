#!/usr/bin/env bash
# codex-delegate.sh — 록이(PM)가 codex에 위임할 때 사용하는 표준 실행기
#
# 사용법:
#   scripts/codex-delegate.sh -C /path/to/project 'prompt'
#
# BatchCooldown / CircuitBreaker / Throttle 자동 적용.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROVIDER="openai-codex"

# Python 경로 자동 탐색 (venv 우선)
if [[ -f "$REPO_ROOT/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [[ -f "$REPO_ROOT/venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/venv/bin/python3"
else
    PYTHON="python3"
fi

if [[ $# -ne 3 ]]; then
    echo "사용법: $0 -C /path/to/project 'prompt'" >&2
    echo "  예시: $0 -C ~/rolemesh '테스트 고쳐줘'" >&2
    exit 1
fi

if [[ "${1:-}" != "-C" ]]; then
    echo "사용법: $0 -C /path/to/project 'prompt'" >&2
    exit 1
fi

WORKDIR="${2:-}"
PROMPT="${3:-}"

if [[ ! -d "$WORKDIR" ]]; then
    echo "[codex-delegate] ❌ 작업 디렉터리 없음: $WORKDIR" >&2
    exit 1
fi

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "[codex-delegate] 📋 위임 시작: $TIMESTAMP" >&2
echo "[codex-delegate] workdir: $WORKDIR" >&2

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
    echo "[codex-delegate] ⏳ 배치 쿨다운: ${CD_DETAIL}s 대기 중..." >&2
    sleep "$WAIT_INT"
fi

if [[ "$CD_STATUS" == "ERR" ]]; then
    echo "[codex-delegate] ⚠️  BatchCooldown 체크 실패 (${CD_DETAIL}) — 체크 없이 진행" >&2
fi

# ── 2. Circuit Breaker 체크 ───────────────────────────────────────────────────
CB_RESULT=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
try:
    from rolemesh.adapters.circuit_breaker import ProviderCircuitBreaker, CBState
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
    echo "[codex-delegate] ❌ Circuit Breaker OPEN — $PROVIDER 차단 중 (${CB_DETAIL}s 남음)" >&2
    exit 1
fi

if [[ "$CB_STATUS" == "ERR" ]]; then
    echo "[codex-delegate] ⚠️  CB 체크 실패 (${CB_DETAIL}) — 체크 없이 진행" >&2
fi

# ── 3. Throttle 체크 ─────────────────────────────────────────────────────────
THROTTLE_RESULT=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
try:
    from rolemesh.adapters.throttle import TokenBucketThrottle
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
    echo "[codex-delegate] ⏳ Throttle: ${TH_DETAIL}s 대기 중..." >&2
    sleep "$WAIT_INT"
fi

if [[ "$TH_STATUS" == "ERR" ]]; then
    echo "[codex-delegate] ⚠️  Throttle 체크 실패 (${TH_DETAIL}) — 체크 없이 진행" >&2
fi

# ── 4. codex 실행 ─────────────────────────────────────────────────────────────
echo "[codex-delegate] ✅ CB=${CB_DETAIL}, Throttle=${TH_STATUS} — codex 실행" >&2
DELEGATE_EXIT=0
codex exec -s danger-full-access --model gpt-5.4 -C "$WORKDIR" "$PROMPT" || DELEGATE_EXIT=$?

# ── 5. 배치 완료 시간 기록 ───────────────────────────────────────────────────
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
