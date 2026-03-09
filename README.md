# RoleMesh

RoleMesh는 여러 AI를 역할별로 연결해서 쓰기 쉽게 만드는 로컬 오케스트레이션 도구입니다.

Current release: `v0.2.3`

## 🚀 5분 설치 가이드

### 1. Python 버전 확인

터미널에서 아래 명령을 실행하세요.

```bash
python3 --version
```

이렇게 보이면 됩니다.

```text
Python 3.14.3
```

`Python 3.10` 이상이면 설치할 수 있습니다.

### 2. RoleMesh 설치

GitHub에서 이 저장소를 받은 뒤, 저장소 폴더 안에서 아래 명령을 실행하세요.

```bash
pip install -e .
```

이제 `rolemesh` 명령이 바로 생깁니다.

설치 확인:

```bash
rolemesh --help
```

만약 `command not found: rolemesh`가 보이면:

1. 터미널을 한 번 닫았다가 다시 여세요.
2. 다시 `pip install -e .`를 실행하세요.
3. 그래도 안 되면 `python3 -m rolemesh --help`로 먼저 실행해도 됩니다.

### 3. 처음 세팅

```bash
rolemesh init
```

조용히 기본 세팅만 하고 싶다면:

```bash
rolemesh init --lite
```

### 4. 현재 등록된 AI 보기

```bash
rolemesh agents
```

### 5. 바로 써보기

```bash
rolemesh route "이 프로젝트 구조를 설명해줘"
```

## 🔌 새 AI 추가하기 (nanoclaw 예시)

`nanoclaw` 같은 새 AI를 플러그인처럼 붙일 수 있습니다.

```bash
rolemesh integration add \
  --name nanoclaw \
  --role builder \
  --cmd "nanoclaw --stdio" \
  --provider nanoclaw \
  --capabilities build,edit,review
```

각 옵션 뜻:

- `--name`: 이 AI의 이름입니다. 마음대로 정해도 됩니다.
- `--role`: 역할입니다. `builder=코딩`, `analyst=분석`, `coordinator=조율`처럼 생각하면 됩니다.
- `--cmd`: 이 AI를 실제로 실행하는 명령어입니다.
- `--provider`: AI 제공자 이름입니다. 마음대로 정해도 됩니다.
- `--capabilities`: 이 AI가 할 수 있는 일 목록입니다.

`--endpoint`를 안 넣으면 자동으로 `local://nanoclaw`처럼 설정됩니다.

추가 후 자동으로 `scripts/nanoclaw-delegate.sh`가 생성됩니다.

확인:

```bash
rolemesh integration list
```

원하면 바로 라우팅 테스트도 가능합니다.

```bash
rolemesh route "간단한 리팩터링 도와줘"
```

## 자주 쓰는 명령

```bash
rolemesh --help
rolemesh init
rolemesh agents
rolemesh status
rolemesh route "테스트 코드 추가해줘"
rolemesh integration list
rolemesh integration remove --name nanoclaw
```

## 비개발자에게 중요한 포인트

- `pip install -e .`를 하면 `rolemesh` 명령이 바로 등록됩니다.
- 새 AI를 추가할 때 `--endpoint`는 보통 직접 넣지 않아도 됩니다.
- `--cmd`만 정확히 넣으면 RoleMesh가 실행 스크립트까지 자동으로 만들어 줍니다.
- AI를 여러 개 붙여도 `rolemesh route "할 일"`처럼 자연어로 요청하면 됩니다.

## 더 쉬운 설명이 필요하면

초보자용 상세 문서는 [docs/Getting-Started.md](/Users/rocky/rolemesh/docs/Getting-Started.md) 에 있습니다.

## 테스트

```bash
python3 -m pytest tests/ -q
```
