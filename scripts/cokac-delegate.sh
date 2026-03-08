#!/usr/bin/env bash
# cokac-delegate.sh — 록이(PM)가 cokac에 위임할 때 사용하는 표준 실행기
#
# 사용법:
#   scripts/cokac-delegate.sh -p "작업 내용"
#   scripts/cokac-delegate.sh --model claude-opus-4-5 -p "복잡한 작업"
#   scripts/cokac-delegate.sh --dangerously-skip-permissions -p "자동 승인 필요한 작업"
#
# 주의: 직접 `claude -p` 호출 금지. 이 스크립트를 통해서만 위임할 것.
# Throttle/CB가 자동 적용되어 Anthropic rate limit 방지.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELEGATE="$SCRIPT_DIR/claude-delegate.sh"

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

# claude-delegate.sh로 위임 (CB/Throttle 체크 포함)
exec "$DELEGATE" "$@"
