# 검증 2: stale 자동복구 동작 확인
**결과**: PASS
**날짜**: 2026-03-08

## 분석 결과

| 항목 | 값 |
|------|-----|
| recover_stale() 함수 존재 | Y |
| 임계값 | 1800초 (30분) |
| 위치 (파일:라인) | queue_worker.py:271 |
| 루프 통합 여부 | Y — run_loop() line 308-310 |
| 실행 주기 | 300초 (5분)마다 |

## 코드 근거

recover_stale(stale_threshold_seconds=1800) @ queue_worker.py:271
- running 상태 + updated_at < (now - 1800) → pending으로 복귀
- STALE_RECOVER_INTERVAL=300 → run_loop에서 5분마다 자동 호출

## 판정 근거

기존 코드에 이미 구현됨. 임계값 1800초(30분)로 요구사항 충족. **PASS**.
