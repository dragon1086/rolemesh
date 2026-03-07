# RoleMesh Architecture (v0.1)

작성일: 2026-03-06  
상태: Draft

## 1. 설계 원칙
- Role-first (기술보다 역할 우선)
- Rule-first routing (LLM은 보조)
- Local-first 실행 (개인 로컬 환경 중심)
- Fault-tolerant message flow (유실/중복 방지)

## 2. 기본 역할
- PM: OpenClaw (필수)
- Builder: cokac (Claude Code/Codex)
- Analyst: amp
- Interface: Telegram, CLI

## 3. 컴포넌트
1) **Registry (SQLite)**
- agents / capabilities / performance / routing_log
- messages / task_queue

2) **Router (PM 내부)**
- 입력: 요청 + 활성 에이전트 + capability + performance
- 출력: 처리자(agent) + 근거(explanation)

3) **Workers**
- queue_worker: task_queue 실행
- message_worker(agent별): messages 소비
- 상태 전이: pending → processing → done/failed

4) **Adapters**
- openclaw adapter
- cokac adapter
- amp adapter
- (확장) external provider adapters

5) **Installer Wizard**
- 보유 기술 탐지/입력
- 역할 매핑 제안
- 연결 테스트/헬스체크

## 4. 라우팅 파이프라인
1. 하드 룰 적용 (코드 요청→Builder 우선)
2. 후보 점수 계산
3. confidence 낮으면 LLM 보조 분류
4. 최종 라우팅 + 로그 기록
5. 실패 시 failover

## 5. 메시지 신뢰성
- 원자적 claim으로 중복 실행 방지
- stale processing 자동 복구
- retry/backoff (phase 1)
- DLQ(dead-letter queue) (phase 1)

## 6. 확장 모델
- 새 AI 추가 시:
  1) adapter 추가
  2) capability 등록
  3) worker 타겟 등록
- 코어 로직 수정 없이 확장 가능

## 7. A2A/표준 호환 전략
- 단기: 내부 버스(SQLite) 유지
- 중기: envelope 표준화(JSON schema, trace_id)
- 장기: MCP/OpenAPI/이벤트 표준 연동

## 8. 보안/운영
- 토큰 로컬 저장(사용자 환경)
- 외부 호출 최소화
- 감사 로그(routing_log, task/result)
- launchd 기반 자동기동
