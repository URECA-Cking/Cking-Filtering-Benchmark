"""소량 호출 검증용 스크립트 (이슈 #3).

합성 샘플 몇 건을 모델에 호출해 응답 형식, 오류, 응답 시간만 확인한다.
판별 정확도는 계산하지 않는다. 그건 평가 데이터 검수와 실행기 구현 뒤의 본 실험에서 한다.

사용법
    export OPENAI_API_KEY=...        # 키는 환경변수로만 전달한다
    python src/smoke_check.py openai
    python src/smoke_check.py openai --limit 3

    export GEMINI_API_KEY=...
    python src/smoke_check.py gemini --model <모델 ID> --limit 3

    python src/smoke_check.py gemini --list-models   # 이 키로 쓸 수 있는 모델 목록
    python src/smoke_check.py openai --data data/probes.jsonl --show-scores   # 유형별 탐색용 세트와 점수 출력
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
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"

PROMPT_VERSION = "pilot-v1"
ACTIONS = ["PASS", "HOLD", "BLOCK"]
CATEGORIES = ["NONE", "ABUSE", "HATE", "SPAM", "PRIVACY"]

# docs/rubric.md의 유형·처리 기준을 요약한 프롬프트. 본 실험에서 다듬는 초안이다.
SYSTEM_PROMPT = """너는 크리에이터 게시글에 달린 한국어 댓글을 검토하는 필터다. 댓글 하나를 읽고 판정한다.

유형
- ABUSE: 특정 사람을 향한 욕설, 모욕, 조롱, 인신공격
- HATE: 성별·국적·장애·출신 등 집단에 대한 혐오나 차별 표현
- SPAM: 무관한 광고, 외부 링크 유도, 반복 도배, 구매·가입 유도
- PRIVACY: 연락처, 주소, 계정, 실명 등 개인을 특정할 수 있는 정보
- NONE: 위 유형에 해당하지 않음

처리 결과
- PASS: 그대로 게시
- HOLD: 위반인지 애매해 확인이 필요함
- BLOCK: 명백한 위반

원칙
- 크리에이터나 콘텐츠에 대한 정중한 비판이나 의견은 위반이 아니다.
- 특정 대상을 향하지 않는 감탄이나 강조 표현은 위반이 아니다.
- 위반이 없으면 categories는 ["NONE"]이다. NONE은 다른 유형과 함께 쓰지 않는다.
- 판단이 애매하면 BLOCK 대신 HOLD를 고른다."""

GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "action": {"type": "STRING", "enum": ACTIONS},
        "categories": {"type": "ARRAY", "items": {"type": "STRING", "enum": CATEGORIES}},
        "reason": {"type": "STRING"},
    },
    "required": ["action", "categories", "reason"],
}


def load_samples(limit, path=None):
    rows = []
    with (Path(path) if path else SAMPLES).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


SHOW_SCORES = False  # --show-scores: 점수 상위 항목을 화면에 출력한다
SHOW_ERROR_DETAIL = False  # --show-error: 오류 응답의 status·message를 기록한다(키는 가려서)


def error_detail(e, secret):
    """오류 응답 본문에서 status·message만 뽑는다. 키 문자열은 가리고 길이를 제한한다."""
    try:
        err = json.loads(e.read().decode("utf-8")).get("error", {})
        text = f"{err.get('status', '')}: {err.get('message', '')}"
    except Exception:
        return "unreadable error body"
    if secret:
        text = text.replace(secret, "[KEY]")
    return text[:300]


def post_json(url, headers, body, timeout):
    """JSON POST. (응답 dict, 오류 dict)를 돌려준다. 둘 중 하나만 채워진다."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        # 응답 본문은 기록하지 않는다. 401 등에서 키 일부가 섞여 올 수 있다.
        result = {"apiStatus": "error", "error": f"http {e.code}"}
        if SHOW_ERROR_DETAIL:
            secret = next(iter(v.removeprefix("Bearer ") for v in headers.values()), None)
            result["errorDetail"] = error_detail(e, secret)
        return None, result
    except (TimeoutError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        status = "timeout" if isinstance(reason, TimeoutError) or "timed out" in str(reason) else "error"
        return None, {"apiStatus": status, "error": type(reason).__name__}
    except json.JSONDecodeError:
        return None, {"apiStatus": "error", "error": "response is not json"}


def list_gemini_models(api_key, timeout):
    """이 키로 generateContent를 쓸 수 있는 모델 이름을 출력한다."""
    request = urllib.request.Request(GEMINI_LIST_URL, headers={"x-goog-api-key": api_key}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            models = json.loads(response.read().decode("utf-8")).get("models", [])
    except urllib.error.HTTPError as e:
        sys.exit(f"모델 목록 조회 실패: http {e.code}")
    except (TimeoutError, urllib.error.URLError) as e:
        sys.exit(f"모델 목록 조회 실패: {type(getattr(e, 'reason', e)).__name__}")
    names = sorted(
        m["name"].removeprefix("models/")
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    )
    print(f"generateContent를 쓸 수 있는 모델 {len(names)}개 (이 목록에 있어도 무료 한도가 없을 수 있다)")
    for name in names:
        print(f"  {name}")


def call_openai(text, api_key, timeout, _model):
    payload, error = post_json(
        OPENAI_URL, {"Authorization": f"Bearer {api_key}"}, {"model": OPENAI_MODEL, "input": text}, timeout
    )
    if error:
        return error
    try:
        return {"apiStatus": "ok", **summarize_moderation(payload["results"][0])}
    except (KeyError, IndexError):
        return {"apiStatus": "error", "error": "unexpected response format"}


def summarize_moderation(result):
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


def call_gemini(text, api_key, timeout, model):
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": f"댓글: {text}"}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": GEMINI_RESPONSE_SCHEMA,
        },
    }
    # 키는 URL이 아니라 헤더로 보낸다. URL은 오류 메시지에 남을 수 있다.
    payload, error = post_json(GEMINI_URL.format(model=model), {"x-goog-api-key": api_key}, body, timeout)
    if error:
        return error
    return parse_gemini_response(payload)


def parse_gemini_response(payload):
    try:
        raw = payload["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw)
        usage = payload.get("usageMetadata", {})
        record = {
            "apiStatus": "ok",
            "predictedAction": parsed["action"],
            "predictedCategories": parsed["categories"],
            "reason": parsed.get("reason", ""),
            "inputTokens": usage.get("promptTokenCount"),
            "outputTokens": usage.get("candidatesTokenCount"),
        }
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return {"apiStatus": "error", "error": "unexpected response format"}
    if record["predictedAction"] not in ACTIONS or not set(record["predictedCategories"]) <= set(CATEGORIES):
        return {"apiStatus": "error", "error": "value outside the allowed set"}
    return record


PROVIDERS = {
    "openai": {"env": "OPENAI_API_KEY", "call": call_openai, "model": OPENAI_MODEL},
    "gemini": {"env": "GEMINI_API_KEY", "call": call_gemini, "model": None},
}


def run(provider, model, rows, timeout, dry_run):
    config = PROVIDERS[provider]
    api_key = os.environ.get(config["env"])
    if not dry_run and not api_key:
        sys.exit(f"{config['env']} 환경변수가 없습니다. 키는 환경변수로만 전달하세요.")
    model = model or config["model"]
    if not model:
        sys.exit("--model로 모델 ID를 지정하세요. AI Studio에서 무료로 쓸 수 있는 모델을 확인해야 합니다.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records = []
    for row in rows:
        record = {
            "runId": run_id,
            "commentId": row["id"],
            "model": model,
            "promptVersion": PROMPT_VERSION if provider == "gemini" else None,
            "expectedAction": row["expectedAction"],
            "expectedCategories": row["categories"],
        }
        if dry_run:
            record["apiStatus"] = "not_run"
        else:
            started = time.perf_counter()
            result = config["call"](row["text"], api_key, timeout, model)
            record["latencyMs"] = round((time.perf_counter() - started) * 1000)
            record.update(result)
        records.append(record)
        time.sleep(1.0 if provider == "gemini" else 0.2)  # 무료 한도(분당 호출 수)를 넘지 않게 천천히 호출한다
    return run_id, model, records


def print_report(records):
    ok = [r for r in records if r["apiStatus"] == "ok"]
    print(f"\n호출 {len(records)}건: ok {len(ok)} / 실패·미실행 {len(records) - len(ok)}")
    for r in records:
        expected = f"정답={r['expectedAction']}/{','.join(r['expectedCategories'])}"
        if r["apiStatus"] != "ok":
            print(f"  {r['commentId']}: {r['apiStatus']} {r.get('error', '')}")
            if r.get("errorDetail"):
                print(f"    {r['errorDetail']}")
        elif "flagged" in r:
            print(f"  {r['commentId']}: {expected}  모델 flagged={r['flagged']} {r['flaggedCategories']}  {r['latencyMs']}ms")
            if SHOW_SCORES:
                print(f"    점수 {r['topScores']}")
        else:
            print(f"  {r['commentId']}: {expected}  모델 {r['predictedAction']}/{','.join(r['predictedCategories'])}  {r['latencyMs']}ms")
    groups = {}
    for r in ok:
        if "flagged" in r and "-" in r["commentId"]:
            g = groups.setdefault(r["commentId"].rsplit("-", 1)[0], [0, 0])
            g[0] += 1
            g[1] += int(r["flagged"])
    if len(groups) > 1:
        print("\n그룹별 flagged 수 (id 접두어 기준):")
        for name, (total, flagged) in groups.items():
            print(f"  {name}: {flagged}/{total}")
    latencies = [r["latencyMs"] for r in ok]
    if latencies:
        print(f"응답 시간 ms: 중앙값 {statistics.median(latencies):.0f}, 최대 {max(latencies)}")
    if ok and "returnedCategoryCount" in ok[0]:
        print(f"응답 분류 항목 수: {ok[0]['returnedCategoryCount']}개")
    tokens = [(r.get("inputTokens"), r.get("outputTokens")) for r in ok if r.get("inputTokens") is not None]
    if tokens:
        print(f"토큰: 입력 평균 {statistics.mean(t[0] for t in tokens):.0f}, 출력 평균 {statistics.mean(t[1] or 0 for t in tokens):.0f}")


def main():
    # Windows 콘솔에서 한글이 깨지지 않도록 출력을 UTF-8로 고정한다.
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("provider", choices=sorted(PROVIDERS))
    parser.add_argument("--model", help="모델 ID (gemini는 필수, openai는 omni-moderation-latest 고정)")
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N건만 호출 (기본: 전체)")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true", help="호출 없이 입력과 기록 형식만 확인")
    parser.add_argument("--show-error", action="store_true", help="오류 응답의 status·message도 출력(키는 가려서)")
    parser.add_argument("--data", help="평가 데이터 JSONL 경로 (기본: data/samples.jsonl)")
    parser.add_argument("--show-scores", action="store_true", help="분류기 응답의 점수 상위 항목도 출력")
    parser.add_argument("--list-models", action="store_true", help="(gemini) 이 키로 쓸 수 있는 모델 목록 출력")
    args = parser.parse_args()
    global SHOW_ERROR_DETAIL
    SHOW_ERROR_DETAIL = args.show_error
    global SHOW_SCORES
    SHOW_SCORES = args.show_scores

    if args.list_models:
        if args.provider != "gemini":
            sys.exit("--list-models는 gemini에서만 지원합니다.")
        key = os.environ.get(PROVIDERS["gemini"]["env"])
        if not key:
            sys.exit("GEMINI_API_KEY 환경변수가 없습니다. 키는 환경변수로만 전달하세요.")
        list_gemini_models(key, args.timeout)
        return

    rows = load_samples(args.limit, args.data)
    run_id, model, records = run(args.provider, args.model, rows, args.timeout, args.dry_run)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"smoke-{args.provider}-{run_id}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print_report(records)
    print(f"\n모델: {model}\n저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
