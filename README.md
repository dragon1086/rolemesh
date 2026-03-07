# RoleMesh

Role-first local AI orchestration for non-developers.

## Current Status
- ✅ Documentation baseline (PRD, architecture, routing, UX, tests)
- ✅ Core implementation migrated under `src/rolemesh/`
  - registry + routing
  - queue worker
  - message bus worker
  - auto-evolution worker + controls

## Structure
- `src/rolemesh/` core modules
- `scripts/` runtime scripts
- `docs/` product and architecture docs

## vNext (Contract-first)
- Contract-based PM routing packet (`contract_id`, `session_id`, acceptance/deliverables)
- PM packet quality scoring (JSONL)
- Weekly quality report: `scripts/update_pm_quality_weekly.sh`
- Design doc: `docs/VNext-Design.md`
- Engineering commit/push policy: `docs/Engineering-Rules.md`

## Next
- tighten imports/package layout
- add unit tests and E2E smoke tests
- installer wizard (`rolemesh init`)
