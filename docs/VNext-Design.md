# RoleMesh vNext Design (Contract-first)

작성일: 2026-03-07  
상태: Implementing

## 목표
장문/노이즈 요청에서도 PM이 핵심 요구를 압축하고, 작업마다 독립 Contract 세션으로 실행해 문맥 비대증을 방지한다.

## 핵심 아이디어
1. **Contract-first**: WorkItem을 바로 던지지 않고 Contract로 정규화
2. **Session-per-contract**: contract_id/session_id를 생성해 실행 단위를 격리
3. **PM Packet Quality**: 패킷 품질 점수화 + 주간 리포트
4. **Rules vs Skills 분리**: Rules는 제한/정책, Skills는 절차 템플릿

## Contract 스키마
- `contract_id`: UUID
- `session_id`: `ctr-<8hex>`
- `title`, `goal`
- `scope`: 해야 할 일
- `out_of_scope`: 하지 말아야 할 일
- `acceptance`: 수용 기준
- `deliverables`: 산출물 기준
- `timeout_sec`
- `owner`: PM/Builder/Analyst
- `created_at`

## 실행 플로우
1. 사용자 요청 수신
2. PM이 core_request 압축
3. Contract 생성 (`WorkItem -> Contract`)
4. PM Packet 작성 (focus/acceptance/deliverables/harness)
5. 대상 에이전트로 라우팅
6. 결과 수집 + 품질 로그 저장

## 관측 지표
- PM packet 품질 점수(0~100)
- low quality 비율(<70)
- high quality 비율(>=85)
- contract당 평균 핵심요청 길이
- kind/assignee별 평균 품질

## 현재 구현 범위 (이번 반영)
- `src/rolemesh/contracts.py` 추가
- `symphony_fusion.py`에서 Contract 생성/주입
- PM quality JSONL 로깅 + 주간 리포트 스크립트
- `autoevo_worker.py`에 무한 루프 방지용 **Convergence Brake** 추가
  - no-op/거부 비율 과다 시 자동 pause
  - 연속 빈 enqueue 발생 시 자동 pause
  - 상태 파일: `/tmp/rolemesh-autoevo.state.json`

## 다음 단계
- Contract별 실제 isolated executor 프로세스 분리
- Rules/Skills registry 및 충돌 검사(cleanup)
- Contract 실패 유형별 자동 remediation 룰
