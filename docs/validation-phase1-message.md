# 검증 1: 메시지 유실 확인
**결과**: N/A (코드 분석 대체)
**날짜**: 2026-03-08

## 조회 결과

registry.db 파일 위치: `~/ai-comms/registry.db`
→ 현 세션 허용 디렉토리(`~/rolemesh`)가 아니어서 직접 SQL 쿼리 불가.

코드 분석(queue_worker.py)으로 대체:

| 항목 | 결과 |
|------|------|
| stale(30분+) running 복구 | recover_stale() 존재, 5분마다 자동 실행 |
| retry 미작동 의심 | retry 로직 구현됨 (max 3회, 지수 백오프 30→60→120s) |
| DLQ(dead_letter) 존재 | move_to_dlq() 구현됨, retry 3회 소진 시 이동 |
| 직접 DB 쿼리 | 세션 외부 경로로 불가 |

## 코드 근거

- `queue_worker.py` line 248-263: retry_count < 3이면 지수 백오프로 재시도
- `queue_worker.py` line 257: retry 소진 시 `client.move_to_dlq()` 호출
- `queue_worker.py` line 271-295: `recover_stale()` 함수 (임계값 1800초)
- `queue_worker.py` line 308-310: run_loop에서 300초마다 recover_stale() 호출

## 판정 근거

DB 직접 쿼리 불가로 N/A 처리. 그러나 코드 레벨에서 메시지 유실 방지 메커니즘
(retry, DLQ, stale 복구) 모두 구현 확인됨 → 코드 기준 PASS 수준.

**직접 검증 방법 (수동 실행 필요)**:
```bash
sqlite3 ~/ai-comms/registry.db "SELECT status, COUNT(*) FROM task_queue GROUP BY status;"
sqlite3 ~/ai-comms/registry.db "SELECT COUNT(*) FROM task_queue WHERE status='running' AND (strftime('%s','now') - strftime('%s', updated_at)) > 1800;"
```
