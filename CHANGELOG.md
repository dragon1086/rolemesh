# Changelog

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
