# RoleMesh PRD (vNext Contract-first)

작성일: 2026-03-06 (updated: 2026-03-07)  
상태: Active

## 1) 제품 한 줄
**RoleMesh**는 비개발자도 설치마법사로 로컬 AI 팀(PM/Builder/Analyst)을 구성하고, 역할 기반으로 자동 라우팅해 협업시키는 오케스트레이션 시스템이다.

## 2) 목표
- 비개발자 설치 시간 15분 이내
- 기본 번들: OpenClaw(PM) + cokac(Builder) + amp(Analyst) + Telegram 즉시 사용
- 신규 통합 추가 시 PM 라우팅에 자동 반영
- LLM 없어도 동작(룰 기반), 애매한 요청만 LLM 보조

## 3) 비목표 (v0.1)
- 완전한 클라우드 SaaS
- 모든 A2A 표준 100% 준수
- 고급 멀티테넌시/권한 시스템

## 4) 핵심 사용자
1. **비개발자 운영자**: "나는 OpenClaw/Claude Code 있음" 수준에서 바로 사용
2. **파워유저**: API/Repo를 연결해 역할 확장

## 5) 핵심 시나리오
1. 설치마법사 실행 → 보유 기술 탐지/입력
2. 시스템이 역할 매핑 추천 (PM/Builder/Analyst)
3. 기본 번들 구성 완료 → Telegram/CLI로 즉시 요청
4. 신규 통합 추가 → PM 라우팅 후보에 자동 포함

## 6) 기능 요구사항
- Role-first Registry
  - 역할(role), capability, cost/latency, heartbeat 등록
- Router
  - Rule-first + LLM-assist
  - fallback: deterministic routing
- Message Bus
  - task_queue + messages 소비 워커
  - pending→processing→done/failed, stale recovery
- Installer Wizard
  - 기술 입력/자동탐지
  - 역할 추천 + 충돌 해결
- Integration Add
  - 기술/플랫폼 입력 시 역할 추천
  - optional: repo/web 분석 기반 추천

### vNext 추가 요구사항 (Contract-first)
1. **Contract 생성 의무화**
   - 모든 라우팅에 `contract_id`, `session_id`, `owner`, `timeout_sec` 포함
   - PM 패킷은 core_request/acceptance/deliverables/focus_points를 반드시 포함
2. **IntentGate 선행**
   - PM이 라우팅 전에 요청 의도 정제(distill) + 모호성 검사
   - coding 요청은 최소 스펙(대상 파일/모듈, I/O, acceptance) 없으면 `clarify`로 차단
3. **Feature Manifest + Handoff Artifact**
   - contract별 `feature_manifest.json` 생성 (`passes=false/true` 관리)
   - contract별 `handoff_progress.md` 생성 (다음 세션 인계 표준)
4. **품질 계측**
   - PM 패킷 점수(0~100) 자동 기록(JSONL)
   - 주간 리포트 자동 생성(샘플 수, 평균, 저품질 비율, 하위 케이스)
5. **운영 노이즈 최소화**
   - 완료 이벤트 티어링 + 쿨다운
   - 중복 메시지 억제
6. **추상 태스크 차단**
   - Builder Prototype 등 스펙 미충족 coding 요청은 enqueue admission gate에서 차단
7. **무한루프 브레이크 + 재개조건**
   - convergence risk/empty enqueue streak 시 auto pause
   - manual trigger, 외부 활성태스크, 최근 non-noop 회복 시 auto resume
8. **Rules/Skills 정리 루프**
   - 주간 중복/충돌 점검 리포트 자동 생성 및 정리 액션 관리

## 7) 기본 역할 세트 (Default Bundle)
- PM: OpenClaw (필수)
- Builder: cokac (Claude Code/Codex)
- Analyst: amp
- Interface: Telegram + CLI

## 8) 성공 지표 (vNext)
- 설치 성공률 > 90%
- 첫 요청 처리 성공률 > 95%
- 라우팅 정확도(수동 라벨 기준) > 80%
- 메시지 유실률 0%
- PM 패킷 평균 점수 >= 85
- 저품질 패킷(<70) 비율 <= 10%
- 중복 enqueue/메시지 재발율 주간 감소 추세 유지

## 9) 리스크
- 로컬 환경 편차(토큰/경로/권한)
- 특정 에이전트 오프라인
- 메시지 소비자 미기동

## 10) 완화
- 설치 전 진단
- 워커 헬스체크 + auto-start
- dead-letter queue + 재시도 정책
