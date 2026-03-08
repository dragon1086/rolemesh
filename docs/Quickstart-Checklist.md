# Quickstart Checklist

External user quickstart validation — 2026-03-08.

## Prerequisites

- [x] python3 --version >= 3.10
- [x] pip install -e . 성공

## CLI Commands

- [x] python3 -m rolemesh init --lite 실행
- [x] python3 -m rolemesh status 출력
- [x] python3 -m rolemesh suggest --stack claude,openclaw 출력

## Results

| Check | Result | Notes |
|-------|--------|-------|
| python3 >= 3.10 | PASS | version 3.14.3 |
| pip install -e . | PASS | editable install OK |
| rolemesh --help | PASS | all commands listed |
| rolemesh status | PASS | 태스크 큐 상태 출력 (dlq: 0) |
| rolemesh suggest | PASS | pm=openclaw-pm 95%, builder=claude-builder 95% |

## Sample Output

### `python3 -m rolemesh status`
```
[init_db] 스키마 초기화 완료
태스크 큐 상태:
  dlq            : 0
```

### `python3 -m rolemesh suggest --stack claude,openclaw`
```
스택: claude, openclaw

역할                   에이전트                      신뢰도        이유
--------------------------------------------------------------------------------
pm                   openclaw-pm               95%        openclaw 감지 — PM 전담 에이전트 (우선 배정)
builder              claude-builder            95%        claude 감지 — 코드 구현 전담 Builder (우선 배정)
```
