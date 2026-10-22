# Cking Filtering Benchmark

Cking 서비스의 **댓글 필터링**에 적용할 모델과 방식을 정하기 위해 **별도로** 비교하는 실험 저장소입니다. 운영 API와 데이터 저장은 [Cking-BE](https://github.com/URECA-Cking/Cking-BE)의 책임입니다. 이 저장소의 실험 결과만으로 운영 기능의 성공을 주장하지 않습니다.

## 범위

- 필터링 대상: 크리에이터 게시글의 댓글(1~500자). 이후 다른 입력으로 넓힐지는 결과를 본 뒤 정합니다.
- 필터링 유형: 욕설·모욕(`ABUSE`), 혐오·차별(`HATE`), 스팸·광고(`SPAM`), 개인정보 노출(`PRIVACY`). 위반이 없으면 `NONE`입니다. 정의와 판단 원칙은 [평가 기준](docs/rubric.md)을 따릅니다.
- 처리 결과: **통과(`PASS`)와 차단(`BLOCK`) 두 값**입니다. 사람이 확인하는 단계는 두지 않으며, 정답 라벨의 `HOLD`는 AI 재판정이 필요한 경계 사례 표시입니다. 판정 규칙은 [평가 기준](docs/rubric.md)에 있습니다.
- 비교 대상: 무료로 쓸 수 있는 후보를 우선합니다. 현재 소량 호출로 검증한 후보는 판정 전용 분류기(OpenAI `omni-moderation-latest`)뿐입니다. Gemini는 무료로 호출할 수 없어 제외했고, LLM 후보는 별도 작업에서 다시 정합니다. 검토 내용은 [선정 기록](docs/selection.md)에 있습니다. 모델 ID·제공 상태·무료 한도·요금은 실행 직전에 다시 확인합니다.
- 평가 항목: 판별 정확도, 오탐(정상 댓글을 차단)·미탐(문제 댓글을 통과), 응답 시간, 호출 비용, 운영 부담

## 현재 상태

**결론:** 외부 API 없이 **로컬 규칙 + 로컬 2차 모델**만 쓰는 구성을 채택했습니다. 정규화 → 규칙(욕설 사전·개인정보·스팸) → 로컬 모델 점수(임계값 0.95) 순으로 판정하고 근거(`reasons`)를 남깁니다. 진입점은 `src/local_pipeline.py`입니다. 채택 이유, 평가 결과, 한계, 데이터 이용 조건, 배포 방침과 아직 정할 것은 [채택 결정 문서](docs/local-filter-decision.md)에 있습니다.

- 스팸은 모델 없이 규칙만으로 잡습니다. 링크가 포함된 댓글은 정상 공유도 모두 차단합니다.
- 노골적 성적·폭력·자해처럼 API가 강한 유형은 검증하지 않았습니다. 이전 API 포함 파이프라인(`src/pipeline.py`)과 탐색 기록([선정 기록](docs/selection.md))은 남겨 두었습니다.

문장은 모두 합성이고 정답 라벨은 사람 검수 전이며 기준은 **초안으로 팀 합의 전**입니다. 이 수치는 운영 성능이 아니라 평가 범위 안의 결과입니다. 학습 데이터(KOLD, DKTC)가 비상업 조건이라 상업 서비스에는 쓸 수 없고 시연 범위로 한정합니다.

## 평가 원칙

모델이 낸 판정과 사람이 검수한 정답 라벨을 대조해 평가합니다. API 호출 성공이나 응답 형식이 맞다는 것만으로 판별이 정확하다고 보지 않습니다. 오탐과 미탐을 따로 집계하고, 서비스에서 어느 쪽 오류가 더 큰 문제인지는 [평가 기준](docs/rubric.md)에 근거를 적습니다. 평가 데이터의 출처와 라벨 부여 방식은 항상 기록합니다.

외부 API 호출이 실패하거나 지연될 때의 처리 방식은 서비스 정책에 영향을 주므로, 모델 성능과 **별도로** 기록합니다. 파이프라인은 호출 실패를 상태로 남기고 규칙 신호만으로 판정합니다.

## 데이터와 설정

- [`docs/rubric.md`](docs/rubric.md): 필터링 유형과 라벨 기준, 최종 판정 규칙, 오류 비용, 평가 지표
- [`docs/data-policy.md`](docs/data-policy.md): Git에 올리는 데이터와 올리지 않는 데이터
- [`docs/results-format.md`](docs/results-format.md): 실행 결과 기록 형식
- [`docs/selection.md`](docs/selection.md): 후보 검토, 탐색 결과, 파이프라인 검증 기록
- [`data/comments.schema.json`](data/comments.schema.json): 평가 데이터 한 건의 계약
- `data/*.jsonl`: 합성 문장(샘플 7건과 유형별 탐색 문장). 모두 `pending_human`이며 사람 검수 전입니다.
- [`data/context_eval.jsonl`](data/context_eval.jsonl): 문맥 판별 평가 세트 96건(유형 8개 × 정상·위반 6쌍). 개발용(`dev`) 64건과 최종 평가용(`final`) 32건으로 나뉘며, 최종 평가용은 방법을 확정한 뒤 한 번만 봅니다.
- [`data/realistic_comments.jsonl`](data/realistic_comments.jsonl): 인스타그램·유튜브·페이스북 댓글 말투를 참고해 직접 작성한 60건(정상 48건, 위반 12건). 실제 수집 댓글은 아니며 라벨은 검수 전입니다. 개발용 45건과 최종 평가용 15건을 나누어 두었습니다. `python -m src.check_pipeline --data data/realistic_comments.jsonl --split dev`로 개발용을 평가합니다. API 키가 없으면 같은 명령에 `--dry-run`을 붙여 규칙만 확인할 수 있습니다.
- [`configs/pilot.yaml`](configs/pilot.yaml): 비교 실험 설정 초안

## 코드

- `src/rules/`: 정규화(`normalize.py`), 스팸·개인정보 규칙(`patterns.py`), 욕설 사전(`profanity.py`), 최종 판정 결합(`decision.py`)
- `src/local_pipeline.py`: **채택한 구성.** 정규화 → 규칙 → 로컬 모델 점수 → 최종 판정(`LocalFilter.moderate`). 외부 API를 호출하지 않는다.
- `server/app.py`: `src/local_pipeline.py`를 HTTP로 감싼 필터 서버(FastAPI). Cking-BE가 `POST /moderate`로 호출한다. 실행은 아래 [필터 서버](#필터-서버)
- `src/pipeline.py`: 이전 구성. 정규화 → 모델(OpenAI Moderation API) → 규칙 → 최종 판정. 탐색 기록용으로 남겨 둠
- `src/train_*.py`, `src/eval_*.py`, `src/prepare_*.py`: 2차 모델 학습·평가·데이터 준비 스크립트(재현 순서는 [채택 결정 문서](docs/local-filter-decision.md))
- `src/smoke_check.py`: 모델 소량 호출 검증 (OpenAI, Gemini)
- `src/check_pipeline.py`: 파이프라인을 탐색 문장으로 돌려 모델만 쓸 때와 비교
- `tests/`: `PYTHONUTF8=1 python -m unittest discover -s tests -t .` (설치할 패키지 없음)

실제 API 키는 환경변수로만 전달합니다. 키를 코드, 설정 파일, `.env`, 로그, Git에 저장하지 않습니다. 평가 데이터에는 욕설·비방 문구가 포함될 수 있으므로 원본 데이터와 원시 API 응답, 로컬 결과는 Git에 포함하지 않습니다.

## 필터 서버

Cking-BE는 이 서버의 `POST /moderate`를 호출해 댓글을 판정합니다(BE의 `COMMENT_FILTER_ENABLED`가 `true`일 때). 서버는 켜질 때 모델을 한 번 읽고, 요청마다 `LocalFilter.moderate`로 판정합니다. 외부 API를 호출하지 않습니다.

**준비**
- 패키지: 모델 실행용 `requirements-ml.txt`(PyTorch는 환경에 맞는 빌드를 먼저 설치)와 서버용 `requirements-server.txt`
- 모델 파일: Git에 없습니다(`results/`는 제외 대상). 저장소 루트 기준 `results/kold-classifier/threat-ctx-v1-reviewed/best/`에 아래 7개 파일을 둡니다(약 419MB). 배포에서는 S3에서 받아 이 경로에 둡니다. 경로는 `src/local_pipeline.py`의 `MODEL_DIR`에 고정돼 있고, `/moderate` 응답의 `modelVersion`은 `best`의 부모 폴더 이름(`threat-ctx-v1-reviewed`)입니다. 파일이 없으면 서버가 시작되지 않고 `FileNotFoundError`로 종료합니다.
  - `config.json`, `model.safetensors`, `special_tokens_map.json`, `stage2_config.json`, `tokenizer.json`, `tokenizer_config.json`, `training_args.bin`

**실행** (저장소 루트에서, 패키지를 설치한 파이썬으로)

```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
```

**PyTorch 스레드 설정(선택):** `FILTER_TORCH_THREADS`로 모델 연산에 사용할 스레드 수를 지정합니다. 환경변수를 설정하지 않으면 PyTorch 기본값을 유지합니다. 설정할 때는 양의 정수만 허용하며, 빈 값·0·음수·숫자가 아닌 값이면 서버 시작 시 `ValueError`로 종료합니다.

```bash
FILTER_TORCH_THREADS=1 python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Lambda에서는 메모리 설정별로 판정 시간을 측정하면서 이 값을 조정할 수 있습니다.

- `GET /health` → `{"status":"ok"}`. 모델을 다 읽은 뒤에 응답합니다.
- `POST /moderate`: 요청 `{"commentId": 1, "content": "댓글"}`(`content`는 1~500자, BE의 댓글 최대 길이와 같음) → 응답 `{"action": "PASS"|"BLOCK", "reasons": [...], "ruleVersion": "local-1", "modelVersion": "threat-ctx-v1-reviewed"}`. 형식이 틀리면 422이며, 응답에 댓글 원문을 되돌려 주지 않습니다.
- 규칙을 바꿀 때는 `server/app.py`의 `RULE_VERSION`을 올립니다.

**BE 연결:** `COMMENT_FILTER_ENABLED=true`, `COMMENT_FILTER_BASE_URL=http://<필터 서버 주소>:8000`

컴퓨트 방식, 로그 항목, 장애 시 처리는 [채택 결정 문서](docs/local-filter-decision.md#배포-방침과-아직-정할-것)에서 정합니다.

### 배포 (Lambda 컨테이너)

필터 서버는 AWS Lambda(arm64) 컨테이너 이미지로 배포합니다. BE는 Lambda 함수 URL을 IAM 서명(SigV4)으로 호출합니다(`COMMENT_FILTER_AUTH=aws-iam`).

- `Dockerfile`: CPU 전용 torch(기본 PyPI의 arm64 torch는 CUDA 패키지를 함께 받음), 고정 버전 목록 `requirements-image.txt`, Lambda Web Adapter(`/health`로 준비 확인), 서버 실행에 필요한 코드(`server/`, `src/local_pipeline.py`, `src/rules/`)와 모델만 넣습니다. 나머지는 `.dockerignore`로 빌드 문맥에서 뺍니다
- 모델: 경로는 `src/local_pipeline.py`의 `MODEL_DIR` 한 곳에서만 정합니다. `scripts/build-image.sh`가 이 값을 읽어 모델 이름(`MODEL_DIR`의 상위 폴더, 지금은 `threat-ctx-v1-reviewed`)과 이미지 안 경로를 정합니다. 모델 파일은 로컬 학습 결과(`MODEL_DIR`)가 있으면 그것을, 없으면 개발 배포 버킷 `s3://dev-cking-deploy-551372961758/filter/models/<모델 이름>/best/`를 씁니다. 모은 파일은 `model.sha256`과 목록·내용이 같아야 하고, 다르면 빌드 전에 멈춥니다
- 모델 교체: `MODEL_DIR`을 새 모델 이름의 경로로 바꾸고, `(cd <MODEL_DIR> && shasum -a 256 *) > model.sha256`으로 `model.sha256`을 다시 만들어 같은 커밋에 넣은 뒤, 그 이름으로 개발 배포 버킷 `filter/models/<모델 이름>/best/`에 파일을 올립니다. 응답의 `modelVersion`이 모델 이름이므로 이미 쓴 이름의 파일은 바꾸지 않습니다. `Dockerfile`, `.dockerignore`, CI는 고치지 않습니다
- CI(`.github/workflows/ci.yml`)
  - PR: 단위 테스트, 워크플로 검사
  - develop 푸시(이미지에 들어가는 파일이 바뀔 때): `scripts/build-image.sh`(모델 받기·빌드) → `scripts/check-image.sh`(Lambda와 같은 읽기 전용 파일 시스템·root가 아닌 사용자로 기동, `/health`, `/moderate` 통과·차단·422) → ECR `cking-comment-filter`에 커밋 태그로 푸시 → 개발 Lambda `dev-cking-comment-filter` 이미지 교체
    - 같은 커밋을 다시 실행하면 새로 빌드하지 않고 ECR에 올려 둔 이미지를 받아 확인한 뒤 그 이미지를 배포합니다
    - develop 실행은 푸시 순서대로 하나씩 돕니다. 대기 중인 실행은 새 푸시가 오면 취소되고 새 실행이 대신합니다
    - 개발 Lambda에 배포된 커밋이 이 커밋의 조상이면 교체하고, 이 커밋보다 새로우면(지난 실행 재시도) 건너뛰고, 이력이 갈라졌으면 실패합니다. 배포된 이미지에 커밋 태그가 여럿이면(내용이 같은 이미지) 모두 비교해, 하나라도 이 커밋보다 새로우면 건너뜁니다. 되돌릴 때는 되돌리는 커밋을 develop에 올립니다
    - 지난 실행을 다시 실행하면 대기 중인 최신 실행이 취소되므로, 다시 배포할 때는 가장 최근 실행을 다시 실행합니다
- 의존성을 바꾸면 linux/arm64, Python 3.12에서 CPU torch를 먼저 설치한 뒤 두 의존성 파일을 설치하고, `pip freeze`로 `requirements-image.txt`를 다시 만듭니다. `pip freeze`에 나오지 않는 setuptools는 `Dockerfile`에서 torch와 함께 고정합니다
- 의존성 갱신: Dependabot(`.github/dependabot.yml`, 매월, 마이너·패치만)이 액션, `requirements-image.txt`, `Dockerfile`의 이미지(베이스 이미지, Lambda 어댑터) PR을 올립니다. 베이스 이미지는 Python 3.12 계열을 유지하고(같은 태그의 새 digest만), 범위 지정인 `requirements-ml.txt`·`requirements-server.txt`는 받지 않습니다. PR CI는 이미지를 만들지 않으므로 `requirements-image.txt`·`Dockerfile` 변경은 develop 머지 뒤 개발 배포의 이미지 빌드·확인에서 검증되고, 확인에 실패하면 ECR에 올리기 전에 멈춥니다

로컬에서 이미지를 확인하려면 다음을 실행합니다(Docker, `jq` 필요. `MODEL_DIR`에 모델이 없으면 AWS 자격 증명으로 개발 배포 버킷에서 받음).

```bash
scripts/build-image.sh filter:check
scripts/check-image.sh filter:check
```

## 다음 단계

서비스 연동은 Cking-BE에서 진행합니다. 필터는 별도 서비스로 띄우고, 모델은 S3에서 받아 쓰며, 판정은 비동기로 하고 장애 시에는 댓글을 통과시킨 뒤 다시 필터링하는 방침입니다. 컴퓨트 방식, 로그 항목, 요청·응답 형식은 아직 정하지 않았고 [채택 결정 문서](docs/local-filter-decision.md#배포-방침과-아직-정할-것)에 정리했습니다. 놓친 댓글은 신고 → 사람 검수 → 추가 학습·규칙 보강 경로로 보완합니다. 비꼬기와 문맥이 필요한 위협은 이번 범위에서 제외했습니다.
