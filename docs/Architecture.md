# RoleMesh Architecture (v0.2.1)

작성일: 2026-03-06  
최종 업데이트: 2026-03-08  
상태: Active

## 1. 설계 원칙
- Role-first (기술보다 역할 우선)
- Rule-first routing (LLM은 보조)
- Local-first 실행 (개인 로컬 환경 중심)
- Fault-tolerant message flow (유실/중복 방지)

## 2. 기본 역할
- PM: `RegistryClient` + `SmartRouter`
- Builder: `queue_worker` + delegate scripts (`cokac`, `codex`, `gemini`)
- Analyst: `amp_caller`
- Interface: CLI, launchd/status scripts

## 3. 컴포넌트
1) **Registry (SQLite)**
- agents / capabilities / performance / routing_log
- messages / task_queue / dead_letter / quality_scores

2) **Router (PM 내부)**
- 입력: 요청 + 활성 에이전트 + capability + performance
- 출력: 처리자(agent) + 근거(explanation) + contract/session 메타데이터

3) **Workers**
- `src/rolemesh/workers/queue_worker.py`: task_queue 실행, provider circuit-breaker/throttle 연동
- `src/rolemesh/workers/message_worker.py`: messages 소비
- `src/rolemesh/workers/autoevo_worker.py`: self-improvement enqueue/pause-resume 루프
- 상태 전이: pending → running/processing → done/failed/DLQ

4) **Adapters**
- `src/rolemesh/adapters/smart_router.py`: delegate 선택
- `src/rolemesh/adapters/provider_router.py`: queue runtime provider 선택
- `src/rolemesh/adapters/amp_caller.py`: analyst 품질 평가
- `src/rolemesh/adapters/circuit_breaker.py` / `throttle.py`: provider 보호장치

5) **Installer Wizard**
- `rolemesh init`
- 역할 매핑 제안
- 연결 테스트/헬스체크

## 4. 라우팅 파이프라인
1. 하드 룰 적용 (코드 요청→Builder 우선)
2. 후보 점수 계산
3. confidence 낮으면 LLM 보조 분류
4. contract/session 생성 + PM packet 기록
5. 최종 라우팅 + 로그 기록
6. provider 실패 시 fallback

## 5. 메시지/태스크 신뢰성
- 원자적 claim으로 중복 실행 방지
- stale processing 자동 복구
- retry/backoff
- DLQ(dead-letter queue)
- PM 품질 점수 주간 리포트

## 6. 확장 모델
- 새 AI 추가 시:
  1) `rolemesh integration add`
  2) capability 등록
  3) 필요 시 delegate script 자동 생성
- 코어 로직 수정 없이 확장 가능

## 7. A2A/표준 호환 전략
- 단기: 내부 버스(SQLite) 유지
- 중기: envelope 표준화(JSON schema, trace_id)
- 장기: MCP/OpenAPI/이벤트 표준 연동

## 8. 보안/운영
- 토큰 로컬 저장(사용자 환경)
- 외부 호출 최소화
- 감사 로그(routing_log, task/result, quality_scores)
- launchd 기반 자동기동
