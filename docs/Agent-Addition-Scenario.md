# Agent Addition Scenario — RoleMesh 15차

새 AI 에이전트를 RoleMesh에 추가하고 delegate.sh가 자동 생성되는 시나리오 문서.

---

## 시나리오 A: Gemini CLI 추가 (builder 역할)

```bash
python3 -m rolemesh integration add \
  --name gemini \
  --role builder \
  --cmd "gemini -p" \
  --provider gemini \
  --capabilities analyze,summarize,code
```

### 기대 결과
- `scripts/gemini-delegate.sh` 생성
- 스크립트 내 BatchCooldown / CircuitBreaker / Throttle 체크 코드 포함
- `PROVIDER=gemini` 반영
- `gemini -p "$@"` 실행 블록 포함

### dry-run 확인
```bash
bash -n scripts/gemini-delegate.sh   # 문법 오류 없음
ls -la scripts/gemini-delegate.sh    # 실행 권한 확인
grep "gemini -p" scripts/gemini-delegate.sh
grep "gemini" scripts/gemini-delegate.sh | grep PROVIDER
```

---

## 시나리오 B: amp 분석기 추가 (analyst 역할)

```bash
python3 -m rolemesh integration add \
  --name amp-analyst \
  --role analyst \
  --cmd "python3 ~/amp/amp/interfaces/cli.py" \
  --provider anthropic \
  --capabilities analyze,debate,decide
```

### 기대 결과
- `scripts/amp-analyst-delegate.sh` 생성
- `PROVIDER=anthropic` 반영
- `python3 ~/amp/amp/interfaces/cli.py "$@"` 실행 블록 포함

### dry-run 확인
```bash
bash -n scripts/amp-analyst-delegate.sh
ls -la scripts/amp-analyst-delegate.sh
grep "amp/interfaces/cli.py" scripts/amp-analyst-delegate.sh
```

---

## 시나리오 C: 중복 추가 방지 확인

```bash
# 첫 등록 (성공)
python3 -m rolemesh integration add \
  --name gemini \
  --role builder \
  --cmd "gemini -p" \
  --provider gemini

# 중복 등록 (실패 예상 — DuplicateIntegrationError)
python3 -m rolemesh integration add \
  --name gemini \
  --role builder \
  --cmd "gemini -p" \
  --provider gemini
# → 오류: 'gemini' 통합이 이미 등록되어 있습니다.

# allow_update로 덮어쓰기 (스크립트도 갱신)
python3 -m rolemesh integration add \
  --name gemini \
  --role builder-v2 \
  --cmd "gemini --new-flag -p" \
  --provider gemini \
  --update
# → scripts/gemini-delegate.sh 갱신 확인
```

---

## 시나리오 D: 잘못된 cmd 입력 방어

```bash
# cmd가 빈 문자열 → ValueError
python3 -m rolemesh integration add \
  --name bad-bot \
  --role builder \
  --cmd "" \
  --provider openai
# → 오류: auto_script=True일 때 cmd는 비어 있을 수 없습니다.

# --no-auto-script를 사용하면 cmd 없이도 등록 가능
python3 -m rolemesh integration add \
  --name bad-bot \
  --role builder \
  --no-auto-script
# → delegate.sh 미생성, 레지스트리 등록만 완료
```

---

## 확인 명령

```bash
# 등록된 통합 목록
python3 -m rolemesh integration list

# 생성된 스크립트 목록
ls -la scripts/*-delegate.sh

# 문법 검사
for f in scripts/*-delegate.sh; do bash -n "$f" && echo "OK: $f"; done
```
