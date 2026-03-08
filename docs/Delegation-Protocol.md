# Delegation Protocol — PM → cokac 위임 표준

## 핵심 규칙

**직접 `claude -p` 호출 절대 금지.**
모든 위임은 `scripts/cokac-delegate.sh`를 통해야 한다.

---

## 위임 경로

```
록이(PM)
  └─▶ scripts/cokac-delegate.sh   ← PM이 호출하는 진입점
        └─▶ scripts/claude-delegate.sh  ← CB/Throttle 체크
              ├─ Circuit Breaker OPEN? → exit 1 (위임 차단)
              ├─ Throttle wait > 0?   → sleep 후 진행
              └─▶ claude [args]       ← 실제 실행
```

---

## 사용법

```bash
# 기본 위임
scripts/cokac-delegate.sh -p "버그 수정해줘"

# 모델 지정
scripts/cokac-delegate.sh --model claude-opus-4-5 -p "복잡한 리팩토링"

# 자동 승인 (CI/배치 환경)
scripts/cokac-delegate.sh --dangerously-skip-permissions -p "자동화 작업"

# claude-delegate.sh 직접 사용 (non-cokac 컨텍스트)
scripts/claude-delegate.sh -p "질문"
scripts/claude-delegate.sh --version
```

---

## Throttle 설정

설정 파일: `~/rolemesh/config/throttle.yaml`

```yaml
anthropic: 15   # 분당 15회 (Anthropic rate limit 여유 확보)
openai: 20
gemini: 60
```

- 이 파일을 수정하면 **즉시 반영** (재시작 불필요)
- 기본값보다 높게 올리면 rate limit에 걸릴 수 있음

---

## Circuit Breaker 상태 확인

```bash
# 현재 CB 상태 확인
python3 -c "
from src.rolemesh.circuit_breaker import ProviderCircuitBreaker
cb = ProviderCircuitBreaker()
print('anthropic:', cb.get_state('anthropic'))
print('남은 시간:', cb.cooldown_remaining('anthropic'), 's')
"

# CB 강제 초기화 (장애 복구용)
python3 -c "
from src.rolemesh.circuit_breaker import ProviderCircuitBreaker
ProviderCircuitBreaker().reset('anthropic')
print('CB reset 완료')
"

# 상태 파일 직접 확인
cat /tmp/rolemesh-cb-anthropic.json
```

---

## 왜 이 프로토콜이 필요한가?

연속 배치 실행 시 Anthropic API rate limit 초과가 발생했다 (8배치 연속 실행 → rate limit).

기존 Throttle/Circuit Breaker는 **큐 워커 내부**에만 적용되어 있었고,
PM이 직접 `claude -p`로 위임하는 경로에는 보호장치가 없었다.

이 프로토콜로:
- **Throttle**: 분당 요청 수를 15회로 제한해 rate limit 여유 확보
- **Circuit Breaker**: 연속 실패 시 자동 차단 → 불필요한 API 호출 방지
- **위임 로그**: 타임스탬프 포함 위임 이력 stderr 기록

---

## 에러 핸들링

| 상황 | 동작 |
|------|------|
| CB OPEN | exit 1, 남은 시간 출력 |
| Throttle wait 필요 | sleep 후 자동 실행 |
| CB/Throttle 체크 실패 (Python 오류) | 경고 출력 후 claude 그대로 실행 |
| claude 실행 실패 | claude 종료 코드 그대로 전파 |
