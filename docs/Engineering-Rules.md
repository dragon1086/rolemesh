# RoleMesh Engineering Rules

## 1) Commit Cadence (핵심 규칙)
**작은 단위로 자주 커밋한다.**

- 기본: 20~40분 또는 의미 있는 변경 1세트마다 커밋
- 커밋 기준:
  - 동작하는 최소 단위(compile/test 가능한 상태)
  - 변경 의도가 메시지에 명확히 드러남
- 금지:
  - 대규모 변경을 한 번에 뭉쳐 커밋
  - 실행 불가능/깨진 상태 커밋(긴급 hotfix 제외)

## 2) Push Policy
- 최소 하루 1회 이상 push
- 핵심 변경(라우팅/큐/안정성)은 커밋 직후 push
- 장시간 로컬 체류 금지(분실/충돌 리스크)

## 3) Message Quality
- 커밋 메시지 템플릿:
  - `feat: ...`
  - `fix: ...`
  - `refactor: ...`
  - `docs: ...`
  - `test: ...`
- 예시:
  - `fix: add autoevo convergence brake and resume conditions`
  - `feat: add contract artifacts (feature_manifest/handoff)`

## 4) Review Hygiene
- 변경 후 최소 1회:
  - `python3 -m py_compile` 또는 테스트
  - 실행 로그/리포트 생성 확인
- PR/병합 전:
  - PRD/Test-Plan/Phase-Plan 문서 동기화

## 5) Ops-Safe Rule
- 운영 노이즈를 키우는 변경은 기본 거부
- 알림/큐/오토루프 관련 변경은 반드시 cooldown/dedupe 관점 검토
