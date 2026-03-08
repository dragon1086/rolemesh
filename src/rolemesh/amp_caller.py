"""amp_caller.py — 록이(OpenClaw)가 amp에 질문을 보낼 때 사용하는 표준 인터페이스.

사용 예시:
    from amp_caller import ask_amp, is_amp_available

    # 헬스체크 후 호출
    if is_amp_available():
        result = ask_amp('삼성전자 지금 매수 타이밍이야?')
        print(result['answer'])
    else:
        print("amp 서버 오프라인")

    # 비교 질문 → 자동으로 debate (4-round) 선택
    result = ask_amp('성장주 vs 가치주 지금 어느 게 낫나?')

    # 폴백 확인
    if result.get('fallback'):
        print(f"폴백 이유: {result['reason']}")
"""

import json
import re
import time
import httpx
import asyncio
from typing import Optional

# amp MCP 서버 주소
AMP_MCP_URL = "http://127.0.0.1:3010"
CB_STATE_FILE = "/tmp/amp-circuit-breaker.json"
CB_OPEN_SEC = 600  # 10분
AMP_TIMEOUT_LOG = "/tmp/amp-timeouts.jsonl"

# 상록 기본 프로필 컨텍스트
DEFAULT_PROFILE = (
    "분석 대상 독자: 투자/주식 텔레그램 채널 운영자 (@stock_ai_ko). "
    "중장기 관점(3개월~1년) 중심. 개인투자자 대상 콘텐츠 제작. "
    "한국어로 답변할 것."
)

# debate (4-round) 트리거 패턴
_DEBATE_PATTERNS = [
    r"\bvs\b", "비교", "어느 게 낫", "뭐가 나아", "뭐가 좋",
    "장단점", "pros and cons", "찬반", "compare", "which is better",
    "차이", "대결", r"vs\.", "반박", "논쟁",
]




def _cb_state() -> dict:
    try:
        with open(CB_STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"opened_until": 0, "failures": 0, "last_error": ""}


def _cb_save(st: dict) -> None:
    try:
        with open(CB_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception:
        pass


def _cb_open(last_error: str) -> None:
    st = _cb_state()
    st["opened_until"] = int(time.time()) + CB_OPEN_SEC
    st["failures"] = int(st.get("failures", 0)) + 1
    st["last_error"] = (last_error or "")[:200]
    _cb_save(st)


def _cb_reset() -> None:
    _cb_save({"opened_until": 0, "failures": 0, "last_error": ""})


def _cb_is_open() -> tuple[bool, int, str]:
    st = _cb_state()
    now = int(time.time())
    until = int(st.get("opened_until", 0) or 0)
    if until > now:
        return True, until - now, st.get("last_error", "")
    return False, 0, ""

def _log_timeout_event(event: str, tool: str, timeout_s: float, attempt: int, error: str = "", elapsed_ms: int = 0, circuit_open: bool = False) -> None:
    try:
        row = {
            "ts": int(time.time()),
            "event": event,
            "tool": tool,
            "timeout_s": timeout_s,
            "attempt": attempt,
            "elapsed_ms": elapsed_ms,
            "error": (error or "")[:300],
            "circuit_open": circuit_open,
        }
        with open(AMP_TIMEOUT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _classify_tool(query: str, force_tool: Optional[str]) -> str:
    """질문 유형 자동 분류 → 'analyze' | 'debate' | 'quick_answer'"""
    if force_tool:
        return force_tool

    q = query.lower()
    for pattern in _DEBATE_PATTERNS:
        if re.search(pattern, q):
            return "debate"

    return "analyze"


def _cser_to_text(cser: Optional[float]) -> str:
    """CSER 점수 → 한국어 설명"""
    if cser is None:
        return ""
    if cser < 0.30:
        return "⚠️ 두 AI가 비슷한 의견이라 한 번 더 깊이 파봤어요"
    elif cser < 0.60:
        return "✅ 두 AI가 적절히 다른 시각 (균형잡힌 분석)"
    elif cser < 0.80:
        return "✅ 두 AI가 꽤 다른 시각 (풍부한 분석)"
    else:
        return "🔥 두 AI가 매우 다른 시각 (창의적 충돌)"


def _parse_response(raw: dict) -> dict:
    """MCP JSON-RPC 응답 파싱 → 표준 결과 dict"""
    result = raw.get("result", {})
    content_list = result.get("content", [])
    text = content_list[0].get("text", "") if content_list else ""

    # CSER 파싱 (응답 텍스트에서 추출)
    cser = None
    cser_match = re.search(r"(\d+\.\d+)\s*[|｜]", text)
    if cser_match:
        try:
            cser = float(cser_match.group(1))
        except ValueError:
            pass

    return {
        "answer": text,
        "cser": cser,
        "cser_text": _cser_to_text(cser),
        "raw": raw,
    }


def is_amp_available(timeout: int = 5) -> bool:
    """amp MCP 서버 헬스체크. 접근 가능하면 True.

    Args:
        timeout: 연결 타임아웃 (초)

    Returns:
        True이면 서버 응답 중, False이면 오프라인/타임아웃.
    """
    try:
        http_timeout = httpx.Timeout(float(timeout), connect=float(timeout))
        with httpx.Client(timeout=http_timeout) as client:
            # 빈 JSON-RPC ping으로 연결 확인 (응답 내용 무관)
            client.post(
                AMP_MCP_URL,
                json={"jsonrpc": "2.0", "id": 0, "method": "ping", "params": {}},
            )
        return True
    except (httpx.ConnectError, httpx.TimeoutException):
        return False
    except Exception:
        return False


def ask_amp(
    query: str,
    profile_context: Optional[str] = None,
    force_tool: Optional[str] = None,
    timeout: int = 90,
) -> dict:
    """amp에 질문 전송 (동기). 실패 시 1회 재시도 (5초 대기).

    Args:
        query:           질문 내용
        profile_context: 분석 컨텍스트 (None이면 상록 기본 프로필 사용)
        force_tool:      'analyze' | 'debate' | 'quick_answer' | None (자동)
        timeout:         HTTP 타임아웃 (초, 기본 45초)

    Returns:
        성공 시:
          dict with keys: 'answer', 'tool_used', 'cser', 'cser_text', 'raw'
        폴백 시 (접근 불가):
          dict with keys: 'fallback'=True, 'reason', 'answer', 'tool_used', 'cser', 'cser_text', 'raw'
    """
    tool = _classify_tool(query, force_tool)
    context = profile_context or DEFAULT_PROFILE
    tool_timeout = timeout
    if force_tool is None:
        # 기본값일 때만 도구별 상향 타임아웃 적용
        if tool == "debate":
            tool_timeout = max(timeout, 150)
        elif tool == "analyze":
            tool_timeout = max(timeout, 120)
        elif tool == "quick_answer":
            tool_timeout = max(timeout, 60)
    full_query = f"[분석 컨텍스트: {context}]\n\n{query}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": {"query": full_query},
        },
    }

    open_now, remain, last_err = _cb_is_open()
    if open_now:
        _log_timeout_event("circuit_open_skip", tool, float(tool_timeout), attempt=0, error=last_err, circuit_open=True)
        return {
            "fallback": True,
            "reason": "amp circuit-open",
            "answer": f"⚠️ amp 일시 차단 중({remain}s 남음). 로컬 fallback으로 진행.",
            "tool_used": tool,
            "cser": None,
            "cser_text": "",
            "raw": {},
        }

    http_timeout = httpx.Timeout(float(tool_timeout), connect=15.0)
    last_exc: str = ""

    for attempt in range(3):  # 최대 3회 (초기 + 2회 재시도)
        if attempt > 0:
            time.sleep(5)  # 재시도 전 5초 대기

        try:
            started = time.time()
            with httpx.Client(timeout=http_timeout) as client:
                resp = client.post(AMP_MCP_URL, json=payload)
                resp.raise_for_status()
                raw = resp.json()
            parsed = _parse_response(raw)
            parsed["tool_used"] = tool
            _cb_reset()
            _log_timeout_event("success", tool, float(tool_timeout), attempt=attempt+1, elapsed_ms=int((time.time()-started)*1000))
            return parsed

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exc = str(e)
            _cb_open(last_exc)
            _log_timeout_event("timeout", tool, float(tool_timeout), attempt=attempt+1, error=last_exc)
            continue

        except Exception as e:
            # 기타 오류 (HTTP 4xx, 파싱 오류 등) → 재시도 없이 즉시 폴백
            return {
                "fallback": True,
                "reason": f"amp error: {type(e).__name__}",
                "answer": f"⚠️ amp 호출 오류: {e}",
                "tool_used": tool,
                "cser": None,
                "cser_text": "",
                "raw": {},
            }

    # 모든 재시도 소진 → 폴백
    _cb_open(last_exc)
    _log_timeout_event("fallback_unavailable", tool, float(tool_timeout), attempt=3, error=last_exc, circuit_open=True)
    return {
        "fallback": True,
        "reason": "amp unavailable",
        "answer": "⚠️ amp 서버 불안정으로 로컬 fallback으로 진행.",
        "tool_used": tool,
        "cser": None,
        "cser_text": "",
        "raw": {},
    }


async def ask_amp_async(
    query: str,
    profile_context: Optional[str] = None,
    force_tool: Optional[str] = None,
    timeout: int = 90,
) -> dict:
    """amp에 질문 전송 (비동기). 실패 시 1회 재시도 (5초 대기).

    동기 버전과 동일한 인터페이스. asyncio 이벤트 루프에서 사용.
    """
    tool = _classify_tool(query, force_tool)
    context = profile_context or DEFAULT_PROFILE
    tool_timeout = timeout
    if force_tool is None:
        # 기본값일 때만 도구별 상향 타임아웃 적용
        if tool == "debate":
            tool_timeout = max(timeout, 150)
        elif tool == "analyze":
            tool_timeout = max(timeout, 120)
        elif tool == "quick_answer":
            tool_timeout = max(timeout, 60)
    full_query = f"[분석 컨텍스트: {context}]\n\n{query}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": {"query": full_query},
        },
    }

    open_now, remain, last_err = _cb_is_open()
    if open_now:
        _log_timeout_event("circuit_open_skip", tool, float(tool_timeout), attempt=0, error=last_err, circuit_open=True)
        return {
            "fallback": True,
            "reason": "amp circuit-open",
            "answer": f"⚠️ amp 일시 차단 중({remain}s 남음). 로컬 fallback으로 진행.",
            "tool_used": tool,
            "cser": None,
            "cser_text": "",
            "raw": {},
        }

    http_timeout = httpx.Timeout(float(tool_timeout), connect=15.0)
    last_exc: str = ""

    for attempt in range(2):
        if attempt > 0:
            await asyncio.sleep(5)

        try:
            started = time.time()
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                resp = await client.post(AMP_MCP_URL, json=payload)
                resp.raise_for_status()
                raw = resp.json()
            parsed = _parse_response(raw)
            parsed["tool_used"] = tool
            _cb_reset()
            _log_timeout_event("success", tool, float(tool_timeout), attempt=attempt+1, elapsed_ms=int((time.time()-started)*1000))
            return parsed

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exc = str(e)
            _cb_open(last_exc)
            _log_timeout_event("timeout", tool, float(tool_timeout), attempt=attempt+1, error=last_exc)
            continue

        except Exception as e:
            return {
                "fallback": True,
                "reason": f"amp error: {type(e).__name__}",
                "answer": f"⚠️ amp 호출 오류: {e}",
                "tool_used": tool,
                "cser": None,
                "cser_text": "",
                "raw": {},
            }

    _cb_open(last_exc)
    _log_timeout_event("fallback_unavailable", tool, float(tool_timeout), attempt=3, error=last_exc, circuit_open=True)
    return {
        "fallback": True,
        "reason": "amp unavailable",
        "answer": "⚠️ amp 서버 불안정으로 로컬 fallback으로 진행.",
        "tool_used": tool,
        "cser": None,
        "cser_text": "",
        "raw": {},
    }


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "삼성전자 지금 들어가도 될까?"
    print(f"질문: {query}")
    print(f"amp 서버 상태: {'✅ 온라인' if is_amp_available() else '❌ 오프라인'}")
    result = ask_amp(query)
    if result.get("fallback"):
        print(f"\n⚠️ 폴백 (이유: {result['reason']})")
    else:
        print(f"\n도구: {result['tool_used']}")
        print(f"CSER: {result['cser_text']}")
        print(f"\n답변:\n{result['answer']}")
