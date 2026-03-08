# RoleMesh

Role-first local AI orchestration for non-developers.

Current release: `v0.2.1`

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
                        │ PM (RegistryClient +        │
                        │ SmartRouter)                │
                        │  • intent parsing           │
                        │  • capability matching      │
                        │  • provider failover        │
                        │  • contract routing         │
                        └──────────────┬──────────────┘
                                       │  WorkItem
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
               ┌──────────────┐ ┌──────────┐ ┌──────────────┐
               │ Builder Pool │ │ Analyst  │ │  AutoEvo     │
               │(QueueWorker +│ │(AmpCaller│ │  Worker      │
               │ Codex/Claude)│ │• quality │ │• self-improve│
               │ • executes   │ │  scoring │ │• rule updates│
               │   tasks      │ │          │ │              │
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

**Roles**
- **PM** (`RegistryClient`) — routes tasks to the best registered agent by capability score
- **PM Runtime** (`SmartRouter`) — provider selection, fallback, circuit-breaker aware delegation
- **Builder** (`queue_worker`) — executes tasks from the SQLite queue via Claude/Codex-capable delegates
- **Analyst** (`amp_caller`) — quality scoring and PM packet evaluation
- **AutoEvo** (`autoevo_worker`) — self-evolving rules and skill cleanup

## Status

`v0.2.1` includes:
- contract-first routing and PM quality tracking
- provider-aware delegation via `smart-delegate.sh` and `codex-delegate.sh`
- integration CLI for external agent registration and delegate generation
- launchd/status scripts for local worker operations

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

## Delegation Scripts

- `scripts/smart-delegate.sh`: 권장 기본 진입점. provider 선택, circuit breaker, throttle, fallback을 처리합니다.
- `scripts/codex-delegate.sh`: OpenAI Codex 직접 위임 경로입니다.
- `scripts/cokac-delegate.sh`: Anthropic/Claude 중심 기본 빌더 경로입니다.

## Structure

```
src/rolemesh/      # core Python package
scripts/           # worker launchers, delegate wrappers, status tools
tests/             # pytest test suite
docs/              # PRD, architecture, engineering rules
```

## Requirements

- Python >= 3.10
- httpx >= 0.27.0
