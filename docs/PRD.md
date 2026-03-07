# RoleMesh PRD (v0.1 Draft)

작성일: 2026-03-06  
상태: Draft (리뷰 대기)

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

## 7) 기본 역할 세트 (Default Bundle)
- PM: OpenClaw (필수)
- Builder: cokac (Claude Code/Codex)
- Analyst: amp
- Interface: Telegram + CLI

## 8) 성공 지표 (v0.1)
- 설치 성공률 > 90%
- 첫 요청 처리 성공률 > 95%
- 라우팅 정확도(수동 라벨 기준) > 80%
- 메시지 유실률 0%

## 9) 리스크
- 로컬 환경 편차(토큰/경로/권한)
- 특정 에이전트 오프라인
- 메시지 소비자 미기동

## 10) 완화
- 설치 전 진단
- 워커 헬스체크 + auto-start
- dead-letter queue + 재시도 정책
