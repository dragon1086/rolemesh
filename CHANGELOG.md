# Changelog

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
