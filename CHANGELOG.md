# Changelog

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
