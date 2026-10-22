# 전체 개발 댓글 평가

`src.eval_full_dev`의 기본 실행은 개발 댓글 **109건 전체**를 두 모델에 각각 입력한다. 기존 `src.eval_kold_classifier`의 1차 `PASS` 77건 결과와 달리, 1차가 `BLOCK`한 댓글 32건도 모델 단독 성능 계산에 포함한다. `final` 분할은 명시적인 옵션과 별도 1차 결과 파일이 있어야 읽는다.

1차 결과는 이미 저장된 `results/pipeline-20261001T141252Z.jsonl`, `results/pipeline-20261001T145042Z.jsonl`을 사용한다. API를 다시 호출하지 않는다. 임계값 0.95는 이전 개발셋에서 정한 탐색용 값이다. 결과에는 1차 단독, KOLD 모델 단독, DKTC 모델 단독, 1차+KOLD, 1차+DKTC의 차단·오차단 수를 각각 출력한다. 모델 단독 지표는 API 제거 가능성을 살피는 첫 자료지만, 이 109건만으로 제거를 결정하지 않는다.

사용자가 Git Bash에서 실행:

```bash
cd /c/Ureca/BackEnd/Cking-Filtering-Benchmark
source .venv/Scripts/activate
python -m src.eval_full_dev --threshold 0.95
```

행별 점수는 Git 제외 경로 `results/full-dev/dktc-gap-v1-scores.jsonl`에 저장된다. 이미 있으면 덮어쓰지 않는다. 성능을 보고 설정을 더 조정하려면 별도 결과 이름을 사용하고, 최종 평가 세트는 개발을 마친 뒤 한 번만 실행한다.

## 고정한 설정으로 최종 평가 1회

개발 비교 결과에 따라 2차 모델 `results/kold-classifier/dktc-gap-v1/best`와 임계값 `0.95`를 고정했다. 최종 평가에서는 `context_eval.jsonl`과 `realistic_comments.jsonl`의 `final` 47건을 한 번만 사용한다. 먼저 1차 API·규칙 결과를 저장하고, 그 결과 파일을 두 모델의 전체 댓글 비교에 전달한다. API 키는 환경변수 `OPENAI_API_KEY`에만 둔다.

```bash
python -m src.check_pipeline --data data/context_eval.jsonl --data data/realistic_comments.jsonl --split final --allow-final --output results/final-stage1-20261002.jsonl
python -m src.eval_full_dev --split final --allow-final --stage-one-result results/final-stage1-20261002.jsonl --threshold 0.95
```

두 명령은 같은 고정 파일 경로를 사용하므로 파일명 치환이 필요 없다. 첫 명령이 정상 완료된 뒤 두 번째 명령을 실행한다. 두 번째 명령은 API를 다시 호출하지 않고, `final` 전체에서 1차 단독·모델 단독·결합 결과를 출력한다. 결과는 Git 제외 경로 `results/final/dktc-gap-v1-scores.jsonl`에 저장되며 기존 파일을 덮어쓰지 않는다. 최종 결과를 보고 임계값이나 데이터를 바꾸면 이 세트는 더 이상 독립 최종 평가가 아니다.
