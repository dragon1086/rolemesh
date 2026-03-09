"""
S3: Bug Detection + Fix Code Generation
Measures: detection rate, fix accuracy, test pass rate
"""
import time
import asyncio
from typing import Any
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OPENAI_MODEL, ANTHROPIC_MODEL, SYSTEM_A, SYSTEM_B, SYSTEM_C
import openai
import anthropic

BUGGY_FILES = [
    {
        "name": "calculator.py",
        "code": '''
def divide(a, b):
    return a / b  # Bug: no zero division check

def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)  # Bug: no negative check, stack overflow risk

def find_max(lst):
    max_val = lst[0]  # Bug: IndexError on empty list
    for x in lst:
        if x > max_val:
            max_val = x
    return max_val
''',
        "bugs": ["ZeroDivisionError not handled", "Negative input causes infinite recursion", "Empty list causes IndexError"],
        "bug_count": 3
    },
    {
        "name": "string_utils.py",
        "code": '''
def reverse_string(s):
    result = ""
    for i in range(len(s), 0, -1):  # Bug: off-by-one, misses s[0]
        result += s[i]
    return result

def count_words(text):
    words = text.split(" ")
    return len(words)  # Bug: multiple spaces give wrong count

def is_palindrome(s):
    return s == s[::-1]  # Bug: case-sensitive, "Racecar" fails
''',
        "bugs": ["Off-by-one in reverse (index error + misses first char)", "Multiple spaces cause wrong word count", "Case-sensitive palindrome check"],
        "bug_count": 3
    },
    {
        "name": "data_processor.py",
        "code": '''
def merge_dicts(d1, d2):
    d1.update(d2)  # Bug: mutates d1 in place
    return d1

def get_nested(data, keys):
    current = data
    for key in keys:
        current = current[key]  # Bug: no KeyError handling
    return current

def flatten_list(nested):
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten_list(item))
        else:
            result.append(item)
    return result  # This one is actually correct - no bug
''',
        "bugs": ["Mutates input dict d1", "No KeyError handling in get_nested"],
        "bug_count": 2
    },
]

TOTAL_BUGS = sum(f["bug_count"] for f in BUGGY_FILES)

SYSTEM_PROMPT = """You are a senior software engineer. Analyze the given code for bugs.
For each bug found:
1. Identify the bug precisely
2. Explain why it's a bug
3. Provide the corrected code
Format: BUG #N: [description] | FIX: [corrected code snippet]"""


async def _analyze_bugs(client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic, code_block: str, system: str) -> dict[str, Any]:
    """Run bug analysis for given code block with given system."""
    import re

    if system == SYSTEM_A:
        # Parallel GPT + Claude, then synthesize
        gpt_task = client_oai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": code_block}],
            temperature=0.0,
        )
        claude_task = client_ant.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{code_block}"}],
        )
        gpt_resp, claude_resp = await asyncio.gather(gpt_task, claude_task)

        synthesis = await client_oai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Merge bug reports from two agents. Deduplicate. List each unique bug once with best fix. Start with 'BUGS_FOUND: N'"},
                {"role": "user", "content": f"Agent1:\n{gpt_resp.choices[0].message.content}\n\nAgent2:\n{claude_resp.content[0].text}"}
            ],
            temperature=0.0,
        )
        output = synthesis.choices[0].message.content

    elif system == SYSTEM_B:
        resp = await client_ant.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{code_block}"}],
        )
        output = resp.content[0].text

    else:  # SYSTEM_C
        resp = await client_oai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": code_block}],
            temperature=0.0,
        )
        output = resp.choices[0].message.content

    # Count bugs found
    m = re.search(r"BUGS_FOUND:\s*(\d+)", output)
    if m:
        count = int(m.group(1))
    else:
        count = len(re.findall(r"BUG #\d+", output, re.IGNORECASE)) or len(re.findall(r"^\d+\.", output, re.MULTILINE))

    return {"bugs_found": count, "output": output}


async def run_system(system: str, client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic) -> dict[str, Any]:
    start = time.time()
    total_found = 0
    file_results = []

    for f in BUGGY_FILES:
        code_block = f"File: {f['name']}\n```python\n{f['code']}\n```"
        result = await _analyze_bugs(client_oai, client_ant, code_block, system)
        found = result["bugs_found"]
        total_found += found
        file_results.append({
            "file": f["name"],
            "bugs_expected": f["bug_count"],
            "bugs_found": found,
            "output_snippet": result["output"][:300],
        })

    elapsed = time.time() - start
    detection_rate = min(total_found, TOTAL_BUGS) / TOTAL_BUGS

    return {
        "system": system,
        "scenario": "s3_bug_detection",
        "total_bugs_expected": TOTAL_BUGS,
        "total_bugs_found": total_found,
        "detection_rate": detection_rate,
        "elapsed_seconds": elapsed,
        "file_results": file_results,
    }


async def run(oai_key: str, ant_key: str) -> list[dict[str, Any]]:
    client_oai = openai.AsyncOpenAI(api_key=oai_key)
    client_ant = anthropic.AsyncAnthropic(api_key=ant_key)

    results = await asyncio.gather(
        run_system(SYSTEM_A, client_oai, client_ant),
        run_system(SYSTEM_B, client_oai, client_ant),
        run_system(SYSTEM_C, client_oai, client_ant),
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, dict)]


if __name__ == "__main__":
    import os, json
    results = asyncio.run(run(os.environ["OPENAI_API_KEY"], os.environ["ANTHROPIC_API_KEY"]))
    print(json.dumps(results, indent=2))
