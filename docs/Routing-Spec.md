# RoleMesh Routing Spec (v0.1)

## 1) 원칙
- **Rule-first**: 기본은 룰/스코어 기반
- **LLM-assist**: 애매한 요청만 LLM 분류
- **Safe fallback**: 실패 시 항상 deterministic

## 2) 입력 모델
- user_request
- active_agents (heartbeat active)
- capabilities (keywords, description, cost_level, avg_latency)
- performance history (success_rate, avg_duration)

## 3) 점수 계산
`final_score = role_match*0.35 + capability_match*0.35 + perf_score*0.2 + cost_latency_fit*0.1`

- role_match: 요청 intent와 역할 일치도
- capability_match: 키워드/의미 매칭
- perf_score: 최근 N건 성공률/지연
- cost_latency_fit: 사용자 모드(빠름/저비용/정확)

## 4) 라우팅 절차
1. 하드 룰 적용 (예: 코드요청→Builder 우선)
2. 후보 점수 계산
3. top1 confidence < threshold면 LLM 보조 분류
4. 최종 선택 + routing_log 기록
5. 실행 실패 시 차선 후보로 failover

## 5) 처리자 지정 방식
- 명시 라우팅: `to_agent` 직접 지정
- 자동 라우팅: `send_message_auto(task_text)`

## 6) 메시지 상태 머신
`pending -> processing -> done|failed`
- processing stale timeout 초과 시 `pending` 복구
- 재시도 초과 시 DLQ 이동(phase2)

## 7) 관측성
- routing_log: 선택 근거/점수
- feedback loop: `routing_feedback(routing_id, was_correct)`
- 대시보드 지표: accuracy, fallback율, retry율
