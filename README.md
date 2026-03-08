# RoleMesh

Role-first local AI orchestration for non-developers.

## Quick Start

Get from zero to your first routed request in 3 steps:

```bash
# 1. Install
pip install -e .

# 2. Initialize (detects your environment, registers agents)
rolemesh init

# 3. Route a task
rolemesh route '코드 리뷰해줘'
```

That's it. RoleMesh finds the right agent for your task automatically.

## Architecture

```
                        ┌─────────────────────────────┐
                        │         User / CLI          │
                        └──────────────┬──────────────┘
                                       │  task text
                                       ▼
                        ┌─────────────────────────────┐
                        │       PM (RegistryClient)   │
                        │  • intent parsing           │
                        │  • capability matching      │
                        │  • contract routing         │
                        └──────────────┬──────────────┘
                                       │  WorkItem
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
               ┌──────────────┐ ┌──────────┐ ┌──────────────┐
               │   Builder    │ │ Analyst  │ │  AutoEvo     │
               │ (QueueWorker)│ │(AmpCaller│ │  Worker      │
               │ • executes   │ │• quality │ │• self-improve│
               │   tasks      │ │  scoring │ │• rule updates│
               └──────────────┘ └──────────┘ └──────────────┘
                          │            │
                          └────────────┘
                                       │  WorkResult
                                       ▼
                        ┌─────────────────────────────┐
                        │    SymphonyMACRS (Fusion)   │
                        │  • result aggregation       │
                        │  • round reporting          │
                        └─────────────────────────────┘
```

**Roles:**
- **PM** (`RegistryClient`) — routes tasks to the best registered agent by capability score
- **Builder** (`queue_worker`) — executes tasks from the SQLite queue
- **Analyst** (`amp_caller`) — quality scoring and PM packet evaluation
- **AutoEvo** (`autoevo_worker`) — self-evolving rules and skill cleanup

## Status

Check live worker health:

```bash
bash scripts/status.sh
```

Example output:
```
[rolemesh] Worker Status
──────────────────────────────
queue_worker      PID 12345  RUNNING
message_worker    PID 12346  RUNNING
autoevo_worker    not running

Task Queue:
  pending        : 3
  in_progress    : 1
  completed      : 47
  failed         : 0
```

## Running Tests

```bash
python3 -m pytest tests/ -q
```

## Phase Roadmap

- [x] **Phase 1** — Core stability: launchd retry, DLQ, health CLI
- [x] **Phase 2** — IntentGate regression & E2E smoke tests
- [ ] **Phase 3** — Contract-first PM routing (contract_id, acceptance criteria, JSONL scoring)
- [ ] **Phase 4** — Dashboard & weekly quality reports

## Structure

```
src/rolemesh/      # core Python package
scripts/           # shell worker launchers and status tools
tests/             # pytest test suite
docs/              # PRD, architecture, engineering rules
```

## Requirements

- Python >= 3.10
- httpx >= 0.27.0
