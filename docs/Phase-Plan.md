# RoleMesh Phase Plan (v0.1)

## Phase 0 — 문서/검토 (현재)
- [x] PRD 초안
- [x] Routing Spec 초안
- [x] Installer UX 초안
- [ ] 아키텍처 리뷰
- [ ] 승인(Go)

## Phase 1 — 안정화 기반
- [ ] worker auto-start (launchd)
- [ ] retry/backoff 정책
- [ ] dead-letter queue
- [ ] status/health CLI
- [x] enqueue admission gate (추상 coding 요청 차단)
- [x] semantic dedupe (활성 중복 태스크 재생성 억제)
- [x] done-event tiering + cooldown
- [x] message dedupe(동일 메시지 억제)
검증:
- [ ] 메시지 유실 0건
- [ ] stale 자동복구 동작

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
- [x] Rules/Skills weekly cleanup 리포트 스크립트
검증:
- [ ] 주간 평균 점수 >= 85
- [ ] 저품질 비율 <= 10%
- [ ] 하위 10개 개선 루프 운영
- [ ] IntentGate 오탐/미탐 점검
- [ ] pause/resume 정책 회귀 테스트

## Phase 3 — 설치마법사
- [ ] `rolemesh init` CLI
- [ ] 역할 자동 매핑
- [ ] 라이트 모드
검증:
- [ ] 신규 환경 설치 15분 이내
- [ ] 첫 요청 성공

## Phase 3 — 통합 확장
- [ ] `rolemesh integration add`
- [ ] 기술 입력 -> 역할 추천
- [ ] repo/web 분석 추천 (옵션)
검증:
- [ ] 신규 통합 후 라우팅 후보 자동 반영

## Phase 4 — OSS 패키징
- [ ] core/workers/adapters 분리
- [ ] 샘플 번들 배포
- [ ] 문서/예제/라이선스
검증:
- [ ] 외부 사용자 quickstart 통과
