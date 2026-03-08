# RoleMesh CB/Throttle Integration Status

> 생성일: 2026-03-08
> 버전: RoleMesh 10차 통합 완료

---

## CB/Throttle 적용 경로 목록

| 경로 | CB 적용 | Throttle 적용 | provider 키 | 비고 |
|------|---------|--------------|------------|------|
| `src/rolemesh/symphony_fusion.py` | ✅ (`ProviderCircuitBreaker`) | ✅ (`TokenBucketThrottle`) | `"amp"` | graceful degradation |
| `src/rolemesh/autoevo_worker.py` | ❌ | ✅ (`TokenBucketThrottle`) | `"anthropic"` | enqueue 직전 체크, 1회 재시도 |
| `src/rolemesh/queue_worker.py` | ✅ (`ProviderRouter` 내장) | ✅ (`TokenBucketThrottle`) | per-provider | THROTTLE_MAX_RETRIES=3 |
| `src/rolemesh/amp_caller.py` | ✅ (자체 amp CB, `/tmp/amp-circuit-breaker.json`) | ❌ | `"amp"` (자체 구현) | rolemesh CB와 별도 |
| `src/rolemesh/provider_router.py` | ✅ (`ProviderCircuitBreaker` 내장) | ❌ | multi-provider | route() 시 자동 fallback |

---

## 미적용 경로

| 경로 | 이유 | 권장 조치 |
|------|------|----------|
| `src/rolemesh/integration.py` | registry 조작만 (외부 API 미호출) | 불필요 |
| `src/rolemesh/registry_client.py` | SQLite 로컬 I/O | 불필요 |
| `src/rolemesh/installer.py` | 설치 마법사, 단발성 작업 | 불필요 |
| `src/rolemesh/message_worker.py` | 메시지 큐 내부 처리 | 검토 권장 (low priority) |
| `src/rolemesh/round_reporter.py` | 보고서 생성, 외부 호출 없음 | 불필요 |

---

## 경로별 Rate Limit 위험도

| 경로 | 위험도 | 근거 |
|------|--------|------|
| `symphony_fusion.py` | **high** | amp/anthropic 외부 API 직접 호출, 장시간 실행 |
| `autoevo_worker.py` | **high** | 자동 루프로 enqueue 반복 → 연쇄 API 호출 유발 |
| `queue_worker.py` | **medium** | throttle 적용되나 THROTTLE_MAX_RETRIES 초과 시 재스케줄 |
| `amp_caller.py` | **medium** | 자체 CB 있으나 rolemesh CB/Throttle과 상태 분리됨 |
| `provider_router.py` | **low** | CB 내장, 복수 provider fallback |
| `message_worker.py` | **low** | 내부 메시지 처리, 직접 외부 API 미사용 |

---

## CB/Throttle 상태 파일

| 파일 | 용도 |
|------|------|
| `/tmp/rolemesh-cb-<provider>.json` | ProviderCircuitBreaker 상태 |
| `/tmp/rolemesh-throttle-<provider>.json` | TokenBucketThrottle 토큰 상태 |
| `/tmp/amp-circuit-breaker.json` | amp_caller 자체 CB 상태 |
| `/tmp/amp-timeouts.jsonl` | amp 타임아웃 이벤트 로그 |

---

## 통합 아키텍처 요약

```
autoevo_worker  →  [Throttle: anthropic]  →  enqueue(task_queue)
                                                    ↓
                                           queue_worker polls
                                                    ↓
                                    [ProviderRouter CB + Throttle]
                                                    ↓
                                          symphony_fusion.execute()
                                                    ↓
                                    [CB: amp] + [Throttle: amp]
                                                    ↓
                                               ask_amp()
                                                    ↓
                                    [amp_caller 자체 CB: amp]
                                                    ↓
                                           amp MCP server
```
