# RoleMesh Test Plan (v0.1)

작성일: 2026-03-06  
상태: Draft

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

### L2. 통합 테스트
- queue_worker + message_worker 동시 실행
- send_message_auto 라우팅 검증
- adapter 호출 성공/실패 폴백

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

## 4) 회귀 테스트 체크리스트
- 새 adapter 추가 후 기존 기본 번들 동작 유지
- 워커 재시작/재부팅 후 자동기동 확인
- routing_log/feedback 통계 정상

## 5) 테스트 아티팩트
- test report (markdown)
- routing sample logs
- worker health snapshots
- UX 시나리오 녹취/체크리스트

## 6) 릴리즈 전 승인 기준
- L1~L3 all pass
- UX critical issue 0
- known issue 문서화 완료
