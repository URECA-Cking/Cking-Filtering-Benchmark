"""소량 호출 검증용 스크립트 (이슈 #3).

합성 샘플 몇 건을 모델에 호출해 응답 형식, 오류, 응답 시간만 확인한다.
판별 정확도는 계산하지 않는다. 그건 평가 데이터 검수와 실행기 구현 뒤의 본 실험에서 한다.

사용법
    export OPENAI_API_KEY=...        # 키는 환경변수로만 전달한다
    python src/smoke_check.py openai
    python src/smoke_check.py openai --limit 3
    python src/smoke_check.py openai --dry-run   # 호출 없이 입력만 확인

결과는 results/ 아래 JSONL로 저장한다(results/는 Git에 포함하지 않는다).
키는 출력하지 않으며, 오류는 상태 코드와 오류 종류만 기록한다(응답 본문에 키 일부가 섞일 수 있다).
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "samples.jsonl"
RESULTS_DIR = ROOT / "results"

OPENAI_URL = "https://api.openai.com/v1/moderations"
OPENAI_MODEL = "omni-moderation-latest"


def load_samples(limit):
    rows = []
    with SAMPLES.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


def call_openai_moderation(text, api_key, timeout):
    """OpenAI 모더레이션 호출. (결과 dict, 오류 dict)를 돌려준다. 둘 중 하나만 채워진다."""
    body = json.dumps({"model": OPENAI_MODEL, "input": text}).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload["results"][0]
        return result, None
    except urllib.error.HTTPError as e:
        # 응답 본문은 기록하지 않는다. 401 등에서 키 일부가 섞여 올 수 있다.
        return None, {"apiStatus": "error", "error": f"http {e.code}"}
    except (TimeoutError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        status = "timeout" if isinstance(reason, TimeoutError) or "timed out" in str(reason) else "error"
        return None, {"apiStatus": status, "error": type(reason).__name__}
    except (KeyError, IndexError, json.JSONDecodeError):
        return None, {"apiStatus": "error", "error": "unexpected response format"}


def summarize(result):
    categories = result.get("categories", {})
    scores = result.get("category_scores", {})
    flagged = sorted(name for name, on in categories.items() if on)
    top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "flagged": bool(result.get("flagged")),
        "flaggedCategories": flagged,
        "topScores": {name: round(score, 4) for name, score in top},
        "returnedCategoryCount": len(categories),
    }


def run_openai(rows, timeout, dry_run):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not dry_run and not api_key:
        sys.exit("OPENAI_API_KEY 환경변수가 없습니다. 키는 환경변수로만 전달하세요.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records = []
    for row in rows:
        record = {
            "runId": run_id,
            "commentId": row["id"],
            "model": OPENAI_MODEL,
            "expectedAction": row["expectedAction"],
            "expectedCategories": row["categories"],
        }
        if dry_run:
            record.update({"apiStatus": "not_run"})
        else:
            started = time.perf_counter()
            result, error = call_openai_moderation(row["text"], api_key, timeout)
            record["latencyMs"] = round((time.perf_counter() - started) * 1000)
            if error:
                record.update(error)
            else:
                record["apiStatus"] = "ok"
                record.update(summarize(result))
        records.append(record)
        time.sleep(0.2)  # 무료 한도를 아끼기 위해 천천히 호출한다
    return run_id, records


def print_report(records):
    ok = [r for r in records if r["apiStatus"] == "ok"]
    print(f"\n호출 {len(records)}건: ok {len(ok)} / 실패·미실행 {len(records) - len(ok)}")
    for r in records:
        if r["apiStatus"] == "ok":
            print(f"  {r['commentId']}: 정답={r['expectedAction']}/{','.join(r['expectedCategories'])}"
                  f"  모델 flagged={r['flagged']} {r['flaggedCategories']}  {r['latencyMs']}ms")
        else:
            print(f"  {r['commentId']}: {r['apiStatus']} {r.get('error', '')}")
    latencies = [r["latencyMs"] for r in ok]
    if latencies:
        print(f"응답 시간 ms: 중앙값 {statistics.median(latencies):.0f}, 최대 {max(latencies)}")
    if ok:
        print(f"응답 분류 항목 수: {ok[0]['returnedCategoryCount']}개")


def main():
    # Windows 콘솔에서 한글이 깨지지 않도록 출력을 UTF-8로 고정한다.
    sys.stdout.reconfigure(encoding="utf-8")
    parser =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("provider", choices=["openai"])
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N건만 호출 (기본: 전체)")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true", help="호출 없이 입력과 기록 형식만 확인")
    args = parser.parse_args()

    rows = load_samples(args.limit)
    run_id, records = run_openai(rows, args.timeout, args.dry_run)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"smoke-{args.provider}-{run_id}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print_report(records)
    print(f"\n저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
