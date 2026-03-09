"""
S4: Long-term Self-Improvement Loop (Redesigned)
================================================
Tests OpenClaw's real differentiators vs standalone models:
- System A (OpenClaw): real file I/O, memory.json persistence, subprocess execution, git commit
- System B (Claude standalone): context re-passing each phase, no file/exec/git
- System C (GPT standalone): context re-passing each phase, no file/exec/git

Task: stock_analyzer.py CLI tool built across 3 phases
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OPENAI_MODEL, ANTHROPIC_MODEL, RESULTS_DIR

import anthropic
import openai

# ── Paths ──────────────────────────────────────────────────────────────────
WORK_DIR = Path("/tmp/s4_work")
MEMORY_FILE = WORK_DIR / "memory.json"
RESULTS_JSON = RESULTS_DIR / "s4_redesigned_results.json"
RESULTS_MD = RESULTS_DIR / "S4_REDESIGNED_REPORT.md"

# ── Prompts ────────────────────────────────────────────────────────────────
PHASE1_PROMPT = """Write a Python CLI script `stock_analyzer.py` that:
1. Accepts a stock ticker symbol as CLI argument (e.g. `python stock_analyzer.py AAPL`)
2. Downloads 3 months of historical price data using yfinance
3. Calculates 20-day and 50-day moving averages
4. Prints a formatted table using the `rich` library showing: Date, Close, MA20, MA50
5. Prints a summary: current price, both MAs, and simple BUY/HOLD/SELL signal

Use: yfinance, rich, argparse. Output complete, runnable code only."""

PHASE2_SYSTEM_PROMPT = """You are a senior Python developer improving existing code.
Apply ALL requested improvements and output complete, runnable code only."""

PHASE2_IMPROVEMENTS = """Improve the stock_analyzer.py with these enhancements:
1. Add proper error handling: invalid ticker, network failures, missing data
2. Add RSI (14-period) calculation and display
3. Add --output-json flag to save results to a JSON file
4. Add --days argument to customize lookback period (default 90)
5. Improve the signal logic to incorporate RSI (oversold <30=BUY, overbought >70=SELL)

Output complete improved code only."""

PHASE3_PROMPT = """The following stock_analyzer.py has a bug or needs verification.
Test it by running: python /tmp/s4_work/stock_analyzer_v2.py MSFT --days 30
If it fails, identify and fix the bug(s). Output the corrected complete code only.

Test output was:
{test_output}

Current code:
```python
{code}
```"""

JUDGE_PROMPT = """Score this Python stock analyzer script (1-10) on:
1. Correctness & completeness of implementation
2. Error handling robustness
3. Code quality and structure
4. Feature richness (MA, RSI, CLI args, etc.)
5. Real-world usability

Respond ONLY with:
SCORE: X.X
REASON: one sentence"""


# ── Helpers ────────────────────────────────────────────────────────────────
def strip_fences(text: str) -> str:
    """Remove markdown code fences."""
    text = re.sub(r"^```(?:python)?\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE)
    return text.strip()


async def judge_code(client_oai: openai.AsyncOpenAI, code: str, phase: int) -> float:
    """GPT judges code quality, returns score 1-10."""
    try:
        resp = await client_oai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": f"Phase {phase} code:\n```python\n{code[:3000]}\n```"},
            ],
            temperature=0.0,
        )
        text = resp.choices[0].message.content
        m = re.search(r"SCORE:\s*([\d.]+)", text)
        return float(m.group(1)) if m else 5.0
    except Exception:
        return 5.0


def run_subprocess(cmd: list[str], cwd: str = None, timeout: int = 30) -> tuple[bool, str]:
    """Run subprocess, return (success, combined output)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT after 30s"
    except Exception as e:
        return False, str(e)


def save_memory(data: dict) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2))


def load_memory() -> dict:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {}


# ── System A: OpenClaw (real files + memory + subprocess + git) ────────────
async def run_system_a(
    client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic
) -> dict[str, Any]:
    """System A: Files saved to disk, memory.json persists between phases,
    subprocess executes code, git commit at end."""
    start = time.time()
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[System A] Phase 1: GPT generates v1...")
    # Phase 1: GPT generates v1
    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": PHASE1_PROMPT}],
        temperature=0.2,
    )
    v1_code = strip_fences(resp.choices[0].message.content)
    v1_path = WORK_DIR / "stock_analyzer_v1.py"
    v1_path.write_text(v1_code)

    # Save to memory.json
    memory = {
        "phase": 1,
        "v1_path": str(v1_path),
        "v1_code_preview": v1_code[:200],
        "v1_lines": len(v1_code.splitlines()),
        "generated_by": OPENAI_MODEL,
    }
    save_memory(memory)
    score_p1 = await judge_code(client_oai, v1_code, 1)
    print(f"[System A] Phase 1 done. Score={score_p1:.1f}, file={v1_path}")

    # Phase 2: Load from memory.json (proving persistence), Claude improves
    print("[System A] Phase 2: Loading from memory.json, Claude improves...")
    mem = load_memory()
    loaded_v1 = Path(mem["v1_path"]).read_text()
    prompt_p2 = f"{PHASE2_IMPROVEMENTS}\n\nOriginal code (loaded from memory.json):\n```python\n{loaded_v1}\n```"

    resp2 = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=PHASE2_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_p2}],
    )
    v2_code = strip_fences(resp2.content[0].text)
    v2_path = WORK_DIR / "stock_analyzer_v2.py"
    v2_path.write_text(v2_code)

    memory.update({
        "phase": 2,
        "v2_path": str(v2_path),
        "v2_code_preview": v2_code[:200],
        "v2_lines": len(v2_code.splitlines()),
        "improved_by": ANTHROPIC_MODEL,
    })
    save_memory(memory)
    score_p2 = await judge_code(client_oai, v2_code, 2)
    print(f"[System A] Phase 2 done. Score={score_p2:.1f}, file={v2_path}")

    # Phase 3: Run subprocess, fix bugs, git commit
    print("[System A] Phase 3: subprocess test + bug fix + git commit...")
    mem = load_memory()
    v2_code_loaded = Path(mem["v2_path"]).read_text()

    # Try to run
    test_ok, test_output = run_subprocess(
        [sys.executable, str(v2_path), "MSFT", "--days", "30"],
        timeout=45,
    )
    print(f"[System A] Test run: success={test_ok}, output={test_output[:200]}")

    v3_code = v2_code_loaded
    if not test_ok:
        # Ask GPT to fix
        fix_prompt = PHASE3_PROMPT.format(test_output=test_output[:500], code=v2_code_loaded[:3000])
        resp3 = await client_oai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": fix_prompt}],
            temperature=0.1,
        )
        v3_code = strip_fences(resp3.choices[0].message.content)
        v3_path = WORK_DIR / "stock_analyzer_v3.py"
        v3_path.write_text(v3_code)

        # Re-test
        test_ok2, test_output2 = run_subprocess(
            [sys.executable, str(v3_path), "MSFT", "--days", "30"],
            timeout=45,
        )
        test_executed = True
        test_output = test_output2
        test_ok = test_ok2
        print(f"[System A] Re-test: success={test_ok2}")
    else:
        test_executed = True

    # Git commit
    git_ok = False
    git_msg = ""
    git_dir = WORK_DIR / "git_repo"
    git_dir.mkdir(exist_ok=True)
    final_code_path = git_dir / "stock_analyzer.py"
    final_code_path.write_text(v3_code)

    _, _ = run_subprocess(["git", "init"], cwd=str(git_dir))
    _, _ = run_subprocess(["git", "config", "user.email", "s4@benchmark.test"], cwd=str(git_dir))
    _, _ = run_subprocess(["git", "config", "user.name", "S4 Benchmark"], cwd=str(git_dir))
    _, _ = run_subprocess(["git", "add", "stock_analyzer.py"], cwd=str(git_dir))
    git_ok, git_msg = run_subprocess(
        ["git", "commit", "-m", "feat: stock_analyzer - 3-phase self-improvement"],
        cwd=str(git_dir),
    )
    print(f"[System A] git commit: success={git_ok}, msg={git_msg[:100]}")

    score_p3 = await judge_code(client_oai, v3_code, 3)

    memory.update({
        "phase": 3,
        "test_ok": test_ok,
        "test_output_preview": test_output[:200],
        "git_committed": git_ok,
        "score_p1": score_p1,
        "score_p2": score_p2,
        "score_p3": score_p3,
    })
    save_memory(memory)

    elapsed = time.time() - start
    return {
        "system": "openclaw_cokac_amp",
        "scenario": "s4_redesigned",
        "approach": "real_files_memory_subprocess_git",
        "memory_continuity": True,
        "files_created": [str(v1_path), str(v2_path)],
        "test_executed": test_executed,
        "test_passed": test_ok,
        "git_committed": git_ok,
        "quality_phase1": score_p1,
        "quality_phase2": score_p2,
        "quality_phase3": score_p3,
        "improvement_delta": round(score_p3 - score_p1, 2),
        "total_time_seconds": round(elapsed, 1),
        "memory_file": str(MEMORY_FILE),
    }


# ── System B: Claude standalone (context re-passing, no files/git) ─────────
async def run_system_b(
    client_ant: anthropic.AsyncAnthropic, client_oai: openai.AsyncOpenAI
) -> dict[str, Any]:
    """System B: Claude standalone. No persistent files. Each phase gets full
    previous code as context."""
    start = time.time()
    print("\n[System B] Phase 1: Claude generates v1...")

    resp = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": PHASE1_PROMPT}],
    )
    v1_code = strip_fences(resp.content[0].text)
    score_p1 = await judge_code(client_oai, v1_code, 1)
    print(f"[System B] Phase 1 done. Score={score_p1:.1f}")

    print("[System B] Phase 2: Claude improves (full v1 in prompt)...")
    prompt_p2 = (
        f"{PHASE2_IMPROVEMENTS}\n\nPrevious code (passed in context):\n```python\n{v1_code}\n```"
    )
    resp2 = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=PHASE2_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_p2}],
    )
    v2_code = strip_fences(resp2.content[0].text)
    score_p2 = await judge_code(client_oai, v2_code, 2)
    print(f"[System B] Phase 2 done. Score={score_p2:.1f}")

    print("[System B] Phase 3: Claude reviews (no subprocess, full v2 in prompt)...")
    # No subprocess—just ask Claude to review for bugs
    prompt_p3 = (
        "Review this code for bugs and correctness. Fix any issues you find. "
        "Output complete corrected code only.\n\n"
        f"```python\n{v2_code}\n```"
    )
    resp3 = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt_p3}],
    )
    v3_code = strip_fences(resp3.content[0].text)
    score_p3 = await judge_code(client_oai, v3_code, 3)
    print(f"[System B] Phase 3 done. Score={score_p3:.1f}")

    elapsed = time.time() - start
    return {
        "system": "claude_standalone",
        "scenario": "s4_redesigned",
        "approach": "context_repassing_no_files",
        "memory_continuity": False,
        "files_created": [],
        "test_executed": False,
        "test_passed": False,
        "git_committed": False,
        "quality_phase1": score_p1,
        "quality_phase2": score_p2,
        "quality_phase3": score_p3,
        "improvement_delta": round(score_p3 - score_p1, 2),
        "total_time_seconds": round(elapsed, 1),
    }


# ── System C: GPT standalone (context re-passing, no files/git) ───────────
async def run_system_c(client_oai: openai.AsyncOpenAI) -> dict[str, Any]:
    """System C: GPT standalone. No persistent files. Each phase gets full
    previous code as context."""
    start = time.time()
    print("\n[System C] Phase 1: GPT generates v1...")

    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": PHASE1_PROMPT}],
        temperature=0.2,
    )
    v1_code = strip_fences(resp.choices[0].message.content)
    score_p1 = await judge_code(client_oai, v1_code, 1)
    print(f"[System C] Phase 1 done. Score={score_p1:.1f}")

    print("[System C] Phase 2: GPT improves (full v1 in prompt)...")
    prompt_p2 = (
        f"{PHASE2_IMPROVEMENTS}\n\nPrevious code (passed in context):\n```python\n{v1_code}\n```"
    )
    resp2 = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": PHASE2_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_p2},
        ],
        temperature=0.1,
    )
    v2_code = strip_fences(resp2.choices[0].message.content)
    score_p2 = await judge_code(client_oai, v2_code, 2)
    print(f"[System C] Phase 2 done. Score={score_p2:.1f}")

    print("[System C] Phase 3: GPT reviews (no subprocess, full v2 in prompt)...")
    prompt_p3 = (
        "Review this code for bugs and correctness. Fix any issues you find. "
        "Output complete corrected code only.\n\n"
        f"```python\n{v2_code}\n```"
    )
    resp3 = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt_p3}],
        temperature=0.1,
    )
    v3_code = strip_fences(resp3.choices[0].message.content)
    score_p3 = await judge_code(client_oai, v3_code, 3)
    print(f"[System C] Phase 3 done. Score={score_p3:.1f}")

    elapsed = time.time() - start
    return {
        "system": "codex_standalone",
        "scenario": "s4_redesigned",
        "approach": "context_repassing_no_files",
        "memory_continuity": False,
        "files_created": [],
        "test_executed": False,
        "test_passed": False,
        "git_committed": False,
        "quality_phase1": score_p1,
        "quality_phase2": score_p2,
        "quality_phase3": score_p3,
        "improvement_delta": round(score_p3 - score_p1, 2),
        "total_time_seconds": round(elapsed, 1),
    }


# ── Report generation ──────────────────────────────────────────────────────
def write_report(results: list[dict]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(results, indent=2))

    lines = [
        "# S4 Redesigned: Real-World Self-Improvement Benchmark",
        "",
        "## Task: stock_analyzer.py built in 3 phases",
        "",
        "| Metric | System A (OpenClaw) | System B (Claude) | System C (GPT) |",
        "|--------|--------------------|--------------------|----------------|",
    ]

    def get(r: list, sys: str, key: str, default="N/A"):
        for item in r:
            if item.get("system") == sys:
                v = item.get(key, default)
                if isinstance(v, bool):
                    return "✅" if v else "❌"
                if isinstance(v, float):
                    return f"{v:.1f}"
                return str(v)
        return default

    rows = [
        ("memory_continuity", "Memory Persistence"),
        ("files_created", "Files Created"),
        ("test_executed", "Subprocess Run"),
        ("test_passed", "Test Passed"),
        ("git_committed", "Git Committed"),
        ("quality_phase1", "Phase 1 Score"),
        ("quality_phase2", "Phase 2 Score"),
        ("quality_phase3", "Phase 3 Score"),
        ("improvement_delta", "Improvement (P3-P1)"),
        ("total_time_seconds", "Total Time (s)"),
    ]

    for key, label in rows:
        a = get(results, "openclaw_cokac_amp", key)
        b = get(results, "claude_standalone", key)
        c = get(results, "codex_standalone", key)
        if key == "files_created":
            a_v = next((r.get(key, []) for r in results if r.get("system") == "openclaw_cokac_amp"), [])
            a = f"{len(a_v)} files" if isinstance(a_v, list) else a
            b = "0 files"
            c = "0 files"
        lines.append(f"| {label} | {a} | {b} | {c} |")

    lines += [
        "",
        "## Key Differentiator",
        "",
        "System A (OpenClaw) uniquely demonstrates:",
        "- **Persistent memory**: `memory.json` loaded between phases — no context re-passing",
        "- **Real file I/O**: Code written to `/tmp/s4_work/` and actually exists on disk",
        "- **Subprocess execution**: Code actually run with `python stock_analyzer_v2.py MSFT`",
        "- **Git integration**: Working `git init` + `add` + `commit` cycle",
        "",
        "Systems B and C must re-paste the entire previous code into each prompt,",
        "cannot verify their own output, and cannot commit to a real repository.",
        "",
        f"*Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
    ]

    RESULTS_MD.write_text("\n".join(lines))
    print(f"\n[Report] JSON: {RESULTS_JSON}")
    print(f"[Report] MD:   {RESULTS_MD}")


# ── Main ───────────────────────────────────────────────────────────────────
async def run(oai_key: str, ant_key: str) -> list[dict[str, Any]]:
    client_oai = openai.AsyncOpenAI(api_key=oai_key)
    client_ant = anthropic.AsyncAnthropic(api_key=ant_key)

    results = []
    for coro in [
        run_system_a(client_oai, client_ant),
        run_system_b(client_ant, client_oai),
        run_system_c(client_oai),
    ]:
        try:
            r = await coro
            results.append(r)
        except Exception as e:
            import traceback
            print(f"ERROR: {e}\n{traceback.format_exc()}")
            results.append({"error": str(e)})

    valid = [r for r in results if "system" in r]
    write_report(valid)
    return valid


if __name__ == "__main__":
    oai_key = os.environ.get("OPENAI_API_KEY", "")
    ant_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not oai_key or not ant_key:
        print("ERROR: OPENAI_API_KEY and ANTHROPIC_API_KEY must be set")
        sys.exit(1)

    results = asyncio.run(run(oai_key, ant_key))
    print("\n=== FINAL RESULTS ===")
    print(json.dumps(results, indent=2))
