# 결과 형식

실행 결과는 `results/` 아래에 JSONL로 저장한다. `results/`는 Git에 포함하지 않는다. 판별 성능과 API 실패는 [평가 기준](rubric.md#api-실패지연)에 따라 분리해 기록한다. **초안이며 첫 실행기를 만들 때 확정한다.**

## 실행 한 건 (JSONL 한 줄)

| 필드 | 설명 |
| --- | --- |
| `runId` | 실행 묶음 ID. 같은 설정으로 돌린 실행을 묶는다 |
| `commentId` | `data/*.jsonl`의 `id` |
| `model` | 모델 ID. 실행 직전에 확인한 값을 기록한다 |
| `promptVersion` | 프롬프트 버전 |
| `apiStatus` | `ok` / `error` / `timeout` / `not_run` |
| `predictedAction` | `PASS` / `HOLD` / `BLOCK`. `apiStatus`가 `ok`일 때만 존재한다 |
| `predictedCategories` | 모델이 낸 유형. 없으면 빈 배열 |
| `reason` | 모델이 낸 판정 이유(참고용, 점수에 쓰지 않는다) |
| `latencyMs` | 호출 응답 시간 |
| `inputTokens`, `outputTokens` | 토큰 수 |
| `costUsd` | 호출 비용. 단가가 설정에 없으면 실행하지 않는다 |
| `error` | 실패 시 오류 요약 |

모델 원시 응답은 저장하더라도 `results/` 안에서만 보관한다.

## 집계

- 판별 지표는 `apiStatus == ok`인 건만으로 계산하고, 제외한 건수(`error`/`timeout`/`not_run`)를 항상 같이 보고한다.
- 지표 목록은 [평가 기준](rubric.md#평가-지표)을 따른다.
- 집계 결과 요약은 `docs/selection.md`에 옮길 때 원본 데이터를 포함하지 않는다.
