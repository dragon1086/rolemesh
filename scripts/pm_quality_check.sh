#!/usr/bin/env bash
# pm_quality_check.sh — PM packet quality 평균 점수 출력
# 대상: ~/ai-comms/pm_packet_quality.jsonl 또는 ~/rolemesh/pm_quality.jsonl
# 없으면 N/A 출력 (실패하지 않음)

set -euo pipefail

JSONL_FILES=(
    "$HOME/ai-comms/pm_packet_quality.jsonl"
    "$HOME/ai-comms/pm_quality.jsonl"
    "$HOME/rolemesh/pm_quality.jsonl"
)

# 존재하는 파일 중 첫 번째 사용
FOUND=""
for f in "${JSONL_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        FOUND="$f"
        break
    fi
done

if [[ -z "$FOUND" ]]; then
    echo "N/A (파일 없음: ${JSONL_FILES[*]})"
    exit 0
fi

python3 - "$FOUND" <<'PYEOF'
import json
import sys

path = sys.argv[1]
scores = []

try:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if "score" in row:
                    scores.append(float(row["score"]))
            except Exception:
                continue
except Exception as e:
    print(f"N/A (읽기 오류: {e})")
    sys.exit(0)

if not scores:
    print("N/A (점수 데이터 없음)")
else:
    avg = sum(scores) / len(scores)
    mn = min(scores)
    mx = max(scores)
    print(f"평균 PM 품질 점수: {avg:.1f}  (최소 {mn:.1f} / 최대 {mx:.1f} / 총 {len(scores)}건)")
    print(f"파일: {path}")
PYEOF
