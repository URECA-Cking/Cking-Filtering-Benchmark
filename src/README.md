# src

필터링 실험과 로컬 파이프라인 코드다. 채택 구성과 근거는 [채택 결정 문서](../docs/local-filter-decision.md)에 있다.

- `local_pipeline.py`: 채택한 로컬 전용 파이프라인(정규화 → 규칙 → 로컬 모델 → 최종 판정). 명령줄 실행도 지원한다.
- `rules/`: 정규화, 스팸·개인정보 규칙, 욕설 사전, 최종 판정 결합
- `pipeline.py`, `smoke_check.py`, `check_pipeline.py`: API를 쓰던 이전 구성과 탐색 도구
- `prepare_*.py`, `train_*.py`, `eval_*.py`: 데이터 준비, 2차 모델 학습·평가. 학습과 평가는 직접 실행하며 출력 경로는 새 이름이어야 한다.

데이터와 모델 파일은 Git에 올리지 않는다([데이터 정책](../docs/data-policy.md)).
