# Cking Filtering Benchmark

Cking 서비스의 **댓글 필터링**에 적용할 모델과 방식을 정하기 위해 **별도로** 비교하는 실험 저장소입니다. 운영 API와 데이터 저장은 [Cking-BE](https://github.com/URECA-Cking/Cking-BE)의 책임입니다. 이 저장소의 실험 결과만으로 운영 기능의 성공을 주장하지 않습니다.

## 범위

- 필터링 대상: 크리에이터 게시글의 댓글(1~500자). 이후 다른 입력으로 넓힐지는 결과를 본 뒤 정합니다.
- 필터링 유형: 욕설·모욕(`ABUSE`), 혐오·차별(`HATE`), 스팸·광고(`SPAM`), 개인정보 노출(`PRIVACY`). 위반이 없으면 `NONE`입니다. 정의와 판단 원칙은 [평가 기준](docs/rubric.md)을 따릅니다.
- 처리 결과: **통과(`PASS`)와 차단(`BLOCK`) 두 값**입니다. 사람이 확인하는 단계는 두지 않으며, 정답 라벨의 `HOLD`는 AI 재판정이 필요한 경계 사례 표시입니다. 판정 규칙은 [평가 기준](docs/rubric.md)에 있습니다.
- 비교 대상: 무료로 쓸 수 있는 후보를 우선합니다. 현재 소량 호출로 검증한 후보는 판정 전용 분류기(OpenAI `omni-moderation-latest`)뿐입니다. Gemini는 무료로 호출할 수 없어 제외했고, LLM 후보는 별도 작업에서 다시 정합니다. 검토 내용은 [선정 기록](docs/selection.md)에 있습니다. 모델 ID·제공 상태·무료 한도·요금은 실행 직전에 다시 확인합니다.
- 평가 항목: 판별 정확도, 오탐(정상 댓글을 차단)·미탐(문제 댓글을 통과), 응답 시간, 호출 비용, 운영 부담

## 현재 상태

**결론:** 외부 API 없이 **로컬 규칙 + 로컬 2차 모델**만 쓰는 구성을 채택했습니다. 정규화 → 규칙(욕설 사전·개인정보·스팸) → 로컬 모델 점수(임계값 0.95) 순으로 판정하고 근거(`reasons`)를 남깁니다. 진입점은 `src/local_pipeline.py`입니다. 채택 이유, 평가 결과, 한계, 데이터 이용 조건, 배포 전에 정할 것은 [채택 결정 문서](docs/local-filter-decision.md)에 있습니다.

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
- `src/pipeline.py`: 이전 구성. 정규화 → 모델(OpenAI Moderation API) → 규칙 → 최종 판정. 탐색 기록용으로 남겨 둠
- `src/train_*.py`, `src/eval_*.py`, `src/prepare_*.py`: 2차 모델 학습·평가·데이터 준비 스크립트(재현 순서는 [채택 결정 문서](docs/local-filter-decision.md))
- `src/smoke_check.py`: 모델 소량 호출 검증 (OpenAI, Gemini)
- `src/check_pipeline.py`: 파이프라인을 탐색 문장으로 돌려 모델만 쓸 때와 비교
- `tests/`: `PYTHONUTF8=1 python -m unittest discover -s tests -t .` (설치할 패키지 없음)

실제 API 키는 환경변수로만 전달합니다. 키를 코드, 설정 파일, `.env`, 로그, Git에 저장하지 않습니다. 평가 데이터에는 욕설·비방 문구가 포함될 수 있으므로 원본 데이터와 원시 API 응답, 로컬 결과는 Git에 포함하지 않습니다.

## 다음 단계

서비스 연동은 Cking-BE에서 진행합니다. 배포 방식(컴퓨트, 모델 파일 전달, 동기·비동기 판정, 장애 시 처리, 로그 정책)은 아직 정하지 않았고 [채택 결정 문서](docs/local-filter-decision.md#배포-전에-정할-것)에 목록이 있습니다. 놓친 댓글은 신고 → 사람 검수 → 추가 학습·규칙 보강 경로로 보완합니다. 비꼬기와 문맥이 필요한 위협은 이번 범위에서 제외했습니다.
