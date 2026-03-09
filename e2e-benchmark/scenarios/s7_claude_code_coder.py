"""
S7: Claude Code 코더 실험
구현 태스크에서 Claude 단독 vs GPT 단독 vs 크로스모델(GPT 설계 → Claude 구현) 비교

Tasks: Python 패키지 3개 구현
- T1: 캐싱 데코레이터 (with TTL, LRU)
- T2: 비동기 HTTP 재시도 미들웨어
- T3: 타입 안전 설정 관리자 (Pydantic 기반)

Measures: pytest pass rate, code lines, type hint coverage, elapsed time
Judge: 실제 pytest 실행 (객관적)
"""
import asyncio
import time
import sys
import os
import re
import tempfile
import subprocess
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OPENAI_MODEL, ANTHROPIC_MODEL
import openai
import anthropic

SYSTEM_CLAUDE = "claude_coder"
SYSTEM_GPT = "gpt_coder"
SYSTEM_CROSS = "cross_model_gpt_design_claude_impl"

TASKS = [
    {
        "id": "t1",
        "name": "캐싱 데코레이터 (TTL + LRU)",
        "prompt": """Implement a Python caching decorator with both TTL (time-to-live) and LRU (least-recently-used) eviction.

Requirements:
- `@cache(ttl=60, maxsize=128)` decorator syntax
- Thread-safe implementation
- Type hints throughout
- Works on sync functions

Include a `CacheStats` dataclass with hit_count, miss_count, eviction_count.

Provide ONLY the implementation code (no explanation). The code must be runnable as-is.""",
        "test_code": """
import time
import pytest

def test_basic_cache(cache_module):
    call_count = 0

    @cache_module.cache(ttl=60, maxsize=128)
    def add(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    assert add(1, 2) == 3
    assert add(1, 2) == 3  # cached
    assert call_count == 1

def test_ttl_expiry(cache_module):
    @cache_module.cache(ttl=0.1, maxsize=128)
    def get_val(x):
        return x * 2

    assert get_val(5) == 10
    time.sleep(0.2)
    get_val(5)  # should recompute after TTL

def test_lru_eviction(cache_module):
    @cache_module.cache(ttl=60, maxsize=2)
    def compute(x):
        return x ** 2

    compute(1)
    compute(2)
    compute(3)  # evicts 1
    # No assertion on eviction order, just no crash
    assert compute(3) == 9

def test_cache_stats(cache_module):
    @cache_module.cache(ttl=60, maxsize=10)
    def fn(x):
        return x

    fn(1)
    fn(1)
    fn(2)
    stats = fn.cache_stats()
    assert hasattr(stats, 'hit_count')
    assert stats.hit_count >= 1
""",
    },
    {
        "id": "t2",
        "name": "비동기 HTTP 재시도 미들웨어",
        "prompt": """Implement an async HTTP retry middleware for Python using aiohttp.

Requirements:
- `AsyncRetryMiddleware` class
- Configurable: max_retries=3, backoff_factor=1.5, retry_on=(500, 502, 503, 504)
- Exponential backoff with jitter
- Type hints throughout
- `get(url)`, `post(url, data)` async methods that return dict

Provide ONLY the implementation code (no explanation). The code must be runnable as-is.""",
        "test_code": """
import asyncio
import pytest

def test_middleware_instantiation(retry_module):
    m = retry_module.AsyncRetryMiddleware(max_retries=3, backoff_factor=1.5)
    assert m is not None

def test_retry_config(retry_module):
    m = retry_module.AsyncRetryMiddleware(max_retries=5, backoff_factor=2.0, retry_on=(500, 503))
    assert m.max_retries == 5
    assert m.backoff_factor == 2.0
    assert 500 in m.retry_on

def test_backoff_calculation(retry_module):
    m = retry_module.AsyncRetryMiddleware(max_retries=3, backoff_factor=1.5)
    # Backoff for attempt 0 should be ~1.5^0 = 1.0 (with jitter)
    delay = m._calculate_delay(0)
    assert delay >= 0

def test_has_required_methods(retry_module):
    m = retry_module.AsyncRetryMiddleware()
    assert hasattr(m, 'get')
    assert hasattr(m, 'post')
    assert asyncio.iscoroutinefunction(m.get)
    assert asyncio.iscoroutinefunction(m.post)
""",
    },
    {
        "id": "t3",
        "name": "타입 안전 설정 관리자 (Pydantic 기반)",
        "prompt": """Implement a type-safe configuration manager using Pydantic v2.

Requirements:
- `ConfigManager` class that loads from dict, .env file, or environment variables
- Priority: env vars > .env file > dict defaults
- `get(key, default=None)` method with type coercion
- `reload()` method to refresh from sources
- Support nested config via dot notation: `get("database.host")`
- Type hints throughout

Provide ONLY the implementation code (no explanation). The code must be runnable as-is.""",
        "test_code": """
import os
import pytest

def test_basic_config(config_module):
    cm = config_module.ConfigManager(defaults={"host": "localhost", "port": 5432})
    assert cm.get("host") == "localhost"
    assert cm.get("port") == 5432

def test_default_fallback(config_module):
    cm = config_module.ConfigManager()
    assert cm.get("nonexistent", "fallback") == "fallback"

def test_env_override(config_module):
    os.environ["TEST_CM_HOST"] = "prod.example.com"
    cm = config_module.ConfigManager(defaults={"TEST_CM_HOST": "localhost"})
    assert cm.get("TEST_CM_HOST") == "prod.example.com"
    del os.environ["TEST_CM_HOST"]

def test_nested_dot_notation(config_module):
    cm = config_module.ConfigManager(defaults={"database": {"host": "db.local", "port": 5432}})
    assert cm.get("database.host") == "db.local"
    assert cm.get("database.port") == 5432

def test_reload(config_module):
    cm = config_module.ConfigManager(defaults={"x": 1})
    os.environ["TEST_RELOAD_KEY"] = "42"
    cm.reload()
    # reload should not crash
    del os.environ["TEST_RELOAD_KEY"]
""",
    },
]

DESIGN_PROMPT_PREFIX = "You are a senior software architect. Design a detailed implementation plan for the following Python module. Specify: class structure, method signatures, key algorithms, data structures. Be specific enough that a developer can implement it directly.\n\n"


def _count_type_hints(code: str) -> float:
    """Estimate type hint coverage as ratio of annotated defs."""
    defs = re.findall(r"def \w+\(", code)
    annotated = re.findall(r"def \w+\([^)]*:.*?\)", code, re.DOTALL)
    arrow_returns = re.findall(r"\) ->", code)
    if not defs:
        return 0.0
    hint_score = min(1.0, (len(arrow_returns) + len(annotated) * 0.5) / max(len(defs), 1))
    return round(hint_score, 2)


def _run_pytest_on_code(impl_code: str, test_code: str, module_fixture_name: str) -> dict:
    """Write impl + test to temp files and run pytest. Returns pass rate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write implementation
        impl_path = Path(tmpdir) / "impl.py"
        impl_path.write_text(impl_code)

        # Write conftest to expose the impl module as a fixture
        conftest = f"""
import sys
sys.path.insert(0, "{tmpdir}")
import pytest
import impl as _impl_module

@pytest.fixture
def {module_fixture_name}():
    return _impl_module
"""
        (Path(tmpdir) / "conftest.py").write_text(conftest)

        # Write test file
        test_path = Path(tmpdir) / "test_impl.py"
        test_path.write_text(test_code)

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmpdir,
            )
            stdout = result.stdout + result.stderr
            passed = len(re.findall(r" PASSED", stdout))
            failed = len(re.findall(r" FAILED|ERROR", stdout))
            total = passed + failed
            pass_rate = passed / total if total > 0 else 0.0
            return {"passed": passed, "failed": failed, "total": total, "pass_rate": round(pass_rate, 3), "output": stdout[-800:]}
        except subprocess.TimeoutExpired:
            return {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0, "output": "TIMEOUT"}
        except Exception as e:
            return {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0, "output": str(e)}


def _extract_code(text: str) -> str:
    """Extract code block from LLM response."""
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


async def _implement_claude(client_ant: anthropic.AsyncAnthropic, task: dict) -> tuple[str, float]:
    start = time.time()
    resp = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": task["prompt"]}],
    )
    return _extract_code(resp.content[0].text), time.time() - start


async def _implement_gpt(client_oai: openai.AsyncOpenAI, task: dict) -> tuple[str, float]:
    start = time.time()
    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are an expert Python developer. Provide only clean, runnable code."},
            {"role": "user", "content": task["prompt"]},
        ],
        temperature=0.1,
    )
    return _extract_code(resp.choices[0].message.content), time.time() - start


async def _implement_cross(client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic, task: dict) -> tuple[str, float]:
    """GPT-5.4 designs, Claude implements."""
    start = time.time()
    design_resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": DESIGN_PROMPT_PREFIX},
            {"role": "user", "content": task["prompt"]},
        ],
        temperature=0.2,
    )
    design = design_resp.choices[0].message.content

    impl_resp = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": f"Implement the following Python module based on this design specification:\n\n{design}\n\nOriginal requirements:\n{task['prompt']}\n\nProvide ONLY the implementation code.",
        }],
    )
    return _extract_code(impl_resp.content[0].text), time.time() - start


def _score_task_result(test_result: dict, code: str, elapsed: float) -> dict:
    lines = len([l for l in code.split("\n") if l.strip()])
    return {
        "pass_rate": test_result["pass_rate"],
        "tests_passed": test_result["passed"],
        "tests_total": test_result["total"],
        "code_lines": lines,
        "type_hint_coverage": _count_type_hints(code),
        "elapsed_seconds": round(elapsed, 1),
    }


async def run(oai_key: str, ant_key: str) -> list[dict[str, Any]]:
    """Run S7: Claude coder vs GPT coder vs Cross-model coder."""
    client_oai = openai.AsyncOpenAI(api_key=oai_key)
    client_ant = anthropic.AsyncAnthropic(api_key=ant_key)

    fixture_names = {"t1": "cache_module", "t2": "retry_module", "t3": "config_module"}

    system_results = {
        SYSTEM_CLAUDE: [],
        SYSTEM_GPT: [],
        SYSTEM_CROSS: [],
    }

    for task in TASKS:
        fixture = fixture_names[task["id"]]

        claude_code, claude_time = await _implement_claude(client_ant, task)
        gpt_code, gpt_time = await _implement_gpt(client_oai, task)
        cross_code, cross_time = await _implement_cross(client_oai, client_ant, task)

        system_results[SYSTEM_CLAUDE].append(_score_task_result(
            _run_pytest_on_code(claude_code, task["test_code"], fixture), claude_code, claude_time))
        system_results[SYSTEM_GPT].append(_score_task_result(
            _run_pytest_on_code(gpt_code, task["test_code"], fixture), gpt_code, gpt_time))
        system_results[SYSTEM_CROSS].append(_score_task_result(
            _run_pytest_on_code(cross_code, task["test_code"], fixture), cross_code, cross_time))

    def _aggregate_system(task_results: list[dict], system: str, agents: list[str]) -> dict:
        n = len(task_results)
        return {
            "system": system,
            "scenario": "s7_claude_code_coder",
            "average_score": round(sum(r["pass_rate"] for r in task_results) / n, 3),
            "avg_pass_rate": round(sum(r["pass_rate"] for r in task_results) / n, 3),
            "total_tests_passed": sum(r["tests_passed"] for r in task_results),
            "total_tests": sum(r["tests_total"] for r in task_results),
            "avg_code_lines": round(sum(r["code_lines"] for r in task_results) / n),
            "avg_type_hint_coverage": round(sum(r["type_hint_coverage"] for r in task_results) / n, 2),
            "elapsed_seconds": round(sum(r["elapsed_seconds"] for r in task_results), 1),
            "tasks_evaluated": n,
            "agents_used": agents,
        }

    return [
        _aggregate_system(system_results[SYSTEM_CLAUDE], SYSTEM_CLAUDE, ["claude-impl"]),
        _aggregate_system(system_results[SYSTEM_GPT], SYSTEM_GPT, ["gpt-impl"]),
        _aggregate_system(system_results[SYSTEM_CROSS], SYSTEM_CROSS, ["gpt-design", "claude-impl"]),
    ]


if __name__ == "__main__":
    import json
    r = asyncio.run(run(os.environ["OPENAI_API_KEY"], os.environ["ANTHROPIC_API_KEY"]))
    print(json.dumps(r, indent=2, ensure_ascii=False))
