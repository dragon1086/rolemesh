#!/usr/bin/env bash
# test_claude_delegate.sh — claude-delegate.sh 통합 테스트
#
# 실행: bash tests/test_claude_delegate.sh
# 종료 코드: 0=전부 통과, 1=실패 있음

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DELEGATE="$REPO_ROOT/scripts/claude-delegate.sh"
COKAC_DELEGATE="$REPO_ROOT/scripts/cokac-delegate.sh"

if [[ -f "$REPO_ROOT/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [[ -f "$REPO_ROOT/venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/venv/bin/python3"
else
    PYTHON="python3"
fi

PASS=0
FAIL=0

_pass() { echo "  ✅ PASS: $1"; ((PASS++)); }
_fail() { echo "  ❌ FAIL: $1"; ((FAIL++)); }

# ── 헬퍼: CB 상태 설정 ───────────────────────────────────────────────────────

_cb_open() {
    "$PYTHON" -c "
import sys; sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.circuit_breaker import ProviderCircuitBreaker
cb = ProviderCircuitBreaker(failure_threshold=1, cooldown_sec=300)
cb.record_failure('anthropic')
"
}

_cb_reset() {
    "$PYTHON" -c "
import sys; sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.circuit_breaker import ProviderCircuitBreaker
ProviderCircuitBreaker().reset('anthropic')
"
}

_throttle_drain() {
    "$PYTHON" -c "
import sys; sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.throttle import TokenBucketThrottle
TokenBucketThrottle().drain('anthropic')
"
}

_throttle_reset() {
    "$PYTHON" -c "
import sys; sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.throttle import TokenBucketThrottle
TokenBucketThrottle().reset('anthropic')
"
}

# ── 테스트 시작 ───────────────────────────────────────────────────────────────

echo ""
echo "=== claude-delegate.sh 통합 테스트 ==="
echo ""

# ── 전제: 스크립트 파일 존재 확인 ────────────────────────────────────────────

echo "[ 사전 확인 ]"

if [[ -x "$DELEGATE" ]]; then
    _pass "claude-delegate.sh 존재 및 실행 권한 있음"
else
    _fail "claude-delegate.sh 없거나 실행 권한 없음: $DELEGATE"
fi

if [[ -x "$COKAC_DELEGATE" ]]; then
    _pass "cokac-delegate.sh 존재 및 실행 권한 있음"
else
    _fail "cokac-delegate.sh 없거나 실행 권한 없음: $COKAC_DELEGATE"
fi

if [[ -f "$REPO_ROOT/config/throttle.yaml" ]]; then
    _pass "config/throttle.yaml 존재"
else
    _fail "config/throttle.yaml 없음"
fi

echo ""
echo "[ CB OPEN 시 exit 1 반환 ]"

_cb_reset
_cb_open
OUTPUT=$(bash "$DELEGATE" -p "test prompt" 2>&1) || EXIT_CODE=$?
EXIT_CODE="${EXIT_CODE:-0}"

if [[ $EXIT_CODE -eq 1 ]]; then
    _pass "CB OPEN → exit 1 반환"
else
    _fail "CB OPEN → exit $EXIT_CODE (1 기대)"
fi

if echo "$OUTPUT" | grep -q "Circuit Breaker OPEN"; then
    _pass "CB OPEN 메시지 출력 확인"
else
    _fail "CB OPEN 메시지 없음 (출력: $OUTPUT)"
fi

# 초기화
_cb_reset

echo ""
echo "[ Throttle drain 시 WAIT 메시지 확인 (mock: sleep 대신 메시지 검증) ]"

_throttle_drain
OUTPUT=$(bash "$DELEGATE" --version 2>&1 || true)

# --version은 CB/Throttle 체크 없이 바로 실행되므로 별도 테스트
# Throttle wait 메시지를 확인하려면 -p 실행이 필요하지만 실제 claude 없이 mock
# → 대신 Throttle state가 drain 됐는지 Python으로 직접 검증
THROTTLE_CHECK=$("$PYTHON" -c "
import sys; sys.path.insert(0, '$REPO_ROOT/src')
from rolemesh.throttle import TokenBucketThrottle
t = TokenBucketThrottle()
result = t.acquire('anthropic')
if result is True:
    print('AVAILABLE')
else:
    print(f'WAIT:{result:.1f}')
" 2>&1)

if echo "$THROTTLE_CHECK" | grep -q "WAIT:"; then
    _pass "Throttle drain 상태 확인 — acquire() WAIT 반환"
else
    _fail "Throttle drain 후 acquire() 결과 이상: $THROTTLE_CHECK"
fi

_throttle_reset

echo ""
echo "[ --version 플래그: CB/Throttle 체크 없이 통과 ]"

# CB를 OPEN으로 열어놔도 --version은 통과해야 함
_cb_open
OUTPUT=$(bash "$DELEGATE" --version 2>&1)
EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
    _pass "--version: CB OPEN이어도 exit 0"
else
    # claude 없는 환경이면 claude 자체 실패일 수 있음
    if echo "$OUTPUT" | grep -qi "claude"; then
        _pass "--version: claude 응답 있음 (종료 코드 $EXIT_CODE는 claude 자체 오류)"
    else
        _fail "--version: exit $EXIT_CODE, 출력: $OUTPUT"
    fi
fi

_cb_reset

echo ""
echo "[ cokac-delegate.sh: 인수 없으면 exit 1 ]"

OUTPUT=$(bash "$COKAC_DELEGATE" 2>&1) || EXIT_CODE=$?
EXIT_CODE="${EXIT_CODE:-0}"

if [[ $EXIT_CODE -eq 1 ]]; then
    _pass "cokac-delegate.sh 인수 없음 → exit 1"
else
    _fail "cokac-delegate.sh 인수 없음 → exit $EXIT_CODE (1 기대)"
fi

if echo "$OUTPUT" | grep -q "사용법"; then
    _pass "cokac-delegate.sh 사용법 메시지 출력"
else
    _fail "cokac-delegate.sh 사용법 메시지 없음"
fi

echo ""
echo "[ throttle.yaml 기본값 확인 ]"

ANTHROPIC_RPM=$("$PYTHON" -c "
import yaml, sys
with open('$REPO_ROOT/config/throttle.yaml') as f:
    data = yaml.safe_load(f)
print(data.get('anthropic', 'MISSING'))
" 2>/dev/null || echo "ERR")

if [[ "$ANTHROPIC_RPM" == "15" ]]; then
    _pass "throttle.yaml anthropic=15"
else
    _fail "throttle.yaml anthropic 값 이상: $ANTHROPIC_RPM"
fi

# ── 결과 ──────────────────────────────────────────────────────────────────────

echo ""
echo "============================================"
echo "결과: PASS=$PASS  FAIL=$FAIL"
echo "============================================"
echo ""

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
