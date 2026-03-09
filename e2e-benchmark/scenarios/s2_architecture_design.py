"""
S2: Architecture Design Decision
Measures: analysis depth (1-10), perspectives considered, feasibility
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

DESIGN_PROMPT = """
A fintech startup needs to decide their backend architecture. Here are the constraints:

**Business Requirements:**
- 50,000 users at launch, projected 5M in 2 years
- Real-time transaction processing (< 100ms P99)
- Regulatory compliance: PCI-DSS, SOC2, GDPR
- 99.99% uptime SLA
- Budget: $50K/month infrastructure initially

**Technical Team:**
- 8 backend engineers (mostly Python/Go experience)
- 2 DevOps engineers
- No dedicated DBA

**Options to evaluate:**
A) Microservices (Kubernetes + service mesh)
B) Modular Monolith (single deployable, well-structured modules)
C) Serverless (AWS Lambda + Step Functions)

**Question:** Which architecture should they choose and why?
Provide detailed analysis covering: scalability, cost, complexity, team capability, compliance, time-to-market, and risk factors.
"""

EVALUATOR_PROMPT = """You are a senior architect evaluator. Score the following architecture recommendation on these dimensions (1-10 each):

1. Analysis Depth: How thoroughly are trade-offs analyzed?
2. Perspectives: How many relevant angles are covered? (tech, business, team, risk, cost, compliance)
3. Feasibility: Is the recommendation practically implementable?
4. Specificity: Are concrete implementation details provided?
5. Risk Awareness: Are risks and mitigations identified?

Response MUST start with:
SCORES: depth=X, perspectives=X, feasibility=X, specificity=X, risk_awareness=X
TOTAL_PERSPECTIVES: N (count distinct perspectives covered)
RECOMMENDATION_QUALITY: excellent/good/fair/poor
"""


async def _score_response(client_oai: openai.AsyncOpenAI, response: str) -> dict[str, Any]:
    """Score an architecture response using GPT as evaluator."""
    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": EVALUATOR_PROMPT},
            {"role": "user", "content": f"Evaluate this architecture recommendation:\n\n{response}"}
        ],
        temperature=0.0,
    )
    text = resp.choices[0].message.content
    scores = _parse_scores(text)
    return scores


def _parse_scores(text: str) -> dict[str, Any]:
    import re
    result = {"raw_eval": text}

    m = re.search(r"SCORES:\s*depth=(\d+),\s*perspectives=(\d+),\s*feasibility=(\d+),\s*specificity=(\d+),\s*risk_awareness=(\d+)", text)
    if m:
        vals = [int(x) for x in m.groups()]
        result["depth"] = vals[0]
        result["perspectives_score"] = vals[1]
        result["feasibility"] = vals[2]
        result["specificity"] = vals[3]
        result["risk_awareness"] = vals[4]
        result["average_score"] = sum(vals) / len(vals)

    m2 = re.search(r"TOTAL_PERSPECTIVES:\s*(\d+)", text)
    if m2:
        result["perspectives_count"] = int(m2.group(1))

    m3 = re.search(r"RECOMMENDATION_QUALITY:\s*(\w+)", text)
    if m3:
        result["quality"] = m3.group(1)

    return result


async def run_system_a(client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic) -> dict[str, Any]:
    """System A: OpenClaw (GPT) + cokac (Claude) + amp synthesis."""
    start = time.time()

    # Parallel analysis from two agents
    gpt_task = client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a senior software architect with expertise in distributed systems, fintech, and cloud infrastructure. Provide comprehensive analysis."},
            {"role": "user", "content": DESIGN_PROMPT}
        ],
        temperature=0.2,
    )
    claude_task = client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": f"You are a senior architect specializing in fintech systems, regulatory compliance, and team dynamics.\n\n{DESIGN_PROMPT}"}],
    )

    gpt_resp, claude_resp = await asyncio.gather(gpt_task, claude_task)
    gpt_analysis = gpt_resp.choices[0].message.content
    claude_analysis = claude_resp.content[0].text

    # amp synthesizes
    synthesis_resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are an architecture synthesis agent. Combine two expert analyses into the most comprehensive, balanced recommendation. Highlight areas where experts agree and resolve disagreements with evidence."},
            {"role": "user", "content": f"Expert 1 Analysis:\n{gpt_analysis}\n\nExpert 2 Analysis:\n{claude_analysis}\n\nSynthesize into final recommendation."}
        ],
        temperature=0.1,
    )
    synthesis = synthesis_resp.choices[0].message.content
    elapsed = time.time() - start

    scores = await _score_response(client_oai, synthesis)

    return {
        "system": SYSTEM_A,
        "scenario": "s2_architecture_design",
        "elapsed_seconds": elapsed,
        "raw_output": synthesis,
        "agents_used": ["gpt-architect", "claude-architect", "gpt-synthesis"],
        **scores,
    }


async def run_system_b(client_ant: anthropic.AsyncAnthropic, client_oai: openai.AsyncOpenAI) -> dict[str, Any]:
    """System B: Claude standalone."""
    start = time.time()

    resp = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": DESIGN_PROMPT}],
    )
    output = resp.content[0].text
    elapsed = time.time() - start
    scores = await _score_response(client_oai, output)

    return {
        "system": SYSTEM_B,
        "scenario": "s2_architecture_design",
        "elapsed_seconds": elapsed,
        "raw_output": output,
        "agents_used": ["claude-single"],
        **scores,
    }


async def run_system_c(client_oai: openai.AsyncOpenAI) -> dict[str, Any]:
    """System C: GPT standalone."""
    start = time.time()

    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a senior software architect."},
            {"role": "user", "content": DESIGN_PROMPT}
        ],
        temperature=0.2,
    )
    output = resp.choices[0].message.content
    elapsed = time.time() - start
    scores = await _score_response(client_oai, output)

    return {
        "system": SYSTEM_C,
        "scenario": "s2_architecture_design",
        "elapsed_seconds": elapsed,
        "raw_output": output,
        "agents_used": ["gpt-single"],
        **scores,
    }


async def run(oai_key: str, ant_key: str) -> list[dict[str, Any]]:
    client_oai = openai.AsyncOpenAI(api_key=oai_key)
    client_ant = anthropic.AsyncAnthropic(api_key=ant_key)

    results = await asyncio.gather(
        run_system_a(client_oai, client_ant),
        run_system_b(client_ant, client_oai),
        run_system_c(client_oai),
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, dict)]


if __name__ == "__main__":
    import os, json
    results = asyncio.run(run(os.environ["OPENAI_API_KEY"], os.environ["ANTHROPIC_API_KEY"]))
    print(json.dumps(results, indent=2))
