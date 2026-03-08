# RoleMesh Codebase Exploration — Batch Cooldown Implementation Guide

## 1. Directory Structure

### Top-Level
```
/Users/rocky/rolemesh/
├── .git/
├── .omc/                    # OMC state files
├── config/
│   └── throttle.yaml        # Provider RPM configuration
├── docs/                    # Documentation
├── examples/                # Example scripts
├── scripts/                 # Operational scripts (key delegation/status scripts)
├── src/
│   └── rolemesh/
│       └── adapters/        # Core adapter modules
├── tests/                   # Test suite
├── rolemesh.db              # SQLite database
├── conftest.py              # Pytest configuration
├── pytest.ini               # Pytest settings
└── pyproject.toml           # Project metadata
```

### src/rolemesh/adapters/ — Core Rate-Limiting & Circuit Breaking
```
adapters/
├── __init__.py
├── throttle.py              # TokenBucketThrottle implementation (PRIMARY)
├── circuit_breaker.py       # ProviderCircuitBreaker with 3-state model
├── amp_caller.py            # AMP adapter
└── provider_router.py       # Provider routing with CB integration
```

---

## 2. Configuration: config/throttle.yaml

```yaml
# throttle.yaml — Provider RPM limits for RoleMesh delegation
# 분당 요청 수 상한. Rate limit 여유 확보를 위해 공식 한도보다 낮게 설정.
#
# 이 파일을 수정하면 claude-delegate.sh / cokac-delegate.sh가 자동으로 반영.
# 재시작 불필요 (매 호출마다 읽음).

anthropic: 15   # Anthropic API — 실제 한도 여유 확보 (rate limit 방지)
openai: 20      # OpenAI API
gemini: 60      # Google Gemini API
```

**Key Points:**
- RPM = Requests Per Minute (token bucket rate)
- Config is read on every call (no restart needed)
- Values are conservative (below official limits)
- Fallback defaults in code if file missing

---

## 3. Scripts for Delegation & Status

### scripts/cokac-delegate.sh
```bash
#!/usr/bin/env bash
# cokac-delegate.sh — 록이(PM)가 cokac에 위임할 때 사용하는 표준 실행기
#
# 사용법:
#   scripts/cokac-delegate.sh -p "작업 내용"
#   scripts/cokac-delegate.sh --model claude-opus-4-5 -p "복잡한 작업"
#   scripts/cokac-delegate.sh --dangerously-skip-permissions -p "자동 승인 필요한 작업"
#
# 주의: 직접 `claude -p` 호출 금지. 이 스크립트를 통해서만 위임할 것.
# Throttle/CB가 자동 적용되어 Anthropic rate limit 방지.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELEGATE="$SCRIPT_DIR/claude-delegate.sh"

if [[ ! -f "$DELEGATE" ]]; then
    echo "[cokac-delegate] ❌ claude-delegate.sh 없음: $DELEGATE" >&2
    exit 1
fi

# ... delegates to claude-delegate.sh with CB/Throttle checks
exec "$DELEGATE" "$@"
```

**Key Points:**
- Standard entry point for PM delegation to cokac agent
- Enforces throttle/circuit-breaker checks automatically
- Wraps claude-delegate.sh (which implements the actual rate limiting)

### scripts/status.sh
```bash
#!/bin/bash
# RoleMesh 상태 대시보드
# Displays:
# - Task queue status (pending/completed/failed counts)
# - Dead letter queue (DLQ) count and recent errors
# - Running workers (queue_worker, message_worker, autoevo_worker)
# - Provider Circuit Breaker Status for each provider (anthropic, openai, gemini)
#   - Shows state: CLOSED, OPEN, or HALF_OPEN
#   - For OPEN: shows cooldown remaining seconds

# Example CB status output:
#   anthropic: CLOSED
#   openai: OPEN (cooldown: 45s 남음)
#   gemini: HALF_OPEN
```

**Key Points:**
- Reads CB state from `/tmp/rolemesh-cb-{provider}.json`
- Calculates cooldown_remaining dynamically
- Shows task queue health and worker status

---

## 4. Existing Throttle Implementation: src/rolemesh/adapters/throttle.py

### Architecture
- **Pattern:** Token-bucket rate limiter (per-provider)
- **State Persistence:** `/tmp/rolemesh-throttle-{provider}.json`
- **Config Source:** `~/rolemesh/config/throttle.yaml` (optional, auto-fallback)

### Key Methods
```python
class TokenBucketThrottle:
    def __init__(self, rpm_overrides: dict[str, int] | None = None):
        """Initialize with optional RPM overrides."""

    def acquire(self, provider: str) -> Union[bool, float]:
        """Attempt to consume one token.

        Returns:
            True  — token available, request can proceed immediately
            float — seconds to wait before retrying
        """

    def reset(self, provider: str) -> None:
        """Reset bucket to full capacity (testing/manual recovery)."""

    def drain(self, provider: str) -> None:
        """Drain all tokens (testing)."""
```

### Token Refill Logic
- **Capacity:** RPM value from config (e.g., anthropic: 15 = 15 tokens/min)
- **Rate:** capacity / 60 tokens per second
- **Refill:** Incremental based on elapsed time since last refill
- **Formula:** `new_tokens = min(capacity, old_tokens + elapsed_sec * rate)`

### State Structure (JSON)
```json
{
    "tokens": 14.8,          // Current token count (float)
    "last_refill": 1678000000.123  // Timestamp of last refill
}
```

---

## 5. Circuit Breaker Implementation: src/rolemesh/adapters/circuit_breaker.py

### 3-State Model
- **CLOSED:** Normal operation (provider available)
- **OPEN:** Provider unavailable (cooldown active)
- **HALF_OPEN:** Testing provider recovery (cooldown elapsed)

### State Transitions
```
CLOSED --[3 failures]--> OPEN --[cooldown elapsed]--> HALF_OPEN
                                                            ↓
                                               Success → CLOSED
                                               Failure → OPEN
```

### Key Methods
```python
class ProviderCircuitBreaker:
    def is_available(self, provider: str) -> bool:
        """Return True if provider can accept requests (CLOSED or HALF_OPEN)."""

    def record_success(self, provider: str) -> None:
        """Record successful call → transition to CLOSED."""

    def record_failure(self, provider: str) -> None:
        """Record failed call → increment failure counter or transition."""

    def get_state(self, provider: str) -> CBState:
        """Current state (with auto-transition OPEN→HALF_OPEN applied)."""

    def cooldown_remaining(self, provider: str) -> int:
        """Seconds remaining in OPEN cooldown (0 if not OPEN)."""
```

### State Persistence
```json
{
    "state": "OPEN",           // CLOSED | OPEN | HALF_OPEN
    "failures": 0,             // Failure counter (reset on success)
    "opened_at": 1678000000,   // Unix timestamp when OPEN started
    "cooldown_sec": 60         // Cooldown duration
}
```

### Default Configuration
- **failure_threshold:** 3 consecutive failures trigger OPEN
- **cooldown_sec:** 60 seconds in OPEN before attempting HALF_OPEN

---

## 6. Test Files Structure

### Available Tests
```
tests/
├── test_throttle.py              # 13 tests: TokenBucketThrottle behavior
├── test_circuit_breaker.py       # 14 tests: ProviderCircuitBreaker + ProviderRouter
├── test_queue_worker.py          # Queue worker integration
├── test_registry_client.py        # Registry client tests
├── test_integration.py            # E2E integration tests
├── test_e2e_smoke.py             # Smoke tests
└── ... (other test files)
```

### Test Fixtures
```python
@pytest.fixture(autouse=True)
def clean_throttle_files(tmp_path, monkeypatch):
    """Redirect throttle state files to tmp_path for test isolation."""
    monkeypatch.setattr("rolemesh.adapters.throttle._STATE_DIR", tmp_path)
    yield

@pytest.fixture(autouse=True)
def clean_cb_files(tmp_path, monkeypatch):
    """Redirect CB state files to tmp_path for test isolation."""
    monkeypatch.setattr("rolemesh.adapters.circuit_breaker._STATE_DIR", tmp_path)
    yield
```

### Key Test Coverage
- **Throttle:** Fresh bucket, drained bucket, refill over time, RPM proportionality, state persistence
- **CB:** CLOSED→OPEN transitions, cooldown→HALF_OPEN, HALF_OPEN success/failure, fallback routing
- **Integration:** Provider selection with throttle checks, reschedule behavior when all providers unavailable

---

## 7. How Current Rate-Limiting Works

### Throttle Flow
1. **Request arrives** at queue_worker or delegation endpoint
2. **Call `throttle.acquire(provider)`**
   - Returns `True` → proceed immediately (token consumed)
   - Returns `float` (wait_sec) → reschedule task with retry_after = wait_sec
3. **Token bucket refills** based on elapsed time
4. **Config changes apply automatically** (no restart needed)

### Circuit Breaker Flow
1. **Check `cb.is_available(provider)`**
   - If False (OPEN) → skip provider, try next
   - If all OPEN → reschedule with 60s cooldown
2. **On success:** `cb.record_success(provider)` → resets to CLOSED
3. **On failure:** `cb.record_failure(provider)` → increment counter
4. **Cooldown auto-transition:** OPEN→HALF_OPEN after `cooldown_sec` seconds

### Combined Usage
```python
# Pseudo-code from queue_worker._run_task
provider = _select_provider_with_throttle(task_id, client)
if provider is None:
    # All providers unavailable (throttled or circuit-broken)
    client.retry_task(task_id, retry_count + 1, retry_after=60)
    return

# Provider available — proceed with call
try:
    result = call_provider(provider, task_data)
    _router.record_success(provider)
except Exception as e:
    _router.record_failure(provider)
    raise
```

---

## 8. Key Integration Points for Batch Cooldown

### Where to Hook In
1. **throttle.py:** Add `batch_cooldown` tracking alongside token bucket
2. **circuit_breaker.py:** Already has cooldown logic (cooldown_sec, opened_at)
3. **queue_worker:** Uses both throttle + CB for provider selection
4. **status.sh:** Display batch cooldown status (like CB status)

### State Files to Create
- `/tmp/rolemesh-batch-cooldown-{provider}.json` — Track batch cooldown timestamps

### Configuration
- Add to `config/throttle.yaml`: `batch_cooldown_sec: 300` (example: 5 min)

### Test Pattern
- Use `monkeypatch` fixtures to redirect state dir to `tmp_path`
- Mock `time.time()` to simulate cooldown elapsed
- Test reschedule behavior when batch cooldown active

---

## 9. Summary for Batch Cooldown Implementation

**What Exists:**
- Token-bucket throttle (per-minute rate limit)
- Circuit breaker (3-state fault tolerance with cooldown)
- Config system (YAML-driven, no restart needed)
- Test infrastructure (pytest fixtures, state isolation)

**What's Needed:**
- Batch detection logic (identify when N consecutive tasks from same batch fail)
- Batch cooldown state persistence
- Integration with `_select_provider_with_throttle()` to check batch cooldown
- Status.sh update to show batch cooldown status
- Test coverage (fresh batch, cooldown active, cooldown elapsed)

**Files to Modify:**
1. `src/rolemesh/adapters/throttle.py` — Add `BatchCooldown` class or extend existing
2. `config/throttle.yaml` — Add `batch_cooldown_sec` parameter
3. `src/rolemesh/workers/queue_worker.py` — Integrate batch cooldown check
4. `scripts/status.sh` — Display batch cooldown status
5. `tests/test_throttle.py` or `tests/test_batch_cooldown.py` — Add test coverage

**State Persistence:**
- Location: `/tmp/rolemesh-batch-cooldown-{provider}.json` (same pattern as throttle/CB)
- Schema: `{ "cooldown_until": unix_timestamp, "batch_id": "...", "failure_count": N }`

