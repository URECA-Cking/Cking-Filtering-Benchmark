# KOLD 기반 2차 분류 모델 실험

이슈 #17의 로컬 학습·평가 절차다. 모델 학습과 추론은 사용자가 실행한다. 원본 KOLD와 전처리 데이터, 모델 가중치, 평가 결과는 모두 Git에서 제외된 경로에 저장한다.

## 목표와 라벨

2차 모델은 현재 1차 필터가 `PASS`한 **댓글 본문만** 받는다. KOLD 학습에는 `OFF=false`를 정상(0), `OFF=true`이면서 `TGT=individual` 또는 `group`인 댓글을 대상 공격(1)으로 사용한다. `OFF=true`의 `untargeted`·`other`는 이번 학습에서 제외한다. 이 라벨은 우리 서비스의 최종 `PASS/BLOCK` 정답이 아니라 학습용 근사치다. 협박과 비꼼이 별도 라벨로 제공되는 것은 아니므로 두 유형의 개선 여부는 반드시 우리 개발용 평가 세트에서 따로 확인한다.

KOLD 원본은 `data/raw/kold/data/kold_v1.json`에 있고, `python -m src.prepare_kold` 실행 결과는 `data/restricted/kold/`에 저장된다. 같은 댓글 문장의 중복을 제외하고 게시글 제목 기준으로 학습·검증·시험 데이터를 나눈다.

## 로컬 실행

Git Bash에서 프로젝트 루트로 이동한 다음 가상 환경을 만들고 의존성을 설치한다. Windows CPU 환경에서 PyTorch 설치 방식은 [공식 설치 안내](https://pytorch.org/get-started/locally/)에 맞춘다.

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-ml.txt
```

모델 입력은 댓글 본문 하나다. 게시글 제목은 모델에 전달하지 않는다. 학습 결과는 `results/kold-classifier/comment/best/`에 저장된다.

```bash
python -m src.train_kold_classifier
python -m src.eval_kold_classifier --model-dir results/kold-classifier/comment/best
```

CPU 학습에는 시간이 오래 걸릴 수 있다. 모델 구조·배치 크기·에폭 수를 바꾸면 별도 결과 디렉터리를 지정해 실험을 구분한다.

## 판단 기준

KOLD의 검증·시험 수치는 학습 정상 동작을 확인하는 참고 지표다. 실제 채택 판단은 우리 개발용 데이터에서 기존 1차 `PASS` 77건 중 추가로 잡은 위반 11건의 수, 정상 66건의 새 오차단 수, 특히 협박·비꼼 유형별 결과로 한다. 비꼼도 댓글 본문만으로 평가하고, 놓친 사례는 그대로 미탐에 포함한다. `src.eval_kold_classifier`는 점수별 임곗값과 댓글당 추론 시간(p50/p95)을 보여준다. 프로젝트의 `final` 분할은 읽지 않는다.

기존 Qwen 로컬 결과는 추가 탐지 1/11, 추가 오차단 0/66, p50 10.4초다. 더 많은 위반을 잡더라도 정상 댓글 오차단이 크게 늘면 적용하지 않는다. 개발용 77건은 작고 합성 라벨은 사람 검수 전이므로 실제 운영 성능으로 일반화하지 않는다.
