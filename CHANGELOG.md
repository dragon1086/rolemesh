# Changelog

## [0.2.3] - 2026-03-09

### Fixed
- 30~31차 완성도 작업을 릴리스에 반영해 logging 전환, 입력 검증, 에러 메시지, `__all__`, docstring, 타입 힌트 정리를 공식화
- `src/rolemesh/adapters/amp_caller.py`와 `src/rolemesh/routing/symphony_fusion.py`의 비-CLI `print()` 사용을 제거해 사용자 출력과 라이브러리 경계를 분리
- `amp_caller`, `circuit_breaker`, `throttle`의 상태 파일/로그 파일 저장 실패를 무음 `pass` 대신 디버그 로그로 남기도록 보강

## [0.2.2] - 2026-03-08

### Fixed
- message worker에 stale message 복구 로깅과 루프 단위 예외 경계를 추가해 소비 루프 중단 리스크를 완화
- autoevo state 저장을 atomic replace로 바꿔 pause/resume 상태파일 partial write 가능성을 제거
- autoevo enqueue를 태스크 단위 예외 처리로 분리해 단일 enqueue 실패가 라운드 전체를 끊지 않도록 보강
- autoevo 루프에서 DB connection을 iteration마다 재확인해 장시간 실행 중 stale connection 복구성을 높임
- README/패키지 버전을 `v0.2.2`로 정리하고 Codex Pro 일시적 builder 전제 문구를 일반 Codex builder 표현으로 유지

## [0.2.1] - 2026-03-08

### Fixed
- Atomic save 적용으로 state 파일 쓰기 중단 시 partial write 리스크 완화 (20차)
- shared DB connection pool로 `QualityTracker`/registry 경로의 연결 재사용 안정화 (21차)
- timeout 예외를 재시도·DLQ 분기로 명확히 구분해 워커 오동작 감소 (22차)
- comms/delegate 스크립트 경로를 실제 설치 위치 기준으로 수정 (23차)
- round reporter의 `DONE_REPORT_V1` 파싱을 multiline/code-block payload까지 허용하도록 보강 (25차)
- `DONE_REPORT_V1`에 `score`가 없을 때 대체 점수 키를 허용하고 없으면 안전하게 skip 처리 (25차)
- amp fallback 결과를 `SymphonyMACRS`가 `done`으로 오인하지 않도록 `WorkResult.status` 일관성 수정 (25차)
- `ask_amp_async()` 재시도 횟수를 동기 버전과 일치시켜 timeout 처리 편차 제거 (25차)

## [0.2.0] - 2026-03-08

### Added
- SmartRouter: Anthropic -> Codex -> Gemini 자동 fallback (17차)
- `scripts/smart-delegate.sh`: provider 자동 선택 위임 진입점
- QualityTracker: 배치 품질 점수 수집 + 주간 평균 추적 (18차)
- `scripts/quality-report.sh`: quality report CLI
- `scripts/codex-delegate.sh`: Codex 빌더 전용 위임 진입점 (16차)
- `integration add` 시 `delegate.sh` 자동 생성 (15차)

## [0.1.0] - 2026-03-08

### Phase 1 — Core Stability
- launchd-based worker auto-restart with configurable retry backoff
- Dead Letter Queue (DLQ) for failed tasks with requeue support
- Health CLI (`rolemesh status`) showing per-worker PID and queue counts
- `scripts/status.sh` for shell-level process inspection

### Phase 2 — IntentGate & Testing
- IntentGate regression suite preventing routing regressions
- E2E smoke tests covering init → route → queue → result cycle
- `completed_with_announce_error` status for partial success tracking
- Unit tests for registry, queue worker, and symphony fusion modules

### Packaging
- `pyproject.toml` with setuptools build backend
- `rolemesh` CLI entry point (`rolemesh init`, `agents`, `status`, `route`)
- Package installable via `pip install -e .`
- Relative imports throughout `src/rolemesh/` for correct installed-package behavior
