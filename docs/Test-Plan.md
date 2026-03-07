# RoleMesh Test Plan (vNext)

작성일: 2026-03-06 (updated: 2026-03-07)  
상태: Active

## 1) 목표
- 비개발자 설치 성공
- 라우팅 정확성/안정성 검증
- 메시지 유실/중복 없는 실행 보장

## 2) 테스트 레벨

### L1. 단위 테스트
- registry CRUD
- capability 등록/조회
- 라우팅 점수 계산
- 메시지 상태 전이(pending→processing→done/failed)
- stale recovery
- contract 생성기(`contracts.build_contract`) 필드 완전성 검증
- PM packet score 계산 정확성 검증(필수 필드 누락/충분 조건)

### L2. 통합 테스트
- queue_worker + message_worker 동시 실행
- send_message_auto 라우팅 검증
- adapter 호출 성공/실패 폴백
- PM routing packet에 `contract_id/session_id` 포함 여부 검증
- fallback message bus payload에 `pm_packet + contract` 포함 여부 검증
- IntentGate `clarify/proceed` 분기 검증
- contract artifact(`feature_manifest.json`, `handoff_progress.md`) 생성 검증
- admission gate(추상 coding 요청 차단) 검증
- autoevo pause/resume 조건(수동 트리거/외부 활성태스크/non-noop 회복) 검증

### L3. E2E 테스트
- 기본 번들(OpenClaw+cokac+amp+Telegram)
- 시나리오:
  1) 코드 요청 → Builder
  2) 분석 요청 → Analyst
  3) 일반 조정 요청 → PM
- 결과: 응답 성공, 로그 생성, 상태 정상

### L4. UX 테스트 (비개발자)
- 설치마법사 15분 내 완료 여부
- 실패 메시지 이해도
- 라이트 모드 온보딩 성공률

## 3) 품질 게이트
- 설치 성공률 > 90%
- 첫 요청 성공률 > 95%
- 라우팅 정확도 > 80%
- 메시지 유실률 0%
- 재시도 후 최종 실패는 DLQ로 100% 이동
- PM packet 평균 점수 >= 85
- 저품질(<70) 비율 <= 10%
- IntentGate 차단 정확도(스펙 미충족 coding) >= 95%
- contract artifact 생성 성공률 100%
- 주간 리포트 자동 생성 성공률 100%

## 4) 회귀 테스트 체크리스트
- 새 adapter 추가 후 기존 기본 번들 동작 유지
- 워커 재시작/재부팅 후 자동기동 확인
- routing_log/feedback 통계 정상

## 5) 테스트 아티팩트
- test report (markdown)
- routing sample logs
- worker health snapshots
- UX 시나리오 녹취/체크리스트
- `pm_packet_quality.jsonl` 샘플
- `pm-quality-weekly.md` 리포트 스냅샷

## 6) 릴리즈 전 승인 기준
- L1~L3 all pass
- UX critical issue 0
- known issue 문서화 완료
