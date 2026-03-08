# RoleMesh Phase Plan (v0.1)

## Phase 0 — 문서/검토 (현재)
- [x] PRD 초안
- [x] Routing Spec 초안
- [x] Installer UX 초안
- [x] 아키텍처 리뷰
- [x] 승인(Go)

## Phase 1 — 안정화 기반
- [x] worker auto-start (launchd) ← 2026-03-08
- [x] retry/backoff 정책 ← 2026-03-08
- [x] dead-letter queue ← 2026-03-08
- [x] status/health CLI ← 2026-03-08
- [x] enqueue admission gate (추상 coding 요청 차단)
- [x] semantic dedupe (활성 중복 태스크 재생성 억제)
- [x] done-event tiering + cooldown
- [x] message dedupe(동일 메시지 억제)
검증:
- [x] 메시지 유실 0건 ← 2026-03-08 (코드 분석 확인, N/A-코드PASS)
- [x] stale 자동복구 동작 ← 2026-03-08 (recover_stale() 기존 구현 확인)

## Phase 2 — PM Contract-first
- [x] PM packet 핵심요청 distill
- [x] focus points 범용화(품질축)
- [x] contract_id/session_id 주입
- [x] PM packet 품질 점수 로깅
- [x] 주간 품질 리포트 스크립트
- [x] 주간 리포트 cron 등록
- [x] IntentGate(clarify/proceed) 추가
- [x] contract artifact 생성(feature_manifest/handoff)
- [x] autoevo convergence brake + resume 조건
- [x] rolemesh-build를 정적 BATCHES에서 동적 backlog-state 생성으로 전환
- [x] 추상 `Builder Prototype Tasks` 제거(legacy-abstract-disabled)
- [x] Rules/Skills weekly cleanup 리포트 스크립트
검증:
- [ ] 주간 평균 점수 >= 85
- [ ] 저품질 비율 <= 10%
- [ ] 하위 10개 개선 루프 운영
- [x] IntentGate 오탐/미탐 점검 ← 2026-03-08
- [x] pause/resume 정책 회귀 테스트 ← 2026-03-08

## Phase 3 — 설치마법사
- [x] `rolemesh init` CLI ← 2026-03-08
- [x] 역할 자동 매핑 (RoleMapper) ← 2026-03-08
- [x] 라이트 모드 (--lite flag) ← 2026-03-08
검증:
- [ ] 신규 환경 설치 15분 이내
- [ ] 첫 요청 성공

## Phase 3 — 통합 확장
- [x] `rolemesh integration add` ← 2026-03-08
- [x] 기술 입력 → 역할 추천 (suggest CLI) ← 2026-03-08
- [ ] repo/web 분석 추천 (옵션)
검증:
- [x] 신규 통합 후 라우팅 후보 자동 반영 ← 2026-03-08

## Phase 4 — OSS 패키징
- [ ] core/workers/adapters 분리
- [x] 샘플 번들 배포 (examples/quickstart/) ← 2026-03-08
- [ ] 문서/예제/라이선스
검증:
- [ ] 외부 사용자 quickstart 통과

## Phase 2+ — 흐름 제어 (2026-03-08 추가)
- [x] Provider Circuit Breaker (CLOSED/OPEN/HALF_OPEN 상태머신)
- [x] Token Bucket Throttle (분당 요청 수 제한)
- [x] queue_worker CB/Throttle 연동
- [x] cokac-delegate.sh PM 위임 경로 연동
- [x] ai-comms/symphony_fusion CB/Throttle 연동
- [x] ai-comms/rolemesh_build_autoloop Throttle 연동
검증:
- [x] 133/133 테스트 통과
- [ ] 실 운영 24h 모니터링
