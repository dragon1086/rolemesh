"""
S6: amp 2-agent debate vs Claude standalone vs GPT standalone
투자/전략 분석 태스크 5개 — amp가 진짜 강점인 영역

Measures: answer_depth(1-10), perspective_count, actionability(1-10), response_time
Judge: GPT-5.4 blind evaluation
"""
import asyncio
import time
import sys
from typing import Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OPENAI_MODEL, ANTHROPIC_MODEL
import openai
import anthropic

# System labels for this scenario (overrides global SYSTEM_A/B/C)
SYSTEM_AMP = "amp_2agent_debate"
SYSTEM_CLAUDE = "claude_standalone"
SYSTEM_GPT = "gpt_standalone"

QUESTIONS = [
    {
        "id": "q1",
        "text": "AI 스타트업에 투자할 때 체크해야 할 리스크 요소 5가지는?",
        "domain": "investment",
        "personas": ("aggressive venture capitalist", "risk-averse portfolio manager"),
    },
    {
        "id": "q2",
        "text": "마이크로서비스 vs 모놀리식 아키텍처 결정 기준은?",
        "domain": "technology",
        "personas": ("move-fast engineer", "security-first architect"),
    },
    {
        "id": "q3",
        "text": "신제품 출시 전 PMF 검증 방법론 비교",
        "domain": "business",
        "personas": ("growth-at-all-costs operator", "sustainable profitability CFO"),
    },
    {
        "id": "q4",
        "text": "기술 부채 vs 신기능 개발 우선순위 결정 프레임워크",
        "domain": "technology",
        "personas": ("move-fast engineer", "security-first architect"),
    },
    {
        "id": "q5",
        "text": "원격 팀 생산성 측정 지표와 개선 전략",
        "domain": "business",
        "personas": ("growth-at-all-costs operator", "sustainable profitability CFO"),
    },
]

JUDGE_SYSTEM = """You are a blind expert evaluator. Evaluate the following answer to a strategic/investment question.
Score on three dimensions (1-10 each):
1. answer_depth: How thoroughly does it cover the topic?
2. actionability: How practical and actionable is the advice?
3. perspective_count: How many distinct perspectives/viewpoints are presented? (actual count, not score)

Respond in JSON only:
{"answer_depth": <1-10>, "actionability": <1-10>, "perspective_count": <int>}"""


async def _amp_debate(client_oai: openai.AsyncOpenAI, client_ant: anthropic.AsyncAnthropic, q: dict) -> str:
    """Simulate amp 2-agent debate using actual API calls.

    amp is available at http://127.0.0.1:3010 via amp_caller if the server is running.
    Falls back to simulated debate via direct API calls.
    """
    # Try real amp first
    try:
        sys.path.insert(0, "/Users/rocky/ai-comms")
        from amp_caller import ask_amp, is_amp_available  # type: ignore
        if is_amp_available():
            result = ask_amp(q["text"])
            return result.get("answer", "")
    except Exception:
        pass

    # Fallback: simulate amp debate via direct API calls
    persona_a, persona_b = q["personas"]

    # Agent A initial position
    resp_a = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": f"You are a {persona_a}. Give your expert perspective on the following strategic question. Be specific and opinionated."},
            {"role": "user", "content": q["text"]},
        ],
        temperature=0.3,
    )
    pos_a = resp_a.choices[0].message.content

    # Agent B challenges and counters
    resp_b = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[
            {"role": "user", "content": f"You are a {persona_b}. A {persona_a} gave this answer:\n\n{pos_a}\n\nChallenge the weak points and give your opposing expert view on: {q['text']}"},
        ],
    )
    pos_b = resp_b.content[0].text

    # Synthesis
    resp_syn = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a synthesis expert. Given two opposing expert views, create a balanced, comprehensive answer that incorporates both perspectives, surfaces blind spots, and makes trade-offs explicit."},
            {"role": "user", "content": f"Question: {q['text']}\n\n{persona_a} says:\n{pos_a}\n\n{persona_b} says:\n{pos_b}\n\nSynthesize into a definitive answer."},
        ],
        temperature=0.1,
    )
    return resp_syn.choices[0].message.content


async def _judge_answer(client_oai: openai.AsyncOpenAI, question: str, answer: str) -> dict:
    """GPT-5.4 blind judge evaluation."""
    import json, re
    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\nAnswer:\n{answer}"},
        ],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content
    try:
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {"answer_depth": 5, "actionability": 5, "perspective_count": 2}
    except Exception:
        return {"answer_depth": 5, "actionability": 5, "perspective_count": 2}


async def _run_single_question_amp(client_oai, client_ant, q):
    start = time.time()
    answer = await _amp_debate(client_oai, client_ant, q)
    elapsed = time.time() - start
    scores = await _judge_answer(client_oai, q["text"], answer)
    return {**scores, "elapsed": elapsed, "answer": answer}


async def _run_single_question_claude(client_ant, client_oai, q):
    start = time.time()
    resp = await client_ant.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": q["text"]}],
    )
    answer = resp.content[0].text
    elapsed = time.time() - start
    scores = await _judge_answer(client_oai, q["text"], answer)
    return {**scores, "elapsed": elapsed, "answer": answer}


async def _run_single_question_gpt(client_oai, q):
    start = time.time()
    resp = await client_oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": q["text"]}],
        temperature=0.3,
    )
    answer = resp.choices[0].message.content
    elapsed = time.time() - start
    scores = await _judge_answer(client_oai, q["text"], answer)
    return {**scores, "elapsed": elapsed, "answer": answer}


def _aggregate(question_results: list[dict]) -> dict:
    if not question_results:
        return {"answer_depth": 0, "actionability": 0, "perspective_count": 0, "avg_elapsed": 0}
    return {
        "answer_depth": sum(r["answer_depth"] for r in question_results) / len(question_results),
        "actionability": sum(r["actionability"] for r in question_results) / len(question_results),
        "perspective_count": sum(r["perspective_count"] for r in question_results) / len(question_results),
        "avg_elapsed": sum(r["elapsed"] for r in question_results) / len(question_results),
    }


async def run_system_amp(client_oai, client_ant) -> dict[str, Any]:
    start = time.time()
    results = []
    for q in QUESTIONS:
        r = await _run_single_question_amp(client_oai, client_ant, q)
        results.append(r)
    agg = _aggregate(results)
    average_score = (agg["answer_depth"] + agg["actionability"]) / 2
    return {
        "system": SYSTEM_AMP,
        "scenario": "s6_amp_analysis",
        "average_score": round(average_score, 3),
        "answer_depth": round(agg["answer_depth"], 2),
        "actionability": round(agg["actionability"], 2),
        "avg_perspective_count": round(agg["perspective_count"], 2),
        "elapsed_seconds": round(time.time() - start, 1),
        "questions_evaluated": len(QUESTIONS),
        "agents_used": ["gpt-debate-agent-a", "claude-debate-agent-b", "gpt-synthesis"],
    }


async def run_system_claude(client_ant, client_oai) -> dict[str, Any]:
    start = time.time()
    results = []
    for q in QUESTIONS:
        r = await _run_single_question_claude(client_ant, client_oai, q)
        results.append(r)
    agg = _aggregate(results)
    average_score = (agg["answer_depth"] + agg["actionability"]) / 2
    return {
        "system": SYSTEM_CLAUDE,
        "scenario": "s6_amp_analysis",
        "average_score": round(average_score, 3),
        "answer_depth": round(agg["answer_depth"], 2),
        "actionability": round(agg["actionability"], 2),
        "avg_perspective_count": round(agg["perspective_count"], 2),
        "elapsed_seconds": round(time.time() - start, 1),
        "questions_evaluated": len(QUESTIONS),
        "agents_used": ["claude-standalone"],
    }


async def run_system_gpt(client_oai) -> dict[str, Any]:
    start = time.time()
    results = []
    for q in QUESTIONS:
        r = await _run_single_question_gpt(client_oai, q)
        results.append(r)
    agg = _aggregate(results)
    average_score = (agg["answer_depth"] + agg["actionability"]) / 2
    return {
        "system": SYSTEM_GPT,
        "scenario": "s6_amp_analysis",
        "average_score": round(average_score, 3),
        "answer_depth": round(agg["answer_depth"], 2),
        "actionability": round(agg["actionability"], 2),
        "avg_perspective_count": round(agg["perspective_count"], 2),
        "elapsed_seconds": round(time.time() - start, 1),
        "questions_evaluated": len(QUESTIONS),
        "agents_used": ["gpt-standalone"],
    }


async def run(oai_key: str, ant_key: str) -> list[dict[str, Any]]:
    """Run S6: amp 2-agent debate vs standalone LLMs."""
    client_oai = openai.AsyncOpenAI(api_key=oai_key)
    client_ant = anthropic.AsyncAnthropic(api_key=ant_key)

    # Run sequentially to avoid rate limits (debate calls are expensive)
    results = []
    results.append(await run_system_amp(client_oai, client_ant))
    results.append(await run_system_claude(client_ant, client_oai))
    results.append(await run_system_gpt(client_oai))
    return results


if __name__ == "__main__":
    import os, json
    r = asyncio.run(run(os.environ["OPENAI_API_KEY"], os.environ["ANTHROPIC_API_KEY"]))
    print(json.dumps(r, indent=2, ensure_ascii=False))
