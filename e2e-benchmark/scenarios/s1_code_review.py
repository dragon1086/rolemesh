"""
S1: Code Review + Security Vulnerability Analysis
Measures: vuln count, accuracy, false positive rate, time
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

VULNERABLE_CODE = '''
import sqlite3
import hashlib
import os
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_PATH = "users.db"
SECRET_KEY = "hardcoded_secret_key_12345"

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]
    # SQL injection vulnerability
    conn = sqlite3.connect(DB_PATH)
    query = f"SELECT * FROM users WHERE username=\'{username}\' AND password=\'{password}\'"
    cursor = conn.execute(query)
    user = cursor.fetchone()
    if user:
        return jsonify({"token": SECRET_KEY + username})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/user/<user_id>")
def get_user(user_id):
    # No authentication check (missing authz)
    conn = sqlite3.connect(DB_PATH)
    result = conn.execute(f"SELECT * FROM users WHERE id={user_id}").fetchone()
    return jsonify({"user": result})

@app.route("/upload", methods=["POST"])
def upload():
    # Path traversal vulnerability
    filename = request.form["filename"]
    content = request.files["file"].read()
    with open(f"/uploads/{filename}", "wb") as f:
        f.write(content)
    return jsonify({"status": "uploaded"})

@app.route("/exec", methods=["POST"])
def execute_command():
    # Command injection
    cmd = request.form["cmd"]
    result = os.popen(cmd).read()
    return jsonify({"output": result})

def store_password(password: str) -> str:
    # Weak hashing (MD5)
    return hashlib.md5(password.encode()).hexdigest()

if __name__ == "__main__":
    app.run(debug=True)  # Debug mode in production
'''

# Ground truth: 7 vulnerabilities
GROUND_TRUTH_VULNS = [
    "SQL Injection (login endpoint)",
    "SQL Injection (get_user endpoint)",
    "Hardcoded secret key",
    "Missing authentication on get_user",
    "Path traversal in upload",
    "Command injection in execute_command",
    "Weak hashing (MD5)",
    "Debug mode in production",
]
GROUND_TRUTH_COUNT = len(GROUND_TRUTH_VULNS)

SYSTEM_PROMPT = """You are a security expert. Analyze the given Python code for security vulnerabilities.
For each vulnerability found, provide:
1. Vulnerability name/type
2. Location (function name)
3. Severity (Critical/High/Medium/Low)
4. Brief description
5. Remediation suggestion

Be precise. Do not report false positives."""

USER_PROMPT = f"""Analyze this Python Flask application for security vulnerabilities:

```python
{VULNERABLE_CODE}
```

List ALL security vulnerabilities you find."""


async def run_system_a(client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic) -> dict[str, Any]:
    """System A: OpenClaw+cokac+amp tri-agent approach.

    - OpenClaw (GPT) does initial scan
    - cokac (Claude) does deep analysis
    - amp synthesizes and deduplicates
    """
    start = time.time()

    # Agent 1: GPT initial scan
    gpt_resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a security scanner. Find ALL security vulnerabilities quickly. Be comprehensive."},
            {"role": "user", "content": USER_PROMPT}
        ],
        temperature=0.1,
    )
    gpt_findings = gpt_resp.choices[0].message.content

    # Agent 2: Claude deep analysis
    claude_resp = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[
            {"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}\n\nAdditional context from initial scan:\n{gpt_findings}"}
        ],
    )
    claude_findings = claude_resp.content[0].text

    # Agent 3 (amp): Synthesis and dedup
    synthesis_resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a security analyst synthesizer. Given findings from two security agents, create a deduplicated, comprehensive vulnerability report. Count exact number of unique vulnerabilities."},
            {"role": "user", "content": f"Agent 1 findings:\n{gpt_findings}\n\nAgent 2 findings:\n{claude_findings}\n\nSynthesize into final report. Start with 'TOTAL UNIQUE VULNERABILITIES: N'"}
        ],
        temperature=0.0,
    )
    synthesis = synthesis_resp.choices[0].message.content

    elapsed = time.time() - start
    vuln_count = _extract_vuln_count(synthesis)

    return {
        "system": SYSTEM_A,
        "scenario": "s1_code_review",
        "vuln_count_found": vuln_count,
        "ground_truth_count": GROUND_TRUTH_COUNT,
        "detection_rate": min(vuln_count, GROUND_TRUTH_COUNT) / GROUND_TRUTH_COUNT,
        "elapsed_seconds": elapsed,
        "raw_output": synthesis,
        "agents_used": ["gpt-scan", "claude-deep", "gpt-synthesis"],
    }


async def run_system_b(client_ant: anthropic.AsyncAnthropic) -> dict[str, Any]:
    """System B: Claude standalone multi-agent (two Claude calls)."""
    start = time.time()

    resp1 = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"}],
    )
    first_pass = resp1.content[0].text

    resp2 = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1000,
        messages=[
            {"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"},
            {"role": "assistant", "content": first_pass},
            {"role": "user", "content": "Review your findings. Did you miss any? Count total unique vulnerabilities. Start with 'TOTAL UNIQUE VULNERABILITIES: N'"}
        ],
    )
    final = resp2.content[0].text
    elapsed = time.time() - start
    vuln_count = _extract_vuln_count(final)

    return {
        "system": SYSTEM_B,
        "scenario": "s1_code_review",
        "vuln_count_found": vuln_count,
        "ground_truth_count": GROUND_TRUTH_COUNT,
        "detection_rate": min(vuln_count, GROUND_TRUTH_COUNT) / GROUND_TRUTH_COUNT,
        "elapsed_seconds": elapsed,
        "raw_output": final,
        "agents_used": ["claude-pass1", "claude-pass2"],
    }


async def run_system_c(client_oai: openai.AsyncOpenAI) -> dict[str, Any]:
    """System C: GPT standalone (single call)."""
    start = time.time()

    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ],
        temperature=0.1,
    )
    output = resp.choices[0].message.content
    elapsed = time.time() - start
    vuln_count = _extract_vuln_count(output)

    return {
        "system": SYSTEM_C,
        "scenario": "s1_code_review",
        "vuln_count_found": vuln_count,
        "ground_truth_count": GROUND_TRUTH_COUNT,
        "detection_rate": min(vuln_count, GROUND_TRUTH_COUNT) / GROUND_TRUTH_COUNT,
        "elapsed_seconds": elapsed,
        "raw_output": output,
        "agents_used": ["gpt-single"],
    }


def _extract_vuln_count(text: str) -> int:
    """Extract vulnerability count from response text."""
    import re
    patterns = [
        r"TOTAL UNIQUE VULNERABILITIES:\s*(\d+)",
        r"(\d+)\s*unique vulnerabilit",
        r"found\s*(\d+)\s*vulnerabilit",
        r"(\d+)\s*vulnerabilit",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    # Count numbered items as fallback
    items = re.findall(r"^\d+\.", text, re.MULTILINE)
    return len(items) if items else 0


async def run(oai_key: str, ant_key: str) -> list[dict[str, Any]]:
    """Run S1 scenario for all three systems."""
    client_oai = openai.AsyncOpenAI(api_key=oai_key)
    client_ant = anthropic.AsyncAnthropic(api_key=ant_key)

    results = await asyncio.gather(
        run_system_a(client_oai, client_ant),
        run_system_b(client_ant),
        run_system_c(client_oai),
        return_exceptions=True,
    )

    return [r for r in results if isinstance(r, dict)]


if __name__ == "__main__":
    import os, json
    results = asyncio.run(run(os.environ["OPENAI_API_KEY"], os.environ["ANTHROPIC_API_KEY"]))
    print(json.dumps(results, indent=2))
