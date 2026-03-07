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
검증:
- [ ] 메시지 유실 0건
- [ ] stale 자동복구 동작

## Phase 2 — 설치마법사
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
