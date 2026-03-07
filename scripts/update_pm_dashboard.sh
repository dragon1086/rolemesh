#!/bin/bash
set -euo pipefail
DB="$HOME/ai-comms/registry.db"
OUT="$HOME/obsidian-vault/projects/pm-dashboard.md"
NOW=$(date '+%Y-%m-%d %H:%M %Z')

q(){ sqlite3 -noheader "$DB" "$1"; }

ROLE_DONE=$(q "select count(*) from task_queue where source='rolemesh-autoevo' and status='done';")
ROLE_RUN=$(q "select count(*) from task_queue where source='rolemesh-autoevo' and status='running';")
ROLE_PEN=$(q "select count(*) from task_queue where source='rolemesh-autoevo' and status='pending';")
ROLE_FAIL=$(q "select count(*) from task_queue where source='rolemesh-autoevo' and status='failed';")

PAPER_DONE=$(q "select count(*) from task_queue where source='paper-autoevo' and status='done';")
PAPER_RUN=$(q "select count(*) from task_queue where source='paper-autoevo' and status='running';")
PAPER_PEN=$(q "select count(*) from task_queue where source='paper-autoevo' and status='pending';")
PAPER_FAIL=$(q "select count(*) from task_queue where source='paper-autoevo' and status='failed';")

ROLE_LAST=$(q "select ifnull(max(datetime(done_at,'unixepoch','localtime')),'-') from task_queue where source='rolemesh-autoevo' and done_at is not null;")
PAPER_LAST=$(q "select ifnull(max(datetime(done_at,'unixepoch','localtime')),'-') from task_queue where source='paper-autoevo' and done_at is not null;")

# 안정성 지표: 중복 억제/스펙부재 거부 카운트 (최근 24h)
ROLE_DEDUP_24H=$(q "select count(*) from task_queue where source='rolemesh-autoevo' and created_at >= strftime('%s','now')-86400 and (coalesce(result_summary,'') like '%already-implemented-repeat%' or coalesce(result_summary,'') like '%spec-missing-repeat%' or coalesce(error,'') like '%already-implemented-repeat%' or coalesce(error,'') like '%spec-missing-repeat%');")
ROLE_SPEC_REJECT_24H=$(q "select count(*) from task_queue where source='rolemesh-autoevo' and created_at >= strftime('%s','now')-86400 and (coalesce(result_summary,'') like '%스펙 부재%' or coalesce(error,'') like '%스펙 부재%');")
RB_BUILDER_REPEAT_24H=$(q "select count(*) from task_queue where source='rolemesh-autoevo' and created_at >= strftime('%s','now')-86400 and lower(title) like '%builder prototype tasks%';")

cat > "$OUT" <<MD
# PM Dashboard

업데이트: $NOW

## 1) RoleMesh 구축
- Done: $ROLE_DONE
- Running: $ROLE_RUN
- Pending: $ROLE_PEN
- Failed: $ROLE_FAIL
- Last Done: $ROLE_LAST

### 안정성 지표 (최근 24h)
- Dedupe/Repeat 억제 시그널: $ROLE_DEDUP_24H
- 스펙 부재 거부 건수: $ROLE_SPEC_REJECT_24H
- Builder Prototype Tasks 생성 건수: $RB_BUILDER_REPEAT_24H

## 2) 논문 개선 (N-cycle)
- Done: $PAPER_DONE
- Running: $PAPER_RUN
- Pending: $PAPER_PEN
- Failed: $PAPER_FAIL
- Last Done: $PAPER_LAST

## 최근 RoleMesh 작업 5개
$(sqlite3 -line "$DB" "select title, status, datetime(done_at,'unixepoch','localtime') as done_at from task_queue where source='rolemesh-autoevo' order by created_at desc limit 5;" | sed 's/^/  /')

## 최근 논문 작업 5개
$(sqlite3 -line "$DB" "select title, status, datetime(done_at,'unixepoch','localtime') as done_at from task_queue where source='paper-autoevo' order by created_at desc limit 5;" | sed 's/^/  /')

## Top Blockers (최근 24h)
$(sqlite3 -line "$DB" "
SELECT
  CASE
    WHEN coalesce(error,'') LIKE '%spec too generic%' THEN 'spec-too-generic-blocked'
    WHEN coalesce(error,'') LIKE '%스펙 부재%' OR coalesce(result_summary,'') LIKE '%스펙 부재%' THEN 'spec-missing'
    WHEN coalesce(error,'') LIKE '%already-implemented-repeat%' OR coalesce(result_summary,'') LIKE '%already-implemented-repeat%' THEN 'already-implemented-repeat'
    WHEN coalesce(error,'') LIKE '%spec-missing-repeat%' OR coalesce(result_summary,'') LIKE '%spec-missing-repeat%' THEN 'spec-missing-repeat'
    ELSE 'other'
  END AS blocker,
  COUNT(*) AS cnt
FROM task_queue
WHERE created_at >= strftime('%s','now')-86400
  AND source IN ('rolemesh-autoevo','rolemesh-build')
  AND (status='failed' OR coalesce(error,'')<>'' OR coalesce(result_summary,'')<>'')
GROUP BY blocker
ORDER BY cnt DESC
LIMIT 5;
" | sed 's/^/  /')
MD

echo "updated: $OUT"
