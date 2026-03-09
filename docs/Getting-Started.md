# Getting Started for Non-Developers

이 문서는 "GitHub에서 처음 내려받은 뒤, 설치하고, 새 AI를 하나 붙여서, 제대로 등록됐는지 확인하는 과정"만 따라가면 되게 만든 안내서입니다.

## 1. 준비물

- Mac 또는 Linux 터미널
- Python 3.10 이상
- 이 저장소를 내려받은 폴더

Python 확인:

```bash
python3 --version
```

예시:

```text
Python 3.14.3
```

## 2. RoleMesh 설치

터미널에서 RoleMesh 폴더로 이동한 뒤 실행:

```bash
pip install -e .
```

설치가 끝나면 아래로 확인:

```bash
rolemesh --help
```

정상이라면 도움말이 출력됩니다.

만약 `rolemesh` 명령을 못 찾으면:

1. 터미널을 다시 열기
2. 같은 폴더에서 `pip install -e .` 다시 실행
3. 임시로 `python3 -m rolemesh --help` 사용

## 3. 첫 초기화

```bash
rolemesh init
```

이 명령은 RoleMesh가 쓸 기본 DB와 초기 설정을 준비합니다.

등록된 AI 목록 확인:

```bash
rolemesh agents
```

## 4. 새 AI를 플러그인처럼 추가하기

여기서는 예시로 `nanoclaw`라는 AI를 붙입니다.

```bash
rolemesh integration add \
  --name nanoclaw \
  --role builder \
  --cmd "nanoclaw --stdio" \
  --provider nanoclaw \
  --capabilities build,edit,review
```

### 각 항목 쉽게 설명

- `--name`
  이 AI의 등록 이름입니다. 나중에 목록에서 보이는 이름입니다.
- `--role`
  이 AI의 담당 역할입니다.
  `builder`: 코드 작성/수정
  `analyst`: 분석/검토
  `coordinator`: 조율/정리
- `--cmd`
  실제로 이 AI를 실행하는 명령입니다.
- `--provider`
  이 AI 묶음의 이름이라고 생각하면 됩니다.
- `--capabilities`
  이 AI가 잘하는 일 목록입니다.

### `--endpoint`는 왜 안 넣었나요?

안 넣어도 됩니다.

RoleMesh가 자동으로 아래처럼 채웁니다.

```text
local://nanoclaw
```

### 추가 후 무엇이 생기나요?

자동으로 아래 파일이 생성됩니다.

```text
scripts/nanoclaw-delegate.sh
```

이 파일은 RoleMesh가 나중에 `nanoclaw`를 호출할 때 쓰는 실행 스크립트입니다.

## 5. 추가가 잘 됐는지 확인

```bash
rolemesh integration list
```

여기서 `nanoclaw`가 보이면 등록 성공입니다.

## 6. 실제로 써보기

```bash
rolemesh route "이 코드베이스를 빠르게 요약해줘"
```

RoleMesh는 등록된 AI 중에서 역할과 능력에 맞는 대상을 골라 작업을 넘깁니다.

## 7. 삭제하고 싶을 때

```bash
rolemesh integration remove --name nanoclaw
```

## 8. 자주 막히는 문제

### `rolemesh: command not found`

- 저장소 폴더 안에서 `pip install -e .`를 다시 실행
- 터미널을 다시 열기
- 급하면 `python3 -m rolemesh --help`로 먼저 사용

### `--cmd`를 모르겠어요

그 AI를 터미널에서 실행할 때 쓰는 명령을 넣으면 됩니다.

예:

- `nanoclaw --stdio`
- `claude`
- `codex`

### `--capabilities`는 꼭 넣어야 하나요?

필수는 아닙니다.
하지만 넣어두면 RoleMesh가 더 잘 고릅니다.

## 9. 가장 짧은 요약

처음 한 번만:

```bash
pip install -e .
rolemesh init
```

새 AI 추가:

```bash
rolemesh integration add --name nanoclaw --role builder --cmd "nanoclaw --stdio" --provider nanoclaw
```

확인:

```bash
rolemesh integration list
```
