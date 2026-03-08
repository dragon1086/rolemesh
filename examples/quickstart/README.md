# RoleMesh Quickstart — 3단계로 시작하기

## 사전 요구사항
- Python 3.10+
- RoleMesh 설치: `pip install -e .` (프로젝트 루트에서)

---

## Step 1 — 초기화

```bash
python3 -m rolemesh init
```

환경을 탐지하고 기본 레지스트리 DB를 생성합니다.

---

## Step 2 — 에이전트 등록

```bash
python3 -m rolemesh integration add \
  --name mybot \
  --role builder \
  --endpoint http://localhost:8080 \
  --capabilities "build,deploy,test"
```

등록 확인:

```bash
python3 -m rolemesh integration list
```

---

## Step 3 — 첫 번째 요청 처리

데모 태스크를 큐에 추가하고 상태를 확인합니다:

```bash
bash run_demo.sh
```

또는 수동으로:

```bash
# 태스크 라우팅 확인
python3 -m rolemesh route "빌드 실행"

# 큐 상태 확인
python3 -m rolemesh status
```

---

## 설정 커스터마이즈

`sample_config.yaml`을 참고하여 에이전트 역할·엔드포인트를 수정하세요.

환경변수로 DB 경로 변경:

```bash
export ROLEMESH_DB=~/my-project/rolemesh.db
```
