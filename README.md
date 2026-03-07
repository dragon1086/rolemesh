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

## Next
- tighten imports/package layout
- add unit tests and E2E smoke tests
- installer wizard (`rolemesh init`)
