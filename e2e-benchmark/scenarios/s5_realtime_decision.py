"""
S5: Real-time Decision Making (Investment/Risk Simulation)
Measures: decision quality, response time, confidence calibration
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

SCENARIOS_DATA = [
    {
        "id": "portfolio_rebalance_1",
        "description": "Tech-heavy portfolio (70% FAANG) hit -35% YTD. Rising interest rates. Inflation at 6%. User is 35 years old, 25 years to retirement.",
        "optimal_action": "rebalance",
        "optimal_allocation": {"bonds": 20, "international": 20, "tech": 35, "value": 25},
        "risk_level": "high",
    },
    {
        "id": "crypto_panic_sell",
        "description": "User holds $50K crypto (BTC 60%, ETH 40%). Market dropped 40% in 1 week. User asking if should sell everything.",
        "optimal_action": "hold_or_partial",
        "optimal_allocation": {"crypto": 30, "cash": 20, "stocks": 50},
        "risk_level": "extreme",
    },
    {
        "id": "emergency_fund_invest",
        "description": "User has $30K emergency fund (6 months expenses). Wants to invest $20K of it in growth stocks for 'better returns'.",
        "optimal_action": "keep_emergency_fund",
        "optimal_allocation": {"emergency_fund": 30000, "invest_only_surplus": True},
        "risk_level": "low",
    },
    {
        "id": "concentrated_position",
        "description": "Employee has $200K in company stock (RSUs). This represents 80% of net worth. Company is growing 40% YoY.",
        "optimal_action": "diversify",
        "optimal_allocation": {"company_stock": 20, "diversified": 80},
        "risk_level": "high",
    },
    {
        "id": "market_timing",
        "description": "S&P500 at all-time high. User wants to wait for 'the crash' before investing $50K sitting in cash for 18 months.",
        "optimal_action": "dollar_cost_average",
        "optimal_allocation": {"invest_immediately_dca": True, "holding_cash": False},
        "risk_level": "medium",
    },
]

DECISION_PROMPT = """You are a financial advisor AI. For each portfolio scenario, provide:
1. RECOMMENDED ACTION: (1-2 words: rebalance/hold/sell/buy/diversify/dca)
2. REASONING: (3-5 key points)
3. RISK ASSESSMENT: (Critical/High/Medium/Low)
4. CONFIDENCE: (0-100%)
5. ALLOCATION SUGGESTION: (% breakdown if applicable)

Be decisive. No hedging."""

EVALUATOR_PROMPT = """Evaluate a financial advisor's decision against the optimal strategy.

Score 0-10 on:
1. Decision Quality: Does the recommended action align with optimal strategy?
2. Risk Calibration: Is the risk assessment accurate?
3. Reasoning Depth: Are key factors addressed?
4. Actionability: Is the advice concrete and implementable?

Format:
DECISION_SCORE: X (0-10, was the action correct?)
QUALITY_SCORE: X.X (weighted average)
CONFIDENCE_CALIBRATION: appropriate/overconfident/underconfident
"""


def _format_scenarios_prompt(scenarios: list[dict]) -> str:
    parts = []
    for i, s in enumerate(scenarios, 1):
        parts.append(f"SCENARIO {i}: {s['description']}")
    return "\n\n".join(parts)


async def _evaluate_decisions(client_oai: openai.AsyncOpenAI, response: str, scenarios: list[dict]) -> dict[str, Any]:
    import re

    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": EVALUATOR_PROMPT},
            {"role": "user", "content": f"Financial advisor response:\n{response}\n\nOptimal strategies: {[s['optimal_action'] for s in scenarios]}"}
        ],
        temperature=0.0,
    )
    text = resp.choices[0].message.content

    m1 = re.search(r"DECISION_SCORE:\s*([\d.]+)", text)
    m2 = re.search(r"QUALITY_SCORE:\s*([\d.]+)", text)
    m3 = re.search(r"CONFIDENCE_CALIBRATION:\s*(\w+)", text)

    return {
        "decision_score": float(m1.group(1)) if m1 else 5.0,
        "quality_score": float(m2.group(1)) if m2 else 5.0,
        "confidence_calibration": m3.group(1) if m3 else "unknown",
        "eval_text": text,
    }


async def _extract_confidence(text: str) -> float:
    import re
    matches = re.findall(r"CONFIDENCE:\s*(\d+)%?", text, re.IGNORECASE)
    if matches:
        return sum(float(m) for m in matches) / len(matches)
    return 70.0


async def run_system_a(client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic) -> dict[str, Any]:
    """System A: Parallel GPT+Claude analysis, then synthesis with risk arbitration."""
    start = time.time()
    prompt = _format_scenarios_prompt(SCENARIOS_DATA)

    gpt_task = client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": DECISION_PROMPT}, {"role": "user", "content": prompt}],
        temperature=0.1,
    )
    claude_task = client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": f"{DECISION_PROMPT}\n\n{prompt}"}],
    )
    gpt_resp, claude_resp = await asyncio.gather(gpt_task, claude_task)

    # amp arbitrates disagreements
    synthesis = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a risk arbitrator. When two advisors disagree, choose the more conservative/evidence-based approach. Synthesize into final recommendations."},
            {"role": "user", "content": f"Advisor 1:\n{gpt_resp.choices[0].message.content}\n\nAdvisor 2:\n{claude_resp.content[0].text}\n\nSynthesize final recommendations."}
        ],
        temperature=0.0,
    )
    output = synthesis.choices[0].message.content
    elapsed = time.time() - start

    eval_result = await _evaluate_decisions(client_oai, output, SCENARIOS_DATA)
    confidence = await _extract_confidence(output)

    return {
        "system": SYSTEM_A,
        "scenario": "s5_realtime_decision",
        "elapsed_seconds": elapsed,
        "raw_output": output[:800],
        "avg_confidence": confidence,
        **eval_result,
    }


async def run_system_b(client_ant: anthropic.AsyncAnthropic, client_oai: openai.AsyncOpenAI) -> dict[str, Any]:
    """System B: Claude standalone."""
    start = time.time()
    prompt = _format_scenarios_prompt(SCENARIOS_DATA)

    resp = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": f"{DECISION_PROMPT}\n\n{prompt}"}],
    )
    output = resp.content[0].text
    elapsed = time.time() - start

    eval_result = await _evaluate_decisions(client_oai, output, SCENARIOS_DATA)
    confidence = await _extract_confidence(output)

    return {
        "system": SYSTEM_B,
        "scenario": "s5_realtime_decision",
        "elapsed_seconds": elapsed,
        "raw_output": output[:800],
        "avg_confidence": confidence,
        **eval_result,
    }


async def run_system_c(client_oai: openai.AsyncOpenAI) -> dict[str, Any]:
    """System C: GPT standalone."""
    start = time.time()
    prompt = _format_scenarios_prompt(SCENARIOS_DATA)

    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": DECISION_PROMPT}, {"role": "user", "content": prompt}],
        temperature=0.1,
    )
    output = resp.choices[0].message.content
    elapsed = time.time() - start

    eval_result = await _evaluate_decisions(client_oai, output, SCENARIOS_DATA)
    confidence = await _extract_confidence(output)

    return {
        "system": SYSTEM_C,
        "scenario": "s5_realtime_decision",
        "elapsed_seconds": elapsed,
        "raw_output": output[:800],
        "avg_confidence": confidence,
        **eval_result,
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
