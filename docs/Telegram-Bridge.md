# Telegram Bridge

`TelegramBridge`는 텔레그램 대화를 RoleMesh 내부 라우팅 규칙으로 변환하는 얇은 게이트웨이 계층이다.

## 목적

- 상록과 록이(OpenClaw)의 텔레그램 메시지를 직접 처리하지 않고 RoleMesh를 통해 분류한다.
- 코딩 요청은 기존 delegate 스크립트로 위임한다.
- 분석 요청은 analyst 경로로 전달한다.
- 기억/일반 대화는 RoleMesh 내부 coordination 흐름에서 자체 처리한다.

## 구성 요소

- `src/rolemesh/gateway/telegram_bridge.py`
  - `MessageClass`: `CODING`, `ANALYSIS`, `MEMORY`, `COORDINATION`
  - `RouteResult`: 최종 라우팅 결과를 담는 dataclass
  - `TelegramBridge`: 규칙 기반 분류와 provider/script 결정을 담당
- `scripts/telegram-route.sh`
  - 입력 메시지 1개를 받아 `TelegramBridge.route()`를 호출
  - JSON `{class, provider, delegate_script, reason}`를 stdout으로 출력

## 라우팅 규칙

- `CODING`
  - 코딩/버그/리팩토링/테스트 등 키워드를 감지
  - `SmartRouter`가 사용 가능한 provider를 선택
  - delegate script:
    - `anthropic` -> `scripts/cokac-delegate.sh`
    - `openai-codex` -> `scripts/codex-delegate.sh`
    - `gemini` -> `scripts/gemini-delegate.sh`
- `ANALYSIS`
  - 전략/매수/매도/리스크/분석 등 키워드를 감지
  - 원격 provider가 가능하면 `scripts/amp-analyst-delegate.sh` 사용
- `MEMORY`
  - 기억/저장/메모 계열 명령
  - `provider=self`, `delegate_script=None`
- `COORDINATION`
  - 일반 대화, 인사, 상태 확인
  - `provider=self`, `delegate_script=None`

## 목표 아키텍처

1. 텔레그램 메시지 수신
2. `TelegramBridge.classify()`로 메시지 성격 결정
3. `TelegramBridge.route()`로 provider/delegate script 결정
4. 코딩/분석은 RoleMesh delegate 실행기로 전달
5. 기억/일반 대화는 RoleMesh 내부 처리

이 구조로 모든 텔레그램 대화는 먼저 RoleMesh를 통과하고, 그 뒤에만 실제 처리 경로가 결정된다.
