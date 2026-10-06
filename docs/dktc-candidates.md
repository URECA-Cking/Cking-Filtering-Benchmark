# DKTC 협박 발화 검토 후보

DKTC `data/train.csv`의 `class`는 **대화 전체**에 붙은 라벨이다. 이 스크립트는 `협박 대화`의 줄별 발화 중 위협 표현 단서가 있는 것을 검토 후보로 모을 뿐, 댓글의 `BLOCK` 정답을 만들지 않는다. DKTC 테스트 분할은 읽지 않는다. 출처는 [TUNiB DKTC](https://github.com/tunib-ai/DKTC)이며 라이선스는 CC BY-NC-SA 4.0이다. 비상업적 로컬 실험 범위에서만 사용한다.

Git Bash에서 실행:

```bash
python -m src.prepare_dktc_candidates
python -m src.prepare_dktc_candidates --all-classes
```

결과는 Git에서 제외된 `data/restricted/dktc/threat_candidates.jsonl`에 저장된다. `source`, `conversationId`, `turnIndex`, `text`, `cueTypes`, `privacyFlags`, `reviewStatus`, `expectedAction`, `notes`를 남긴다. `expectedAction`은 `null`이며 모델 학습에는 이 파일을 바로 사용하지 않는다. 단서 검색은 비유나 인용을 포함할 수 있고 단서가 없는 간접 위협은 빠질 수 있다.

두 번째 명령은 `data/restricted/dktc/all_class_candidates.jsonl`을 별도로 만든다. DKTC 학습 3,950개 대화 전체에서 후보 632줄(협박 476, 갈취 67, 기타 괴롭힘 50, 직장 괴롭힘 39)을 찾았다. 다른 대화 유형에서도 명확한 위협이 있지만, `때려치우다`, 피해자의 신고, 합법적인 항의처럼 검색 오류도 많다. `conversationClass`는 원래 **대화 전체 라벨**을 기록하는 메타데이터일 뿐 각 줄의 정답이 아니다. 전화번호·주소의 자동 가림은 완전하지 않으므로 원문 검토가 필요하다.

## 현재 모델의 빈틈을 우선 검토

현재 1차 통과 개발셋에서 협박 0/4, 관용적 위협 0/1, 비꼼 1/4를 차단했다. DKTC 검토에서는 노골적인 살해·욕설 표현보다 **위해를 완곡하게 암시하거나 거주지·가족 정보를 이용해 압박하는 발화**를 먼저 본다. `stalking_or_exposure`, `implicit_threat` 단서는 이 용도의 후보 검색이며, 단서 자체가 위협 판정은 아니다.

첫 검토 묶음은 로컬 `data/restricted/dktc/gap_review_decisions.tsv`에 후보 ID와 임시 판단 근거를 기록했다. 다음 명령으로 원문 후보와 결합한다.

```bash
python -m src.make_dktc_review_batch
```

결과 `data/restricted/dktc/gap_review_batch.jsonl`의 `suggestedDisposition`은 Codex의 검토 제안이다. `propose_block`은 한 줄만 읽어도 위협으로 보이는 문장, `needs_context`는 판정 유보, `exclude`는 피해자 발언·법적 대응 등의 검색 오류를 뜻한다. **어느 것도 확정 라벨이 아니며** `reviewStatus: pending_human`, `expectedAction: null`을 유지한다. `exclude`를 자동으로 `PASS` 학습 예시로 바꾸지 않는다.

사람이 검토하기 편한 CSV는 다음 명령으로 한 번 만든다. 이 파일에는 위 DKTC 30건과, 비슷한 단어를 쓰지만 정상인 새 합성 댓글 12건이 함께 있다. 기존 CSV가 있으면 덮어쓰지 않아 검토 내용을 보호한다.

```bash
python -m src.export_dktc_review_sheet
```

`data/restricted/dktc/gap_review_sheet.csv`에서 `text`를 댓글 하나로 판단한다. 판정이 확실한 행만 `expectedAction`에 `BLOCK` 또는 `PASS`, `reviewStatus`에 `approved`를 넣고 `notes`에 근거를 남긴다. 맥락이 필요한 행은 빈칸과 `pending_human`을 유지한다. 원문에 이름이나 개인정보가 보이면 먼저 삭제하거나 그 행을 제외한다. `exclude` 행은 오탐 예시를 보여주기 위한 것이며, 그대로 `PASS` 학습에 넣는 대상이 아니다.

Git Bash에서 검토표를 기본 CSV 프로그램으로 열고, 저장한 뒤 검증한다.

```bash
explorer.exe "$(cygpath -w data/restricted/dktc/gap_review_sheet.csv)"
python -m src.validate_dktc_review_sheet
```

검증기는 `approved` 행에만 `BLOCK`/`PASS`를 허용하고, `notes`의 검토 근거를 요구한다. 기존 개발 평가 문장과 일치하거나 같은 문장이 중복되면 중단한다. 통과하면 확정 행만 Git 제외 경로 `data/restricted/dktc/approved_comments.jsonl`에 저장한다. 라벨이 확정되기 전에는 검증 명령이 실패하는 것이 정상이다.

Codex가 문장별로 판단한 탐색용 라벨은 `python -m src.prepare_dktc_provisional`로 `data/restricted/dktc/provisional_comments.jsonl`에 저장한다. 이 파일의 `reviewStatus`는 `codex_provisional`이며 사람 승인으로 표시하지 않는다. 현재 `BLOCK` 13건과 합성 `PASS` 12건이다. 이 작은 표본만으로 실사용을 결정하지 않으며, 모델 변화 방향을 보는 실험에만 쓴다.

**사용자가** Git Bash에서 아래 명령으로 추가 학습·평가한다. 새 모델은 기존 KOLD 체크포인트와 다른 폴더에 저장된다. KOLD 학습 행을 일부 다시 섞어 기존 공격 탐지 능력의 급격한 손실을 줄이려는 탐색적 설정이며, 작은 신규 데이터로 얻은 개선은 개발셋과 별도 새 평가 자료에서 확인해야 한다.

```bash
source .venv/Scripts/activate
python -m src.prepare_dktc_provisional
python -m src.train_dktc_gap_classifier --output-dir results/kold-classifier/dktc-gap-v1
python -m src.eval_kold_classifier --model-dir results/kold-classifier/dktc-gap-v1/best
```

학습 결과 폴더가 이미 있으면 학습 스크립트가 중단한다. 새 실험은 `--output-dir`에 다른 이름을 준다. 사람이 검토한 CSV를 나중에 사용하려면 `python -m src.validate_dktc_review_sheet`로 승인 데이터를 내보내고 학습 명령에 `--approved data/restricted/dktc/approved_comments.jsonl`을 지정한다. 비꼼은 이 DKTC 추가 학습으로 해결될 것으로 보지 않으며 별도 보강 실험이 필요하다.

DKTC는 협박 대화 자료라 **비꼼·간접 조롱 보강에는 적합한 공급원이 아니다.** 비꼼은 별도의 댓글 단위 자료 또는 새로 작성한 문장을 독립적으로 검토해야 한다. 기존 개발 평가 문장의 복제나 단순 치환은 쓰지 않는다.

## 사람 검토

1. 각 `text`만 읽고 독립된 크리에이터 댓글이라면 어떻게 판단할지 검토한다. 앞뒤 대화를 알아야 위협인 발화는 제외한다.
2. 이름, 전화번호, 주소, 계정 등 개인 정보가 없는지 확인한다. 전화번호·이메일·주민등록번호 형태는 일부 자동 가림 처리하지만 완전한 익명화가 아니다. `privacyFlags`가 비어 있어도 직접 확인한다. 개인 정보가 있으면 제거하거나 해당 행을 제외한다.
3. 위협 표현이어도 인용, 농담, 작품 설명, 자기 피해 호소 등은 자동 `BLOCK`으로 취급하지 않는다. 확정한 행에만 `reviewStatus: "approved"`, `expectedAction: "BLOCK"` 또는 `"PASS"`를 넣고 `notes`에 근거를 쓴다. 애매하면 `pending_human`과 `null`을 유지하거나 제외한다.
4. 표현이 가까운 정상 댓글 `PASS`를 별도로 마련한다. DKTC 협박 대화에는 정상 대화 학습 분할이 없으므로, 해당 대화의 다른 발화를 정상 정답으로 재활용하지 않는다.
5. 같은 `conversationId`의 모든 발화는 한 학습·검증·시험 분할에만 둔다. 동일·거의 동일 문장도 분할 간 중복 여부를 확인한다. 기존 개발 평가의 `ctx-threat-*`, `ctx-sarcasm-*`, `ctx-idiom-03b` 문장은 학습에서 제외한다.

검토가 끝난 데이터만 별도 파일로 만들어 이후 추가 학습에 사용한다. 기존 KOLD 체크포인트와 출력 폴더는 보존한다. 모델 학습과 성능 평가는 사용자가 Git Bash에서 실행한다.
