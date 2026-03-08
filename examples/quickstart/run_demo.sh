#!/usr/bin/env bash
# run_demo.sh — RoleMesh 데모: 태스크 enqueue → 상태 확인
#
# 사용법:
#   bash run_demo.sh
#
# 사전 조건:
#   1. pip install -e . (프로젝트 루트)
#   2. python3 -m rolemesh init
#   3. python3 -m rolemesh integration add --name demo-bot --role builder \
#        --endpoint http://localhost:8080 --capabilities "build,test"

set -euo pipefail

echo "=== RoleMesh Demo ==="
echo ""

# 1) 현재 등록된 통합 확인
echo "[1/3] 등록된 통합 목록:"
python3 -m rolemesh integration list || echo "  (등록된 통합 없음)"
echo ""

# 2) 라우팅 테스트 — "빌드 실행" 태스크에 적합한 에이전트 조회
echo "[2/3] 라우팅 조회: '빌드 실행'"
python3 -m rolemesh route "빌드 실행" || echo "  (적합한 에이전트 없음 — integration add 먼저 실행하세요)"
echo ""

# 3) 큐 상태 확인
echo "[3/3] 태스크 큐 상태:"
python3 -m rolemesh status
echo ""

echo "=== 데모 완료 ==="
echo "다음 단계: python3 -m rolemesh --help"
