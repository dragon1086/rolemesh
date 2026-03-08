# Delegation Protocol — PM → Builder 위임 표준

## 핵심 규칙

기본 빌더 경로는 `scripts/cokac-delegate.sh`이며,
Anthropic rate limit 상황에서는 `scripts/codex-delegate.sh` fallback을 권장한다.
자동 fallback까지 포함한 기본 진입점은 `scripts/smart-delegate.sh`다.

빌더 옵션:
- `cokac` (Claude Code): 기본 빌더 (Anthropic)
- `codex` (OpenAI Codex): 대체 빌더
- `gemini`: 2차 fallback 빌더

---

## 위임 경로

```
록이(PM)
  └─▶ scripts/smart-delegate.sh   ← 권장 스마트 진입점
        ├─ SmartRouter(provider 우선순위: anthropic → openai-codex → gemini)
        ├─ CB OPEN / throttle 소진 provider 자동 스킵
        ├─ delegate 실행 실패 시 다음 provider로 최대 2회 fallback
        └─▶ 선택된 delegate.sh 실행

록이(PM)
  └─▶ scripts/cokac-delegate.sh   ← PM이 호출하는 기본 진입점
        └─▶ scripts/claude-delegate.sh
              ├─ Circuit Breaker 체크
              ├─ Throttle 체크
              └─▶ claude [args]

록이(PM)
  └─▶ scripts/codex-delegate.sh   ← OpenAI Codex 대체 진입점
        ├─ BatchCooldown 체크
        ├─ Circuit Breaker(provider=openai-codex) 체크
        ├─ Throttle(provider=openai-codex) 체크
        └─▶ codex exec -s danger-full-access --model gpt-5.3-codex -C <workdir> "<prompt>"
```

---

## 사용법

```bash
# 기본 위임
scripts/cokac-delegate.sh -p "버그 수정해줘"

# 스마트 fallback 위임 (권장)
scripts/smart-delegate.sh -C /path/to/project "버그 수정해줘"

# 모델 지정
scripts/cokac-delegate.sh --model claude-opus-4-5 -p "복잡한 리팩토링"

# 자동 승인 (CI/배치 환경)
scripts/cokac-delegate.sh --dangerously-skip-permissions -p "자동화 작업"

# claude-delegate.sh 직접 사용
scripts/claude-delegate.sh -p "질문"
scripts/claude-delegate.sh --version

# codex 빌더 위임
scripts/codex-delegate.sh -C /path/to/project "버그 수정해줘"
```

---

## Throttle 설정

설정 파일: `~/rolemesh/config/throttle.yaml`

```yaml
anthropic: 15
openai: 20
openai-codex: 30
gemini: 60
```

- 이 파일을 수정하면 즉시 반영됨
- 기본값보다 높게 올리면 rate limit에 걸릴 수 있음

---

## Circuit Breaker 상태 확인

```bash
# 현재 CB 상태 확인
python3 -c "
from rolemesh.adapters.circuit_breaker import ProviderCircuitBreaker
cb = ProviderCircuitBreaker()
print('anthropic:', cb.get_state('anthropic'))
print('남은 시간:', cb.cooldown_remaining('anthropic'), 's')
"

# CB 강제 초기화 (장애 복구용)
python3 -c "
from rolemesh.adapters.circuit_breaker import ProviderCircuitBreaker
ProviderCircuitBreaker().reset('anthropic')
print('CB reset 완료')
"

# 상태 파일 직접 확인
cat /tmp/rolemesh-cb-anthropic.json
```

---

## 왜 이 프로토콜이 필요한가?

연속 배치 실행 시 Anthropic API rate limit 초과가 발생했다.

기존 Throttle/Circuit Breaker는 큐 워커 내부에만 적용되어 있었고,
PM이 직접 위임하는 경로에는 보호장치가 부족했다.

이 프로토콜로:
- Throttle: provider별 요청 수 제한
- Circuit Breaker: 연속 실패 시 자동 차단
- Smart fallback router: Anthropic 차단/소진 시 Codex, 이후 Gemini로 자동 전환
- 위임 로그: 타임스탬프 포함 이력 stderr 기록

---

## 에러 핸들링

| 상황 | 동작 |
|------|------|
| CB OPEN | exit 1, 남은 시간 출력 |
| Throttle wait 필요 | sleep 후 자동 실행 |
| smart-delegate 1차 실패 | 다음 provider로 자동 fallback (최대 2회) |
| CB/Throttle 체크 실패 (Python 오류) | 경고 출력 후 delegate 그대로 실행 |
| delegate 실행 실패 | 종료 코드 그대로 전파 |

## 관련 스크립트

- `scripts/smart-delegate.sh`: 권장 기본 진입점
- `scripts/codex-delegate.sh`: OpenAI Codex 직접 위임
- `scripts/cokac-delegate.sh`: Anthropic/Claude 중심 기본 경로
