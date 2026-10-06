# 별도 댓글 평가 세트: gap challenge v1

`data/restricted/gap_challenge_v1.jsonl`은 기존 KOLD 모델과 DKTC 추가 학습 모델을 **같은 새 댓글**에서 비교하기 위해 만든 48건의 합성 평가 세트다. 댓글 본문 하나만 모델에 입력한다. 기존 개발 평가 문장과 DKTC 추가 학습 문장의 정확한 중복을 검사했다. 어느 학습에도 넣지 않는다.

| 유형 | BLOCK | PASS | 확인하려는 오류 |
| --- | ---: | ---: | --- |
| 추적·감시·사생활 노출 위협 | 12 | 10 | 위협 미탐과 안전 조언 오차단 |
| 인용·신고 | 0 | 8 | 피해 호소 오차단 |
| 비꼼·칭찬 | 9 | 9 | 간접 조롱 미탐과 칭찬 오차단 |

문장은 Codex가 새로 작성했고 `reviewStatus: codex_provisional`이다. 실제 댓글의 출현 비율이나 운영 오차단률을 추정하는 자료가 아니다. 비꼼 등 경계 사례의 라벨은 사람이 검토하면 더 신뢰할 수 있다. 기존 개발 점수에서 선택한 **임계값 0.95를 평가 전에 고정**한다. 이 세트를 보고 다시 문장을 고치거나 임계값을 반복 조정하면 독립 확인의 의미가 줄어든다.

사용자가 Git Bash에서 두 모델을 점수화한다. 이 명령은 학습하지 않으며 1차 Moderation API도 실행하지 않는다. 따라서 결과는 **2차 모델 단독 진단**이고 전체 파이프라인 차단률이 아니다.

```bash
cd /c/Ureca/BackEnd/Cking-Filtering-Benchmark
source .venv/Scripts/activate
python -m src.eval_gap_challenge --threshold 0.95
```

출력은 화면의 유형별 집계와 Git에서 제외된 `results/gap-challenge-v1/scores.jsonl`이다. 이미 출력이 있으면 덮어쓰지 않는다. 평가 데이터의 원본 TSV는 `data/restricted/gap_challenge_v1.tsv`, 생성 코드는 `python -m src.prepare_gap_challenge`다. 프로젝트의 `final` 분할은 읽지 않는다.
